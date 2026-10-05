@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is required.& pause & exit /b 1)
where java >nul 2>nul || (echo JDK 25 is required and java is not in PATH.& pause & exit /b 1)
for /f "tokens=3" %%V in ('java -version 2^>^&1 ^| findstr /i "version"') do set JAVAVER=%%~V
echo Detected Java: %JAVAVER%
echo %JAVAVER% | findstr /b "25." >nul || (
  echo.
  echo This Universal Modder guest requires JDK 25.
  echo Install JDK 25, reopen PowerShell, and run setup-windows.bat again.
  pause
  exit /b 1
)
if not exist C:\msys64\usr\bin\bash.exe (
  echo.
  echo MSYS2 was not found at C:\msys64.
  echo Install MSYS2 before building the SM64 host.
)
python tools\bootstrap_um.py || (pause & exit /b 1)
python tools\sync_um_reference.py || (pause & exit /b 1)
python tools\generate_sm64_host.py || (pause & exit /b 1)
echo.
echo Universal Modder reference, verbatim Universal Modder Minecraft guest and clean SM64 host adapter are ready.
echo Next: put baserom.us.z64 in rom\ or the repo root.
echo Then run build-sm64.bat and start-crossmod.bat
pause
