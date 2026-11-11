@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Elmos World - Build and Install Desktop App
echo.
echo Preparing the standalone Elmos World application.
echo Windows will compile an executable and then open Setup.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build\Build_Release.ps1"
if errorlevel 1 (
  echo.
  echo Could not finish building the Windows setup. Read the message above.
  pause
  exit /b 1
)
if not exist "%~dp0dist_setup\ElmosWorld_Setup_3.1.1.exe" (
  echo Setup.exe was not created.
  pause
  exit /b 1
)
start "" /wait "%~dp0dist_setup\ElmosWorld_Setup_3.1.1.exe"
if errorlevel 1 (
  echo Setup was cancelled or failed.
  pause
  exit /b 1
)
echo.
echo Elmos World is installed. Open it from the desktop or Start menu.
pause
