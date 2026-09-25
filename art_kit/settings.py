"""The artist's preferences: one small JSON file beside the library (#v2.4.0).

Favourite colours, the last tool used, the symmetry bar's settings. Nothing
here is a drawing — losing this file costs a few clicks, never any art — so
it is deliberately simpler than store.py: no format versioning, no backup,
and a file that cannot be read is replaced by the defaults rather than
reported.
"""
import colorsys
import json
import random
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
    "show_rulers": True,    # x1 x2 ... over the canvas, y1 y2 ... down its left (#v2.9.0)
    "offered_designs": [],  # bundled designs already put in the library once (#v2.9.0)
    "eraser": {"w": 1, "h": 1},
    # #v2.7.0
    "language": "en",
    "library_collapsed": False,
    # #v2.8.0 - the last answer to "what sits behind the empty pixels?", so
    # an artist who always wants white is asked once and defaulted after.
    # "transparent", or a six-digit hex colour.
    "export_background": "transparent",
    # ...and the last colour PICKED, kept even when the last answer was
    # transparent or white, so COLOUR opens on it again next time.
    "export_colour": "808080",
    "camera": "free",   # how the view may move: see app.CAMERA_MODES
    # Each artist's colour, "name" -> "RRGGBB": picked at random the first time
    # a name appears, then kept, so an initial on a library row is always the
    # same artist's colour (#v2.8.0).
    "artist_colours": {},
    # The artist's mark on exports (#v2.8.0, sixth test pass): the name ON the
    # picture - "none", "corner", "watermark" or "corner+watermark" - the name
    # INSIDE the file, and whether each export is written down in the log.
    "export_signature": "none",
    "export_metadata": True,
    "export_log": True,
    # #v2.9.0 - REVERSE's panel, as the artist last left it: the axis the
    # block is turned over across, the arrow, and the distance (one number,
    # or X and Y apart). See symmetry.reverse_copy.
    "reverse": {"axis": "y", "direction": "right", "spacing": "same",
                "gap": 0, "gap_x": 0, "gap_y": 0},
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

    @property
    def reverse(self):
        merged = dict(DEFAULTS["reverse"])
        for key, value in self.data["reverse"].items():
            if key in merged and type(value) is type(merged[key]):
                merged[key] = value
        return merged

    def set_reverse(self, **changes):
        current = self.reverse
        current.update({k: v for k, v in changes.items() if k in current})
        if current != self.data["reverse"]:
            self.data["reverse"] = current
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
    def offered_designs(self):
        return [k for k in self.data["offered_designs"] if isinstance(k, str)]

    def offer_designs(self, keys):
        keys = [k for k in keys if k not in self.data["offered_designs"]]
        if keys:
            self.data["offered_designs"] = self.offered_designs + keys
            self.save()

    @property
    def show_rulers(self):
        return bool(self.data["show_rulers"])

    @show_rulers.setter
    def show_rulers(self, value):
        self.data["show_rulers"] = bool(value)
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

    # --- #v2.7.0 ---------------------------------------------------------------
    @property
    def language(self):
        value = self.data.get("language", "en")
        return value if value in ("en", "tr", "pl", "de") else "en"

    @language.setter
    def language(self, code):
        code = code if code in ("en", "tr", "pl", "de") else "en"
        if self.data.get("language") != code:
            self.data["language"] = code
            self.save()

    # --- #v2.8.0 ---------------------------------------------------------------
    @property
    def export_background(self):
        """None for a transparent export, else an upper-case hex colour.

        None rather than the string, because that is what `engine_io`'s
        exporters take: the preference file keeps a word a human can read,
        the app keeps the value its exporters understand, and the
        translation happens in exactly one place."""
        value = self.data.get("export_background", "transparent")
        if not isinstance(value, str) or not _is_hex(value):
            return None
        return value.lstrip("#").upper()

    @export_background.setter
    def export_background(self, value):
        stored = "transparent" if value is None else str(value).lstrip("#").upper()
        if stored != "transparent" and not _is_hex(stored):
            return
        if self.data.get("export_background") != stored:
            self.data["export_background"] = stored
            self.save()

    @property
    def export_colour(self):
        """The last colour the artist mixed for an export, or None.

        Separate from `export_background` on purpose: that one is the ANSWER
        (transparent / white / a colour) and gets overwritten every time, so
        one white export would otherwise throw away a colour that took a
        minute to mix (#v2.8.0)."""
        value = self.data.get("export_colour", "")
        if not isinstance(value, str) or not _is_hex(value):
            return None
        return value.lstrip("#").upper()

    @export_colour.setter
    def export_colour(self, value):
        if value is None:
            return
        value = str(value).lstrip("#").upper()
        if not _is_hex(value) or self.data.get("export_colour") == value:
            return
        self.data["export_colour"] = value
        self.save()

    # The modes are app.CAMERA_MODES; named here rather than imported so the
    # preferences file stays readable on its own and settings.py keeps its
    # promise of importing nothing from the window.
    CAMERAS = ("free", "lock", "centre", "left", "right",
               "top_left", "top_right", "bottom_left", "bottom_right")

    @property
    def camera(self):
        value = self.data.get("camera", "free")
        return value if value in self.CAMERAS else "free"

    @camera.setter
    def camera(self, mode):
        if mode not in self.CAMERAS:
            return
        if self.data.get("camera") != mode:
            self.data["camera"] = mode
            self.save()

    def artist_colour(self, name):
        """`name`'s colour as "RRGGBB", chosen now if this is a new artist.

        Random, as asked - but not blindly: of a few dozen random bright,
        readable tones the one furthest in hue from every colour already
        given out is kept, so two artists who share an initial are still
        told apart by the one thing that differs. Saved the moment it is
        picked."""
        colours = self.data.setdefault("artist_colours", {})
        known = colours.get(name)
        if isinstance(known, str) and _is_hex(known):
            return known.upper()
        taken = []
        for other in colours.values():
            if isinstance(other, str) and _is_hex(other):
                r, g, b = (int(other[i:i + 2], 16) / 255 for i in (0, 2, 4))
                taken.append(colorsys.rgb_to_hsv(r, g, b)[0])
        rnd = random.Random()

        def distance(hue):
            return min((min(abs(hue - t), 1 - abs(hue - t)) for t in taken), default=1)

        hue = max((rnd.random() for _ in range(48)), key=distance)
        r, g, b = colorsys.hsv_to_rgb(hue, rnd.uniform(0.55, 0.75), rnd.uniform(0.88, 0.98))
        colours[name] = f"{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"
        self.save()
        return colours[name]

    # provenance.MODES, spelled out: the corner and the watermark are two
    # independent marks, so "both" is a value of its own.
    SIGNATURES = ("none", "corner", "watermark", "corner+watermark")

    @property
    def export_signature(self):
        """How an export is signed: "none", "corner", "watermark", or both."""
        value = self.data.get("export_signature", "none")
        return value if value in self.SIGNATURES else "none"

    @export_signature.setter
    def export_signature(self, mode):
        if mode in self.SIGNATURES and self.data.get("export_signature") != mode:
            self.data["export_signature"] = mode
            self.save()

    @property
    def export_metadata(self):
        """Does an export carry the artist's name and © inside the file?"""
        return bool(self.data.get("export_metadata", True))

    @export_metadata.setter
    def export_metadata(self, value):
        if self.data.get("export_metadata") != bool(value):
            self.data["export_metadata"] = bool(value)
            self.save()

    @property
    def export_log(self):
        """Is every export written down in export-log.jsonl? The artist's
        choice, ticked by default (sixth test pass)."""
        return bool(self.data.get("export_log", True))

    @export_log.setter
    def export_log(self, value):
        if self.data.get("export_log") != bool(value):
            self.data["export_log"] = bool(value)
            self.save()

    def rename_artist(self, old, new):
        """`old`'s colour goes with the new name (#v2.8.0, ninth test pass) -
        unless the new name already has one of its own, which it keeps."""
        colours = self.data.setdefault("artist_colours", {})
        if old in colours:
            kept = colours.pop(old)
            colours.setdefault(new, kept)
            self.save()

    def forget_artist(self, name):
        """An artist taken off every drawing gives their colour back."""
        colours = self.data.setdefault("artist_colours", {})
        if colours.pop(name, None) is not None:
            self.save()

    @property
    def library_collapsed(self):
        return bool(self.data.get("library_collapsed", False))

    @library_collapsed.setter
    def library_collapsed(self, value):
        self.data["library_collapsed"] = bool(value)
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
