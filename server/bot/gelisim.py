"""Botların deneyime bağlı, kalıcı ve ayrı ayrı gelişen becerileri.

XP durum.json içindeki bot kaydında tutulur; eski kayıtlar ilk kullanımda güvenli
varsayılanlarla yükseltilir. Seviye 1-10 arasındadır.
"""
import math

ALANLAR = ("savas", "ekonomi", "hayatta_kalma")
AZAMI_XP = 1000000.0
AZAMI_SEVIYE = 10


def xp(kayit, alan):
    if alan not in ALANLAR:
        return 0.0
    beceriler = kayit.setdefault("beceri", {})
    if not isinstance(beceriler, dict):
        beceriler = kayit["beceri"] = {}
    try:
        return max(0.0, min(AZAMI_XP, float(beceriler.get(alan, 0.0))))
    except (TypeError, ValueError):
        return 0.0


def seviye(kayit, alan):
    return min(AZAMI_SEVIYE, 1 + int(math.sqrt(xp(kayit, alan) / 100.0)))


def oran(kayit, alan):
    """Znormalizowany postęp poziomu 0..1, używany przez zachowania AI."""
    return (seviye(kayit, alan) - 1) / float(AZAMI_SEVIYE - 1)


def kazan(kayit, alan, miktar):
    """Dodaje dodatnie XP i zwraca nowy poziom."""
    if alan not in ALANLAR:
        return 1
    try:
        miktar = float(miktar)
    except (TypeError, ValueError):
        return seviye(kayit, alan)
    if miktar <= 0:
        return seviye(kayit, alan)
    beceriler = kayit.setdefault("beceri", {})
    if not isinstance(beceriler, dict):
        beceriler = kayit["beceri"] = {}
    beceriler[alan] = round(min(AZAMI_XP, xp(kayit, alan) + miktar), 3)
    return seviye(kayit, alan)


def ozet(kayit):
    return {
        alan: {"xp": round(xp(kayit, alan), 1), "seviye": seviye(kayit, alan)}
        for alan in ALANLAR
    }
