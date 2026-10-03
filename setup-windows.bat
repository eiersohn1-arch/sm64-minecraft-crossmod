@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  SM64 x Minecraft Crossmod - Full Setup
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

echo [1/6] Verifying local SM64 ROM...
python tools\verify_rom.py rom\baserom.us.z64
if errorlevel 1 exit /b 1

echo.
echo [2/6] Fetching public development sources...
python tools\bootstrap_sources.py
if errorlevel 1 exit /b 1

echo.
echo [3/6] Creating source import plan...
python tools\make_import_plan.py
if errorlevel 1 exit /b 1

echo.
echo [4/6] Building full Peach's Castle hub plan...
python tools\build_castle_plan.py
if errorlevel 1 exit /b 1

echo.
echo [5/6] Building complete Bob-omb Battlefield plan...
python tools\build_course_plan.py bob_omb_battlefield
if errorlevel 1 exit /b 1

echo.
echo [6/6] Building Fabric mod...
call gradlew.bat build
if errorlevel 1 exit /b 1

echo.
echo ==========================================
echo  SETUP COMPLETE
echo ==========================================
echo.
echo Launch:
echo   gradlew.bat runClient
echo.
echo The first world load builds Peach's Castle automatically.
echo Bob-omb Battlefield is prepared automatically and entered through the blue painting.
echo.
endlocal
