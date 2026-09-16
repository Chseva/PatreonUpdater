# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks.tcl_tk import tcltk_info

if not tcltk_info.available:
    raise SystemExit('Tkinter is unavailable in this Python environment. Repair Python Tcl/Tk support before building; no release will be produced.')

datas = [('assets', 'assets')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['patreon_updater.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Playwright's installation registry contains machine-local paths. Filter after
# Analysis as hooks can add their own collected files. Keep browser executables.
def distributable(entry):
    return '/.local-browsers/.links/' not in ('/' + entry[0].replace('\\', '/'))

a.datas = [entry for entry in a.datas if distributable(entry)]
a.binaries = [entry for entry in a.binaries if distributable(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Patreon Updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/PU.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Patreon Updater',
)
