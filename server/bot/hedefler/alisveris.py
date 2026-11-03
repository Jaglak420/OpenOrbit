"""Alışveriş: parası yeten en verimli yükseltmeyi almak ya da büyük bir hedef için biriktirmek.

Adaylar katalogdan (lazer, kalkan/hız jeneratörü, dron, gemi): her biri için yeni donanımın güç artışı / fiyat (kredi karşılığı,
1 U = kur kredisi). Tutumlu bot biriktirdiği büyük hedef (Goliath gibi) varken küçük alımlara para harcamaz; dürtüsel bot ara
sıra en iyisi olmayan bir şey de alır (insan hatası).
"""
from ..beyin import Hedef, hedef
from .. import katalog as K
from .. import kisilik as KS

KUR = 100                 # 1 uridyum kaç kredi (fiyatlar.json kur)
SEFER_ALIM = 15           # bir alışveriş seferinde en çok bu kadar eşya
try:
    import json, os
    KUR = json.load(open(os.path.join(K.HERE, 'data', 'fiyatlar.json'), encoding='utf8')).get('kur', KUR)
except (OSError, ValueError):
    pass


def adaylar(bot):
    """[(güç artışı, para, fiyat, loot[, değiştirilecek_dron])]: yükseltme adayları."""
    if bot._adaylar is None:
        bot._adaylar = _adaylar(bot)
    return bot._adaylar


def _adaylar(bot):
    e = bot.k['ekip']
    kp = bot.kalkan_payi()
    td = K.degerler(e, kp)
    taban = td['guc']
    yuva = K.donat(e, kp)
    out = []
    mevcut_dronlar = e.get('dron', {})
    dron_sayisi = sum(mevcut_dronlar.values())
    dron_siniri = int(K.ESYA.get('dron_azami', 8))

    def dene(loot, sahip=0, zorla=False, replace=None):
        f = K.fiyat(loot, sahip)
        if not f or f[1] <= 0:
            return
        y = {a: dict(v) if isinstance(v, dict) else v for a, v in e.items()}
        if loot.startswith('ship_'):
            y['gemi'] = loot
        elif loot in K.ESYA['dronlar']:
            if replace:
                old = K.ESYA['dronlar'].get(replace)
                new = K.ESYA['dronlar'][loot]
                if not y.get('dron', {}).get(replace, 0) or not old:
                    return
                # Ne zamandır sahip olduğu değil, oyun içindeki dron seviyesi belirleyici:
                # daha düşük tür/yuva sayısına geçiş yapma.
                if new.get('tur', 0) <= old.get('tur', 0) and new.get('yuva', 1) <= old.get('yuva', 1):
                    return
                y['dron'][replace] -= 1
                if not y['dron'][replace]:
                    del y['dron'][replace]
            elif dron_sayisi >= dron_siniri:
                return
            y.setdefault('dron', {})[loot] = y.get('dron', {}).get(loot, 0) + 1
        else:
            grup = 'lazer' if loot in K.ESYA['lazerler'] else 'kalkan' if loot in K.ESYA['kalkan_jeneratorleri'] else \
                'hiz' if loot in K.ESYA['hiz_jeneratorleri'] else 'dron'
            y[grup][loot] = y[grup].get(loot, 0) + 1

        yd = K.degerler(y, kp)
        artis = yd['guc'] - taban + 0.02 * (yd['hiz'] - td['hiz']) * (0.5 + bot.o('risk'))
        if loot.startswith('ship_'):
            artis *= 1.35 if KS.zevk(bot.k['kisilik']) in loot else 0.9

        if loot in K.ESYA['dronlar']:
            # Iris/Apis/Zeus can open extra laser sockets. If the bot does not yet own enough
            # lasers to fill them, value one newly opened socket as a future upgrade.
            # The weapon itself stays a separate purchase; no free laser is added to the real loadout.
            new_slots = K.donat(y, kp)['lazer_yuva']
            extra_slots = max(0, new_slots - yuva['lazer_yuva'])
            missing = max(0, new_slots - sum(y.get('lazer', {}).values()))
            future_slots = min(extra_slots, missing)
            if future_slots:
                best_laser = max((l for l, n in y.get('lazer', {}).items() if n and l in K.ESYA['lazerler']),
                                 key=lambda l: K.ESYA['lazerler'][l]['hasar'], default=None)
                if best_laser:
                    future = {a: dict(v) if isinstance(v, dict) else v for a, v in y.items()}
                    future['lazer'][best_laser] = future['lazer'].get(best_laser, 0) + future_slots
                    artis += max(0.0, K.degerler(future, kp)['guc'] - yd['guc']) * 0.55

        if artis > 1e-6 or zorla:
            aday = (max(artis, 1e-3), f[0], f[1], loot)
            if replace:
                aday += (replace,)
            out.append(aday)

    # Lazer: boş yuva varsa ya da en zayıfından iyiyse.
    lz = K.lazerler()
    for loot in sorted(lz, key=lz.get):
        if len(yuva['lazer']) < yuva['lazer_yuva'] or lz[loot] > min(yuva['lazer'] or [0]):
            dene(loot)
    for loot in K.kalkanlar():
        dene(loot)
    for loot in K.hizlar():
        dene(loot)

    # Dronlar: önce boş yuvaya al; sekiz dron dolduğunda düşük seviyeliyi üst modelle değiştir.
    for loot, d in K.ESYA['dronlar'].items():
        n = mevcut_dronlar.get(loot, 0)
        if not K.fiyat(loot, n):
            continue
        if dron_sayisi < dron_siniri:
            dene(loot, n)
        else:
            for replace, adet in mevcut_dronlar.items():
                old = K.ESYA['dronlar'].get(replace)
                if adet and old and (d.get('tur', 0) > old.get('tur', 0) or d.get('yuva', 1) > old.get('yuva', 1)):
                    dene(loot, n, replace=replace)

    simdiki = K.ESYA['gemiler'].get(e['gemi'], {})
    for loot, g in K.gemiler().items():
        if loot != e['gemi'] and g['hp'] + 20000 * (g['laser'] + g['generators']) > simdiki.get('hp', 0) + 20000 * (
                simdiki.get('laser', 0) + simdiki.get('generators', 0)):
            dene(loot)
    istenen = bot.k.get('birikim')
    if istenen and not any(c[3] == istenen for c in out) and (istenen.startswith('ship_') or any(
            istenen in K.ESYA[g] for g in ('lazerler', 'kalkan_jeneratorleri', 'hiz_jeneratorleri', 'dronlar'))):
        dene(istenen, e.get('dron', {}).get(istenen, 0), zorla=True)
    from .. import ekstra as EK
    out += EK.adaylar(bot)
    from .. import teknoloji as TK
    out += TK.adaylar(bot)
    return out


def satin_al(bot, aday):
    """Alışveriş adayını uygula; varsa zayıf dronu önce çıkarıp yenisini takar."""
    if not aday or len(aday) < 4:
        return False
    _, para, fiyat, loot = aday[:4]
    replace = aday[4] if len(aday) > 4 else None
    dronlar = bot.k['ekip'].setdefault('dron', {})
    if replace and not dronlar.get(replace, 0):
        bot._adaylar = None
        return False
    if not bot.ode(para, fiyat):
        return False
    if replace:
        dronlar[replace] -= 1
        if not dronlar[replace]:
            del dronlar[replace]
    if bot.ekle(loot):
        bot.beceri_kazan('ekonomi', 0.5)
        return True
    if replace:
        dronlar[replace] = dronlar.get(replace, 0) + 1
        bot.ekip_degisti()
    wallet = 'kredi' if para == 'C' else 'uridyum'
    bot.k[wallet] += int(fiyat)
    bot.ist('harcama_' + wallet, -int(fiyat))
    bot._adaylar = None
    return False


def gelir(bot):
    """Saatlik tahmini kazanç {'C': kredi, 'U': uridyum}: bulunduğu haritada kasarsa (katalog.harita_degerlendir)."""
    d = bot.deger()
    try:
        r = K.harita_degerlendir(int(bot.harita), d['dps'], d['ehp'], 0.5)
    except (KeyError, ValueError, TypeError):
        return {'C': 0.0, 'U': 0.0}
    return {'C': r['saat_kredi'], 'U': r['saat_uridyum'] + 25}           # +25: bonus kutuları, görev ödülleri


def aday(bot):
    """-> (şimdi alınacak (artis, para, fiyat, loot) ya da None, biriktirilen hedef ya da None).

    Gerçek oyuncu gibi hedefli: yakında (tutumluluğa göre 1-2,5 saatlik kazançla) ulaşabileceği en verimli yükseltme hedeftir;
    parası yetiyorsa onu alır. Yetmiyorsa ancak hedef kadar verimli (en az %70) küçük bir alım yapar, yoksa biriktirir. Önceden
    yeten en verimli şeyi hemen alıyordu: SLL-01'e (50.000 C) para biriktirirken sırayla 2.000-8.000 C'lik hız jeneratörleri
    ve MP-1 alıp tek yuvalı Phoenix'te birbirinin yerine koyuyordu (paket analizi 2026-10-29)."""
    tum = adaylar(bot)
    if not tum:
        return None, None
    m = bot.oa.carpan('magaza_fiyat')                  # profilin mağaza fiyatı çarpanı
    if m != 1.0:
        tum = [(c[0], c[1], c[2] * m) + tuple(c[3:]) for c in tum]
    para = {'C': bot.k['kredi'], 'U': bot.k['uridyum']}
    para['C'] = max(0, para['C'] - bot.klan_birikimi())                     # klan kuracak: kuruluş bedelini biriktirir
    ceq = lambda c: c[2] * (KUR if c[1] == 'U' else 1)
    # verim: artış / (fiyat + servetin çeyreği): az parada kredi başına verim, çok parada artışın büyüklüğü öne geçer (zengin bot
    # 80M kredi ve 2M uridyumla +3,4 güçlü Apis yerine 2.000 C'lik +0,04'lük hız jeneratörünü seçiyordu; Laya denemesi 2026-10-31)
    servet = para['C'] + para['U'] * KUR
    verim = lambda c: c[0] / max(1.0, ceq(c) + 0.25 * servet) * 1e5
    t = bot.o('tutumluluk')
    ekonomi = bot.beceri('ekonomi')
    hedefi = next((c for c in tum if c[3] == bot.k.get('birikim')), None)
    if hedefi is not None:                       # kendi seçtiği biriktirme hedefi (ajanın biriktir aracı): yalnız onu alır
        if para[hedefi[1]] >= hedefi[2]:
            return hedefi, hedefi
        # hedefin birikimini geciktirmeyen alımlar serbest (başka para birimi ya da hedefin üstünde kalan para): önceden yalnız
        # hedefe bakıyordu, 80.000 U'luk gemiye biriktiren bot 66M kredisiyle kalkan/motor almadan duruyordu (oyuncu bildirimi 2026-11-01)
        serbest = [c for c in tum if c[1] != hedefi[1] and para[c[1]] >= c[2] * (1 + 0.3 * bot.o('tutumluluk'))
                   or c[1] == hedefi[1] and para[c[1]] - c[2] >= hedefi[2]]
        return max(serbest, key=lambda c: c[0], default=None), hedefi
    yetisir = [c for c in tum if para[c[1]] >= c[2] * (1 + 0.3 * t)]        # tutumlu bot biraz yedek bırakır
    g = gelir(bot)
    ufuk = 1.0 + 1.5 * t + 0.5 * ekonomi
    ulasir = [c for c in tum if c[2] * (1 + 0.3 * t) <= para[c[1]] + g[c[1]] * ufuk]
    hedef_c = max(ulasir, key=verim, default=None)
    # uzak biriktirme hedefi (panel, sohbet): parası yetmeyen en büyük artış
    kalan = [c for c in tum if c not in yetisir]
    birikim = max(kalan, key=lambda c: c[0] * (0.5 + t) - ceq(c) / 5e6, default=None)
    if hedef_c is not None and hedef_c not in yetisir:
        birikim = hedef_c
    if not yetisir:
        return None, birikim
    if bot.r.random() < 0.05 * (1 - t):                                     # dürtüsel alım (insan hatası)
        return bot.r.choice(yetisir), birikim
    if hedef_c is None or hedef_c in yetisir:
        return max(yetisir, key=verim), birikim
    # Doświadczony ekonomicznie bot cierpliwiej oszczędza na wyraźnie lepszą konfigurację.
    prog = 0.7 + 0.12 * ekonomi
    iyi = [c for c in yetisir if verim(c) >= prog * verim(hedef_c)]
    return (max(iyi, key=verim) if iyi else None), birikim


@hedef
class Alisveris(Hedef):
    ad = 'alisveris'
    izin = 'magaza'
    en_az_sn = 5

    def uygun(self, bot, b):
        return b.alisveris[0] is not None

    def puan(self, bot, b):
        artis = b.alisveris[0][0]
        return min(1.6, 0.45 + artis / max(1.0, bot.deger()['guc']) * 3 + 0.2 * bot.o('hirs'))

    def basla(self, bot, b):
        # bir alışveriş seferinde parası yettikçe sırayla alır (en çok SEFER_ALIM): önceden sefer başına tek eşya alıyordu, 10M
        # kredili bot bir saatte 8 eşya alıp paranın %80'ini harcamadan duruyordu (oyuncu bildirimi 2026-10-31)
        c = b.alisveris[0]
        for _ in range(SEFER_ALIM):
            artis, para, fiyat, loot = c[:4]
            replace = c[4] if len(c) > 4 else None
            if not satin_al(bot, c):
                break
            bot.ist('alim')
            bot.ruh.it(moral=0.12 + min(0.3, artis / max(1.0, bot.deger()['guc'])))
            bot.olay('alim', esya=loot, eski_esya=replace, fiyat=fiyat, para=para)
            if loot.startswith('ship_'):
                bot.olay('yeni_gemi', esya=loot)
            if bot.k.get('birikim') == loot:
                bot.k['birikim'] = None                  # biriktirdiği şeye kavuştu (ajanın biriktir aracı)
            bot._adaylar = None                          # (gemi değişmese de kalan yuvalar ve para değişti)
            c = aday(bot)[0]
            if c is None:
                break
        bot.plan['bitti'] = True

    def bitti(self, bot, b):
        return bot.plan.get('bitti', False)
