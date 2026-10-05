@echo off
setlocal
cd /d "%~dp0"
if not exist vendor\universal-modder\examples\minecraft-gta5-passthrough\host\fakehost.py (
  echo Run setup-windows.bat first.
  pause
  exit /b 1
)
python vendor\universal-modder\examples\minecraft-gta5-passthrough\host\fakehost.py
pause
