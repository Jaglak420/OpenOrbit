@echo off
setlocal
title OpenOrbit - naprawa aktualizatora
cd /d "%~dp0"

if not exist "server\panel\guncelleme.py" (
  echo Nie znaleziono server\panel\guncelleme.py.
  echo Umiesc ten plik BAT w glownym folderze projektu OpenOrbit.
  pause
  exit /b 1
)

set "TARGET=%CD%\server\panel\guncelleme.py"
set "TEMPFILE=%CD%\server\panel\guncelleme.py.new"
set "BACKUP=%CD%\server\panel\guncelleme.py.before-jaglak"

echo Pobieranie aktualizatora z Jaglak420/OpenOrbit...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $u='https://raw.githubusercontent.com/Jaglak420/OpenOrbit/main/server/panel/guncelleme.py'; Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile '%TEMPFILE%'; $c=Get-Content -Raw -LiteralPath '%TEMPFILE%'; if ($c -notmatch \"DEPO = 'Jaglak420/OpenOrbit'\") { throw 'Pobrany plik nie wskazuje na Jaglak420/OpenOrbit.' }"
if errorlevel 1 (
  del "%TEMPFILE%" 2>nul
  echo Nie udalo sie pobrac lub zweryfikowac pliku.
  pause
  exit /b 1
)

copy /Y "%TARGET%" "%BACKUP%" >nul
if errorlevel 1 (
  del "%TEMPFILE%" 2>nul
  echo Nie udalo sie wykonac kopii zapasowej.
  pause
  exit /b 1
)

move /Y "%TEMPFILE%" "%TARGET%" >nul
if errorlevel 1 (
  echo Nie udalo sie podmienic aktualizatora. Kopia zapasowa: %BACKUP%
  pause
  exit /b 1
)

echo.
echo GOTOWE. Aktualizator wskazuje teraz Jaglak420/OpenOrbit, galaz main.
echo Kopia poprzedniego pliku: %BACKUP%
echo Zamknij i uruchom ponownie OpenOrbit Panel, a nastepnie wybierz:
echo Panel - Aktualizacje - Sprawdz teraz.
echo.
pause
