@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CUTROOM 1.1 Beta

if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"
if defined LOCALAPPDATA set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%LOCALAPPDATA%\Microsoft\WinGet\Links;%LOCALAPPDATA%\Programs\Ollama;%PATH%"
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\Ollama\lib\ollama\cuda_v12\cublas64_12.dll" set "PATH=%LOCALAPPDATA%\Programs\Ollama\lib\ollama\cuda_v12;%PATH%"
if defined ProgramFiles if exist "%ProgramFiles%\Ollama\lib\ollama\cuda_v12\cublas64_12.dll" set "PATH=%ProgramFiles%\Ollama\lib\ollama\cuda_v12;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\verify_windows_installer.ps1"
if errorlevel 1 (
  echo.
  echo The CUTROOM Windows installer is damaged or incomplete.
  echo Download CUTROOM again and extract the ZIP completely.
  pause
  exit /b 1
)

set "SETUP_REQUIRED=0"
if not exist ".setup-complete" set "SETUP_REQUIRED=1"
if exist ".setup-complete" findstr /c:"CUTROOM AI 1.1 Beta setup completed" ".setup-complete" >nul 2>&1 || set "SETUP_REQUIRED=1"
if not exist ".venv\Scripts\python.exe" set "SETUP_REQUIRED=1"

if "%SETUP_REQUIRED%"=="1" goto setup
goto verify

:setup
echo CUTROOM needs a one-time local setup.
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if errorlevel 1 (
  echo.
  echo Setup failed. Review data\logs\setup-last-error.txt and data\logs\setup-windows.log.
  pause
  exit /b 1
)
if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"

:verify
".venv\Scripts\python.exe" "scripts\preflight.py" >nul 2>&1
if errorlevel 1 (
  echo CUTROOM found an incomplete environment and will repair it.
  del /q ".setup-complete" >nul 2>&1
  powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
  if errorlevel 1 (
    echo.
    echo Repair failed. Review data\logs\setup-last-error.txt and data\logs\setup-windows.log.
    pause
    exit /b 1
  )
  if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"
  ".venv\Scripts\python.exe" "scripts\preflight.py"
  if errorlevel 1 (
    echo.
    echo Repair completed but the local runtime is still unavailable.
    echo Review data\logs\setup-last-error.txt and data\logs\setup-windows.log.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" server.py
if errorlevel 1 (
  echo.
  echo CUTROOM stopped with an error.
  pause
  exit /b 1
)
exit /b 0
