"""İstemcinin düzeltmeleri BepInEx ile: panel BepInEx 6'yı (Unity IL2CPP, 32 bit) istemci klasörüne kurar ve
eklenti/OpenOrbitYama.dll'i BepInEx/plugins'e koyar. Yamalar (müzayede sayacı, rütbe penceresi, mağaza tutarı) eklentinin kaynağında:
eklenti/Yamalar.cs. README'deki "istemci yamalanmaz" kuralının kullanıcı onaylı istisnası (2026-10-24; BepInEx'e geçiş 2026-10-25,
önceki bellek yamalarının yerine).

İstemcinin kendi dosyaları değişmez; yanına BepInEx'in dosyaları eklenir (winhttp.dll, doorstop_config.ini, .doorstop_version,
changelog.txt, BepInEx/, dotnet/). Doorstop ayarda kapalı: panel istemciyi --doorstop-enabled true ile açar (istemci.komut), aynı
istemci başka yoldan (resmî başlatıcı) açılırsa BepInEx yüklenmez. Linux ve macOS'ta Wine ve Proton öntanımlı olarak kendi yerleşik
winhttp.dll'ini yüklediği için çalıştırıcı WINEDLLOVERRIDES'a winhttp=n,b ekler (calistirici.dll_override): önce oyun klasöründeki
Doorstop winhttp.dll yüklenir, o da sistemin yerleşik winhttp.dll'ine yönlendirir. BepInEx'in konsol penceresi ve interop
derlemelerinin önceden yüklenmesi kapalı (BepInEx/config/BepInEx.cfg; ayar()).
Eklentinin kopyası her açılışta paneldekiyle aynı mı diye bakılır (panel güncellenince yenilenir).

Kurulum: kurulum sihirbazının oyun klasörü adımında, istemci indirilince, İstemci sayfasından ya da ilk OYNA'da. BepInEx arşivi ve
Unity'nin temel kitaplıkları (BepInEx ilk açılışta indirirdi; önceden konunca ilk açılış da internetsiz) belleğe iner, SHA-256'ları
tutarsa açılır; bitince KAYIT yazılır (yarım kurulum kurulu sayılmaz). BepInEx istemcinin kodundan interop derlemelerini üretir (yarım
dakika kadar): panel bunu ilk OYNA'da oyundan önce penceresiz bir açılışta yaptırır (isit), sonraki açılışlar hızlı. Kurulamazsa oyun
düzeltmeler olmadan açılır.
"""
import hashlib, http.client, io, json, math, os, shutil, subprocess, threading, time, zipfile
from urllib.request import Request, urlopen

import surecler as SR
from dil import t as _
from indirme import PARCA, ZAMAN_ASIMI, IndirmeHatasi, Iptal, safe_path

PANEL_DIR = os.path.dirname(os.path.abspath(__file__))
# BepInEx bleeding edge (builds.bepinex.dev): be.788 (2026-09-01) 1.1.115'te denendi (Unity 2022.3.58, IL2CPP metadata v31).
# Değiştirince sha256 de değişir; kurulu eskisinin üstüne yeniden kurulur.
BEPINEX = {'ad': 'BepInEx 6.0.0-be.788',
           'url': 'https://builds.bepinex.dev/projects/bepinex_be/788/BepInEx-Unity.IL2CPP-win-x86-6.0.0-be.788%2B5b766a3.zip',
           'sha256': 'd5954a5993ec39cd1133603d85bff93875d30b6411b712cc13dcf03c8e08a4d3', 'boyut': 31440336}
UNITY = {'ad': 'Unity 2022.3.58', 'url': 'https://unity.bepinex.dev/libraries/2022.3.58.zip',
         'sha256': '37b5b6d5f3a8761ecd8415302f0283e86c552c822a456faaec33aae533ba32ae', 'boyut': 1898155,
         'yol': 'BepInEx/unity-libs/2022.3.58.zip'}
EKLENTI = os.path.join(PANEL_DIR, 'eklenti', 'OpenOrbitYama.dll')
EKLENTI_YOLU = 'BepInEx/plugins/OpenOrbitYama.dll'
GM_CENTER_EKLENTI = os.path.join(PANEL_DIR, 'eklenti', 'OpenOrbitGMCenter.dll')
GM_CENTER_EKLENTI_YOLU = 'BepInEx/plugins/OpenOrbitGMCenter.dll'
AYAR = 'BepInEx/config/BepInEx.cfg'
KAYIT = 'BepInEx/openorbit.json'        # kurulumun bittiğini ve sürümünü söyler
INTEROP = 'BepInEx/interop/assembly-hash.txt'   # BepInEx interop derlemelerini üretince en son bunu yazar
ARGUMANLAR = ['--doorstop-enabled', 'true']
ISINMA = ['-batchmode', '-nographics']           # interop üretimi için penceresiz açılış (isit)
BASLADI = 'BepInEx/ErrorLog.log'                # BepInEx açılışta yazar (ısınmanın ilk aşaması biter)
INTEROP_DOSYA = 101                              # interop klasörünün dosyaları (be.788, 1.1.115: 99 derleme ve 2 .db)


def yol(folder, rel):
    return os.path.join(folder, *rel.split('/'))


def kurulu(folder):
    """BepInEx bu klasöre kurulmuş mu (kurulum bitmiş, sürümü güncel)?"""
    return _kayit(folder).get('bepinex') == BEPINEX['sha256'] and os.path.isfile(os.path.join(folder, 'winhttp.dll'))


def eklenti(folder):
    """Kurulu istemciye panel yamalarını ve (derlenmişse) ayrı GM Center eklentisini kopyala."""
    for source, rel, required in (
        (EKLENTI, EKLENTI_YOLU, True),
        (GM_CENTER_EKLENTI, GM_CENTER_EKLENTI_YOLU, False),
    ):
        try:
            with open(source, 'rb') as fh:
                yeni = fh.read()
        except OSError:
            if required:
                raise
            continue
        p = yol(folder, rel)
        try:
            with open(p, 'rb') as fh:
                if fh.read() == yeni:
                    continue
        except OSError:
            pass
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.openorbit-new'
        with open(tmp, 'wb') as fh:
            fh.write(yeni)
        os.replace(tmp, p)


def ayar(folder):
    """BepInEx.cfg'de interop derlemelerinin önceden yüklenmesini kapat. Açıkken (BepInEx'in öntanımlısı) interop'lar yeni
    üretildikten sonraki ilk bir iki açılışta istemci ilk sahneyi yüklemeden takılıyordu (Windows beyaz ekran, Proton kod 1; 2026-10-28,
    kapalıyken 4/4 açıldı); eklenti gereken derlemeleri kendisi yükler. Öteki ayarlara dokunulmaz."""
    p = yol(folder, AYAR)
    try:
        with open(p, 'rb') as fh:
            eski = fh.read()
    except OSError:
        eski = b''
    if b'PreloadIL2CPPInteropAssemblies = false' in eski:
        return
    if b'PreloadIL2CPPInteropAssemblies = true' in eski:
        yeni = eski.replace(b'PreloadIL2CPPInteropAssemblies = true', b'PreloadIL2CPPInteropAssemblies = false', 1)
    else:
        yeni = eski + b'\n[IL2CPP]\n\nPreloadIL2CPPInteropAssemblies = false\n'
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as fh:
        fh.write(yeni)


def parmak_izi(folder):
    """Oyun kodunun (GameAssembly.dll) boyutu ve zamanı: istemci yerinde güncellenirse interop'lar yeniden üretilmeli."""
    try:
        st = os.stat(os.path.join(folder, 'GameAssembly.dll'))
    except OSError:
        return None
    return '%d-%d' % (st.st_size, int(st.st_mtime))


def _kayit(folder):
    try:
        with open(yol(folder, KAYIT), encoding='utf8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def uretildi(folder):
    """BepInEx interop derlemelerini üretmiş mi?"""
    return os.path.isfile(yol(folder, INTEROP))


def hazir(folder):
    """Interop'lar bu istemci kodu için üretilmiş mi? Isınmanın kaydettiği parmak izi yoksa (önceki panel sürümünün kurulumu)
    GameAssembly.dll interop'lardan yeniyse istemci güncellenmiş sayılır."""
    if not uretildi(folder):
        return False
    iz = _kayit(folder).get('isinma')
    if iz:
        return iz == parmak_izi(folder)
    try:
        return os.path.getmtime(os.path.join(folder, 'GameAssembly.dll')) <= os.path.getmtime(yol(folder, INTEROP))
    except OSError:
        return True


def ilerleme(folder, basla, gorulen):
    """Isınmanın ilerlemesi -> {'asama': 0 istemci açılıyor, 1 derlemeler üretiliyor, 2 dosyalar yazılıyor, 3 bitti; 'yuzde', 'gecen_sn'}.
    BepInEx üretim bitene kadar günlüğünü diske yazmıyor (Windows ve Wine, 2026-10-28): aşamalar dosyalardan (BASLADI, interop
    klasörü). Üretim içeriden görünmez: yüzde süreyle yavaşlayarak ilerler, yazmada dosya sayısıyla. gorulen: isit'in tuttuğu durum."""
    simdi = time.time()
    try:
        basladi = os.path.getmtime(yol(folder, BASLADI)) >= basla - 1   # önceki açılışınki sayılmaz
    except OSError:
        basladi = False
    try:
        yazilan = len(os.listdir(yol(folder, 'BepInEx/interop')))
    except OSError:
        yazilan = 0
    asama = 3 if uretildi(folder) else 2 if yazilan else 1 if basladi or simdi - basla > 10 else 0
    t = simdi - gorulen.setdefault(asama, simdi)
    alt = gorulen.setdefault('yazma', gorulen.get('yuzde', 0)) if asama == 2 else 0   # yazma, gösterilenden sıçramadan sürer
    yuzde = (100 if asama == 3 else alt + (99 - alt) * min(1, yazilan / INTEROP_DOSYA) if asama == 2
             else 10 + 80 * (1 - math.exp(-t / 25)) if asama == 1 else 9 * (1 - math.exp(-t / 4)))
    gorulen['yuzde'] = max(gorulen.get('yuzde', 0), int(yuzde))
    return {'asama': asama, 'yuzde': gorulen['yuzde'], 'gecen_sn': int(simdi - basla)}


def isit(folder, cmd, env, logs, bildir=None, sure=300):
    """Interop derlemelerini oyundan önce ayrı, penceresiz bir açılışta ürettir -> hazır mı. Üretim oyunun kendi açılışında olursa
    32 bitlik istemcinin adres alanı tükeniyor: Proton'da oyun ilk sahnede "System out of memory" ile kapanıyordu (2026-10-28).
    cmd, env: istemci.komut (BepInEx argümanlarıyla); üretim bitince (ya da sure dolunca) bu açılış kapatılır. bildir: ilerleme()'nin
    sonucu yarım saniyede bir (panelin OYNA adımı)."""
    basla, gorulen = time.time(), {}
    shutil.rmtree(yol(folder, 'BepInEx/interop'), ignore_errors=True)    # eski istemcinin interop'ları: yeniden üretilsin
    p = SR.istemci_ac(folder, cmd + ISINMA, env, logs)
    son = basla + sure
    while time.time() < son and p.poll() is None and not uretildi(folder):
        if bildir:
            bildir(ilerleme(folder, basla, gorulen))
        time.sleep(0.5)
    if bildir:
        bildir(ilerleme(folder, basla, gorulen))
    SR.istemci_kapat(p)
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        SR.kill(p.pid)
    if uretildi(folder):                            # hazir(): istemci kodu değişirse yeniden ısınılır
        d = _kayit(folder)
        d['isinma'] = parmak_izi(folder)
        with open(yol(folder, KAYIT), 'w', encoding='utf8') as fh:
            json.dump(d, fh, indent=1)
    son = time.time() + 15
    while os.name != 'nt' and time.time() < son:   # Wine her Windows sürecini kendi oturumunda açar: grubu kapatmak istemciye ulaşmaz
        kalan = isinma_surecleri()
        if not kalan:
            break
        for pid in kalan:
            SR.kill(pid)
        time.sleep(0.5)
    return uretildi(folder)


def isinma_surecleri():
    """Linux ve macOS: açık ısınma istemcileri (Wine'daki DarkOrbit.exe ... -batchmode)."""
    try:
        r = subprocess.run(['ps', '-A', '-o', 'pid=', '-o', 'args='], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(s.split(None, 1)[0]) for s in r.stdout.splitlines()
            if 'darkorbit.exe' in s.lower() and ' %s ' % ISINMA[0] in s + ' ' and 'python' not in s.lower()]


def argumanlar(folder):
    """İstemciyi BepInEx'le açan argümanlar (kurulu değilse yok); eklentinin kopyası ve ayar önce yenilenir."""
    if not kurulu(folder):
        return []
    eklenti(folder)
    ayar(folder)
    return list(ARGUMANLAR)


class Yamaci:
    def __init__(self, log=print, opener=urlopen):
        self.log, self.opener = log, opener
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.d = self._blank('yok', None)

    @staticmethod
    def _blank(durum, folder):
        return {'durum': durum, 'calisiyor': False, 'alinan': 0, 'toplam': BEPINEX['boyut'] + UNITY['boyut'], 'hata': None,
                'klasor': folder}

    def state(self, folder):
        """folder'daki kurulumun durumu (başka klasörün biten işi sayılmaz)."""
        with self.lock:
            d = dict(self.d)
        if not d['calisiyor'] and (not folder or not d['klasor'] or os.path.normcase(os.path.abspath(d['klasor']))
                                   != os.path.normcase(os.path.abspath(folder))):
            d = self._blank('yok', folder)
        if not d['calisiyor'] and folder and kurulu(folder):
            d['durum'] = 'kurulu'
        d.update(gerekli=True, ad=BEPINEX['ad'])
        return d

    def running(self):
        with self.lock:
            return self.d['calisiyor']

    def start(self, folder):
        """BepInEx'i ve eklentiyi istemci klasörüne kur (sürüyorsa ya da kuruluysa bir şey yapmaz) -> durum."""
        with self.lock:
            if folder and not self.d['calisiyor'] and not kurulu(folder):
                self.stop.clear()
                self.d = dict(self._blank('indiriliyor', folder), calisiyor=True)
                threading.Thread(target=self._run, args=(folder,), daemon=True).start()
        return self.state(folder)

    def cancel(self):
        self.stop.set()

    def bekle(self, folder, adim=None):
        """Kurulum bitene dek bekle (adim: (yüzde) -> None, ilerleme) -> kuruldu mu."""
        self.start(folder)
        while self.running():
            if adim:
                st = self.state(folder)
                adim(int(100 * st['alinan'] / st['toplam']))
            time.sleep(0.3)
        return kurulu(folder)

    def _indir(self, parca):
        """Arşivi belleğe indir ve SHA-256'sını doğrula -> bayt."""
        buf = bytearray()
        try:
            with self.opener(Request(parca['url'], headers={'User-Agent': 'OpenOrbit'}), timeout=ZAMAN_ASIMI) as r:
                while True:
                    if self.stop.is_set():
                        raise Iptal()
                    b = r.read(PARCA)
                    if not b:
                        break
                    buf += b
                    with self.lock:
                        self.d['alinan'] += len(b)
        except (OSError, http.client.HTTPException) as e:
            raise IndirmeHatasi(_('İndirme sunucusuna bağlanılamadı (internet bağlantını denetle): %s', e))
        if hashlib.sha256(buf).hexdigest() != parca['sha256']:
            raise IndirmeHatasi(_('%s beklenen dosya değil (SHA-256 tutmadı): yeniden dene.', parca['ad']))
        return bytes(buf)

    def _run(self, folder):
        try:
            self.log('BepInEx indiriliyor: %s, %s' % (BEPINEX['url'], UNITY['url']))
            arsiv, unity = self._indir(BEPINEX), self._indir(UNITY)
            with self.lock:
                self.d['durum'] = 'kuruluyor'
            with zipfile.ZipFile(io.BytesIO(arsiv)) as z:
                for m in z.infolist():
                    p = safe_path(folder, m.filename)
                    if m.is_dir():
                        os.makedirs(p, exist_ok=True)
                        continue
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    with z.open(m) as src, open(p, 'wb') as out:
                        shutil.copyfileobj(src, out)
            p = os.path.join(folder, 'doorstop_config.ini')      # Doorstop kapalı: BepInEx'i yalnız panelin argümanı açar
            with open(p, 'rb') as fh:
                ini = fh.read()
            with open(p, 'wb') as fh:
                fh.write(ini.replace(b'enabled = true', b'enabled = false', 1))
            p = yol(folder, AYAR)
            if not os.path.isfile(p):                           # konsol penceresi açılmasın (öteki ayarları BepInEx ekler)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'wb') as fh:
                    fh.write(b'[Logging.Console]\n\nEnabled = false\n')
            ayar(folder)
            p = yol(folder, UNITY['yol'])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as fh:
                fh.write(unity)
            eklenti(folder)
            with open(yol(folder, KAYIT), 'w', encoding='utf8') as fh:
                json.dump({'bepinex': BEPINEX['sha256'], 'unity': UNITY['sha256'], 'ad': BEPINEX['ad'],
                           'zaman': time.strftime('%Y-%m-%d %H:%M:%S')}, fh, indent=1)
            with self.lock:
                self.d.update(durum='kurulu', alinan=self.d['toplam'])
            self.log('BepInEx kuruldu: %s (%s)' % (BEPINEX['ad'], folder))
        except Iptal:
            with self.lock:
                self.d['durum'] = 'durdu'
            self.log('BepInEx kurulumu durduruldu')
        except IndirmeHatasi as e:
            with self.lock:
                self.d.update(durum='hata', hata=str(e))
            self.log('BepInEx kurulamadı: %s' % e)
        except OSError as e:
            with self.lock:
                self.d.update(durum='hata', hata=_('Dosya yazılamadı: %s', e))
            self.log('BepInEx kurulamadı: %r' % e)
        except Exception as e:
            with self.lock:
                self.d.update(durum='hata', hata=repr(e))
            self.log('BepInEx: beklenmeyen hata: %r' % e)
        finally:
            with self.lock:
                self.d['calisiyor'] = False
