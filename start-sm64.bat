@echo off
setlocal
cd /d "%~dp0"
set EXE=
for %%F in (vendor\sm64-port\build\us_pc\*.exe) do (
  set EXE=%%F
  goto found
)
:found
if "%EXE%"=="" (
  echo SM64 host is not built yet.
  echo Run build-sm64.bat first.
  pause
  exit /b 1
)
echo Starting %EXE%
start "" "%EXE%"
