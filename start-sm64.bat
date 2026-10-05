@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-crossmod.ps1" sm64
if errorlevel 1 pause
