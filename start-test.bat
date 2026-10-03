@echo off
setlocal
cd /d "%~dp0"

echo ======================================================
echo  SM64 x Minecraft Crossmod - Test starten
echo ======================================================
echo.

set "SM64_EXE=%CD%\vendor\sm64-port\build\us_pc\sm64.us.exe"

if not exist "%SM64_EXE%" (
  echo FEHLER: Der SM64-Host wurde noch nicht gebaut.
  echo.
  echo Fuehre zuerst aus:
  echo   setup-windows.bat
  echo.
  pause
  exit /b 1
)

if not exist "gradlew.bat" (
  echo FEHLER: gradlew.bat fehlt.
  echo Starte diese Datei direkt aus dem Projektordner.
  pause
  exit /b 1
)

echo [1/2] Starte den gepatchten Super-Mario-64-Host...
start "SM64 Crossmod Host" "%SM64_EXE%"

echo.
echo [2/2] Starte Minecraft 1.21.1 mit dem Fabric-Crossmod...
echo.
echo WICHTIG:
echo   - SM64 und Minecraft laufen fuer diesen Test gleichzeitig.
echo   - Oeffne in Minecraft eine Welt, damit Steve existiert.
echo   - Der finale gemeinsame 3D-Compositor ist noch in Arbeit.
echo.
call gradlew.bat runClient

endlocal
