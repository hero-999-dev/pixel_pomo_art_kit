"""F12: a picture of the window, and what the kit was doing (#v2.8.0).

The kit is tried by an artist who is not at the keyboard it is fixed from,
and "FIT still is not right" is a sentence where a picture is needed. F12
saves the window exactly as the artist sees it - a dialog or a menu over it
included - and beside it the numbers behind it: the zoom, the pane, where the
camera stands, the drawing's size, the filters. Two files a press,
`snap-<time>.png` and `.json`, in the data folder's `snapshots/`.

The picture is a grab of the SCREEN, cut to the window. Windows scales a
program that does not declare itself DPI-aware, so Tk's idea of where the
window is (in its own, scaled pixels) and the grab (in the screen's real
ones) disagree at 125 % or 150 % - the window's bounds are asked of the
desktop compositor instead, which answers in real pixels. With no screen to
grab at all (a locked or remote session) the numbers are still written, and
the JSON says why the picture is missing.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

FOLDER = "snapshots"


def _frame_hwnd(root):
    try:
        return int(root.wm_frame(), 16)
    except (ValueError, TypeError, AttributeError):
        return 0


def _compositor_bounds(hwnd):
    """The window's rectangle as DWM draws it - in physical pixels, and
    without the invisible resize border `GetWindowRect` counts in."""
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        dwm = ctypes.WinDLL("dwmapi")
        extended_frame_bounds = 9
        if dwm.DwmGetWindowAttribute(wintypes.HWND(hwnd), extended_frame_bounds,
                                     ctypes.byref(rect), ctypes.sizeof(rect)) == 0:
            if rect.right > rect.left and rect.bottom > rect.top:
                return rect.left, rect.top, rect.right, rect.bottom
    except (OSError, AttributeError, ValueError):
        pass
    return None


def _physical_window_rect(hwnd):
    """`GetWindowRect` asked from a thread that is per-monitor DPI aware,
    which makes Windows answer in physical pixels. Restored afterwards."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32")
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        per_monitor_v2 = ctypes.c_void_p(-4)
        old = user32.SetThreadDpiAwarenessContext(per_monitor_v2)
        try:
            rect = wintypes.RECT()
            if user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
                return rect.left, rect.top, rect.right, rect.bottom
        finally:
            if old:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
    except (OSError, AttributeError, ValueError):
        pass
    return None


def window_rect(root):
    """(left, top, right, bottom) of the kit's window on the screen, in the
    pixels a screen grab counts in."""
    if sys.platform.startswith("win"):
        hwnd = _frame_hwnd(root)
        if hwnd:
            rect = _compositor_bounds(hwnd) or _physical_window_rect(hwnd)
            if rect:
                return rect
    x, y = root.winfo_rootx(), root.winfo_rooty()
    return x, y, x + root.winfo_width(), y + root.winfo_height()


def grab(root):
    """The window as it is on screen now, a Pillow image."""
    from PIL import ImageGrab
    return ImageGrab.grab(bbox=window_rect(root), all_screens=True)


def save(root, folder, state):
    """Write `snap-<time>.png` and `snap-<time>.json` into `folder`.

    Returns (base path, error): error is None when the picture was taken,
    else why it was not - the JSON is written either way."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base, n = folder / f"snap-{stamp}", 2
    while base.with_suffix(".png").exists() or base.with_suffix(".json").exists():
        base, n = folder / f"snap-{stamp}-{n}", n + 1
    error = None
    try:
        grab(root).save(base.with_suffix(".png"))
    except Exception as exc:  # no screen to grab, no Pillow: the numbers still count
        error = f"{type(exc).__name__}: {exc}"
    state = dict(state, screenshot=None if error else base.with_suffix(".png").name,
                 grab_error=error)
    base.with_suffix(".json").write_text(
        json.dumps(state, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return base, error
