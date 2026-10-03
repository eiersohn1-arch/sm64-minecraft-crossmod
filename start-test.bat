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

rem Frame transport now follows universal-modder:
rem localhost WebSocket + named shared memory Local\MCPassthroughFrame.

echo [1/2] Starte den nativen Super-Mario-64-Host...
start "SM64 Crossmod Host" "%SM64_EXE%"

echo.
echo [2/2] Starte Minecraft 1.21.1 mit Fabric...
echo.
echo UNIVERSAL-MODDER PASSTHROUGH:
echo   1. Oeffne in Minecraft eine Welt.
echo   2. Sobald die Bridge verbunden ist, legt sich das SM64-Bild
echo      automatisch ueber die Minecraft-Spielflaeche.
echo   3. Minecraft bleibt darunter fokussiert. Tastatur, Maus,
echo      Hotbar und Inventar funktionieren deshalb weiterhin normal.
echo   4. Steve/Items werden mit SM64-Tiefe zusammengesetzt:
echo      eine SM64-Wand kann Steve wirklich verdecken.
echo.
echo SM64-TASTEN:
echo   WASD = laufen     LEERTASTE = A/Sprung
echo   Linksklick/Rechtsklick = B/Angriff/Benutzen
echo   SHIFT = Z         P = Start/Pause
echo   I J K L = C-Tasten, O = R, U = L
echo.
echo Zum ersten Test wird Minecraft in 1280x720 gestartet.
echo.

call gradlew.bat runClient --args="--width 1280 --height 720"

endlocal
