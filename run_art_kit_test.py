"""PyInstaller entry point for the TEST build (`TestPixelPomoArtKit.exe`).

The pre-release channel: this is the build that runs code which has NOT been
pushed or released yet, so that a version can be tried before it becomes
`PixelPomoArtKit.exe` on GitHub. Everything here exists because "unreleased
code" and "the artist's only copy of her drawings" must never be the same
gamble.

Three differences from `run_art_kit.py`, and nothing else:

1. **The updater is inert.** `updater.stage_windows()` unpacks the release's
   `PixelPomoArtKit.exe` out of the Windows zip and the hand-off script moves
   it over `sys.executable` — applied here that would leave a RELEASE binary
   wearing the test name, the one build you cannot trust to be what its
   filename says. It also keeps this build off the network: a frozen kit
   otherwise asks GitHub for the latest release 2.5s after the window opens.

2. **Its own data folder**, `<data>-Test`, seeded with a COPY of the real
   library on every start. Test drawings never reach the real folder, and a
   bug in unreleased code cannot reach the originals. The copy is why this is
   still a realistic test: the same drawings, in a folder nothing else writes
   to. `store.Library` keeps only a one-deep, per-session `.bak`, so a
   corruption noticed one session late is otherwise unrecoverable.

3. **"[TEST]" in the window title**, because the moment two builds have
   separate libraries, "where did my drawing go?" becomes a question worth
   never having to ask.

Nothing in `art_kit/` is modified — these are patched onto the modules, which
is how `app.py` reaches them (`updater.check()`, `paths.data_dir()`), so the
release build is unaffected by every line of this file.
"""
import sys
import tkinter as tk

from art_kit import paths, updater
from art_kit.version import VERSION

TITLE_SUFFIX = "  [TEST]"


# --- 1. the updater, made inert ----------------------------------------------
def _current_release(*_args, **_kwargs):
    """A release at the running version, so `Release.is_newer` is False: the
    startup check stays quiet and the UPDATE button answers truthfully — it
    reports the running version as current, which it is."""
    return updater.Release({"tag_name": f"v{VERSION}"})


updater.check = _current_release
updater.can_self_update = lambda: False


# --- 2. a data folder of its own, seeded from the real one -------------------
# Stashed on the module, not just in a local: if this file is ever executed
# twice in one interpreter (a test harness does exactly that), a plain
# `paths.data_dir` would capture the ALREADY-patched function and redirect to
# `<data>-Test-Test`. The frozen kit runs it once, so this only ever matters
# to the tests that keep the rest of this file honest.
_real_data_dir = getattr(paths, "_artkit_real_data_dir", paths.data_dir)
paths._artkit_real_data_dir = _real_data_dir


def _test_data_dir():
    """`%LOCALAPPDATA%\\PixelPomoArtKit-Test\\` and the macOS equivalent.

    Only when frozen: run from source the kit already writes to the repo root,
    which is not the artist's folder and needs no second copy."""
    real = _real_data_dir()
    if not getattr(sys, "frozen", False):
        return real
    return real.with_name(real.name + "-Test")


def _seed_from_real_library():
    """Copy the real drawings in — `migrate_legacy` copies, never moves, and
    only files the destination does not already have, so this is safe to run
    on every start: new real drawings appear next time, test-only drawings
    stay, and edits made here never travel back."""
    real, test = _real_data_dir(), _test_data_dir()
    if real == test:
        return
    try:
        paths.migrate_legacy(test, candidates=[real])
    except OSError:
        pass  # an unreadable real library is not a reason to refuse to start


paths.data_dir = _test_data_dir
_seed_from_real_library()


# --- 3. the window, marked ---------------------------------------------------
class _TestTk(tk.Tk):
    """Tk whose title always carries the suffix. Wrapped rather than set once,
    because `ArtKitApp` rewrites the title on every drawing it opens."""

    _artkit_test_window = True

    def title(self, string=None):
        if string is not None and not string.endswith(TITLE_SUFFIX):
            string += TITLE_SUFFIX
        return super().title(string)


# Guarded for the same reason as the data folder above: running this file
# twice would otherwise subclass the already-wrapped Tk.
if not getattr(tk.Tk, "_artkit_test_window", False):
    tk.Tk = _TestTk


from art_kit.__main__ import main  # noqa: E402  - after the patches, on purpose

main()
