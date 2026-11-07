@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo CUTROOM's existing Python runtime is missing. Run the normal setup first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0scripts\desktop_windows.py"
exit /b 0
