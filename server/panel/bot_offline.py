"""Symulacja botów poza grą.

Panel uruchamia tę usługę, gdy nie działa klient ani serwer gry. Postęp jest dopisywany
atomowo do zapisu pakietu i zatrzymywany przed startem gry. Limit jest liczony jako czas
offline (maksymalnie 150 h na jedną przerwę między uruchomieniami gry).
"""
import copy
import json
import os
import threading
import time
import traceback
from contextlib import contextmanager
from types import SimpleNamespace

from bot.yonetici import Yonetici


class SymulacjaOffline:
    KROK_MIN = 60.0
    KROK_MAX = 300.0

    def __init__(self, boty, aktywna, log=print, profil_sciezka=None):
        self.boty = boty
        self.aktywna = aktywna
        self.log = log
        self.profil_sciezka = profil_sciezka
        self.lock = threading.RLock()
        self.menedzerowie = {}
        self.wstrzymana = True

    def _meta_sciezka(self, pid):
        return os.path.join(os.path.dirname(self.boty.durum_yolu(pid)), 'offline.json')

    def _czytaj_meta(self, pid):
        p = self._meta_sciezka(pid)
        try:
            with open(p, encoding='utf8') as fh:
                d = json.load(fh)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _zapisz_meta(self, pid, d):
        p = self._meta_sciezka(pid)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf8') as fh:
            json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp, p)

    def _sygnatura(self, pid):
        sciezki = (self.boty.dosya_yolu(pid), self.boty.durum_yolu(pid))
        wynik = []
        for p in sciezki:
            try:
                st = os.stat(p)
                wynik.append((st.st_mtime_ns, st.st_size))
            except OSError:
                wynik.append(None)
        return tuple(wynik)

    def _menedzer(self, pid, pakiet, now):
        sygnatura = self._sygnatura(pid)
        stary = self.menedzerowie.get(pid)
        if stary and stary[0] == sygnatura:
            return stary[1]
        manager = Yonetici(pakiet, self.boty.durum_yolu(pid), self.log, now=now, offline=True)
        self.menedzerowie[pid] = (self._sygnatura(pid), manager)
        return manager

    @contextmanager
    def _swiat_kontekst(self, pid, manager):
        """Klanlar ve CBS için kapalı oyun dünyasının kalıcı profilini geçici olarak bağla."""
        path = self.profil_sciezka(pid) if self.profil_sciezka else None
        if not path or not os.path.isfile(path):
            yield False
            return
        import profil as PF
        import klan as KL
        import topluluk as TP
        import cbs as CB
        from bot import yonetici as BY
        from bot import toplum as BOT_TOPLUM

        old_oyun, old_botlar, old_aktif = TP.OYUN, TP.BOTLAR, BY.AKTIF
        with KL.LOCK:
            old_klanlar = copy.deepcopy(KL.KLANLAR)
            old_silinen = copy.deepcopy(KL.SILINEN)
            old_dosya, old_ad_n = KL.DOSYA, KL.BOT_AD_N
            KL.KLANLAR.clear()
            KL.SILINEN.clear()
            KL.DOSYA = None
            KL.BOT_AD_N = 0
        profil = None
        try:
            profil = PF.Profil(path=path)
            # cbs.ortak() ve topluluk.hepsi() oyunun PROFiL/CURRENT arayüzünü okur.
            TP.OYUN = SimpleNamespace(PROFIL=profil, CURRENT=None)
            klan_dosyasi = os.path.join(os.path.dirname(self.boty.durum_yolu(pid)), 'klanlar.json')
            KL.configure(klan_dosyasi)
            BY.AKTIF = manager
            BOT_TOPLUM.kaydol(manager, None)
            manager.toplum = True
            # .asts mevcut istasyonları ortak kayda alır ve bot klanlarının CBS erişimini hazırlar.
            CB.Cbs(profil, None, self.log).asts
        except Exception:
            self.log('botlar offline: dünya bağlamı kurulamadı (%s)\\n%s' % (pid, traceback.format_exc()))
            manager.toplum = False
            TP.OYUN, TP.BOTLAR, BY.AKTIF = old_oyun, old_botlar, old_aktif
            with KL.LOCK:
                KL.KLANLAR.clear()
                KL.KLANLAR.update(old_klanlar)
                KL.SILINEN.clear()
                KL.SILINEN.update(old_silinen)
                KL.DOSYA, KL.BOT_AD_N = old_dosya, old_ad_n
            yield False
            return
        try:
            yield True
            KL.kaydet()
            if profil.dirty:
                profil.save()
        finally:
            manager.toplum = False
            TP.OYUN, TP.BOTLAR, BY.AKTIF = old_oyun, old_botlar, old_aktif
            with KL.LOCK:
                KL.KLANLAR.clear()
                KL.KLANLAR.update(old_klanlar)
                KL.SILINEN.clear()
                KL.SILINEN.update(old_silinen)
                KL.DOSYA, KL.BOT_AD_N = old_dosya, old_ad_n


    def _resetuj_pakiety(self, now):
        for pid in self.boty.liste_kimlik():
            try:
                d = self._czytaj_meta(pid)
                d.update(last_wall=now, used_seconds=0.0, sim_time=now, paused=True)
                self._zapisz_meta(pid, d)
            except (OSError, ValueError):
                self.log('boty offline: nie można zresetować znacznika pakietu %s' % pid)

    def pauza(self, now=None):
        """Zapisuje bieżący stan i zeruje licznik przerwy przed uruchomieniem klienta."""
        now = time.time() if now is None else now
        with self.lock:
            for pid, pair in list(self.menedzerowie.items()):
                try:
                    pair[1].kaydet(now)
                except Exception:
                    self.log('boty offline: zapis przy pauzie nie powiódł się (%s)\\n%s' %
                             (pid, traceback.format_exc()))
            self.menedzerowie.clear()
            self._resetuj_pakiety(now)
            self.wstrzymana = True

    def tick(self, now=None):
        """Jeden krok harmonogramu panelu; nie działa, gdy klient lub serwer jest uruchomiony."""
        now = time.time() if now is None else now
        try:
            allowed = bool(self.aktywna())
        except Exception:
            allowed = False
        if not allowed:
            if not self.wstrzymana:
                self.pauza(now)
            return
        with self.lock:
            if self.wstrzymana:
                self._resetuj_pakiety(now)
                self.wstrzymana = False
                return
            for pid in self.boty.liste_kimlik():
                try:
                    # Pakiet edytowany podczas symulacji zostanie odczytany ponownie pod wspólną blokadą.
                    with self.boty._KILIT:
                        pakiet = self.boty.oku(pid)
                        meta = self._czytaj_meta(pid)
                        if not pakiet.get('dunya'):
                            meta.update(last_wall=now, used_seconds=0.0, sim_time=now, paused=False)
                            self._zapisz_meta(pid, meta)
                            continue
                        a = pakiet.get('ayarlar') or {}
                        limit_h = max(0, min(150, int(a.get('telafi_saat', 150) or 0)))
                        tempo = max(0.0, min(1.0, float(a.get('telafi_oran', 0.35))))
                        last = float(meta.get('last_wall') or now)
                        used = max(0.0, float(meta.get('used_seconds') or 0.0))
                        if limit_h <= 0 or used >= limit_h * 3600 or tempo <= 0:
                            meta.update(last_wall=now, used_seconds=used, sim_time=float(meta.get('sim_time') or now), paused=False)
                            self._zapisz_meta(pid, meta)
                            continue
                        elapsed = max(0.0, now - last)
                        if elapsed < self.KROK_MIN:
                            continue
                        step = min(self.KROK_MAX, elapsed, limit_h * 3600 - used)
                        if step <= 0:
                            continue
                        sim_start = float(meta.get('sim_time') or (now - step * tempo))
                        sim_now = sim_start + step * tempo
                        manager = self._menedzer(pid, pakiet, sim_start)
                        # Social decisions, clan budgets/diplomacy and CBS station strategy share the same world context.
                        with self._swiat_kontekst(pid, manager):
                            manager.telafi(step * tempo, sim_now)
                        manager.kaydet(sim_now)
                        meta.update(last_wall=last + step, used_seconds=min(limit_h * 3600, used + step),
                                    sim_time=sim_now, paused=False, last_run=now, limit_hours=limit_h)
                        self._zapisz_meta(pid, meta)
                        # kaydet() zmienia mtime durum.json; odśwież sygnaturę cache.
                        self.menedzerowie[pid] = (self._sygnatura(pid), manager)
                except Exception:
                    self.log('boty offline: symulacja pakietu %s nie powiodła się\\n%s' %
                             (pid, traceback.format_exc()))
