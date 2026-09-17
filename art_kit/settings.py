"""The artist's preferences: one small JSON file beside the library (#v2.4.0).

Favourite colours, the last tool used, the symmetry bar's settings. Nothing
here is a drawing — losing this file costs a few clicks, never any art — so
it is deliberately simpler than store.py: no format versioning, no backup,
and a file that cannot be read is replaced by the defaults rather than
reported.
"""
import json
from pathlib import Path

# "Klasik ana renkler": the six the artist asked for, primaries and
# secondaries, as the starting favourites. Editable, so held in settings
# rather than as a constant in the window.
DEFAULT_FAVOURITES = ["FF0000", "FF8000", "FFFF00", "00B000", "0000FF", "8000FF"]

DEFAULTS = {
    "favourites": list(DEFAULT_FAVOURITES),
    "tool": "draw",
    "symmetry": {"orientation": "vertical", "length": 5, "mode": "off"},
    "help_seen": False,
    # #v2.6.0
    "grid": {"c1": "232F28", "c2": "2A3A30"},  # the two checkerboard tones (theme.CHECKER)
    "show_grid": True,                          # the cell lines over the art
    "eraser": {"w": 1, "h": 1},
}


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(json.dumps(DEFAULTS))  # a deep copy
        self._load()

    def _load(self):
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(loaded, dict):
            return
        for key, value in loaded.items():
            if key in DEFAULTS and type(value) is type(DEFAULTS[key]):
                self.data[key] = value
        # Favourites are validated one by one: a hand-edited bad entry drops
        # that entry, not the whole list.
        self.data["favourites"] = [
            h.lstrip("#").upper() for h in self.data["favourites"]
            if isinstance(h, str) and _is_hex(h)]

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # preferences are not worth failing a stroke over

    # --- favourites -------------------------------------------------------
    @property
    def favourites(self):
        return list(self.data["favourites"])

    def add_favourite(self, hexcode):
        """Append (upper-case, no '#'); a colour already there is not
        duplicated. Returns True if the list changed."""
        hexcode = hexcode.lstrip("#").upper()
        if not _is_hex(hexcode) or hexcode in self.data["favourites"]:
            return False
        self.data["favourites"].append(hexcode)
        self.save()
        return True

    def remove_favourite(self, hexcode):
        hexcode = hexcode.lstrip("#").upper()
        if hexcode not in self.data["favourites"]:
            return False
        self.data["favourites"].remove(hexcode)
        self.save()
        return True

    # --- the rest -----------------------------------------------------------
    @property
    def tool(self):
        return self.data["tool"]

    @tool.setter
    def tool(self, name):
        if self.data["tool"] != name:
            self.data["tool"] = name
            self.save()

    @property
    def symmetry(self):
        merged = dict(DEFAULTS["symmetry"])
        merged.update(self.data["symmetry"])
        return merged

    def set_symmetry(self, orientation, length, mode=None):
        current = self.symmetry
        self.data["symmetry"] = {"orientation": orientation, "length": int(length),
                                 "mode": mode if mode is not None else current["mode"]}
        self.save()


    # --- #v2.6.0 ---------------------------------------------------------------
    @property
    def grid(self):
        merged = dict(DEFAULTS["grid"])
        for key, value in self.data["grid"].items():
            if key in merged and isinstance(value, str) and _is_hex(value):
                merged[key] = value.lstrip("#").upper()
        return merged

    def set_grid(self, c1=None, c2=None):
        grid = self.grid
        if c1 is not None and _is_hex(c1):
            grid["c1"] = c1.lstrip("#").upper()
        if c2 is not None and _is_hex(c2):
            grid["c2"] = c2.lstrip("#").upper()
        self.data["grid"] = grid
        self.save()

    def reset_grid(self):
        self.data["grid"] = dict(DEFAULTS["grid"])
        self.save()

    @property
    def show_grid(self):
        return bool(self.data["show_grid"])

    @show_grid.setter
    def show_grid(self, value):
        self.data["show_grid"] = bool(value)
        self.save()

    @property
    def eraser(self):
        merged = dict(DEFAULTS["eraser"])
        for key in ("w", "h"):
            value = self.data["eraser"].get(key)
            if isinstance(value, int) and 1 <= value <= 64:
                merged[key] = value
        return merged

    def set_eraser(self, w, h):
        self.data["eraser"] = {"w": max(1, min(64, int(w))), "h": max(1, min(64, int(h)))}
        self.save()


def _is_hex(text):
    text = text.lstrip("#")
    if len(text) != 6:
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True
