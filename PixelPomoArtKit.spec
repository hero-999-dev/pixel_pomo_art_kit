# -*- mode: python ; coding: utf-8 -*-
import os
import sys

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

# The tomato-and-brush icon (#v2.4.0). Both files are generated from the same
# 16x16 grid by `python -m art_kit.branding` and committed under assets/, so
# the build needs nothing beyond the checkout. The window's own icon is drawn
# at run time from that grid; these are for the .exe / .app and Finder.
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(SPEC)), 'assets')
_ICO = os.path.join(_ASSETS, 'icon.ico')
_ICNS = os.path.join(_ASSETS, 'icon.icns')


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
    icon=_ICNS if sys.platform == 'darwin' else _ICO,
)

# macOS wants a .app bundle, not a bare unix executable — double-clicking the
# raw binary opens a Terminal window alongside the app, and Finder will not show
# it as an application at all. BUNDLE is a no-op on other platforms, but it is
# guarded anyway so a Windows build never carries Mac-only metadata (#v2.1.0).
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='PixelPomoArtKit.app',
        icon=_ICNS,
        bundle_identifier='com.pixelpomo.artkit',
        info_plist={
            'NSHighResolutionCapable': True,
            # Tk on macOS needs this or the window opens behind everything else
            'LSBackgroundOnly': False,
            'CFBundleShortVersionString': '2.4.0',
            'CFBundleVersion': '2.4.0',
            # The kit writes to ~/Documents; macOS shows this text in the
            # permission prompt, so the artist knows what is being asked.
            'NSDocumentsFolderUsageDescription':
                'Pixel Pomo Art Kit keeps your drawings in Documents/PixelPomoArtKit.',
        },
    )
