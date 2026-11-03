"""Bot: bir pilotun kalıcı kaydı (paket durumu, durum.json'da sözlük) ve çalışırken gereken geçici alanları.

Kalıcı kayıt (k):
  no, ad, firma, kisilik            kadrodan (değişmez)
  uid                               sunucudaki kimliği (BOT_UID_TABAN + no)
  seviye, ep, kredi, uridyum, onur  ilerleme
  ekip                              katalog biçiminde donanım (sahip olunan her şey; donat yerleştirir)
  harita, x, y                      son konumu
  ruh, hafiza                       ruh hâli ve kişilere karşı ilişkiler (kisilik.RuhHali, kisilik.Hafiza)
  klan, arkadaslar                  klan kimliği ya da None; arkadaş adları (rehberin kopyası)
  istat                             npc, oyuncu, olum, gorev, sure_sn, harcama
  gorev                             süren görev {id, kosullar: {koşul: sayı}} ya da None; tamam: bitirdiği görevler
  hedef, niyet                      son hedefi (beyin) ve LLM'in eğilimi {hedef: pay, bitis}
"""
import random, time

import profil as PF
from . import katalog as K
from . import kisilik as KS
from . import oyun_ayari as OA
from . import toplum as T

BOT_UID_TABAN = 1800000000


class Bot:
    def __init__(self, k):
        self.k = k
        k.setdefault('uid', BOT_UID_TABAN + int(k['no']))
        k.setdefault('seviye', 1)
        for a in ('ep', 'kredi', 'uridyum', 'onur'):
            k.setdefault(a, 0)
        k.setdefault('ekip', K.yeni_ekip())
        k.setdefault('harita', K.ev(k['firma']))
        k.setdefault('x', 0)
        k.setdefault('y', 0)
        k.setdefault('ruh', {})
        k.setdefault('hafiza', {})
        k.setdefault('klan', None)
        k.setdefault('arkadaslar', [])
        k.setdefault('istat', {})
        if 'npc_puan' not in k['istat']:       # eski kayıt: öldürmelerin türü yok; uzaylı başına sıradan uzaylıların ortalaması (3,7),
            k['istat']['npc_puan'] = round(k['istat'].get('npc', 0) * 3.7)       # oyuncu gemisi başına kendi gemisinin puanı
            k['istat']['oyuncu_puan'] = k['istat'].get('oyuncu', 0) * T.gemi_rutbe_puani(k['ekip']['gemi'])
        k.setdefault('gorev', None)
        k.setdefault('tamam', [])
        k.setdefault('kargo', {})
        k.setdefault('beceri', {})             # kalıcı savaş, ekonomi ve hayatta kalma XP'si
        k.setdefault('stok', {'ammunition_laser_lcb-10': 1000, 'ammunition_rocket_r-310': 20})     # yeni oyuncunun cephanesi
        k.setdefault('hedef', None)
        k.setdefault('niyet', None)
        if k.get('onur', 0) < 0 and not k.get('_onur_duzeltme'):
            k['onur'] = 0              # eski kayıt: kargo kutusu cezasıyla eksiye düşen onur bir kez sıfırlanır (govde.calar_mi)
        k['_onur_duzeltme'] = 1
        k['hafiza'].pop('', None)      # eski kayıt: saldıran bot gemisi adsız hatırlanıyordu (govde._ad)
        k['kisilik']['_ad'] = k['ad']                     # saat dilimi ve zevk adından (kişilik kadrodan her açılışta yeniden gelir)
        self.ruh = KS.RuhHali(k['ruh'], k.get('ruh_t'))
        self.hafiza = KS.Hafiza(k['hafiza'])
        self.r = random.Random('%s|%s|%s' % (k['ad'], k['no'], k['istat'].get('sure_sn', 0)))     # belirlenimci (benzetim)
        # geçici
        self.cevrimici = False
        self.oturum_bitis = 0.0
        self.sonraki_giris = 0.0         # çevrimdışıyken bir sonraki "girsem mi" anı
        self.sonraki_karar = 0.0
        self.hedef = None                # beyin.Hedef örneği
        self.hedef_bas = 0.0
        self.plan = {}                   # hedefin kendi durumu (gidilen harita, hedef uzaylı ...)
        self.yolda = None                # [haritalar ...]: portal yolunda (soyut atlama)
        self.yolda_t = 0.0               # sıradaki atlamanın anı
        self.olu_bitis = 0.0             # öldü: bu ana dek doğmadı (üste dönüyor)
        self.govde = None                # somut gemi (govde.BotGemi) ya da None
        self.son_soyut = time.time()
        self._deger = None               # degerler() önbelleği (ekip değişince sıfırlanır)
        self._adaylar = None             # alisveris.adaylar() önbelleği
        self.olaylar = []                # gelen olaylar (sohbet, davet, saldırı ...): beyin ve LLM okur
        self.bekleyen = []               # yanıt bekleyen davetler [(tür, kimlik, ad, an)] (toplum.davetler)
        self.oturum = None               # çevrimiçiyken toplum.BotOturum
        self.profil = None               # topluluk için Profil (toplum.py)
        self.izin = {}                   # paketin erişim ayarları (yonetici bağlar)
        self.saat = time.time            # olayların saati (yonetici benzetimin saatini bağlar)
        self.oa = OA.STANDART             # paketin oyun ayarı profili (yonetici bağlar; oyuncunun ayarlarından ayrı)

    # ------------------------------------------------------------ kısayollar
    @property
    def ad(self):
        return self.k['ad']

    @property
    def uid(self):
        return self.k['uid']

    @property
    def kayitli(self):
        """Sunucuya kayıt oldu mu (progressive'de pilotlar sırayla katılır; eski kayıtlarda alan yok: kayıtlı)."""
        return self.k.get('kayitli', True)

    @property
    def firma(self):
        return self.k['firma']

    @property
    def seviye(self):
        return self.k['seviye']

    @property
    def harita(self):
        return self.k['harita']

    @property
    def ozellik(self):
        return self.k['kisilik']['ozellik']

    @property
    def arketip(self):
        return self.k['kisilik']['arketip']

    def o(self, ad):
        return self.k['kisilik']['ozellik'][ad]

    def ist(self, ad, n=1):
        self.k['istat'][ad] = self.k['istat'].get(ad, 0) + n

    def beceri_kazan(self, alan, xp):
        from . import gelisim as GL
        return GL.kazan(self.k, alan, xp)

    def beceri(self, alan):
        from . import gelisim as GL
        return GL.oran(self.k, alan)

    def beceriler(self):
        from . import gelisim as GL
        return GL.ozet(self.k)

    def kalkan_payi(self):
        """Jeneratör yuvalarının kalkana ayrılan payı: temkinli kalkan, avcı hız sever; klan emri (klan_emir: tam kalkan, tam hız,
        dengeli) önce gelir."""
        if self.k.get('yapi'):
            from .klan_emir import YAPI_PAYI
            return YAPI_PAYI.get(self.k['yapi'], 0.6)
        return KS.sinirla(0.85 - 0.45 * self.o('risk') * self.o('saldirganlik') - 0.15 * (self.arketip == 'avci'), 0.3, 0.95)

    def klan_birikimi(self):
        """Klan kuracak lider kişilikli bot (klansız, 4+ seviye) kuruluş bedelini kenara ayırır: alışveriş ve açık artırma bu
        krediye dokunmaz. Önceden 8 saatte bile hiçbir bot klan kuramıyordu (para hep başka şeye gidiyordu)."""
        if (self.arketip != 'lider' or self.k.get('klan') is not None or self.seviye < 4 or not self.izin.get('klan', True)
                or not self.izin.get('klan_kur', True)):
            return 0
        import klan as KL
        return KL.KURMA_BEDELI * 1.3

    def deger(self):
        """Savaş değerleri; etkin boosterlar (hasar, can, kalkan) üstüne eklenir (süreleri dolunca kendiliğinden düşer)."""
        d = self._taban_deger()
        from . import ganimet as GB
        hs, can, kal = GB.booster_payi(self, 'DAMAGE'), GB.booster_payi(self, 'HITPOINTS'), GB.booster_payi(self, 'SHIELD')
        if hs or can or kal:
            d = dict(d, dps=d['dps'] * (1 + hs), can=d['can'] * (1 + can), kalkan=d['kalkan'] * (1 + kal),
                     ehp=d['ehp'] * (1 + 0.5 * can + 0.5 * kal))
        return d

    def _taban_deger(self):
        """Savaş değerleri; dps ve ehp uzaylılara karşı: profilin uzaylı canı ve hasarı çarpanıyla (zor profilde aynı gemi daha
        yavaş öldürür, daha çok hasar alır). guc donanımın kendisi (karşılaştırma, panel)."""
        if self._deger is None:
            d = K.degerler(self.k['ekip'], self.kalkan_payi())
            d['dps'] /= max(0.1, self.oa.carpan('npc_can', 'harita'))
            d['ehp'] /= max(0.1, self.oa.carpan('npc_hasar', 'harita'))
            self._deger = d
        return self._deger

    def ekip_degisti(self):
        self._deger = self._adaylar = None
        if self.govde is not None:
            self.govde.yenile()

    # ------------------------------------------------------------ ilerleme
    def kazan(self, ep=0, kredi=0, uridyum=0, onur=0):
        """Kazanç (ya da kayıp); seviye EP tablosundan (profil.level_for). -> yeni seviyeye çıktı mı."""
        k = self.k
        # küsurat birikir: soyut benzetimin 5 sn'lik adımları uridyumu 0,4 gibi parçalarla verir, kesilince hiç birikmiyordu
        kes = self.__dict__.setdefault('_kesir', {})
        tam = {}
        for a, v in (('ep', ep), ('kredi', kredi), ('uridyum', uridyum), ('onur', onur)):
            v = v + kes.get(a, 0.0)
            tam[a] = int(v)
            kes[a] = v - tam[a]
        k['ep'] += tam['ep']
        if tam['kredi'] > 0 and tam['ep'] > 0 and k.get('klan'):
            self._klan_geliri = self.__dict__.get('_klan_geliri', 0) + tam['kredi']   # uzaylı/görev kazancı: klan vergisi (toplum)
        k['kredi'] = max(0, k['kredi'] + tam['kredi'])
        k['uridyum'] = max(0, k['uridyum'] + tam['uridyum'])
        k['onur'] += tam['onur']
        lv = PF.level_for(k['ep'])
        if lv != k['seviye']:
            yukseldi = lv > k['seviye']
            k['seviye'] = lv
            if yukseldi:
                self.ruh.it(moral=0.2, ozguven=0.05)
                self.olay('seviye', seviye=lv)
            return yukseldi
        return False

    def odul(self, kaynak, hiz=1.0, **kazanc):
        """Oyunun ödülü (kaynak: npc, gorev, kutu ya da None): paketin hızı, oyun ayarı profili ve EP/onur boosterlarıyla çarpılır."""
        from . import ganimet as GB
        bst = {'ep': 1 + GB.booster_payi(self, 'EXPERIENCE_POINTS'), 'onur': 1 + GB.booster_payi(self, 'HONOUR_POINTS')}
        return self.kazan(**{k: v * hiz * self.oa.carpan(k, kaynak) * bst.get(k, 1.0) for k, v in kazanc.items()})

    def ode(self, para, tutar):
        """'C' | 'U' ile öde -> ödendi mi."""
        a = 'kredi' if para == 'C' else 'uridyum'
        if self.k[a] < tutar:
            return False
        self.k[a] -= int(tutar)
        self.ist('harcama_' + a, int(tutar))
        return True

    def ekle(self, loot, n=1):
        """Satın alınan ya da kazanılan eşya donanıma (gemi: aktif gemi olur)."""
        e = self.k['ekip']
        if loot.startswith('ship_'):
            if not (K.ESYA['gemiler'].get(loot) or {}).get('hp'):
                return False                             # yalnız görünüm olan tasarım: gemi değil
            e['gemi'] = loot
        elif loot in K.ESYA['lazerler']:
            e['lazer'][loot] = e['lazer'].get(loot, 0) + n
        elif loot in K.ESYA['kalkan_jeneratorleri']:
            e['kalkan'][loot] = e['kalkan'].get(loot, 0) + n
        elif loot in K.ESYA['hiz_jeneratorleri']:
            e['hiz'][loot] = e['hiz'].get(loot, 0) + n
        elif loot in K.ESYA['dronlar']:
            e['dron'][loot] = e['dron'].get(loot, 0) + n
        elif loot in K.ESYA['savas_esyalari']['fircatici']['turler']:
            e['fircatici'] = loot                       # roket fırlatıcısı (teknoloji.py)
        elif loot in K.ESYA['ekstralar'] or loot in K.ESYA['onarim_robotlari']:
            from . import ekstra as EK
            EK.tak(self, loot)                          # CPU ve onarım robotu ekstra yuvasına (ekstra.py)
            return True
        elif loot in K.ESYA['lazer_cephane'] or loot in K.ESYA['roketler'] or loot in K.ESYA['savas_esyalari']['fircatici_cephane'] \
                or loot.startswith('tech_') or loot.startswith('ammunition_'):
            from . import silah as SL
            SL.ekle(self, loot, n)                      # cephane ve roket stoğa (silah.py)
            return True
        else:
            return False
        self.ekip_degisti()
        return True

    # ------------------------------------------------------------ kargo
    def kargo_dolu(self):
        """Kargonun doluluğu (0..1): yer kaplayan cevherler / geminin kargo alanı."""
        k = self.k.get('kargo') or {}
        return sum(v for t, v in k.items() if int(t) in K.KARGO_CEVHER) / max(1, K.kargo_kapasitesi(self.k['ekip']))

    def kargo_ekle(self, icerik):
        """Cevherleri sığdığı kadar kargoya alır -> alınanlar {tür: adet}."""
        kargo = self.k.setdefault('kargo', {})
        bos = K.kargo_kapasitesi(self.k['ekip']) - sum(v for t, v in kargo.items() if int(t) in K.KARGO_CEVHER)
        alinan = {}
        for t, v in sorted(icerik.items(), key=lambda x: -K.cevher_fiyatlari(0).get(int(x[0]), 0)):   # değerliler önce
            n = int(v) if int(t) not in K.KARGO_CEVHER else max(0, min(int(v), bos))
            if n > 0:
                kargo[str(t)] = kargo.get(str(t), 0) + n
                alinan[int(t)] = n
                if int(t) in K.KARGO_CEVHER:
                    bos -= n
        return alinan

    def kargo_sat(self):
        """İstasyonda kargonun satılabilir cevherlerini satar (onura bağlı fiyat, profilin cevher fiyatı çarpanı) -> kazanılan kredi.
        Önce laboratuvar: yükseltmeyi seven bot arıtıp lazerine, kalkanına, roketine yükler (lab.py); kalanı satılır."""
        from . import lab as LB, silah as SL, skylab as SK
        SK.tasi(self, self.saat(), K.kargo_kapasitesi(self.k['ekip']) * 3)      # Skylab'dan gelen cevher (taşıma hakkı kadar)
        LB.karar(self, SL.saatlik_mermi(self))
        fiyat = K.cevher_fiyatlari(self.k['onur'], self.oa.carpan('cevher_fiyat'))
        kargo = self.k.setdefault('kargo', {})
        kredi = 0
        for t in list(kargo):
            if int(t) in fiyat:
                kredi += fiyat[int(t)] * kargo.pop(t)
            elif int(t) in K.KARGO_CEVHER:              # rafineride satılmayan (Palladium: 5-2'deki tüccarda kapı enerjisine) depoya
                from . import silah as SL
                ad = K.ESYA['cevherler']['turler'].get(str(t), 'resource_ore_%s' % t)
                SL.stok(self)[ad] = SL.stok(self).get(ad, 0) + kargo.pop(t)
        if kredi:
            self.kazan(kredi=kredi)
            self.ist('cevher_kredi', kredi)
            self.beceri_kazan('ekonomi', min(5.0, 1.0 + kredi / 1000000.0))
            self.olay('cevher_satti', kredi=kredi)
        return kredi

    def olay(self, tur, now=None, **f):
        """Olay kuyruğu (en çok 30): beyin ve LLM bağlamı için."""
        self.olaylar.append(dict(tur=tur, t=now or self.saat(), **f))
        del self.olaylar[:-30]

    def kayit(self):
        self.k['ruh'] = self.ruh.kayit()
        self.k['ruh_t'] = self.ruh.t
        return self.k

    def ozet(self):
        """Panel ve LLM için kısa durum."""
        d = self.deger()
        return dict(no=self.k['no'], ad=self.ad, firma=self.firma, arketip=self.arketip, seviye=self.seviye, ep=self.k['ep'],
                    kredi=self.k['kredi'], uridyum=self.k['uridyum'], onur=self.k['onur'], gemi=self.k['ekip']['gemi'],
                    guc=round(d['guc'], 1), harita=K.H.name(self.harita), cevrimici=self.cevrimici, klan=self.k['klan'],
                    hedef=self.k['hedef'], somut=self.govde is not None, istat=dict(self.k['istat']), kayitli=self.kayitli,
                    kargo=round(self.kargo_dolu(), 2), beceriler=self.beceriler())
