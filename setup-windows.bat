@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  SM64 x Minecraft Crossmod - Local Setup
echo ==========================================
echo.

where java >nul 2>&1
if errorlevel 1 (
  echo ERROR: Java 21 was not found in PATH.
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python was not found in PATH.
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git was not found in PATH.
  exit /b 1
)

echo [1/5] Verifying local SM64 ROM...
python tools\verify_rom.py rom\baserom.us.z64
if errorlevel 1 exit /b 1

echo.
echo [2/5] Fetching public development sources...
python tools\bootstrap_sources.py
if errorlevel 1 exit /b 1

echo.
echo [3/5] Creating import plan...
python tools\make_import_plan.py
if errorlevel 1 exit /b 1

echo.
echo [4/5] Converting Bob-omb Battlefield collision to a Minecraft block plan...
python tools\build_course_plan.py bob_omb_battlefield
if errorlevel 1 exit /b 1

echo.
echo [5/5] Building Fabric mod...
call gradlew.bat build
if errorlevel 1 exit /b 1

echo.
echo BUILD OK.
echo Block plan: run\config\sm64cross\imported\courses\bob_omb_battlefield.json
echo Mod jar:    build\libs\
echo.
echo To launch the dev client:
echo   gradlew.bat runClient
echo.
echo In a cheats-enabled test world run:
echo   /sm64 build bob_omb_battlefield
endlocal
