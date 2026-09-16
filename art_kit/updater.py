"""Updates from GitHub Releases (#v2.5.0).

* `check()` asks the GitHub API for the latest release of the kit's repo —
  public, so no token — and says whether it is newer than the running
  `VERSION`.
* On **Windows** `download()` fetches the Windows zip and `stage_windows()`
  unpacks the new .exe beside the running one and writes a small `.cmd` that
  waits for this process to exit, swaps the two files, and relaunches. A
  running .exe cannot overwrite itself, hence the hand-off; the old .exe is
  kept as `PixelPomoArtKit.old.exe` for one version so a bad update can be
  reverted by renaming.
* On **macOS** the kit only opens the release page: replacing a `.app` behind
  Gatekeeper's back is exactly what the quarantine machinery is built to
  stop, and the artist has a working two-step recipe for it already
  (READ-ME-FIRST-MAC.txt).

**Nothing here touches the drawings.** They live in the per-user data folder
(`paths.data_dir()`), not beside the program, so swapping the program cannot
reach them — and `backup_library()` zips them once more before an update is
applied, belt and braces.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from art_kit.version import REPO, VERSION, parse

API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
WINDOWS_ASSET = "PixelPomoArtKit-windows.zip"
EXE_NAME = "PixelPomoArtKit.exe"
USER_AGENT = f"PixelPomoArtKit/{VERSION}"


class Release:
    def __init__(self, data):
        self.tag = data.get("tag_name", "")
        self.version = parse(self.tag)
        self.url = data.get("html_url", RELEASES_PAGE)
        self.notes = data.get("body") or ""
        self.assets = {a.get("name"): a.get("browser_download_url")
                       for a in data.get("assets", []) if a.get("name")}

    @property
    def is_newer(self):
        return self.version > parse(VERSION)

    def __repr__(self):
        return f"Release({self.tag}, newer={self.is_newer})"


def check(timeout=8, opener=None):
    """The latest release, or raises (URLError, ValueError, OSError). The
    caller decides whether that is worth a dialog — on a startup check it is
    not, on a button press it is."""
    req = urllib.request.Request(API, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    opener = opener or urllib.request.urlopen
    with opener(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return Release(data)


def download(url, dest, progress=None, opener=None, timeout=30):
    """Fetch `url` to `dest` (a file path), calling `progress(done, total)`
    as it goes. Writes to a sibling temp file first, so an interrupted
    download never leaves a half zip under the real name."""
    dest = Path(dest)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = opener or urllib.request.urlopen
    tmp = dest.with_name(dest.name + ".part")
    with opener(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    os.replace(tmp, dest)
    return dest


def backup_library(data_dir, tag):
    """`<data>/backups/library-before-<tag>-<stamp>.zip`. Returns the path, or
    None if there was nothing to back up."""
    data_dir = Path(data_dir)
    lib = data_dir / "library"
    files = sorted(lib.glob("*.json")) if lib.is_dir() else []
    if not files:
        return None
    out_dir = data_dir / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"library-before-{tag.lstrip('v')}-{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.name)
    return out


def stage_windows(zip_path, exe_path=None):
    """Unpack the new .exe beside the running one as `PixelPomoArtKit.new.exe`
    and write the hand-off script. Returns (new_exe, script). Raises
    ValueError if the zip does not contain the .exe."""
    exe_path = Path(exe_path or sys.executable)
    folder = exe_path.parent
    new_exe = folder / "PixelPomoArtKit.new.exe"
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(EXE_NAME.lower())]
        if not names:
            raise ValueError(f"{zip_path} has no {EXE_NAME} in it")
        with zf.open(names[0]) as src, open(new_exe, "wb") as dst:
            shutil.copyfileobj(src, dst)
    script = folder / "PixelPomoArtKit-update.cmd"
    script.write_text(_handoff_script(exe_path, new_exe, os.getpid()), encoding="ascii")
    return new_exe, script


def _handoff_script(exe_path, new_exe, pid):
    """Wait for `pid` to exit, keep the old .exe as .old.exe, move the new
    one into place, relaunch, and remove this script. Plain cmd, so it runs
    on any Windows with nothing installed."""
    old = exe_path.with_name("PixelPomoArtKit.old.exe")
    return "\r\n".join([
        "@echo off",
        "setlocal",
        f"set PID={pid}",
        ":wait",
        'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >NUL",
        "  goto wait",
        ")",
        f'if exist "{old}" del /f /q "{old}"',
        f'move /y "{exe_path}" "{old}" >NUL',
        f'move /y "{new_exe}" "{exe_path}" >NUL',
        f'start "" "{exe_path}"',
        '(goto) 2>nul & del "%~f0"',
        "",
    ])


def launch_handoff(script):
    """Start the hand-off script in its own hidden console, so it survives
    this process exiting (which is the whole point).

    CREATE_NO_WINDOW, not DETACHED_PROCESS: a detached cmd has no console at
    all, and `tasklist | find` then blocks forever on the pipe — the swap
    never happened in the first dry run. A hidden console gives the tools
    what they need and shows the artist nothing."""
    flags = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
             | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    subprocess.Popen(["cmd.exe", "/c", str(script)], creationflags=flags, close_fds=True,
                     cwd=str(Path(script).parent))


def can_self_update():
    """Only a frozen Windows build can swap its own .exe."""
    return bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win")


def temp_download_path(tag):
    return Path(tempfile.gettempdir()) / f"PixelPomoArtKit-{tag}.zip"
