@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is required.& pause & exit /b 1)
python tools\bootstrap_um.py || (pause & exit /b 1)
python tools\sync_um_reference.py || (pause & exit /b 1)
python tools\generate_sm64_host.py || (pause & exit /b 1)
echo.
echo Universal Modder reference, verbatim Universal Modder Minecraft guest and clean SM64 host adapter are ready.
echo Next: put baserom.us.z64 in rom\ or the repo root.
echo Then run build-sm64.bat and start-crossmod.bat
pause
