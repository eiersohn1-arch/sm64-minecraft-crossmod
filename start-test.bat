@echo off
setlocal
cd /d "%~dp0"

echo ======================================================
echo  SM64 x Minecraft Crossmod - One Window Test
echo ======================================================
echo.

set "SM64_EXE=%CD%\vendor\sm64-port\build\us_pc\sm64.us.exe"

if not exist "%SM64_EXE%" (
  echo FEHLER: Der SM64-Host wurde noch nicht gebaut.
  echo Fuehre zuerst aus:
  echo   setup-windows.bat
  echo.
  pause
  exit /b 1
)

if not exist "gradlew.bat" (
  echo FEHLER: gradlew.bat fehlt.
  pause
  exit /b 1
)

echo [1/2] Starte den sichtbaren SM64-Host...
start "SM64 x Minecraft" "%SM64_EXE%"

echo.
echo [2/2] Starte Minecraft als Hintergrund-Engine...
echo.
echo WICHTIG:
echo   - Minecraft erscheint zuerst noch normal.
echo   - Oeffne einmal deine Minecraft-Welt.
echo   - Sobald Spieler + SM64 verbunden sind, verschiebt die Mod das
echo     Minecraft-Fenster automatisch aus dem sichtbaren Desktop.
echo   - Danach bleibt nur SM64 sichtbar.
echo   - Minecraft rendert Steve, Skin, Hotbar, Inventar und Items weiter
echo     unsichtbar im Hintergrund.
echo.
echo EINGABE IM SICHTBAREN SM64-FENSTER:
echo   WASD        = laufen
echo   LEERTASTE   = A / springen
echo   Linksklick  = B + Minecraft-Waffenangriff
echo   Rechtsklick = B / Item benutzen
echo   SHIFT       = Z
echo   P           = Start / Pause
echo   I J K L     = C-Tasten
echo   O / U       = R / L
echo   1-9         = Minecraft-Hotbar-Slot
echo   E           = Minecraft-Inventar im SM64-Fenster
echo   F5          = Minecraft Perspektive wechseln
echo   Q / Ctrl+Q  = Item / Stack droppen
echo   F           = Offhand tauschen
echo   T           = Minecraft-Chat
echo   V           = originale SM64-B-Aktion
echo.
echo Minecraft wird fuer den Frame-Export mit 1280x720 gestartet.
echo.

call gradlew.bat runClient --args="--width 1280 --height 720"

endlocal
