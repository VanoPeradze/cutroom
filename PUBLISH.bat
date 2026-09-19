@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title CUTROOM - Prepare and publish
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if exist ".venv\Scripts\python.exe" goto venv
where py >nul 2>&1
if not errorlevel 1 goto launcher
where python >nul 2>&1
if not errorlevel 1 goto python
echo Python was not found. Run run_windows.bat once, then try again.
echo No files were uploaded and no software was installed by PUBLISH.
set "PUBLISH_RESULT=1"
goto finish

:venv
".venv\Scripts\python.exe" "scripts\publish.py" %*
set "PUBLISH_RESULT=%ERRORLEVEL%"
goto finish

:launcher
py -3 "scripts\publish.py" %*
set "PUBLISH_RESULT=%ERRORLEVEL%"
goto finish

:python
python "scripts\publish.py" %*
set "PUBLISH_RESULT=%ERRORLEVEL%"

:finish
if "%~1"=="" pause
exit /b %PUBLISH_RESULT%
