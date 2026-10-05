@echo off
setlocal
cd /d "%~dp0"
if not exist generated\minecraft-guest\gradlew.bat (
  echo Run setup-windows.bat first.
  pause
  exit /b 1
)
if not exist vendor\sm64-port\build\us_pc\*.exe (
  echo Run build-sm64.bat first.
  pause
  exit /b 1
)
echo Starting Universal Modder Minecraft guest...
start "Minecraft Guest" cmd /k "cd /d %~dp0generated\minecraft-guest && gradlew.bat runClient"
echo Waiting a few seconds for the guest...
timeout /t 8 /nobreak >nul
echo Starting real SM64 host...
call start-sm64.bat
