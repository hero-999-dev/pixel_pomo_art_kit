# -*- mode: python ; coding: utf-8 -*-
import os

# The game's sprite generator is bundled into the .exe so the packaged app
# still works on a machine with no game checkout. Resolved RELATIVE to this
# spec (ArtKit/ -> Pixel Pomo/ -> App/), because an absolute path here broke
# the moment the folder was moved.
_GEN = os.path.join(os.path.dirname(os.path.abspath(SPEC)), os.pardir,
                    'App', 'flutter', 'tools', 'gen_objects.py')
_GEN = os.path.normpath(_GEN)
if not os.path.exists(_GEN):
    raise SystemExit(f'gen_objects.py not found at {_GEN} — is the App folder '
                     f'still a sibling of ArtKit?')


a = Analysis(
    ['run_art_kit.py'],
    pathex=['.'],
    binaries=[],
    datas=[(_GEN, '.')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='PixelPomoArtKit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
