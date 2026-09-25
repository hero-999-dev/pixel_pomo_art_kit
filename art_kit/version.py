"""The kit's own version — the one place it is written (#v2.5.0).

The release tag is `v` + this string. `updater.py` compares it with the
latest GitHub release; the PyInstaller spec reads it for the .app's plist.
"""
VERSION = "2.9.0"
REPO = "hero-999-dev/pixel_pomo_art_kit"


def parse(text):
    """'v2.5.0' / '2.5.0' -> (2, 5, 0). Anything unparseable -> (0,)."""
    text = str(text).strip().lstrip("vV")
    parts = []
    for piece in text.split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break  # "0-rc1" -> 0: leading digits only, so a suffix can't inflate a number
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)
