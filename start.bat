@echo off
rem Cross-platform helper: Windows
rem Starts ATNF Pulsar Query Center and opens the browser.
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0start.py" %*
  goto :eof
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0start.py" %*
  goto :eof
)

echo error: python not found in PATH
exit /b 1
