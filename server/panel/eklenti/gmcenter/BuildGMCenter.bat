@echo off
setlocal
title Build OpenOrbit GM Center
for %%I in ("%~dp0..\..\..\..") do set "ROOT=%%~fI"
cd /d "%ROOT%"

set "CLIENT=%~1"
if not defined CLIENT if exist "%ROOT%\DarkOrbit_Version1.1.116\DarkOrbit.exe" set "CLIENT=%ROOT%\DarkOrbit_Version1.1.116"
if not defined CLIENT if exist "%ROOT%\DarkOrbit_Version1.1.115\DarkOrbit.exe" set "CLIENT=%ROOT%\DarkOrbit_Version1.1.115"
if not defined CLIENT (
  echo Nie znaleziono klienta w folderze projektu.
  set /p CLIENT=Podaj pelna sciezke do folderu DarkOrbit z DarkOrbit.exe: 
)

if not exist "%CLIENT%\DarkOrbit.exe" (
  echo Nie znaleziono DarkOrbit.exe w: %CLIENT%
  pause
  exit /b 1
)

where dotnet >nul 2>nul
if errorlevel 1 (
  echo Brak .NET SDK. Zainstaluj .NET 8 SDK z:
  echo https://dotnet.microsoft.com/download/dotnet/8.0
  echo Potem uruchom ten skrypt ponownie.
  pause
  exit /b 1
)

set "REF=%CLIENT%\BepInEx"
for %%F in (
  "%REF%\core\BepInEx.Core.dll"
  "%REF%\core\BepInEx.Unity.IL2CPP.dll"
  "%REF%\core\Il2CppInterop.Runtime.dll"
  "%REF%\core\0Harmony.dll"
  "%REF%\interop\Il2Cppmscorlib.dll"
  "%REF%\interop\UnityEngine.CoreModule.dll"
  "%REF%\interop\UnityEngine.IMGUIModule.dll"
  "%REF%\interop\UnityEngine.InputLegacyModule.dll"
) do (
  if not exist "%%~F" (
    echo Brakuje biblioteki: %%~F
    echo Uruchom klienta raz przez OpenOrbit Panel, aby BepInEx wygenerowal interop.
    pause
    exit /b 1
  )
)

echo.
echo Klient: %CLIENT%
echo Budowanie osobnej wtyczki OpenOrbitGMCenter.dll...
dotnet build "%ROOT%\server\panel\eklenti\gmcenter\OpenOrbitGMCenter.csproj" --configuration Release "-p:Istemci=%CLIENT%" --nologo
if errorlevel 1 (
  echo.
  echo Kompilacja nie powiodla sie. Nie podmieniono zadnej biblioteki klienta.
  pause
  exit /b 1
)

set "DLL=%ROOT%\server\panel\eklenti\OpenOrbitGMCenter.dll"
if not exist "%DLL%" (
  echo Kompilacja zakonczona, ale nie znaleziono pliku wynikowego:
  echo %DLL%
  pause
  exit /b 1
)

echo.
echo GOTOWE: %DLL%
echo SHA-256:
certutil -hashfile "%DLL%" SHA256
echo.
echo Nastepny krok: przeslij plik OpenOrbitGMCenter.dll, abym mogl dodac go do Jaglak420/OpenOrbit.
echo Panel bedzie kopiowal go do BepInEx\plugins przy uruchomieniu klienta.
echo.
pause
