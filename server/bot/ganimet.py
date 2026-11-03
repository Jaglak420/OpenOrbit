"""Ganimet: anahtarlı kutular, anahtarlar, boosterlar, uzaylıların ek ganimeti ve Assembly (oyuncunun kuralları: ganimet.py,
dunya.extra_loot, assembly.py, booster.py).

  kutu      haritadaki anahtarlı kutuyu türünün anahtarıyla açar; yeşil kutunun anahtarı yoksa uridyumla alır (oyuncudaki
            autoBuyGreenBootyKeys) ama yalnız kutunun beklenen değeri anahtarın fiyatından yüksekse ve kişiliğe göre (tutumlu bot
            uridyumunu harcamaz); ödül kutunun tablosundan ağırlıkla
  ek        uzaylının ek ganimeti (npc.json ek_odul: Scrapium, Mucosum, günlük dosyası …) stoğa
  assembly  o an görünür tariflerden (tek oyunculu: kayıttaki hepsi; etkinlik parası isteyenler etkinlik sürerken ya da elde para
            varken) malzemesi elde olan ve sonucu harcadığından değerli olanı üretir: anahtar, teknoloji eşyası, cephane, ekipman
  booster   10 saat (booster verisi); EP, onur, kaynak, hasar, can, kalkan payları, türün tavanıyla
Değerler kredi karşılığı (1 U = 100 C): para yüzünden, cephane ve eşya mağaza fiyatından, anahtar kutusunun beklenen değerinden.
"""
import json, os, random

from . import katalog as K

KUR = 100
import ganimet as GN                                   # noqa: E402  (oyunun ganimet modülü: kutular, haritalar, takvim)

TARIF = json.load(open(os.path.join(K.HERE, 'data', 'tarifler.json'), encoding='utf8'))['tarifler']
BOOSTER = K.ESYA['boosterlar']
CEVHER_LOOT = {v: int(k) for k, v in K.ESYA['cevherler']['turler'].items()}     # resource_ore_* -> kargo cevheri
PARA = {'currency_credits': 'kredi', 'currency_uridium': 'uridyum', 'currency_experience': 'ep', 'currency_honour': 'onur'}
_ev = {}


def stok(bot):
    from . import silah as SL
    return SL.stok(bot)


# ------------------------------------------------------------------------------------------------------------ değer
def deger(loot, n=1, derinlik=0):
    """Eşyanın bota yaklaşık değeri (kredi)."""
    if loot in PARA:
        return n * {'kredi': 1, 'uridyum': KUR, 'ep': 0.3, 'onur': 3}[PARA[loot]]
    if loot in CEVHER_LOOT:
        return n * K.cevher_fiyatlari(0).get(CEVHER_LOOT[loot], 0)
    if loot.startswith('resource_booty-key') and derinlik < 1:
        kind = GN.KEYS.get(loot)
        return n * kutu_degeri(kind, derinlik + 1) if kind else 0
    if loot.startswith('booster_'):
        return n * 3000
    f = K.fiyat(loot)
    if f and f[1] > 0:
        v = n * f[1] * (KUR if f[0] == 'U' else 1)
        return v * 0.3 if loot.startswith(('ship_', 'equipment_', 'drone_')) else v     # ganimetten gelen eşya: işine yaramazsa satış değeri
    return 0


def kutu_degeri(kind, derinlik=0):
    """Kutunun beklenen değeri (ödül tablosunun ağırlıklı ortalaması)."""
    if kind in _ev:
        return _ev[kind]
    rows = GN.BOXES[kind].get('odul') or []
    toplam = sum(r[2] for r in rows) or 1
    v = 0.0
    for loot, n, w in rows:
        if loot == GN.PAKET:
            v += w * sum(deger(l, c, derinlik) for l, c in n)
        else:
            v += w * deger(loot, n, derinlik)
    _ev[kind] = v / toplam
    return _ev[kind]


# ------------------------------------------------------------------------------------------------------------ ödül
def ver(bot, loot, n):
    """Ödülü bota: para kazanç, cevher kargoya, booster etkin, eşya ve cephane bot.ekle, gerisi (anahtar, kaynak) stoğa."""
    if loot in PARA:
        bot.odul('kutu', **{PARA[loot]: n})
    elif loot in CEVHER_LOOT:
        bot.kargo_ekle({CEVHER_LOOT[loot]: n})
    elif loot.startswith('booster_'):
        booster(bot, loot)
    elif loot.startswith(('ship_', 'equipment_', 'ammunition_', 'tech_', 'drone_')) and bot.ekle(loot, n):
        pass
    else:
        s = stok(bot)
        s[loot] = s.get(loot, 0) + int(n)


def booster(bot, loot):
    """Booster 10 saat: k['booster'] {tür: [değer, bitiş]} (aynı türden ikincisi süreyi uzatır)."""
    b = bot.k.setdefault('booster', {})
    now = bot.saat()
    for tur, v in (BOOSTER['turler'].get(loot) or {}).items():
        e = b.get(tur)
        bitis = max(now, e[1] if e else now) + BOOSTER['sure_sn']
        b[tur] = [min(BOOSTER['tavan'].get(tur, v), v), bitis]
    bot.ekip_degisti()


def booster_payi(bot, tur):
    e = (bot.k.get('booster') or {}).get(tur)
    return e[0] / 100.0 if e and e[1] > bot.saat() else 0.0


def ek_ganimet(bot, tip, n=1):
    """Uzaylının ek ganimeti (toplanabilir kaynaklar, günlük dosyası) stoğa."""
    import dunya as DN
    for loot, spec in ((K.NPC['tipler'].get(str(tip)) or {}).get('ek_odul') or {}).items():
        c = sum(DN.extra_count(spec) for _ in range(min(int(n), 20))) * (n / min(int(n), 20) if n > 20 else 1)
        if c > 0:
            ver(bot, loot, int(c))


# ------------------------------------------------------------------------------------------------------------ kutular
def anahtar(kind):
    return GN.BOXES[kind]['anahtar']


def acar_mi(bot, kind):
    """Kutuyu açabilir mi / açmaya değer mi: anahtarı varsa evet; yeşil kutu için anahtar alabilir (uridyumu ve kişiliği izin
    veriyorsa ve kutu fiyatından değerliyse). Anahtar alınırsa stoğa eklenir."""
    if not bot.izin.get('ganimet', True):
        return False
    key = anahtar(kind)
    if stok(bot).get(key, 0) > 0:
        return True
    f = K.fiyat(key)
    if key != GN.GREEN_KEY or not f or not bot.izin.get('magaza', True):
        return False
    fiyat = f[1] * bot.oa.carpan('magaza_fiyat')
    t = bot.o('tutumluluk')
    if kutu_degeri(kind) < fiyat * KUR * (0.8 + 0.8 * t) or bot.k['uridyum'] < fiyat * (2 + 4 * t):
        return False
    if not bot.ode('U', fiyat):
        return False
    stok(bot)[key] = stok(bot).get(key, 0) + 1
    bot.ist('anahtar_alim')
    return True


def ac(bot, kind, rng=random):
    """Anahtar harcanır, tablodan ağırlıkla bir ödül -> [(loot, adet)]."""
    s = stok(bot)
    key = anahtar(kind)
    if s.get(key, 0) <= 0:
        return []
    s[key] -= 1
    if not s[key]:
        del s[key]
    rows = GN.BOXES[kind].get('odul') or []
    if not rows:
        return []
    r = rng.choices(rows, weights=[x[2] for x in rows])[0]
    out = list(r[1]) if r[0] == GN.PAKET else [(r[0], r[1])]
    for loot, n in out:
        ver(bot, loot, n)
    bot.ist('kutu_acti')
    bot.olay('kutu_acti', kutu=GN.BOXES[kind]['ad'])
    return out


_etkin = {}


def etkin_kutular(ad):
    """Haritada şimdi doğan anahtarlı kutular [(tür, adet)]: takvim hesabı ağır, dakikada bir (harita başına)."""
    import time
    t = time.time()
    e = _etkin.get(ad)
    if e is None or t - e[0] > 60:
        e = _etkin[ad] = (t, [(k, n) for k, n in GN.spawns(ad) if GN.active(k)])
    return e[1]


def soyut(bot, dt, y):
    """Soyutta haritanın anahtarlı kutularına rastlama: kutu sayısı / yeniden doğma, haritadaki botlarla paylaşılır."""
    import harita as H
    if not bot.izin.get('ganimet', True):
        return
    kalabalik = len(y.haritada.get(bot.harita, ())) if y is not None else 1
    for kind, adet in etkin_kutular(H.name(bot.harita)):
        oran = adet * dt / max(60.0, sum(GN.BOXES[kind]['yeniden_sn']) / 2) / max(1.0, 0.3 * kalabalik)
        if bot.r.random() < oran and acar_mi(bot, kind):
            ac(bot, kind, bot.r)


# ------------------------------------------------------------------------------------------------------------ assembly
def _yeter(bot, parcalar):
    s = stok(bot)
    for p, n in parcalar.items():
        if p in PARA:
            if bot.k[PARA[p]] < n:
                return False
        elif p.startswith('equipment_'):
            if not any(p in v for v in bot.k['ekip'].values() if isinstance(v, dict)) and bot.k['ekip'].get('fircatici') != p:
                return False
        elif s.get(p, 0) < n:
            return False
    return True


def _harca(bot, parcalar):
    s = stok(bot)
    for p, n in parcalar.items():
        if p in PARA:
            bot.k[PARA[p]] -= n
        elif p.startswith('equipment_'):
            if bot.k['ekip'].get('fircatici') == p:
                bot.k['ekip']['fircatici'] = None
        else:
            s[p] -= n
            if not s[p]:
                del s[p]


MALZEME = [(k, tuple(p for p in r['parcalar'] if p not in PARA)) for k, r in TARIF.items()
           if any(p not in PARA for p in r['parcalar']) and 'test' not in k]      # test tarifleri oyuncuya da kapalı      # para tarifleri teknoloji.uret'te


def assembly(bot):
    """Malzemesi elde olan tariflerden en değerlisini üretir (sonucu harcadığından değerliyse; para harcayanlar teknoloji.uret'te).
    Kullanım sınırları: USABLE_ONCE bir kez. -> üretilen sonuç ya da None."""
    if not bot.izin.get('assembly', True):
        return None
    now = bot.saat()
    if now < bot.__dict__.get('_asm_t', 0):
        return None
    bot._asm_t = now + 600                               # oyuncu Assembly'ye arada bakar: 10 dakikada bir
    s = stok(bot)
    if not any(k.startswith('resource_') for k in s):
        return None
    yapilan = bot.k.setdefault('assembly', {})
    en, ed = None, 0.0
    for key, gerek in MALZEME:
        if not all(p in s or p.startswith('equipment_') for p in gerek):
            continue
        r = TARIF[key]
        if r['kullanim'] == 'USABLE_ONCE' and yapilan.get(key):
            continue
        if not _yeter(bot, r['parcalar']):
            continue
        kazanc = sum(deger(l, n) for l, n in r['sonuc'].items())
        maliyet = sum(deger(p, n) for p, n in r['parcalar'].items() if not p.startswith('resource_collectable'))
        if kazanc - maliyet > ed:
            en, ed = key, kazanc - maliyet
    if en is None:
        return None
    r = TARIF[en]
    _harca(bot, r['parcalar'])
    for loot, n in r['sonuc'].items():
        ver(bot, loot, n)
    yapilan[en] = yapilan.get(en, 0) + 1
    bot.ist('assembly')
    bot.beceri_kazan('ekonomi', 2.0)
    return en
