"""Panelowy edytor nagród etapowych Galaxy Trek."""
import json, os, re, tempfile

class GalaxyTrekPanelHatasi(ValueError):
    pass

def _path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ek_etkinlikler.json')

def _read():
    p = _path()
    try:
        with open(p, encoding='utf8') as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise GalaxyTrekPanelHatasi('Nie można odczytać konfiguracji Galaxy Trek: %s' % e)

def _write(data):
    p = _path()
    fd, tmp = tempfile.mkstemp(prefix='.ek-etkinlikler-', suffix='.tmp', dir=os.path.dirname(p))
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write('\\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def get():
    d = _read().get('galaxy_trek') or {}
    return {'basamaklar': [
        {'kimlik': int(t['kimlik']), 'gereken': int(t['gereken']),
         'esyalar': [{'lootId': str(l), 'amount': int(n)} for l, n in t.get('esyalar', [])],
         'unvan': t.get('unvan')}
        for t in d.get('basamaklar', [])
    ]}

def save(body):
    import surecler
    if surecler.YON.running():
        raise GalaxyTrekPanelHatasi('Najpierw zatrzymaj serwer gry. Zmiany nagród zapisuje się przy wyłączonym serwerze.')
    rows = body.get('basamaklar')
    if not isinstance(rows, list):
        raise GalaxyTrekPanelHatasi('Brak listy etapów.')
    data = _read()
    gt = data.get('galaxy_trek')
    if not isinstance(gt, dict):
        raise GalaxyTrekPanelHatasi('Brak konfiguracji Galaxy Trek.')
    current = {int(t['kimlik']): t for t in gt.get('basamaklar', [])}
    if len(rows) != len(current):
        raise GalaxyTrekPanelHatasi('Nie można dodawać ani usuwać etapów w tej wersji edytora.')
    updated = []
    seen = set()
    for row in rows:
        try:
            tid = int(row.get('kimlik'))
        except (TypeError, ValueError):
            raise GalaxyTrekPanelHatasi('Nieprawidłowy etap.')
        if tid not in current or tid in seen:
            raise GalaxyTrekPanelHatasi('Nieznany lub powtórzony etap.')
        seen.add(tid)
        items = row.get('esyalar')
        if not isinstance(items, list) or len(items) > 20:
            raise GalaxyTrekPanelHatasi('Każdy etap może mieć maksymalnie 20 pozycji nagród.')
        clean = []
        for item in items:
            loot = str(item.get('lootId', '')).strip()
            try:
                amount = int(item.get('amount'))
            except (TypeError, ValueError):
                raise GalaxyTrekPanelHatasi('Ilość nagrody musi być liczbą całkowitą.')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', loot):
                raise GalaxyTrekPanelHatasi('Nieprawidłowy identyfikator przedmiotu: %s' % loot)
            if not 1 <= amount <= 1000000000:
                raise GalaxyTrekPanelHatasi('Ilość nagrody musi być w zakresie 1–1 000 000 000.')
            clean.append([loot, amount])
        old = current[tid]
        updated.append(dict(old, esyalar=clean))
    gt['basamaklar'] = sorted(updated, key=lambda t: int(t['gereken']))
    _write(data)
    return get()
