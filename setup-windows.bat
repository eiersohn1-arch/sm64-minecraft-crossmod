@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is required.& pause & exit /b 1)
python tools\bootstrap_um.py || (pause & exit /b 1)
python tools\sync_um_reference.py || (pause & exit /b 1)
python tools\generate_sm64_host.py || (pause & exit /b 1)
echo.
echo Universal Modder reference, Minecraft guest and clean SM64 host adapter are ready.
echo Next: run start-guest.bat
pause
