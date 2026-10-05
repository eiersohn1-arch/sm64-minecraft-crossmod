@echo off
setlocal
cd /d "%~dp0"
if not exist generated\minecraft-guest\gradlew.bat (
  echo Run setup-windows.bat first.
  pause
  exit /b 1
)
cd generated\minecraft-guest
call gradlew.bat runClient
