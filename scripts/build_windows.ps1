$ErrorActionPreference = 'Stop'

# Build a portable Windows folder containing the GUI, Python runtime, Playwright,
# and only the Chromium browser used by Patreon Updater.
$env:PLAYWRIGHT_BROWSERS_PATH = '0'

python -m pip install -e '.[browser]'
python -m pip install pyinstaller
python -m playwright install chromium

python -m PyInstaller --noconfirm --clean 'Patreon Updater.spec'
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }

Write-Host "Build ready: dist\Patreon Updater\Patreon Updater.exe"
