"""Where the kit keeps the artist's files (#v2.5.0).

The rule, in one line: **the data never lives next to the program.** Move the
.exe from Downloads to the Desktop to a USB stick, drag a new .app over the
old one, delete the whole install — the drawings stay where they were.

| | drawings, exports, settings |
|---|---|
| frozen, **Windows** | `%LOCALAPPDATA%\\PixelPomoArtKit\\` |
| frozen, **macOS** | `~/Documents/PixelPomoArtKit/` (or Application Support if Documents is refused — see `app.fallback_dir`) |
| from source | the repository root, as before |

Up to #v2.4.0 the Windows build wrote `library/` **beside the .exe**. That
looked convenient and lost work twice over: moving the .exe left the drawings
behind, and unzipping a new version into a fresh folder started with an
empty library. The first run of #v2.5.0 finds that old folder and copies its
drawings in (`migrate_legacy`) — copies, never moves, so nothing can be lost
if the copy is interrupted.
"""
import os
import shutil
import sys
from pathlib import Path


def program_dir():
    """Beside the executable (frozen) or the repository root (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


DATA_ENV = "ARTKIT_DATA"


def data_dir():
    """The per-user folder the drawings live in. See the module docstring.

    `ARTKIT_DATA` overrides it outright (#v2.8.0). Windows answers
    "%LOCALAPPDATA%" with the folder of whoever RAN the program, not the
    folder beside it - so the same .exe, double-clicked from two accounts on
    one machine, keeps two libraries and the artist finds their work in a
    profile they did not expect. That is the correct default and it stays;
    this is the way to pin it to one folder when one person is both accounts.
    """
    override = os.environ.get(DATA_ENV)
    if override:
        return Path(override)
    if not getattr(sys, "frozen", False):
        return program_dir()
    if sys.platform == "darwin":
        return Path.home() / "Documents" / "PixelPomoArtKit"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "PixelPomoArtKit"
        return Path.home() / "AppData" / "Local" / "PixelPomoArtKit"
    # Linux, or anything else: XDG data home
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "PixelPomoArtKit"


def legacy_dirs():
    """Folders an older version may have written a `library/` into."""
    if not getattr(sys, "frozen", False):
        return []
    if sys.platform == "darwin":
        return []  # #v2.1.1 already moved Mac data to Documents
    return [program_dir()]


def migrate_legacy(data, candidates=None):
    """Copy drawings from an old beside-the-exe `library/` into `data/library`.

    Only files that do not already exist at the destination are copied, so
    running this on every start is safe and idempotent; the old folder is
    left exactly as it was. Returns the number of files copied."""
    candidates = legacy_dirs() if candidates is None else candidates
    dest = Path(data) / "library"
    copied = 0
    for folder in candidates:
        src = Path(folder) / "library"
        if not src.is_dir() or src.resolve() == dest.resolve():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for path in sorted(src.glob("*.json")):
            target = dest / path.name
            if target.exists():
                continue
            try:
                shutil.copy2(path, target)
                copied += 1
            except OSError:
                continue
        settings = Path(folder) / "settings.json"
        if settings.is_file() and not (Path(data) / "settings.json").exists():
            try:
                shutil.copy2(settings, Path(data) / "settings.json")
            except OSError:
                pass
    return copied


def open_in_file_manager(folder):
    """Show `folder` to the artist — Explorer, Finder, or xdg-open."""
    folder = str(folder)
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)  # noqa: S606 - a folder, not a command
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", folder])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", folder])
        return True
    except OSError:
        return False


def reveal(path):
    """Show `path`'s FILE to the artist, selected in the file manager.

    Not the same as `open_in_file_manager`, which opens a folder: this one
    highlights one file inside it (#v2.8.0), so "open file location" lands on
    the drawing the artist asked about rather than on a folder of forty JSONs
    they then have to read. Falls back to opening the containing folder where
    the platform has no select-a-file gesture, and returns False only when
    even that failed."""
    path = Path(path)
    folder = path.parent
    if not path.exists():
        return open_in_file_manager(folder) if folder.is_dir() else False
    try:
        if sys.platform.startswith("win"):
            import subprocess
            # /select, takes the path as ONE argument with no space after the
            # comma; explorer returns 1 even when it worked, so the exit code
            # is deliberately not checked.
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(str(path))}"])
            return True
        if sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", "-R", str(path)])
            return True
    except OSError:
        return open_in_file_manager(folder)
    return open_in_file_manager(folder)  # Linux: no standard "reveal"
