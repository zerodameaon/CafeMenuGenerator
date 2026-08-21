# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app/app.py'],
    pathex=[],
    binaries=[],
    datas=[('app/fonts', 'fonts'), ('app/brightsign_help', 'brightsign_help')],
    hiddenimports=['PIL._tkinter_finder', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='The Cafe Menu Sign Generator',
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
    icon=['app/AppIcon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='The Cafe Menu Sign Generator',
)
app = BUNDLE(
    coll,
    name='The Cafe Menu Sign Generator.app',
    icon='app/AppIcon.icns',
    bundle_identifier=None,
)
