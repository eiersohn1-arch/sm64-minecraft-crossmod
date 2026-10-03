@echo off
setlocal
cd /d "%~dp0"

echo ======================================================
echo  SM64 x Minecraft Crossmod - Passthrough Setup
echo ======================================================
echo.
echo FINAL TARGET:
echo   Original SM64 world/textures/entities
echo   + Minecraft Steve/hotbar/items
echo.
echo The old Minecraft-block recreation is no longer used.
echo.

where java >nul 2>&1
if errorlevel 1 (
  echo ERROR: Java/JDK 21 was not found in PATH.
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3 was not found in PATH.
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git was not found in PATH.
  exit /b 1
)

echo [1/3] Preparing patched SM64 passthrough host...
python tools\prepare_passthrough.py
if errorlevel 1 exit /b 1

echo.
echo [2/3] Building Fabric Minecraft side...
call gradlew.bat build
if errorlevel 1 exit /b 1

echo.
echo [3/3] Checking MSYS2 host build tools...
if exist C:\msys64\usr\bin\bash.exe (
  echo MSYS2 found.
  python tools\prepare_passthrough.py --build-sm64
  if errorlevel 1 (
    echo.
    echo Fabric side is built, but the SM64 host build failed.
    echo If the error above says a package is missing, open "MSYS2 MinGW 64-bit" and run:
    echo.
    echo pacman -S --needed git make python3 mingw-w64-x86_64-gcc mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glew
    echo.
    exit /b 1
  )
) else (
  echo.
  echo MSYS2 is not installed yet.
  echo Install it from https://www.msys2.org/
  echo Then open "MSYS2 MinGW 64-bit" and run:
  echo.
  echo pacman -S --needed git make python3 mingw-w64-x86_64-gcc mingw-w64-x86_64-SDL2 mingw-w64-x86_64-glew
  echo.
  echo After that, run setup-windows.bat again.
  exit /b 1
)

echo.
echo ======================================================
echo  PASSTHROUGH FOUNDATION BUILT
echo ======================================================
echo.
echo Fabric mod:
echo   build\libs\
echo.
echo Patched SM64 host:
echo   vendor\sm64-port\build\us_pc\
echo.
echo The visual compositor is the next milestone.
endlocal
