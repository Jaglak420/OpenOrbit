"""Bot yöneticisi: paketi yükler, botların çevrimiçi takvimini, kararlarını ve soyut benzetimini yürütür, durumu kaydeder.

Oyun sunucusunda tek örnek (BOT): game.py DO_BOT ortam değişkeniyle paketi verir, yönetici kendi iş parçacığında saniyede bir
tick() çalıştırır. Benzetim betiği (tools/bot_benzetim.py) ve testler aynı sınıfı sahte saatle (now parametresi) sürer.

Her tick'te yalnız işi olan botlar işlenir: çevrimdışılar dakikada bir "girsem mi" der; çevrimiçiler kendi karar anlarında düşünür,
soyut etkiler SOYUT_SN'de bir toplu uygulanır. Dünyalar (govde.py) haritalarındaki botları kancalarla öğrenir.
"""
import json, os, random, threading, time, traceback

import harita as H
from . import beyin as B
from . import katalog as K
from . import kisilik as KS
from . import ani as ANI
from . import soyut as S
from .durum import Bot
from . import konusma as KN
from . import oyun_ayari as OA
from .sohbet_motoru import SohbetMotoru
from .hedefler import gorev as GV
from .hedefler import alisveris as ALIS

SOYUT_SN = 5.0
PVP_SN = 10.0
KAYIT_SN = 60.0
GIRIS_DENEME_SN = 60.0
SURUM = 1
AKTIF = None                   # oyun sunucusunun yöneticisi (game.py kurar; govde.py okur)
PRIME_NUFUS = 1.3              # yoğun saatte çevrimiçi olma eğilimi çarpanı
CEPHELER = (16, 16, 29, 13, 14, 15)        # 4-4 iki kat, 4-5, 4-1, 4-2, 4-3

VARSAYILAN = {                 # paketin ayarları (panel/botlar.py aynı anahtarları doğrular)
    'hiz': 1.0,                # ilerleme hızı çarpanı
    'cevrimici_oran': 0.6,     # botların çevrimiçi olma eğilimi çarpanı
    'en_cok_cevrimici': 0,     # aynı anda en çok çevrimiçi (0: sınırsız)
    'telafi_saat': 150,        # istemci kapalıyken panelin simüle edeceği en çok offline saat (0: kapalı)
    'telafi_oran': 1.0,        # offline simülasyon temposu (1: tam hız, 10: %1000)
    'kayit_sn': 15,            # progressive: her firmaya ortalama bu kadar saniyede bir yeni pilot kayıt olur (0: hepsi baştan)
    'firma_guc': [1.0, 1.0, 1.0],        # firmaların gelişim çarpanı (MMO, EIC, VRU)
    'jumpstart_saat': 60,      # jumpstart: ortalama oyun saati (dağılım lognormal)
    'pvp_seviye': 6,
    'yabanci_harita': True,    # başka firmanın haritalarına girebilir
    'sohbet_dk': 6,            # global/firma sohbetinde dakikada en çok bot satırı
    'yardim_en_cok': 3,        # bir yardım çağrısına gelen en çok bot
    'somut_en_cok': 40,        # oyuncunun haritasında gemi olarak gösterilen en çok bot
    'klan_basina': 12,         # kaç bota bir bot klanı
    'kaba_sohbet': 1,          # laf atma: 0 kapalı, 1 hafif, 2 sert, 3 çok sert (küfür ve gerçek tehdit hiçbirinde yok)
    'moderator': False,        # sohbet moderatörü botlar (bot/moderasyon.py)
    'mod_sayisi': 2,
    'kural_buyuk': True, 'kural_sel': True, 'kural_hakaret': True, 'kural_reklam': True,
    'sustur_dk': 10,           # susturma süresi
    'yasak_esik': 3,           # bu kadar susturmadan sonra yasak
    'yasak_saat': 24,
    'prime_baslangic': 19,     # akşam yoğun saatleri (yerel saat): çevrimiçi ve PvP artar, firmalar bir haritada toplanır
    'prime_bitis': 23,
    'prime_pvp': 2.0,          # yoğun saatte PvP isteği çarpanı (1: fark yok)
    'buyuk_savas': True,       # yoğun saatte firmaların PvP botları ortak cephe haritasında toplanır
    'izinler': {'magaza': True, 'gorev': True, 'pvp': True, 'sohbet': True, 'klan': True, 'klan_kur': True, 'arkadas': True,
                'grup': True, 'muzayede': True, 'oyuncuya_saldir': True, 'yardim': True, 'kutu_calma': True, 'kargo': True, 'roket': True, 'ozel_cephane': True, 'ekstra': True, 'mayin': True, 'lab': True, 'skylab': True, 'teknoloji': True, 'ganimet': True, 'assembly': True, 'kapi': True, 'etkinlik': True, 'modlar': True, 'klan_diplomasi': True, 'klan_emir': True, 'kapi_dolgu': True, 'klan_ksi': True},
}


class Yonetici(SohbetMotoru):
    def __init__(self, paket, durum_yolu=None, log=print, now=None, offline=False):
        self.paket = paket
        self.durum_yolu = durum_yolu
        self.offline = bool(offline)       # paneldeki çevrimdışı simülatörü: ilk nüfusu kurma veya telafi etme
        self.log = log
        self.ayarlar = dict(VARSAYILAN, **(paket.get('ayarlar') or {}))
        self.ayarlar['izinler'] = dict(VARSAYILAN['izinler'], **(self.ayarlar.get('izinler') or {}))
        self.kip = paket.get('kip', 'normal')
        self.oa = OA.Profil(self.ayarlar.get('oyun_ayari'))      # botların oyun ayarı profili (oyuncununkinden ayrı)
        self.lock = threading.RLock()
        self.botlar = []
        self.ada = {}                  # ad küçük harf -> Bot
        self.haritada = {}             # harita -> {Bot}: çevrimiçi botlar
        self.dunyalar = []             # govde kancaları: harita_degisti(bot, eski), bot_cevrimici(bot, acik)
        self.insanlar = {}             # ad küçük harf -> (ad, harita, firma): sunucudaki gerçek oyuncular (dünyalar bildirir)
        self.son_pvp = self.son_kayit = self.now = now or time.time()   # now: benzetimin saati (sahte saatte de doğru)
        self.calisiyor = False
        self._is = None
        self.toplum = False            # oyun sunucusunda topluluğa ve sohbete bağlı (toplum.kaydol)
        self.son_sosyal = 0.0
        self.kayit_sirasi = {}         # firma -> [Bot]: henüz kayıt olmamış pilotlar (progressive, sırayla katılır)
        self.sonraki_kayit = {}        # firma -> an
        self.sohbet_hazirla()
        self.yukle(now)

    # ------------------------------------------------------------ ayarlar
    def ayar(self, ad, vars=None):
        return self.ayarlar.get(ad, vars)

    def izin(self, ad):
        return bool(self.ayarlar['izinler'].get(ad, True))

    def hiz(self, bot):
        """Botun ilerleme hızı: paketin hızı x firmasının gücü."""
        fg = self.ayarlar.get('firma_guc') or [1, 1, 1]
        return float(self.ayarlar.get('hiz', 1.0)) * float(fg[bot.firma - 1])

    # ------------------------------------------------------------ yükleme / kayıt
    def yukle(self, now=None):
        now = now or time.time()
        kayit = {}
        if self.durum_yolu and os.path.exists(self.durum_yolu):
            try:
                with open(self.durum_yolu, encoding='utf8') as f:
                    kayit = json.load(f)
            except (OSError, ValueError) as e:
                self.log('   botlar: durum okunamadı (%s), baştan' % e)
        eski = {str(k): v for k, v in (kayit.get('botlar') or {}).items()}
        self.ad_kaydi_n = int(kayit.get('ad_kaydi') or 0)
        yeni = []
        # progressive yeni paket: pilotlar oyuna aynı anda değil, gerçek bir sunucuya kayıt olur gibi tek tek katılır (performans,
        # haritalara doğal dağılım); jumpstart kadrosu zaten oynamış sayılır
        sirali = self.kip != 'basit' and self.paket.get('gelisim') != 'jumpstart' and self.ayar('kayit_sn', 15) > 0
        from . import llm_saglayici as SG
        cok_dilli = SG.cok_dilli()
        for kd in self.paket.get('kadro', []):
            k = eski.get(str(kd['no']))
            if k is None:
                kisilik = dict(kd['kisilik'])
                kisilik['ozellik'] = dict(kisilik.get('ozellik') or {})
                k = dict(no=kd['no'], ad=kd['ad'], firma=kd['firma'], kisilik=kisilik, kayitli=not sirali)
                yeni.append(k)
            else:
                # Panel kişilik temelini güncelleyebilir; savaş deneyimi ayrı delta olarak kalıcıdır.
                adaptasyon = k.get('kisilik_adaptasyon') or {}
                kisilik = dict(kd['kisilik'])
                ozellik = dict(kisilik.get('ozellik') or {})
                for alan, delta in adaptasyon.items():
                    taban = float(ozellik.get(alan, 0.5))
                    ozellik[alan] = round(max(0.05, min(0.95, taban + float(delta))), 3)
                kisilik['ozellik'] = ozellik
                k.update(ad=kd['ad'], firma=kd['firma'], kisilik=kisilik)      # panelde ad değişmiş olabilir
            if self.kip == 'gelismis' and not cok_dilli:
                k['kisilik'] = dict(k['kisilik'], dil='en')      # dahili dil modeli yalnız İngilizce (llm.py; başka sağlayıcıda serbest)
            b = Bot(k)
            b.izin = self.ayarlar['izinler']
            b.kaba = int(self.ayar('kaba_sohbet', 1))       # kaba sohbet düzeyi (llm.tarz, sohbet_motoru)
            b.saat = lambda: self.now
            b.oa = self.oa
            b.hafiza.dinle = (lambda b: lambda ad, tur, now: ANI.olaydan(self, b, ad, tur, now))(b)     # anı defteri (güçlü sağlayıcı)
            b.sonraki_giris = now + b.r.uniform(0, 20)
            self.botlar.append(b)
            self.ada[b.ad.lower()] = b
        self.ad_kaydi_uygula(yukleniyor=True)            # oyun kapalıyken panelde adı değişen ya da silinen botlar
        if self.kip == 'basit':
            from . import basit
            basit.hazirla(self, now)
            return
        if yeni and self.paket.get('gelisim') == 'jumpstart':
            self.jumpstart([b for b in self.botlar if b.k in yeni], now)
        for b in sorted(self.botlar, key=lambda b: b.r.random()):
            if not b.kayitli:
                self.kayit_sirasi.setdefault(b.firma, []).append(b)
        for f in self.kayit_sirasi:
            self.sonraki_kayit[f] = now + self.ayar('kayit_sn', 15) * b.r.uniform(0.2, 1.0)
        t = kayit.get('t')
        if not self.offline and t and self.ayar('telafi_saat', 0) > 0 and now - t > 600:
            self.telafi(min(now - t, self.ayar('telafi_saat') * 3600) * self.ayar('telafi_oran', 0.35), now)
        if not self.offline:
            self.ilk_nufus(now)
        from . import moderasyon as MOD
        MOD.sec(self)

    def ad_kaydi_uygula(self, yukleniyor=False):
        """Panelde adı değişen ya da silinen botlar (ad_kaydi.py): çalışan botların adı, botların hafızası ve rehberleri; oyun
        açıkken (panel kanalı) klanlar ve bağlı oyuncuların rehberi de. -> uygulanan olay sayısı."""
        import ad_kaydi as AK
        yeni = AK.yeniler(getattr(self, 'ad_kaydi_n', 0))
        if not yeni:
            return 0
        from . import toplum
        listeler = ('arkadas', 'gelen', 'giden', 'reddeden', 'engelli')
        with self.lock:
            if not yukleniyor:
                for e in yeni:
                    if e['tur'] != 'ad':
                        continue
                    b = self.ada.pop(AK._k(e['eski']), None)
                    if b is not None:
                        b.k['ad'] = e['yeni']
                        self.ada[b.ad.lower()] = b
                        for x in self.paket.get('kadro', []):
                            if x['no'] == b.k['no']:
                                x['ad'] = e['yeni']
                        if b.profil is not None:
                            toplum.guncelle(b)          # oyundaki adı (gemisi bir sonraki görünüşte yeni adla)
            for b in self.botlar:
                h = b.hafiza.d
                for e in yeni:
                    if e['tur'] == 'ad' and AK._k(e['eski']) in h:
                        x = h.pop(AK._k(e['eski']))
                        x['ad'] = e['yeni']
                        h[AK._k(e['yeni'])] = x
                    elif e['tur'] == 'sil':
                        h.pop(AK._k(e['ad']), None)
                r = b.k.get('rehber') or {}
                for ad in listeler:
                    if isinstance(r.get(ad), list):
                        x = AK.liste_uygula(r[ad], yeni)
                        if x is not None:
                            r[ad] = x
            self.ad_kaydi_n = yeni[-1]['n']
        toplum._KISILER['t'] = 0
        if not yukleniyor:
            import klan as KL
            import topluluk as TP
            AK.klanlar_uygula(KL)
            for k in list(TP.hepsi().values()):
                if k.ad.lower() not in self.ada:
                    AK.profil_uygula(k.profil)           # bağlı oyuncuların rehberi ve klan kopyası
            self.log('   botlar: ad kaydı uygulandı (%d olay)' % len(yeni))
        return len(yeni)

    def kaydet(self, now=None):
        if not self.durum_yolu:
            return
        now = now or time.time()
        with self.lock:                                  # metin kilit içinde: dünya döngüsü sözlüklere eklerken yarım kalmasın
            d = dict(surum=SURUM, t=now, ad_kaydi=self.ad_kaydi_n, botlar={str(b.k['no']): b.kayit() for b in self.botlar})
            if self.llm is not None:
                d['llm'] = self.llm.ozet()                    # panelin kullanım satırı (son bir saat: istek, token)
            metin = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
        tmp = self.durum_yolu + '.tmp'
        os.makedirs(os.path.dirname(self.durum_yolu), exist_ok=True)
        with open(tmp, 'w', encoding='utf8') as f:
            f.write(metin)
        os.replace(tmp, self.durum_yolu)
        self.son_kayit = now

    # ------------------------------------------------------------ çalıştırma
    def baslat(self):
        if self._is:
            return
        self.calisiyor = True
        self._is = threading.Thread(target=self._dongu, name='botlar', daemon=True)
        self._is.start()

    def durdur(self):
        self.calisiyor = False
        try:
            self.kaydet()
        except Exception as e:                           # kapanışta öteki kayıtlar (misafirler, klan) atlanmasın
            self.log('   botlar: kaydedilemedi (%r)' % e)

    def _dongu(self):
        while self.calisiyor:
            t0 = time.time()
            try:
                self.tick(t0)
            except Exception:
                self.log('   botlar: tick hatası\n' + traceback.format_exc())
            time.sleep(max(0.05, 1.0 - (time.time() - t0)))

    def tick(self, now=None):
        now = self.now = now or time.time()
        with self.lock:
            cevrimici = sum(1 for b in self.botlar if b.cevrimici)
            sinir = self.ayar('en_cok_cevrimici', 0) or len(self.botlar)
            cevrimici += self.kayit_tick(now, cevrimici, sinir)
            for b in self.botlar:
                if not b.kayitli:
                    continue
                try:                                     # bir botun hatası (bozuk ya da eski kayıt) ötekileri ve kaydı durdurmasın
                    if not b.cevrimici:
                        if now >= b.sonraki_giris:
                            b.sonraki_giris = now + GIRIS_DENEME_SN * b.r.uniform(0.7, 1.3)
                            if cevrimici < sinir and self._girsin_mi(b, now):
                                self.giris(b, now)
                                cevrimici += 1
                        continue
                    self.bot_tick(b, now)
                    if not b.cevrimici:
                        cevrimici -= 1
                except Exception:
                    self.bot_hatasi(b)
            if now - self.son_pvp >= PVP_SN:
                self.son_pvp = now
                try:
                    self.pvp_tick(now)
                except Exception:
                    self.hata_kaydi('pvp')
            for ad, fn in (('toplum', lambda: self._toplum_tick(now)),
                           ('sohbet', lambda: self.sohbet_tick(now)), ('llm', lambda: self.llm.tick(now) if self.llm else None)):
                try:
                    fn()
                except Exception:
                    self.hata_kaydi(ad)
        if now - self.son_kayit >= KAYIT_SN:
            self.kaydet(now)

    def _toplum_tick(self, now):
        if self.toplum and now - self.son_sosyal >= SOYUT_SN:
            self.son_sosyal = now
            from . import toplum
            toplum.tick(self, now)

    def bot_hatasi(self, b):
        """Bot başına bir kez günlüğe (her saniye aynı iz dökülmesin); 10 hatadan sonra bot bu oturumda dinlenir."""
        n = b.__dict__['_hata'] = b.__dict__.get('_hata', 0) + 1
        if n == 1:
            self.log('   botlar: %s hata verdi (atlandı)\n%s' % (b.ad, traceback.format_exc()))
        if n >= 10:
            b.cevrimici = False
            b.sonraki_giris = self.now + 3600
            self.haritada.get(b.harita, set()).discard(b)

    def hata_kaydi(self, ad):
        c = self.__dict__.setdefault('_hatalar', {})
        c[ad] = c.get(ad, 0) + 1
        if c[ad] in (1, 100, 10000):
            self.log('   botlar: %s hatası (%d. kez)\n%s' % (ad, c[ad], traceback.format_exc()))

    def bot_tick(self, b, now):
        self.now = now
        kosuda = b.hedef is not None and b.hedef.ad in ('kapi', 'mod') and not b.plan.get('bitti')
        if now >= b.oturum_bitis and not b.yolda and b.olu_bitis <= now and not kosuda:   # kapı/mod koşusu bitmeden çıkmaz
            if b.govde is not None and b.govde.alive and not b.__dict__.get('cikis_hazir'):
                # haritanda görünen bot olduğu yerde yok olmaz: istasyonuna ya da bir portala uçup orada çıkar (govde.cikisa_git)
                if not b.__dict__.get('cikis_istegi'):
                    b.cikis_istegi = now
                if now - b.cikis_istegi < 90:
                    return
            b.cikis_istegi = b.cikis_hazir = None
            self.cikis(b, now)
            return
        if b.olu_bitis > now:
            return
        if now >= b.sonraki_karar:
            B.karar(b, self, now)
            b.sonraki_karar = now + B.sonraki_karar_araligi(b)
        dt = now - b.son_soyut
        if dt >= SOYUT_SN:
            b.son_soyut = now
            # oturum uzadıkça yorulur (tutkunlar geç)
            b.ruh.it(yorgunluk=dt / (3600.0 * (1.5 + 3 * (b.k['kisilik']['aliskanlik'] == 'tutkun'))))
            b.ist('sure_sn', int(dt))
            from . import etkinlik as ET
            ET.battle_pass(b, min(dt, 60.0))             # pass görevleri ve Season Pass oynadıkça ilerler (uyku sonrası sınırlı)
            ET.season_pass(b, min(dt, 60.0))
            from . import ganimet as GB
            GB.assembly(b)                                # somut/soyut oyunda malzemesi varsa bot maga önceden değil, kendisi üretir
            if b.govde is None and b.hedef is not None:
                b.hedef.soyut(b, min(dt, 60.0), self)

    def kayit_tick(self, now, cevrimici, sinir):
        """Sıradaki pilotlar kayıt olur: her firmaya ayrı ayrı, ortalama kayit_sn'de (±%33) bir; yeni kayıt olan hemen oyuna girer
        (kendi üssünde, 1. seviye) -> giren sayısı."""
        n = 0
        ort = float(self.ayar('kayit_sn', 15) or 0)
        for f, sira in self.kayit_sirasi.items():
            if not sira or now < self.sonraki_kayit.get(f, 0):
                continue
            b = sira.pop(0)
            b.k['kayitli'] = True
            b.k['kayit_t'] = now                         # rütbe puanı: kayıttan beri gün (toplum.puan)
            self.sonraki_kayit[f] = now + ort * b.r.uniform(0.67, 1.33)
            if cevrimici + n < sinir:
                self.giris(b, now)
                n += 1
            else:
                b.sonraki_giris = now + GIRIS_DENEME_SN
        return n

    def prime(self, now=None):
        """Akşamın yoğun saatleri mi (prime_baslangic-prime_bitis, yerel saat; gece yarısını geçebilir; eşitse yok)."""
        h = time.localtime(now or self.now).tm_hour
        a, b = int(self.ayar('prime_baslangic', 19)), int(self.ayar('prime_bitis', 23))
        return a < b and a <= h < b or a > b and (h >= a or h < b)

    def cephe(self, now=None):
        """Yoğun saatin büyük savaş haritası: saat saat değişir, üç firmanın PvP botları aynı yerde buluşur (4-4, 4-5, 4-1/2/3)."""
        return CEPHELER[int((now or self.now) // 3600) % len(CEPHELER)]

    def _girsin_mi(self, b, now):
        saat = time.localtime(now).tm_hour
        p = KS.cevrimici_egilim(b.k['kisilik'], saat) * self.ayar('cevrimici_oran', 0.6) * (PRIME_NUFUS if self.prime(now) else 1)
        # dakikalık deneme: saatlik eğilimi dakikaya böl (ortalama oturum ~1-3 saat; denge çevrimiçi payını eğilime yaklaştırır)
        return b.r.random() < p / 45.0

    def ilk_nufus(self, now):
        """Sunucu açılınca o saatin dengedeki çevrimiçi nüfusu hemen kurulur (gerçek sunucuya giren oyuncu boş bir evren görmez):
        bot, dakikalık giriş olasılığı ve oturum uzunluğundan çıkan payla çevrimiçidir; oturumunun rastgele bir yerinde, sessizce."""
        saat = time.localtime(now).tm_hour
        sinir = self.ayar('en_cok_cevrimici', 0) or len(self.botlar)
        n = 0
        for b in sorted(self.botlar, key=lambda b: b.r.random()):
            if n >= sinir:
                break
            if not b.kayitli:
                continue
            p = KS.cevrimici_egilim(b.k['kisilik'], saat) * self.ayar('cevrimici_oran', 0.6) * (PRIME_NUFUS if self.prime(now) else 1)
            ort = sum(KS.ALISKANLIKLAR[b.k['kisilik']['aliskanlik']][2]) / 2.0
            pay = (p / 45.0 * ort) / (1 + p / 45.0 * ort)
            if b.r.random() < pay:
                self.giris(b, now, sessiz=True)
                b.son_soyut = now - random.uniform(0, SOYUT_SN)    # soyut adımlar aynı tickte toplanmasın (5 sn de bir kilitte 100+ ms); botun kendi dizisi (b.r) kaymasın
                b.oturum_bitis = now + (b.oturum_bitis - now) * b.r.uniform(0.1, 1.0)
                b.sonraki_karar = now + b.r.uniform(1, 15)
                n += 1
        self.log('   botlar: %d bot çevrimiçi başladı' % n)

    def giris(self, b, now, sessiz=False):
        if b.harita not in K.HARITALAR:                  # kapıda (ya da kapanmış bir haritada) çıkmıştı: üste döner
            b.k['harita'] = K.ev(b.firma)
            b.plan = {}
        b.cevrimici = True
        b.oturum_bitis = now + KS.oturum_dk(b.k['kisilik'], b.r) * 60
        b.ruh.guncelle(now)
        b.ruh.d['yorgunluk'] = 0.0
        b.son_soyut = now
        b.sonraki_karar = now + b.r.uniform(2, 10)
        b.hedef = None
        b.__dict__.pop('_hata', None)                    # hata sayacı oturumluk (ömürlük sayınca her tek hata botu 1 saat düşürüyordu)
        self.haritada.setdefault(b.harita, set()).add(b)
        b._olay_t = now
        if not sessiz and self.kip != 'basit' and b.r.random() < 0.25 * b.o('konuskanlik'):
            self.konus(b, b.r.choice(('global', 'firma')), KN.kalip(b, 'selam'), now=now + b.r.uniform(5, 40))
        for d in list(self.dunyalar):
            d.bot_cevrimici(b, True)

    def cikis(self, b, now):
        if b.r.random() < 0.15 * b.o('konuskanlik'):
            self.konus(b, 'global', KN.kalip(b, 'cikis'), now=now, hemen=True)
            self.sohbet_tick(now)
        b.cevrimici = False
        b.sonraki_giris = now + b.r.uniform(15, 120) * 60          # çıkınca bir süre girmez
        b.hedef = None
        b.k['hedef'] = None
        b.govde = None
        self.haritada.get(b.harita, set()).discard(b)
        for d in list(self.dunyalar):
            d.bot_cevrimici(b, False)

    # ------------------------------------------------------------ kancalar (soyut.py, govde.py)
    def harita_degisti(self, b, eski):
        if b.cevrimici:
            self.haritada.get(eski, set()).discard(b)
            self.haritada.setdefault(b.harita, set()).add(b)
        GV.ilerlet(b, GV.VISIT_MAP, harita=b.harita, y=self)
        if b.harita == K.ev(b.firma):
            GV.ilerlet(b, GV.HOME, harita=b.harita, y=self)
        for d in list(self.dunyalar):
            d.harita_degisti(b, eski)

    def npc_oldurdu(self, b, tip, n=1):
        kimlik = K.NPC['tipler'].get(tip, {}).get('npc_kimlik')
        if kimlik is not None and b.k.get('gorev'):
            GV.ilerlet(b, GV.KILL_NPC, n=n, npc_kimlik=kimlik, harita=b.harita, y=self)

    def bot_oldu(self, b, katil):
        """Ölüm deneyimi botun risk ve sabır dengesini değiştirir; değişimler paket kişiliğine göre kalıcı delta olarak tutulur."""
        if not katil or str(katil).lower() == b.ad.lower():
            return
        rakip = self.ada.get(str(katil).lower())
        base = next((x.get('kisilik', {}).get('ozellik', {}) for x in self.paket.get('kadro', [])
                     if int(x.get('no', -1)) == int(b.k.get('no', -2))), {})
        adapt = b.k.setdefault('kisilik_adaptasyon', {})
        ozellik = b.k['kisilik'].setdefault('ozellik', {})
        etki = 0.008 if rakip is not None else 0.003
        degisim = {'risk': -etki, 'sabir': etki * 0.375}
        if rakip is not None:
            kazanan = rakip.k.setdefault('kisilik_adaptasyon', {})
            kazanan_base = next((x.get('kisilik', {}).get('ozellik', {}) for x in self.paket.get('kadro', [])
                                 if int(x.get('no', -1)) == int(rakip.k.get('no', -2))), {})
            for alan, art in (('risk', 0.002), ('saldirganlik', 0.002)):
                kazanan[alan] = round(max(-0.9, min(0.9, float(kazanan.get(alan, 0.0)) + art)), 3)
                rakip.k['kisilik'].setdefault('ozellik', {})[alan] = round(
                    max(0.05, min(0.95, float(kazanan_base.get(alan, 0.5)) + kazanan[alan])), 3)
        for alan, delta in degisim.items():
            adapt[alan] = round(max(-0.9, min(0.9, float(adapt.get(alan, 0.0)) + delta)), 3)
            ozellik[alan] = round(max(0.05, min(0.95, float(base.get(alan, 0.5)) + adapt[alan])), 3)

    # ------------------------------------------------------------ sorgular
    def cevrimici_ad(self, adlar):
        """Adlardan çevrimiçi ilk kişi (bot) ya da None."""
        for a in adlar:
            b = self.ada.get(str(a).lower())
            if b is not None and b.cevrimici:
                return b
        return None

    def dusman_nufusu(self, bot):
        """harita -> [çevrimiçi düşman firma botları]."""
        return {m: [x for x in s if x.firma != bot.firma and x.olu_bitis <= self.now] for m, s in self.haritada.items()}

    def durum(self):
        with self.lock:
            return [b.ozet() for b in self.botlar]

    # ------------------------------------------------------------ bot-bot PvP (soyut)
    def pvp_tick(self, now, elapsed=PVP_SN):
        """Takım PvP: yakındaki müttefikler korur, ateşi yoğunlaştırır ve aralarında bağ kurar."""
        if not self.izin('pvp'):
            return
        adim_sayisi = max(1.0, min(360.0, float(elapsed or PVP_SN) / PVP_SN))

        def dost_mu(a, x):
            if a is x:
                return False
            try:
                from . import toplum as TP
                iliski = TP.klan_iliskisi(a, x)
                if iliski == 3:                       # klan savaşı: aynı firmada olsalar bile düşmanlar
                    return False
                if iliski in (1, 2):                  # ittifak ve saldırmazlık
                    return True
            except Exception:
                pass
            return a.firma == x.firma

        for m, s in list(self.haritada.items()):
            if m not in K.HARITALAR:
                continue
            canli = [b for b in s if b.olu_bitis <= now and b.govde is None and not b.yolda]
            if len(canli) < 2:
                continue
            for a in canli:
                if a.olu_bitis > now:
                    continue
                dusmanlar = [x for x in canli if x is not a and not dost_mu(a, x)]
                if not dusmanlar:
                    continue
                av = a.hedef is not None and a.hedef.ad == 'pvp'
                p0 = (0.12 if av else 0.006 * a.o('saldirganlik')) * min(1.0, len(dusmanlar) / 3.0)
                p = 1.0 - (1.0 - min(0.95, p0)) ** adim_sayisi
                if a.r.random() >= p:
                    continue
                # Klan savaşı hedefleri öncelik kazanır; aynı firmadaki savaş da gerçek çatışmadır.
                try:
                    from . import toplum as TP
                    klan_savasi = [x for x in dusmanlar if a.k.get('klan') and x.k.get('klan')
                                   and TP.klan_iliskisi(a, x) == 3]
                    if klan_savasi:
                        dusmanlar = klan_savasi
                except Exception:
                    pass
                hedef = a.r.choice(dusmanlar)
                dost_a = [x for x in canli if dost_mu(a, x) and x.olu_bitis <= now]
                dost_b = [x for x in canli if dost_mu(hedef, x) and x.olu_bitis <= now]
                # Sayıca üstün düşman desteği, çok cesur veya öfkeli olmayan yalnız avcıyı caydırabilir.
                if len(dost_b) > len(dost_a) + 1 and a.r.random() > a.o('risk') * 0.65 + 0.15:
                    continue
                oran = hedef.deger()['guc'] / max(0.5, a.deger()['guc'])
                if not av and oran > 0.9 + 0.6 * a.o('risk'):
                    continue
                if oran > 1.6 + a.o('risk') + a.ruh['ofke']:
                    continue
                rol_puani = {'tank': 1.0, 'dps': 1.15, 'destek': 1.2, 'kesif': 0.8, 'denge': 1.0}
                guc_a = min(3.0, sum(rol_puani.get(KS.rol(x.k['kisilik']), 1.0) for x in dost_a))
                guc_b = min(3.0, sum(rol_puani.get(KS.rol(x.k['kisilik']), 1.0) for x in dost_b))
                sonuc = S.karsilasma(a, hedef, self, now, wsparcie_a=guc_a, wsparcie_b=guc_b)
                if sonuc and sonuc[0] == 'kazandi':
                    zwyciezca = sonuc[1]
                    ekipa = dost_a if zwyciezca is a else dost_b
                    for sojusznik in ekipa[:3]:
                        sojusznik.hafiza.olay(zwyciezca.ad, 'birlikte_avlandik', now, kat=0.5)
                        zwyciezca.hafiza.olay(sojusznik.ad, 'yardim_etti', now, kat=0.4)
                        sojusznik.ruh.it(moral=0.025)
                    if zwyciezca.k.get('gorev'):
                        GV.ilerlet(zwyciezca, GV.KILL_PLAYERS, harita=zwyciezca.harita, y=self)

    # ------------------------------------------------------------ hızlı ilerletme
    def hizli(self, b, saniye, now, adim=900.0, pvp=False):
        """Botu saniye kadar oynamış gibi ilerletir (jumpstart, telafi): büyük adımlar, kararlar adım başına."""
        t = now - saniye
        b.cevrimici = True
        b.hedef = None
        while t < now:
            dt = min(adim, now - t)
            t += dt
            self.now = t
            b.olu_bitis = 0
            b.yolda = None
            B.karar(b, self, t)
            if b.hedef is not None:
                if b.yolda:
                    while b.yolda:
                        S.atla(b, b.yolda.pop(0), None)
                b.hedef.soyut(b, dt, self)
            from . import ganimet as GB
            GB.assembly(b)                                # jumpstart ve offline telafide de aynı Assembly karar yolu
            if self.izin('magaza'):
                for _ in range(8):           # büyük adımda biriken parayı harcar (gerçek zamanda ayrı kararlar)
                    c = ALIS.aday(b)[0]
                    if c is None or not ALIS.satin_al(b, c):
                        break
            b.ruh.d['yorgunluk'] = 0.0
        b.cevrimici = False
        b.hedef = None
        b.olu_bitis = 0
        self.now = now

    def jumpstart(self, botlar, now):
        """Yeni kadro gerçekçi bir dağılımla başlar: her bota lognormal "oynadığı saat" (çok acemi, çok orta, az güçlü), firma
        gücüyle çarpılır; bot o kadar oynamış gibi hızlı ilerletilir (donanımı, seviyesi, parası birbiriyle tutarlı)."""
        import math
        ort = max(1.0, float(self.ayar('jumpstart_saat', 60)))
        fg = self.ayar('firma_guc', [1, 1, 1])
        t0 = time.time()
        for b in botlar:
            saat = b.r.lognormvariate(math.log(ort) - 0.5, 1.0) * float(fg[b.firma - 1]) * (0.6 + 0.8 * b.o('hirs'))
            saat = min(saat, ort * 8)
            self.hizli(b, saat * 3600, now, adim=max(1800.0, saat * 3600 / 60))
        self.log('   botlar: jumpstart %d bot, %.1f sn' % (len(botlar), time.time() - t0))

    def telafi(self, saniye, now, offline_tick=None):
        """Oyuncu yokken geçen süreyi ilerlet: bireysel aktiflik, PvP, sosyal kararlar ve klan ilişkileri.
        offline_tick: varsa sanal zamanın dakikalık adımlarında CBS gibi kalıcı dünya işlerini ilerletir."""
        t0 = time.time()
        baslangic = now - max(0.0, float(saniye))
        yeni_kayitlar = {}
        # Progressive kadro çevrimdışıyken de normal sunucu gibi zamanla kayıt olur.
        # sinir=0: canlı oturum açmayız; kayıt olduktan sonra aşağıda soyut ilerleme uygulanır.
        while True:
            siralar = [self.sonraki_kayit.get(f, float('inf')) for f, sira in self.kayit_sirasi.items() if sira]
            if not siralar:
                break
            due = min(siralar)
            if due > now:
                break
            once = {b.k['no'] for b in self.botlar if not b.kayitli}
            self.now = due
            self.kayit_tick(due, 0, 0)
            for b in self.botlar:
                if b.k['no'] in once and b.kayitli:
                    yeni_kayitlar[b.k['no']] = due
        for b in self.botlar:
            if not b.kayitli:
                continue
            etkin_sure = max(0.0, now - max(baslangic, yeni_kayitlar.get(b.k['no'], baslangic)))
            if etkin_sure <= 0:
                continue
            pay = sum(KS.ALISKANLIKLAR[b.k['kisilik']['aliskanlik']][1]) / 24.0 * self.ayar('cevrimici_oran', 0.6)
            s = etkin_sure * pay * b.r.uniform(0.5, 1.5)
            if s > 0:
                self.hizli(b, s, now, adim=900.0)
        if self.kip == 'basit':
            # Basit kip yalnızca sabit haritasındaki PvE etkinliğini simüle eder; sosyal/PvP/CBS stratejisi yoktur.
            self.haritada = {}
        else:
            # Geçici çevrimiçi nüfus: takım PvP'si ve botların sosyal/klan kararları aynı çevrimdışı adımda yürür.
            self.haritada = {}
            gecici = []
            for b in self.botlar:
                if not b.kayitli:
                    continue
                pay = sum(KS.ALISKANLIKLAR[b.k['kisilik']['aliskanlik']][1]) / 24.0 * self.ayar('cevrimici_oran', 0.6)
                if b.r.random() < max(0.0, min(0.95, pay)):
                    b.cevrimici = True
                    self.haritada.setdefault(b.harita, set()).add(b)
                    gecici.append(b)
            try:
                self.pvp_tick(now, elapsed=max(PVP_SN, saniye))
                # Offline adımları duvar saatinden yavaştır; sosyal kararları da bu sanal zaman içinde
                # dakikalık aralıklarla çalıştır ki klan başvuruları, diplomasi ve CBS kararları atlanmasın.
                sanal = now - saniye
                while sanal < now:
                    sanal = min(now, sanal + 60.0)
                    self.now = sanal
                    self._toplum_tick(sanal)
                    if offline_tick is not None:
                        offline_tick(sanal)
            finally:
                for b in gecici:
                    b.cevrimici = False
                self.haritada = {}
        self.now = now
        self.log('   botlar: çevrimdışı simülasyon %.0f dk, %.1f sn' % (saniye / 60, time.time() - t0))



def sunucu(yol, log=print):
    """Oyun sunucusu açılırken (game.main, DO_BOT): paketi okur, yöneticiyi arka planda kurar (jumpstart ve çevrimdışı telafi
    saniyeler sürebilir; oyun beklemez) ve çalıştırır. Paketin durumu paket dosyasının yanındaki <kimlik>/durum.json."""
    global AKTIF
    try:
        with open(yol, encoding='utf8') as f:
            paket = json.load(f)
    except (OSError, ValueError) as e:
        log('   botlar: paket okunamadı (%s): %s' % (yol, e))
        return

    def kur():
        global AKTIF
        kimlik = os.path.splitext(os.path.basename(yol))[0]
        durum = os.path.join(os.path.dirname(yol), kimlik, 'durum.json')
        t0 = time.time()
        y = Yonetici(paket, durum, log)
        import klan as KL
        import topluluk as TP
        from . import toplum
        if not KL.DOSYA:                                  # bot klanları kalıcı (arkadaş sunucusunda ortak klan dosyası zaten var)
            KL.configure(os.path.join(os.path.dirname(durum), 'klanlar.json'))
        toplum.kaydol(y, getattr(TP.OYUN, 'SOHBET', None))
        y.toplum = True
        if y.kip == 'gelismis':
            from . import llm, llm_saglayici, llm_sunucu
            if llm_saglayici.cok_dilli() or llm_sunucu.kurulum() is not None:   # kullanıcının sağlayıcısı ya da kurulu dahili model
                y.llm = llm.Beyin(y, log)                  # model arka planda açılır; hazır olana dek kalıplar
                y.llm.baslat()
            else:
                log('   botlar: Gelişmiş kip ama dil modeli kurulu değil (Botlar > Gelişmiş kip): Normal kip gibi sürüyor')
        AKTIF = y
        y.baslat()
        log('botlar: "%s" (%s, %d bot) %.1f sn' % (paket.get('ad', kimlik), paket.get('kip', 'normal'), len(y.botlar), time.time() - t0))

    threading.Thread(target=kur, name='botlar-kurulum', daemon=True).start()


def kapat():
    """Sunucu kapanıyor (game.stop_gracefully): durum kaydedilir."""
    if AKTIF is not None:
        AKTIF.durdur()
        if AKTIF.llm is not None:
            AKTIF.llm.durdur()
