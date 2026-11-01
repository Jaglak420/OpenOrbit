@echo off
setlocal
title OpenOrbit - diagnostyka i naprawa aktualizatora
cd /d "%~dp0"

set "TARGET=%CD%\server\panel\guncelleme.py"
set "TEMPFILE=%CD%\server\panel\guncelleme.py.new"
set "BACKUP=%CD%\server\panel\guncelleme.py.before-jaglak"
set "REPORT=%CD%\diagnostyka_github.txt"

if not exist "%TARGET%" (
  echo Nie znaleziono server\panel\guncelleme.py.
  echo Ten plik BAT musi lezec obok OpenOrbit Panel.pyw.
  pause
  exit /b 1
)

echo Sprawdzanie, czy Panel nie dziala w tle...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Get-Location).Path; $p=Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(pythonw?\.exe|OpenOrbit.*\.exe)$' -and $_.CommandLine -and $_.CommandLine.Contains($root) }; if ($p) { Write-Host 'WYKRYTO DZIALAJACY PROCES PANELU:'; $p | ForEach-Object { Write-Host $_.Name $_.ProcessId $_.CommandLine }; exit 20 }"
if errorlevel 1 (
  echo.
  echo Zamknij calkowicie OpenOrbit Panel i uruchom ten plik ponownie.
  echo Nie podmieniam pliku, gdy stary kod moze byc zaladowany w pamieci.
  pause
  exit /b 1
)

echo Pobieranie aktualizatora z Jaglak420/OpenOrbit...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u='https://raw.githubusercontent.com/Jaglak420/OpenOrbit/main/server/panel/guncelleme.py'; $f='%TEMPFILE%'; Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $f; $c=Get-Content -Raw -LiteralPath $f; if (-not $c.Contains('DEPO = ''Jaglak420/OpenOrbit''')) { throw 'Pobrany plik nie wskazuje na Jaglak420/OpenOrbit.' }; $latest=Invoke-RestMethod -Headers @{ 'Cache-Control'='no-cache'; 'User-Agent'='OpenOrbit-Updater-Repair' } -Uri 'https://api.github.com/repos/Jaglak420/OpenOrbit/commits/main'; $repoLine=$c.Split([Environment]::NewLine) | Where-Object { $_.StartsWith('DEPO = ') } | Select-Object -First 1; Set-Content -LiteralPath '%REPORT%' -Value ('Repozytorium: Jaglak420/OpenOrbit' + [Environment]::NewLine + 'Branza: main' + [Environment]::NewLine + 'Najnowszy commit GitHub: ' + $latest.sha + [Environment]::NewLine + 'Data: ' + $latest.commit.committer.date + [Environment]::NewLine + 'Plik aktualizatora wskazuje na: ' + $repoLine + [Environment]::NewLine + 'Folder projektu: ' + (Get-Location).Path) -Encoding UTF8"
if errorlevel 1 (
  del "%TEMPFILE%" 2>nul
  echo Nie udalo sie pobrac lub zweryfikowac aktualizatora.
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
  echo Nie udalo sie podmienic aktualizatora. Kopia: %BACKUP%
  pause
  exit /b 1
)

echo.
echo GOTOWE. Aktualizator kieruje na Jaglak420/OpenOrbit, galaz main.
echo Raport GitHub: %REPORT%
echo Kopia poprzedniego pliku: %BACKUP%
echo.
if exist "%CD%\OpenOrbit Panel.pyw" (
  echo Uruchamiam OpenOrbit Panel...
  start "" "%CD%\OpenOrbit Panel.pyw"
) else (
  echo Nie znaleziono OpenOrbit Panel.pyw. Uruchom Panel recznie.
)
start "" notepad.exe "%REPORT%"
echo.
pause
