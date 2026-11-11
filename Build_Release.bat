@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Elmos World - Build Windows Release
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build\Build_Release.ps1"
if errorlevel 1 (
  echo.
  echo The release build did not complete. Read the error above.
  pause
  exit /b 1
)
echo.
echo Finished. See dist_setup for the Windows Setup installer.
pause
