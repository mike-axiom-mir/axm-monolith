@echo off
setlocal
cd /d "%~dp0"

set SNAPSHOT=..\axm-monolith-test\snapshot
if exist "%SNAPSHOT%\START_AXM.cmd" (
  echo Existing AXM monolith snapshot found.
  echo Launching the complete captured stack...
  call "%SNAPSHOT%\START_AXM.cmd"
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.11+ or run tools\test_week_plus.py with your Python executable.
  pause
  exit /b 1
)

echo No completed monolith snapshot exists yet.
echo Opening the guided first-build flow...
python tools\test_week_plus.py
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo Test week launcher exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
