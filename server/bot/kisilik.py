"""Botun kişiliği: kalıcı özellikler, arketip, oyun alışkanlığı, yazım üslubu, ad; dinamik ruh hâli ve kişilere karşı hafıza.

Kadro paket oluşturulurken bir kez üretilir (kadro_uret, tohumlu ve belirlenimci): aynı paket her açılışta aynı botları verir.
Özellikler 0-1 arası; arketip ortalamaları verir, her bota gürültü eklenir (aynı arketipten iki bot aynı değil). Karar motoru
(beyin.py) hedefleri bu özelliklerle ve ruh hâliyle puanlar.
"""
import math, random, re, time

from . import ad_uslup as AU

OZELLIKLER = ('saldirganlik', 'rekabet', 'sosyallik', 'sabir', 'risk', 'sadakat', 'yardimseverlik', 'konuskanlik', 'tutumluluk',
              'hirs')

# arketip -> (nüfustaki payı, özellik ortalamaları, açıklama). Paylar gerçek bir sunucunun kabaca dağılımı: çoğunluk uzaylı kasar,
# az sayıda avcı ve lider; "rahat" oyuncular haftada birkaç saat girip yavaş ilerler.
ARKETIPLER = {
    'kasici':  (0.27, dict(saldirganlik=.35, rekabet=.50, sosyallik=.35, sabir=.85, risk=.30, sadakat=.60, yardimseverlik=.50,
                           konuskanlik=.30, tutumluluk=.60, hirs=.75), 'PvE kasıcı'),
    'avci':    (0.14, dict(saldirganlik=.90, rekabet=.90, sosyallik=.45, sabir=.40, risk=.80, sadakat=.50, yardimseverlik=.30,
                           konuskanlik=.55, tutumluluk=.35, hirs=.70), 'PvP avcısı'),
    'sosyal':  (0.14, dict(saldirganlik=.30, rekabet=.35, sosyallik=.90, sabir=.50, risk=.40, sadakat=.80, yardimseverlik=.80,
                           konuskanlik=.90, tutumluluk=.50, hirs=.40), 'sosyal'),
    'tuccar':  (0.08, dict(saldirganlik=.20, rekabet=.55, sosyallik=.55, sabir=.70, risk=.35, sadakat=.50, yardimseverlik=.40,
                           konuskanlik=.50, tutumluluk=.85, hirs=.60), 'tüccar'),
    'gorevci': (0.16, dict(saldirganlik=.40, rekabet=.45, sosyallik=.40, sabir=.70, risk=.45, sadakat=.55, yardimseverlik=.60,
                           konuskanlik=.35, tutumluluk=.55, hirs=.65), 'görevci'),
    'rahat':   (0.17, dict(saldirganlik=.30, rekabet=.20, sosyallik=.50, sabir=.35, risk=.50, sadakat=.40, yardimseverlik=.55,
                           konuskanlik=.50, tutumluluk=.30, hirs=.25), 'rahat'),
    'lider':   (0.04, dict(saldirganlik=.55, rekabet=.75, sosyallik=.85, sabir=.60, risk=.55, sadakat=.90, yardimseverlik=.70,
                           konuskanlik=.75, tutumluluk=.60, hirs=.85), 'lider'),
}

# arketipin oyuna ayırdığı zaman (çevrimiçi olma eğilimi çarpanı) ve oynarken verimi (dikkat, optimizasyon)
AKTIFLIK = {'kasici': (1.3, 1.15), 'avci': (1.2, 1.0), 'sosyal': (1.0, 0.8), 'tuccar': (0.9, 0.95), 'gorevci': (1.0, 1.0),
            'rahat': (0.55, 0.7), 'lider': (1.3, 1.0)}

# oyun alışkanlığı: saat -> çevrimiçi olma eğilimi (0-1) ve oturum uzunluğu (dakika, en az-en çok)
ALISKANLIKLAR = {
    'aksamci':   (0.40, [0.15] * 7 + [0.2] * 5 + [0.3] * 5 + [0.8] * 5 + [0.5] * 2, (40, 150)),
    'gece_kusu': (0.20, [0.7] * 4 + [0.2] * 8 + [0.25] * 6 + [0.5] * 3 + [0.85] * 3, (60, 240)),
    'gunduzcu':  (0.20, [0.05] * 8 + [0.6] * 10 + [0.4] * 4 + [0.1] * 2, (30, 120)),
    'tutkun':    (0.20, [0.5] * 8 + [0.7] * 16, (120, 420)),
}

DUYGULAR = ('ofke', 'moral', 'sikilma', 'yorgunluk', 'ozguven')
DUYGU_DENGE = dict(ofke=0.0, moral=0.6, sikilma=0.0, yorgunluk=0.0, ozguven=0.5)
DUYGU_SONUM_SN = dict(ofke=600, moral=1800, sikilma=900, yorgunluk=1e9, ozguven=1200)    # dengeye dönüş süresi (yarı ömür)


def sinirla(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def rol(kisilik):
    """Kişilik ve arketipten takım rolü: tank, dps, destek, keşif ya da dengeli."""
    kisilik = kisilik or {}
    o = kisilik.get('ozellik') or {}
    arketip = kisilik.get('arketip')
    risk = float(o.get('risk', 0.5))
    sabir = float(o.get('sabir', 0.5))
    saldirganlik = float(o.get('saldirganlik', 0.5))
    yardim = float(o.get('yardimseverlik', 0.5))
    if arketip in ('lider', 'sosyal') or yardim >= 0.78:
        return 'destek'
    if arketip == 'avci' or saldirganlik >= 0.78:
        return 'dps'
    if arketip == 'kasici' or (sabir >= 0.72 and risk <= 0.42):
        return 'tank'
    if risk >= 0.72 and sabir <= 0.48:
        return 'kesif'
    return 'denge'


# ------------------------------------------------------------------------------------------------------------ adlar
_LEET = {'a': '4', 'e': '3', 'i': '1', 'o': '0', 's': '5', 't': '7'}
_SAYILAR = ('1', '7', '13', '23', '34', '35', '06', '16', '41', '42', '61', '69', '77', '88', '99', '007', '123', '1903', '1905',
            '1907', '1453', '2000', '2003', '2005', '2010', '666', '777', '1923', '01', '07', '27', '33', '38', '55', '21')
AD_DESEN = re.compile(r'^[^\x00-\x20/|<>\\"\x7f\u200b-\u200f\u2028\u2029]{3,20}$')   # gerçek sunucular gibi süslü adlar
#                                                  (ad_uslup.py); boşluk, / | < > \ " ve görünmez karakterler yok


def _leet(s, r, oran):
    return ''.join(_LEET[c.lower()] if c.lower() in _LEET and r.random() < oran else c for c in s)


def ad_uret(r, dil='karisik'):
    """Gerçek bir MMO sunucusundaki kullanıcı adlarına benzeyen ad, dilin kendi adlarıyla (bot/diller/<kod>.json adlar: parçalar
    ve ağırlıklı desenler; 'karisik': dosyaların ağırlığıyla bir dil)."""
    from .dil_verisi import DILLER, karisik_sec
    d = DILLER.get(dil) or DILLER[karisik_sec(r)]
    a = d['adlar']
    desen = r.choices([x[1] for x in a['desenler']], weights=[x[0] for x in a['desenler']])[0]
    s = re.sub(r'\{([^}]+)\}', lambda m: _parca(m.group(1), a['parcalar'], r), desen)
    s = re.sub(r'[^A-Za-z0-9_.\-]', '', s)
    return s[:20] if len(s) >= 3 else s + r.choice(a['parcalar'].get('sayi') or _SAYILAR)


def _parca(ad, parcalar, r):
    """Desen alanı: {liste}, {liste_k} küçük, {a|b} iki listeden, {liste?} yarı yarıya boş, {leet:liste}."""
    leet = ad.startswith('leet:')
    ad = ad[5:] if leet else ad
    bos = ad.endswith('?')
    ad = ad.rstrip('?')
    kucuk = ad.endswith('_k')
    ad = ad[:-2] if kucuk else ad
    if bos and r.random() < 0.5:
        return ''
    s = r.choice([x for a in ad.split('|') for x in parcalar.get(a, ())] or [''])
    if leet:
        s = _leet(s, r, 0.6)
    return s.lower() if kucuk else s


# ------------------------------------------------------------------------------------------------------------ kadro
def _secim(r, tablo):
    """{anahtar: (pay, ...)} ya da {anahtar: pay} -> paya göre bir anahtar."""
    ks = list(tablo)
    ws = [tablo[k][0] if isinstance(tablo[k], tuple) else tablo[k] for k in ks]
    return r.choices(ks, ws)[0]


def kisilik_uret(r, arketip=None, dil='tr'):
    """Bir botun kalıcı kişiliği: arketip, özellikler (ortalama + gürültü), alışkanlık, üslup, sohbet dili."""
    a = arketip or _secim(r, ARKETIPLER)
    ort = ARKETIPLER[a][1]
    ozellik = {k: round(sinirla(r.gauss(ort[k], 0.14), 0.02, 0.98), 2) for k in OZELLIKLER}
    al = _secim(r, ALISKANLIKLAR)
    kon = ozellik['konuskanlik']
    uslup = dict(
        kucuk_harf=round(sinirla(r.gauss(0.6, 0.25)), 2),       # her şeyi küçük harfle yazar
        noktalama=round(sinirla(r.gauss(0.3, 0.25)), 2),        # cümle sonu noktalama
        kisaltma=round(sinirla(r.gauss(0.5, 0.25)), 2),         # "slm", "nbr", "tmm", "gg", "np"
        emoji=round(sinirla(r.gauss(0.3 + kon * 0.2, 0.2)), 2),  # ":D", "xD", "^^"
        hata=round(sinirla(r.gauss(0.08, 0.06), 0, 0.3), 2),    # yazım hatası
        buyuk_harf=round(sinirla(r.gauss(0.05 + ozellik['saldirganlik'] * 0.1, 0.05), 0, 0.4), 2),   # BAĞIRIR
    )
    return dict(arketip=a, ozellik=ozellik, aliskanlik=al, uslup=uslup, dil=dil,
                tepki_sn=round(sinirla(r.gauss(0.9, 0.35), 0.35, 2.0), 2))   # insan tepki süresi (sn): somut savaşta gecikme


def kadro_uret(tohum, adet, firma_dagilimi=(1, 1, 1), dil='karisik', mevcut=(), ad_dili=None, ozel=(), havuz=None):
    """Paketin kadrosu: [{no, ad, firma, kisilik}]. firma_dagilimi: (MMO, EIC, VRU) ağırlıkları. mevcut: kullanılmış adlar
    (büyük/küçük harf ayrımsız; oyuncunun ve başka botların adlarıyla çakışmasın). Aynı tohum ve girdi aynı kadroyu verir.
    ad_dili: adların dili ('karisik': dosyaların ağırlığıyla); dil: sohbet dili ('karisik': her bot adının dilinde konuşur).
    ozel: kullanıcının kendi botları [{ad, firma?, arketip?, dil?}] (oyuncu isteği 2026-10-30): kadronun başında, verilmeyen
    alanları ötekiler gibi üretilir; firması verilen, dağılımdaki o firmanın bir yerini alır.
    havuz: gerçek oyuncu adları {dil: [ad]} (bot/dostats.py): adlar önce oradan, bitince üretilir."""
    from .dil_verisi import DILLER, karisik_sec
    ad_dili = ad_dili or dil
    r = random.Random(tohum)
    kullanilan = {str(a).lower() for a in mevcut}
    ozel = [o for o in ozel if str(o['ad']).lower() not in kullanilan][:adet]
    toplam = sum(firma_dagilimi) or 1
    # firmaları paylara göre tam sayıya böl (en büyük kalan), sonra karıştır: dağılım küçük kadroda da tutar
    paylar = [adet * f / toplam for f in firma_dagilimi]
    sayi = [int(p) for p in paylar]
    for i in sorted(range(3), key=lambda i: paylar[i] - sayi[i], reverse=True)[:adet - sum(sayi)]:
        sayi[i] += 1
    firmalar = [f + 1 for f in range(3) for _ in range(sayi[f])]
    r.shuffle(firmalar)
    for o in ozel:                                   # firması verilen özel bot o firmanın bir yerini alır
        if o.get('firma') in firmalar:
            firmalar.remove(o['firma'])
    kalan = iter(firmalar)
    out = []
    for no in range(1, adet + 1):
        o = ozel[no - 1] if no <= len(ozel) else {}
        firma = o.get('firma') or next(kalan, None) or r.randint(1, 3)
        adl = ad_dili if ad_dili in DILLER else karisik_sec(r)
        sohbet = o.get('dil') or (dil if dil in DILLER else adl)          # karışık: adı Almanca olan Almanca konuşur
        gercek = [x for x in (havuz or {}).get(adl) or [y for v in (havuz or {}).values() for y in v]
                  if x.lower() not in kullanilan and AU.harf_tutarli(x)]
        if o:
            ad = str(o['ad'])
        elif gercek:
            ad = r.choice(gercek)
        else:
            for _ in range(50):
                ad = AU.susle(ad_uret(r, adl), r, adl)
                if ad.lower() not in kullanilan and AD_DESEN.match(ad) and AU.harf_tutarli(ad):
                    break
            else:
                ad = 'Pilot%d' % r.randint(1000, 99999)
        kullanilan.add(ad.lower())
        x = dict(no=no, ad=ad, firma=firma, kisilik=dict(kisilik_uret(r, arketip=o.get('arketip'), dil=sohbet), ad_dili=o.get('dil') or adl))
        if o:
            x['ozel'] = True                             # kullanıcının botu (panel: Kadro'da işaretli)
        out.append(x)
    return out


# ------------------------------------------------------------------------------------------------------------ ruh hâli
class RuhHali:
    """Dinamik duygular (0-1): olaylar iter, zamanla dengeye döner (üstel sönüm). Kalıcı kayıtta sözlük olarak durur."""
    __slots__ = ('d', 't')

    def __init__(self, d=None, t=None):
        self.d = dict(DUYGU_DENGE, **(d or {}))
        self.t = t or time.time()

    def guncelle(self, now=None):
        now = now or time.time()
        dt = max(0.0, now - self.t)
        self.t = now
        if dt <= 0:
            return
        for k, denge in DUYGU_DENGE.items():
            f = 0.5 ** (dt / DUYGU_SONUM_SN[k])
            self.d[k] = denge + (self.d[k] - denge) * f

    def it(self, **degisim):
        for k, v in degisim.items():
            self.d[k] = sinirla(self.d[k] + v)

    def __getitem__(self, k):
        return self.d[k]

    def kayit(self):
        return {k: round(v, 3) for k, v in self.d.items()}


# ------------------------------------------------------------------------------------------------------------ hafıza
OLAYLAR = {          # olay -> ilişkiye etkisi
    'oldurdu_beni': -0.35, 'oldurdum': -0.05, 'yardim_etti': 0.25, 'yardim_ettim': 0.1, 'sohbet': 0.03, 'hakaret': -0.2,
    'ovgu': 0.12, 'grup': 0.08, 'klan': 0.1, 'arkadas': 0.2, 'reddetti': -0.08, 'birlikte_avlandik': 0.05,
    'dedikodu_iyi': 0.06, 'dedikodu_kotu': -0.08,          # başka bottan duyulan (ani.duydu)
}


class Hafiza:
    """Kişilere karşı ilişki (-1 kin .. 1 dostluk) ve olay sayıları. Kayıtta {ad_kucuk: {d, n: {olay: sayı}, s: son an}}.
    Uzun süre görülmeyen ilişki yavaşça sıfıra döner (unutma); en çok HAFIZA_EN_COK kişi tutulur (en eskisi düşer)."""
    EN_COK = 60
    UNUTMA_SN = 6 * 3600

    def __init__(self, d=None):
        self.d = d if d is not None else {}
        self.dinle = None                # (ad, tür, an) -> olay kancası: güçlü sağlayıcıda anı defteri (ani.olaydan; yönetici bağlar)

    def olay(self, ad, tur, now=None, kat=1.0):
        if not str(ad or '').strip():
            return 0.0                                     # kimliği bilinmeyen (adsız) biri: hatırlanacak kimse yok
        now = now or time.time()
        k = str(ad).lower()
        e = self.d.setdefault(k, {'d': 0.0, 'n': {}, 's': now, 'ad': str(ad)})
        self._unut(e, now)
        e['d'] = round(sinirla(e['d'] + OLAYLAR.get(tur, 0) * kat, -1, 1), 3)
        e['n'][tur] = e['n'].get(tur, 0) + 1
        e['s'] = now
        if len(self.d) > self.EN_COK:
            del self.d[min(self.d, key=lambda x: self.d[x]['s'])]
        if self.dinle is not None:
            self.dinle(ad, tur, now)
        return e['d']

    def _unut(self, e, now):
        dt = now - e.get('s', now)
        if dt > 0:
            e['d'] = e['d'] * 0.5 ** (dt / self.UNUTMA_SN)

    def iliski(self, ad, now=None):
        e = self.d.get(str(ad).lower())
        if not e:
            return 0.0
        dt = (now or time.time()) - e.get('s', 0)
        return e['d'] * 0.5 ** (max(0, dt) / self.UNUTMA_SN)

    def sayi(self, ad, tur):
        e = self.d.get(str(ad).lower())
        return e['n'].get(tur, 0) if e else 0

    def kinliler(self, esik=-0.3, now=None):
        return [e['ad'] for e in self.d.values() if self.iliski(e['ad'], now) <= esik]

    def dostlar(self, esik=0.3, now=None):
        return [e['ad'] for e in self.d.values() if self.iliski(e['ad'], now) >= esik]


def dilim(kisilik):
    """Botun saat dilimi farkı (saat): çoğu sunucunun saatinde, bir kısmı komşu ülkelerde, azı uzakta. Kişilikte yoksa adından
    (eski kayıtlar için kalıcı ve belirlenimci). Herkes aynı saatte yaşasaydı gece sunucu bomboş, akşam tıklım tıklım olurdu."""
    d = kisilik.get('dilim')
    if d is None:
        import zlib
        r = zlib.crc32(str(kisilik.get('_ad') or kisilik.get('arketip')).encode()) % 100
        d = 0 if r < 55 else -1 if r < 70 else 1 if r < 82 else -2 if r < 88 else 2 if r < 93 else -7 if r < 97 else 7
        kisilik['dilim'] = d
    return d


def zevk(kisilik):
    """Botun kalıcı gemi zevki (gemi ailesi): herkes aynı gemiye yakınsamasın. Kişilikte yoksa adından (eski kayıtlar)."""
    z = kisilik.get('zevk')
    if z is None:
        import zlib
        aileler = ('goliath', 'vengeance', 'aegis', 'citadel', 'spearhead', 'leonov', 'nostromo', 'piranha', 'bigboy', 'solace')
        z = kisilik['zevk'] = aileler[zlib.crc32(('z' + str(kisilik.get('_ad') or kisilik.get('arketip'))).encode()) % len(aileler)]
    return z


def cevrimici_egilim(kisilik, saat):
    """Alışkanlığa ve arketipe göre bu saatte (0-23; botun kendi saat diliminde) çevrimiçi olma eğilimi."""
    return ALISKANLIKLAR[kisilik['aliskanlik']][1][int(saat + dilim(kisilik)) % 24] * AKTIFLIK[kisilik['arketip']][0]


def oturum_dk(kisilik, r=random):
    a, b = ALISKANLIKLAR[kisilik['aliskanlik']][2]
    return r.uniform(a, b)


def softmax_sec(puanlar, sicaklik, r=random):
    """[(anahtar, puan)] -> sıcaklığa göre seçilen anahtar (sıcaklık küçükse hep en yüksek)."""
    if not puanlar:
        return None
    t = max(0.02, sicaklik)
    m = max(p for _, p in puanlar)
    ws = [math.exp((p - m) / t) for _, p in puanlar]
    return r.choices([k for k, _ in puanlar], ws)[0]
