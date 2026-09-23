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

# Drawing Patch 1 (#v2.8.0): the game ships these as Mir's own PNGs, not as
# generator output, so they travel with the kit the same way, into objects/
# where `engine_io.patch_sprite` looks when frozen.
_OBJECTS = os.path.normpath(os.path.join(os.path.dirname(_GEN), os.pardir, 'assets', 'objects'))
_PATCH = [os.path.join(_OBJECTS, name) for name in (
    'flower_anthurium.png', 'flower_pilea_0.png', 'flower_pilea_1.png',
    'flower_sundew_0.png', 'flower_sundew_1.png')]
_missing = [p for p in _PATCH if not os.path.exists(p)]
if _missing:
    raise SystemExit(f'Drawing Patch sprites not found: {_missing}')

# The tomato-and-brush icon (#v2.4.0). Both files are generated from the same
# 16x16 grid by `python -m art_kit.branding` and committed under assets/, so
# the build needs nothing beyond the checkout. The window's own icon is drawn
# at run time from that grid; these are for the .exe / .app and Finder.
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(SPEC)), 'assets')

# One version string, read from the package rather than repeated here.
sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))
from art_kit.version import VERSION as _VERSION  # noqa: E402
_ICO = os.path.join(_ASSETS, 'icon.ico')
_ICNS = os.path.join(_ASSETS, 'icon.icns')

# A TEST build — `ARTKIT_TEST_BUILD=1 pyinstaller PixelPomoArtKit.spec` — is
# the same kit under a different name, frozen from an entry point that makes
# the updater inert (see run_art_kit_test.py for why a test binary must never
# swap itself). One spec rather than a second copy, so the release recipe
# cannot drift from the test one; the variable is unset in CI and everywhere
# else, so `pyinstaller PixelPomoArtKit.spec` still builds exactly what it did.
# The differing name also gives PyInstaller its own build/ workpath, so the two
# builds do not overwrite each other's cache.
_TEST = os.environ.get('ARTKIT_TEST_BUILD') == '1'
_SCRIPT = 'run_art_kit_test.py' if _TEST else 'run_art_kit.py'
_NAME = 'TestPixelPomoArtKit' if _TEST else 'PixelPomoArtKit'


a = Analysis(
    [_SCRIPT],
    pathex=['.'],
    binaries=[],
    datas=[(_GEN, '.')] + [(p, 'objects') for p in _PATCH],
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
    name=_NAME,
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
        name=f'{_NAME}.app',
        icon=_ICNS,
        bundle_identifier='com.pixelpomo.artkit',
        info_plist={
            'NSHighResolutionCapable': True,
            # Tk on macOS needs this or the window opens behind everything else
            'LSBackgroundOnly': False,
            'CFBundleShortVersionString': _VERSION,
            'CFBundleVersion': _VERSION,
            # The kit writes to ~/Documents; macOS shows this text in the
            # permission prompt, so the artist knows what is being asked.
            'NSDocumentsFolderUsageDescription':
                'Pixel Pomo Art Kit keeps your drawings in Documents/PixelPomoArtKit.',
        },
    )
