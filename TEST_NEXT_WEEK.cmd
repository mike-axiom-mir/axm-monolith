@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.11+ or run tools\test_week_plus.py with your Python executable.
  pause
  exit /b 1
)
python tools\test_week_plus.py
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo Test week launcher exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
