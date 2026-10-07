@echo off
setlocal
cd /d "%~dp0"

echo ======================================================
echo  SM64 x Minecraft Crossmod - Start
echo ======================================================
echo.

if not exist "vendor\sm64-port\build\us_pc\sm64.us.exe" (
  echo SM64-Host fehlt. Baue ihn zuerst mit:
  echo   build-sm64.bat
  echo.
  pause
  exit /b 1
)

call start-test.bat
endlocal
