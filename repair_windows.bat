@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CUTROOM 1.1 Beta Repair

if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"
if defined LOCALAPPDATA set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%LOCALAPPDATA%\Microsoft\WinGet\Links;%LOCALAPPDATA%\Programs\Ollama;%PATH%"

powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0verify_windows_installer.ps1"
if errorlevel 1 (
  echo.
  echo The CUTROOM Windows installer is damaged or incomplete.
  pause
  exit /b 1
)

del /q ".setup-complete" >nul 2>&1
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if errorlevel 1 (
  echo.
  echo Repair failed. Review data\logs\setup-last-error.txt and data\logs\setup-windows.log.
  pause
  exit /b 1
)

if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"
echo.
echo Repair completed. Run run_windows.bat.
pause
exit /b 0
