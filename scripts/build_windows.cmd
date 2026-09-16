@echo off
setlocal

rem Build a portable Windows folder containing the GUI, Python runtime,
rem Playwright, and only the Chromium browser used by Patreon Updater.
set PLAYWRIGHT_BROWSERS_PATH=0

python -m pip install -e ".[browser]"
if errorlevel 1 exit /b %errorlevel%

python -m pip install pyinstaller
if errorlevel 1 exit /b %errorlevel%

python -m playwright install chromium
if errorlevel 1 exit /b %errorlevel%

python -m PyInstaller --noconfirm --clean "Patreon Updater.spec"

if errorlevel 1 exit /b %errorlevel%
echo.
echo Build ready: dist\Patreon Updater\Patreon Updater.exe
