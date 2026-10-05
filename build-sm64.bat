@echo off
setlocal
cd /d "%~dp0"
python tools\build_sm64.py
if errorlevel 1 (
  echo.
  echo SM64 build failed.
  pause
  exit /b 1
)
echo.
echo SM64 host build finished.
pause
