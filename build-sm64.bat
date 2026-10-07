@echo off
setlocal
cd /d "%~dp0"

echo ======================================================
echo  SM64 x Minecraft Crossmod - Rebuild SM64 Host
echo ======================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Python 3 wurde nicht in PATH gefunden.
  pause
  exit /b 1
)

if not exist "rom\baserom.us.z64" (
  echo FEHLER: rom\baserom.us.z64 fehlt.
  echo Lege deine eigene US-SM64-ROM dort ab. Die ROM gehoert nicht ins Repo.
  pause
  exit /b 1
)

python tools\prepare_passthrough.py --build-sm64
if errorlevel 1 (
  echo.
  echo FEHLER: SM64-Host Build fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo SM64-Host erfolgreich gebaut.
echo EXE: vendor\sm64-port\build\us_pc\sm64.us.exe
echo.
endlocal
