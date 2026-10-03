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

echo [1/3] Verifying local SM64 ROM...
python tools\verify_rom.py rom\baserom.us.z64
if errorlevel 1 exit /b 1

echo.
echo [2/3] Creating import plan...
python tools\make_import_plan.py
if errorlevel 1 exit /b 1

echo.
echo [3/3] Building Fabric mod...
call gradlew.bat build
if errorlevel 1 exit /b 1

echo.
echo BUILD OK. Mod jar is in build\libs\
endlocal
