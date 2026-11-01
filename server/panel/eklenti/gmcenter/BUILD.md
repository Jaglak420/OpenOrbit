# Budowanie OpenOrbit GM Center

GM Center jest osobną wtyczką BepInEx: `OpenOrbitGMCenter.dll`. Nie zastępuje ani nie modyfikuje dotychczasowej `OpenOrbitYama.dll`.

## Wymagania

- Windows
- .NET 8 SDK
- klient DarkOrbit zgodny z OpenOrbit (obecnie projekt wskazuje 1.1.116)
- BepInEx 6 z wygenerowanymi bibliotekami `BepInEx/interop`

## Przygotowanie

1. Pobierz pełny ZIP gałęzi `release/gm-center-jaglak-updater`.
2. Uruchom OpenOrbit Panel i otwórz klienta przez przycisk OYNA przynajmniej raz, aby BepInEx utworzył biblioteki IL2CPP w folderze klienta.
3. Zamknij grę i Panel.
4. Zainstaluj .NET 8 SDK, jeśli nie jest jeszcze zainstalowany.

## Kompilacja

Uruchom:

`server/panel/eklenti/gmcenter/BuildGMCenter.bat`

Skrypt wykryje klienta w folderze projektu albo poprosi o ścieżkę do katalogu z `DarkOrbit.exe`. Sprawdzi wymagane biblioteki, wykona build i utworzy:

`server/panel/eklenti/OpenOrbitGMCenter.dll`

Nie kopiuje ani nie nadpisuje starej biblioteki `OpenOrbitYama.dll`.

## Przekazanie artefaktu do repozytorium

Przed publikacją aktualizacji Panelu dodaj utworzony `OpenOrbitGMCenter.dll` do tego samego Pull Request. Po dodaniu DLL Panel będzie go automatycznie kopiował do `BepInEx/plugins` przy następnym uruchomieniu klienta.

## Ważne

GitHub Actions sprawdza składnię C# względem lekkich atrap Unity/BepInEx oraz uruchamia testy serwerowe. Nie zastępuje to kompilacji przeciwko prawdziwym bibliotekom zainstalowanego klienta ani testu F10 w uruchomionej grze. Nie publikuj samego źródła jako gotowej aktualizacji klienta bez zbudowanego i sprawdzonego DLL.
