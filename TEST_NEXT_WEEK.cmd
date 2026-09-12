@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.11+ or run tools\test_drive.py with your Python executable.
  pause
  exit /b 1
)
python tools\test_drive.py
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo Test drive exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
