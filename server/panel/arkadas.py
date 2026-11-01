"""Arkadaşlarınla Oyna (panel): arkadaş sunucusu kurma (Host) ve arkadaşın sunucusuna katılma (Join).

Host: panel oyun sunucusunu --cok-oyunculu ile başlatır (server/cok_oyunculu.py): oyun (TCP 8081) ve sohbet (TCP 7771) bütün
ağlardan dinlenir, oyuncu kendi kaydıyla oyuna girer. Misafirler ilk girişte kararlı bir kayıt kimliği ve profil gönderir; host
ana profili save/kayitlar/arkadas_<hash>/profil.json altında kalıcı tutar (normal Kayıtlar listesine karışmaz). Oyun her autosave'de
host kopyasını atomik günceller, düzenleme öncesi ve aralıklı yedekler oluşturulur. Bağlı misafirler oyun sunucusunun
canli_durum.json'undan; misafiri çıkarma /yonetim/at ile (yalnız bu bilgisayardan, panelin yönetim anahtarıyla).
Join: seçilen kayıt yedeklenir, kararlı kimliğiyle arkadaşın sunucusuna gönderilir (POST /misafir/giris). Host'ta kayıt varsa
host sürümü yerel profilden üstün tutulur ve oyun açılmadan yerel slota yazılır. Oyun sürerken host'tan gelen her yeni sürüm
(uzun yoklama, GET /misafir/profil) yerel kopyaya eşitlenir; istemci kapanınca (ya da Ayrıl) son hâl alınır (POST /misafir/cikis).
Host profili ana kayıttır; paneldeki Arkadaş kayıtları sekmesinden düzenlenebilir ve oyun oturumu açıkken salt okunurdur.
Oturum yarım kalırsa (panel kapandı, elektrik gitti) yuvanın kayit.json'undaki 'arkadas' bilgisiyle sunucudaki son hâl alınır;
yerel kayıt o arada değiştiyse eski dosyanın host ana kaydını ezmesine izin verilmez.
"""
import gzip, json, os, re, secrets, socket, threading, time, zlib
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from dil import t as _

OYUN_PORTU = 8081
SOHBET_PORTU = 7771
PROTOKOL = 2                    # server/cok_oyunculu.PROTOKOL: kalıcı ana kayıt (test_cok_oyunculu denetler)
BEKLE_SN = 25                   # uzun yoklamanın süresi
YANIT_SINIR = 64 * 1024 * 1024
GENEL_IP_HIZMETI = 'https://api.ipify.org'


class _Yonlendirmesiz(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None               # yönlendirme izlenmez (oturum ve anahtar başka adrese gitmesin): 3xx yanıt HTTPError olur


OPENER = build_opener(ProxyHandler({}), _Yonlendirmesiz())   # yerel ağdaki sunucuya sistemin vekil sunucusu (proxy) üzerinden gidilmesin


class ArkadasHatasi(Exception):
    """Kullanıcıya gösterilen hata."""


# ------------------------------------------------------------------ adresler
def adres_coz(text):
    """'192.168.1.20', '85.100.20.30:8081', 'ev.ornek.com' -> (adres, port)."""
    s = re.sub(r'^[a-z]+://', '', (text or '').strip(), flags=re.I).split('/')[0]
    m = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9.\-]*)(?::(\d{1,5}))?', s)
    if not m or not 0 < int(m.group(2) or OYUN_PORTU) < 65536:
        raise ArkadasHatasi(_('Geçersiz adres: arkadaşının IP adresini ya da alan adını yaz (ör. 192.168.1.20 ya da 85.100.20.30).'))
    return m.group(1), int(m.group(2) or OYUN_PORTU)


def ip_turu(ip):
    """yerel (ev ağı / ZeroTier), radmin (Radmin VPN), tailscale, baglanti (yalnız bağlantı-yerel), genel."""
    a = [int(x) for x in ip.split('.')]
    if a[0] == 26:
        return 'radmin'
    if a[0] == 100 and 64 <= a[1] < 128:
        return 'tailscale'
    if a[0] == 10 or (a[0] == 172 and 16 <= a[1] < 32) or (a[0] == 192 and a[1] == 168):
        return 'yerel'
    if a[0] == 169 and a[1] == 254:
        return 'baglanti'
    return 'genel'


def yerel_ipler():
    """Bu bilgisayarın IPv4 adresleri (varsayılan yolunki önce) -> [{'ip', 'tur'}]."""
    out = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1', 9))               # UDP: paket gitmez, yalnız yerel adres seçilir
            out.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = ai[4][0]
            if ip not in out:
                out.append(ip)
    except OSError:
        pass
    return [{'ip': ip, 'tur': ip_turu(ip)} for ip in out if not ip.startswith(('127.', '0.'))]


def genel_ip():
    """İnternetteki adres (yalnız istenince; GENEL_IP_HIZMETI'ne sorulur)."""
    try:
        ip = OPENER.open(GENEL_IP_HIZMETI, timeout=6).read(64).decode('ascii', 'replace').strip()
    except (OSError, ValueError):
        raise ArkadasHatasi(_('Genel IP bulunamadı: internet bağlantısı yok ya da hizmet yanıt vermedi.'))
    if not re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', ip):
        raise ArkadasHatasi(_('Genel IP bulunamadı: internet bağlantısı yok ya da hizmet yanıt vermedi.'))
    return ip


# ------------------------------------------------------------------ arkadaşın sunucusuna HTTP (oyun portu)
def istek(host, port, method, path, body=None, timeout=10):
    """-> (durum kodu, JSON). Bağlanılamazsa ya da yanıt bir arkadaş sunucusunun değilse ArkadasHatasi."""
    data, hdr = None, {'Accept-Encoding': 'gzip'}
    if body is not None:
        data = gzip.compress(json.dumps(body, ensure_ascii=False).encode('utf8'), 6)
        hdr.update({'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
    req = Request('http://%s:%d%s' % (host, port, path), data=data, headers=hdr, method=method)
    try:
        r = OPENER.open(req, timeout=timeout)
        code = r.status
    except HTTPError as e:
        r, code = e, e.code
    except (URLError, OSError) as e:
        reason = getattr(e, 'reason', e)
        raise ArkadasHatasi(_('%s:%d adresine bağlanılamadı (%s). Arkadaşının sunucusu açık mı, portlar açık mı?', host, port, reason))
    try:
        raw = r.read(YANIT_SINIR + 1)
        if r.headers.get('Content-Encoding') == 'gzip':
            z = zlib.decompressobj(16 + zlib.MAX_WBITS)
            raw = z.decompress(raw, YANIT_SINIR)
        if r.headers.get('X-DarkOrbit') != 'arkadas':
            raise ValueError('başlık yok')
        out = json.loads(raw.decode('utf8'))
    except (OSError, ValueError, zlib.error):
        raise ArkadasHatasi(_('%s:%d bir DarkOrbit arkadaş sunucusu değil (ya da yanıt yarım kaldı).', host, port))
    return code, (out if isinstance(out, dict) else {})


def _mesaj(code, out):
    return out.get('mesaj') or _('Sunucu isteği reddetti (HTTP %s).', code)


# ------------------------------------------------------------------ panel tarafı
class Arkadas:
    def __init__(self, cfg, kay, yon, log, kod):
        self.cfg, self.kay, self.yon, self.log, self.kod = cfg, kay, yon, log, kod
        self.anahtar = secrets.token_urlsafe(24)       # yönetim anahtarı (bu panel açılışında sunucuya verilir)
        self.yerel = secrets.token_urlsafe(24)         # sunucunun kendi oyuncusunun oturumu (oyun sunucusu ve kendi web.py'si)
        self.lock = threading.RLock()
        self.genel = None
        self.friend_busy = set()        # host'ta şu an açık olan kalıcı arkadaş profilleri (edit kilidi)
        self.m = self._bos()

    @staticmethod
    def _bos():
        return {'durum': 'yok', 'adimlar': [], 'hata': None, 'adres': None, 'kayit': None, 'sunucu': None, 'oturum': None,
                'uid': None, 'surum': 0, 'son_esitleme': None, 'baglanti': True, 'not': None, 'bitis': None}

    # ------------------------------------------------------------ host
    def host_ortam(self):
        """Oyun sunucusunun DO_COK_OYUNCULU ortam değişkeni (cok_oyunculu.configure)."""
        return json.dumps({'sifre': self.cfg.get('arkadas_sifre'), 'en_cok': self.cfg.get('arkadas_en_cok'),
                           'anahtar': self.anahtar, 'kod': self.kod, 'yerel': self.yerel})

    def host_durumu(self, canli):
        acik = self.yon.running() and self.yon.arkadas
        ark = (canli or {}).get('arkadas') or {}
        self.friend_busy = set()
        if acik:
            try:
                code, out = istek('127.0.0.1', OYUN_PORTU, 'GET', '/yonetim/zapisy?anahtar=%s' % quote(self.anahtar), timeout=4)
                if code == 200:
                    self.friend_busy = {str(x) for x in out.get('aktif', [])}
                else:
                    self.friend_busy = None          # brak statusu traktuj jak zajęty profil
            except ArkadasHatasi as e:
                self.friend_busy = None           # fail closed: przy braku statusu nie wolno edytować profili gości
                self.log('nie udało się pobrać aktywnych zapisów znajomych: %s' % e)
        return {'acik': acik, 'ipler': yerel_ipler(), 'genel_ip': self.genel, 'oyun_portu': OYUN_PORTU, 'sohbet_portu': SOHBET_PORTU,
                'sifre': self.cfg.get('arkadas_sifre'), 'en_cok': self.cfg.get('arkadas_en_cok'),
                'misafirler': ark.get('misafirler', []) if acik else []}

    def genel_bul(self):
        self.genel = genel_ip()
        return self.genel

    def at(self, oturum):
        if not (self.yon.running() and self.yon.arkadas):
            raise ArkadasHatasi(_('Arkadaş sunucusu açık değil.'))
        code, out = istek('127.0.0.1', OYUN_PORTU, 'POST', '/yonetim/at', {'anahtar': self.anahtar, 'oturum': str(oturum or '')})
        if code != 200:
            raise ArkadasHatasi(_('Misafir bulunamadı: çoktan ayrılmış olabilir.'))
        self.log('arkadaş sunucusu: misafir çıkarıldı (%s)' % str(oturum)[:8])

    # ------------------------------------------------------------ misafir
    def aktif(self):
        return self.m['durum'] in ('baglaniyor', 'oyunda', 'ayriliyor')

    def kullanimda(self, slot):
        return self.aktif() and self.m['kayit'] == slot

    def zapis_kullanimda(self, slot):
        return self.friend_busy is None or slot in self.friend_busy

    def durum(self):
        with self.lock:
            m = dict(self.m)
        m.pop('anahtar', None)
        m['son_adres'] = self.cfg.get('arkadas_son_adres')
        return m

    def dene(self, adres):
        """Arkadaşın sunucusunun bilgisi (bağlanmadan önce)."""
        host, port = adres_coz(adres)
        code, info = istek(host, port, 'GET', '/misafir/bilgi', timeout=6)
        if code != 200 or info.get('sunucu') != 'darkorbit':
            raise ArkadasHatasi(_('%s:%d bir DarkOrbit arkadaş sunucusu değil (ya da yanıt yarım kaldı).', host, port))
        info.update(adres='%s:%d' % (host, port), uyumlu=info.get('protokol') == PROTOKOL)
        return info

    def _adim(self, text, durum='calisiyor'):
        a = self.m['adimlar']
        if a and a[-1]['durum'] == 'calisiyor':
            a[-1]['durum'] = 'tamam'
        a.append({'metin': text, 'durum': durum, 'zaman': time.strftime('%H:%M:%S')})

    def katil(self, adres, sifre, slot, istemci_surumu, istemci_ac):
        """Katılmayı başlatır (arka planda). istemci_ac: istemciyi açan işlev (panel)."""
        host, port = adres_coz(adres)
        with self.lock:
            if self.aktif():
                raise ArkadasHatasi(_('Zaten bir arkadaş sunucusundasın.'))
            self.m = self._bos()
            self.m.update(durum='baglaniyor', adres='%s:%d' % (host, port), kayit=slot)
        self.cfg.update({'arkadas_son_adres': adres.strip()})
        threading.Thread(target=self._katil, args=(host, port, sifre, slot, istemci_surumu, istemci_ac), daemon=True).start()
        return self.durum()

    def _katil(self, host, port, sifre, slot, istemci_surumu, istemci_ac):
        m = self.m
        try:
            self._adim(_('Arkadaşının sunucusu denetleniyor'))
            info = self.dene('%s:%d' % (host, port))
            m['sunucu'] = info
            if not info['uyumlu']:
                raise ArkadasHatasi(_('Arkadaşının paneli başka bir sürüm (hesap gönderimi %s, seninki %s): ikiniz de paneli güncelleyin.',
                                      info.get('protokol'), PROTOKOL))
            if info.get('istemci') and info['istemci'] != istemci_surumu:
                raise ArkadasHatasi(_('Oyun sürümleri farklı: arkadaşının sunucusu %s, senin istemcin %s.', info['istemci'], istemci_surumu))
            if not info.get('yer'):
                raise ArkadasHatasi(_('Sunucu dolu (en çok %s misafir).', info.get('en_cok')))
            self._yarim_oturum(slot)
            self._adim(_('Kayıt yedekleniyor'))
            self.kay.backup(slot, 'oto', _('Arkadaşın sunucusuna katılmadan önce'))
            with open(self.kay.profile(slot), encoding='utf8') as fh:
                d = json.load(fh)
            m['asil_uid'] = d['pilot']['userId']
            client_id = self.kay.meta(slot).get('arkadas_kimligi')
            if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', client_id):
                client_id = secrets.token_urlsafe(32)
                self.kay.set_meta(slot, arkadas_kimligi=client_id)
            self._adim(_('Hesap gönderiliyor'))
            anahtar = secrets.token_urlsafe(24)
            code, r = istek(host, port, 'POST', '/misafir/giris', {'surum': PROTOKOL, 'sifre': sifre or '', 'anahtar': anahtar,
                                                                    'kayit_kimligi': client_id, 'adres': host, 'profil': d}, timeout=60)
            if code != 200:
                raise ArkadasHatasi(_mesaj(code, r))
            m.update(oturum=r['oturum'], anahtar=anahtar, uid=r['uid'], surum=0, dosya=self._dosya(slot))
            if r.get('profil'):
                self._yaz(slot, r['profil'], int(r.get('surum') or 1))   # host kopyasını oyun açılmadan yerel slota al
            else:
                m['surum'] = int(r.get('surum') or 0)
            m['dosya'] = self._dosya(slot)
            self._isaretle(slot)
            self.log('arkadaş sunucusuna katılındı: %s:%d (kayıt %s, sunucudaki kimlik %s)' % (host, port, slot, r['uid']))
            self._adim(_('Web girişi hazırlanıyor'))
            self.yon.start_guest_web(self.kay.profile(slot), slot, [
                '--uzak=%s:%d' % (host, port), '--sohbet=%s:%d' % (host, SOHBET_PORTU), '--oturum=%s' % r['oturum'], '--uid=%d' % r['uid']])
            threading.Thread(target=self._esitle, args=(host, port, slot, r['oturum'], anahtar), daemon=True).start()
            self._adim(_('Oyun açılıyor'))
            istemci_ac()
            m['durum'] = 'oyunda'
            self._adim(_('Arkadaşının sunucusundasın: iyi uçuşlar!'), 'tamam')
        except Exception as e:
            m['hata'] = str(e) if isinstance(e, (ArkadasHatasi, RuntimeError, OSError)) else _('Beklenmeyen hata: %r', e)
            self._adim(m['hata'], 'hata')
            self.log('arkadaşa katılma hatası: %r' % e)
            if m.get('oturum'):
                self._bitir(sessiz=True)
            else:
                m['durum'] = 'hata'

    # ------------------------------------------------------------ eşitleme
    def _dosya(self, slot):
        st = os.stat(self.kay.profile(slot))
        return [st.st_mtime_ns, st.st_size]

    def _isaretle(self, slot):
        """Yuvanın kayit.json'u: süren oturum (yarım kalırsa sonraki katılmada son hâl alınır) ve dosyanın son yazılan hâli."""
        m = self.m
        self.kay.set_meta(slot, arkadas={'adres': m['adres'], 'oturum': m['oturum'], 'anahtar': m['anahtar'], 'surum': m['surum'],
                                         'uid': m['asil_uid'], 'dosya': m['dosya']})

    def _yaz(self, slot, d, surum):
        """Sunucudaki yeni sürümü yuvaya yazar (eskisi ya da başka oyuncunun kaydıysa yazmaz)."""
        with self.lock:
            m = self.m
            if surum <= m['surum']:
                return
            if not (isinstance(d, dict) and isinstance(d.get('pilot'), dict) and isinstance(d.get('gemi'), dict)
                    and isinstance(d.get('konum'), dict) and d['pilot'].get('userId') == m['asil_uid']):
                self.log('arkadaş sunucusu: geçersiz kayıt sürümü %s yok sayıldı' % surum)
                return
            p = self.kay.profile(slot)
            tmp = p + '.arkadas.tmp'
            with open(tmp, 'w', encoding='utf8') as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1)
                fh.flush()
                os.fsync(fh.fileno())
            for k in range(6):                        # panel ya da virüs tarayıcısı o an okuyorsa
                try:
                    os.replace(tmp, p)
                    break
                except PermissionError:
                    if k == 5:
                        raise
                    time.sleep(0.2)
            m['surum'], m['son_esitleme'], m['dosya'] = surum, time.time(), self._dosya(slot)
            if m.get('oturum'):
                self._isaretle(slot)

    def _esitle(self, host, port, slot, oturum, anahtar):
        """Oturum sürdükçe sunucudaki yeni sürümleri yuvaya yazar (uzun yoklama)."""
        m = self.m
        while m.get('oturum') == oturum and m['durum'] in ('baglaniyor', 'oyunda'):
            try:
                code, r = istek(host, port, 'GET', '/misafir/profil?oturum=%s&anahtar=%s&surum=%d&bekle=%d' % (
                    quote(oturum), quote(anahtar), m['surum'], BEKLE_SN), timeout=BEKLE_SN + 20)
            except ArkadasHatasi:
                m['baglanti'] = False
                time.sleep(3)
                continue
            m['baglanti'] = True
            if m.get('oturum') != oturum or m['durum'] == 'ayriliyor':
                return
            if code == 200 and r.get('profil'):
                try:
                    self._yaz(slot, r['profil'], int(r.get('surum') or 0))
                except OSError as e:
                    self.log('arkadaş sunucusu: kayıt yazılamadı: %r' % e)
            if code == 404 or (code == 200 and r.get('bitti')):
                m['not'] = _('Arkadaşının sunucusu oturumu bitirdi (sunucu kapandı ya da seni çıkardı). Kaydın son hâliyle bilgisayarında.')
                if not self.yon.client_alive():
                    self._bitir()
                return
            if code != 200:
                time.sleep(3)

    # ------------------------------------------------------------ ayrılma
    def istemci_kapandi(self):
        """Panelin istemci kapanış işi: misafir oturumundaysa ayrılınır -> True (sunucuları panel kapatmaz)."""
        if not self.aktif() or not self.m.get('oturum'):
            return False
        threading.Thread(target=self._bitir, daemon=True).start()
        return True

    def ayril(self):
        """Ayrıl düğmesi: istemci açıksa kapatılır (kapanış işi ayrılır), değilse hemen ayrılınır."""
        if not self.aktif():
            raise ArkadasHatasi(_('Bir arkadaş sunucusunda değilsin.'))
        if self.yon.client_alive():
            self.yon.stop_client()
        else:
            threading.Thread(target=self._bitir, daemon=True).start()

    def kapanis(self, sn=30):
        """Panel kapanıyor: oturum sürüyorsa ayrılınır, bitene dek (en çok sn) beklenir."""
        if self.aktif() and self.m.get('oturum') and self.m['durum'] != 'ayriliyor':
            self._bitir()
        end = time.time() + sn
        while self.aktif() and time.time() < end:
            time.sleep(0.1)

    def _bitir(self, sessiz=False):
        m = self.m
        with self.lock:
            if m['durum'] == 'ayriliyor' or not m.get('oturum'):
                return
            m['durum'] = 'ayriliyor'
        slot = m['kayit']
        host, port = adres_coz(m['adres'])
        ulasti = False
        try:
            code, r = istek(host, port, 'POST', '/misafir/cikis', {'oturum': m['oturum'], 'anahtar': m['anahtar']}, timeout=30)
            if code == 200 and r.get('profil'):
                self._yaz(slot, r['profil'], int(r.get('surum') or 0))
            ulasti = True
        except (ArkadasHatasi, OSError) as e:
            self.log('arkadaş sunucusundan ayrılma: son hâl alınamadı: %r' % e)
            if not m['not']:
                m['not'] = _('Sunucuya ulaşılamadı: kaydın son eşitlemedeki hâliyle kaldı.')
        try:
            self.yon.stop_servers()                     # misafirin web sunucusu
        finally:
            with self.lock:
                m['oturum'], m['bitis'] = None, time.time()
                if m['durum'] == 'ayriliyor':
                    m['durum'] = 'hata' if sessiz else 'bitti'
            try:
                if ulasti:                              # ulaşılamadıysa kalır: sonraki katılmada son hâl alınır (_yarim_oturum)
                    self.kay.set_meta(slot, arkadas=None)
            except OSError:
                pass
        self.log('arkadaş sunucusundan ayrılındı (kayıt %s, sürüm %s)' % (slot, m['surum']))

    def _yarim_oturum(self, slot):
        """Yarım kalan eski oturum (kayit.json 'arkadas'): sunucuda sürüyorsa biter; yerel kayıt o günden beri değişmediyse sunucudaki
        son hâl yazılır."""
        a = self.kay.meta(slot).get('arkadas')
        if not isinstance(a, dict) or not a.get('oturum'):
            return
        self._adim(_('Yarım kalan oturum kapatılıyor'))
        try:
            host, port = adres_coz(a.get('adres'))
            code, r = istek(host, port, 'POST', '/misafir/cikis', {'oturum': a['oturum'], 'anahtar': a.get('anahtar')}, timeout=20)
            d = r.get('profil')
            if code == 200 and d and int(r.get('surum') or 0) > int(a.get('surum') or 0) and self._dosya(slot) == a.get('dosya') \
                    and isinstance(d.get('pilot'), dict) and d['pilot'].get('userId') == a.get('uid'):
                self.m.update(surum=int(a.get('surum') or 0), asil_uid=a.get('uid'))
                self._yaz(slot, d, int(r['surum']))
                self.log('yarım kalan arkadaş oturumunun son hâli kayda yazıldı (%s)' % slot)
        except (ArkadasHatasi, OSError, ValueError, TypeError) as e:
            self.log('yarım kalan arkadaş oturumu kapatılamadı: %r' % e)
        self.m['surum'] = 0
        self.kay.set_meta(slot, arkadas=None)
