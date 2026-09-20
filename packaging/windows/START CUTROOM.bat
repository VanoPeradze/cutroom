@echo off
setlocal EnableExtensions DisableDelayedExpansion
title CUTROOM 1.1 Beta

if not exist "%~dp0App\run_windows.bat" (
  echo CUTROOM could not find its App folder.
  echo.
  echo Right-click the downloaded ZIP and choose Extract All.
  echo Keep START CUTROOM.bat beside the complete App folder.
  echo Open START HERE.html for help.
  echo.
  pause
  exit /b 1
)

pushd "%~dp0App"
if errorlevel 1 (
  echo CUTROOM could not open its App folder.
  echo Extract the ZIP into a writable local folder and try again.
  pause
  exit /b 1
)

call run_windows.bat
set "CUTROOM_LAUNCH_EXIT=%ERRORLEVEL%"
popd
exit /b %CUTROOM_LAUNCH_EXIT%
