"""The window. Three panes: the library, the canvas, the tools.

Pointer handling is deliberately split - `on_canvas_*` take GRID coordinates and
carry all the behaviour, while the tkinter bindings do nothing but turn a pixel
position into a cell. That is what lets the interaction be tested without a
display, and it keeps the interesting code out of the event handlers.

One integration wrinkle that lives here rather than in the model: `History`
undoes/redoes by swapping `.current` to a whole different `Drawing` object (a
snapshot copy, see model.py), while `Library` recognises drawings by the
identity of the object it was handed via `add()`. Saving `history.current`
straight after an undo would hand the library an object it has never seen and
raise KeyError. `_selected` is kept as the stable, library-registered object;
`_after_change` reconciles its content from `history.current` before saving,
so the library and the on-disk file always describe the same drawing the
library thinks it is holding.

#v2.4.0 reworked the whole pane for the artists (see log.md): matcha theme,
SAVE + Ctrl/Cmd shortcuts, favourites, an editable hex ink, the symmetry bar,
a new-drawing size dialog, a help overlay, previews and size in the
bottom-right corner - and, underneath all of it, image-based rendering with
an incrementally updated library list, because rebuilding 59 thumbnails out
of thousands of canvas rectangles on every stroke was freezing the app.
"""
import colorsys
import math
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from collections import Counter
from datetime import datetime
from fractions import Fraction
from tkinter import filedialog
from pathlib import Path

from art_kit import (branding, dialogs, engine_io, i18n, paths, provenance, raster, snapshot,
                     store, symmetry, theme, updater)
from art_kit.i18n import t
from art_kit.model import Drawing, History, LETTERS, Palette, hex_to_rgba
from art_kit.settings import Settings
from art_kit.version import VERSION

# The two answers `BackgroundDialog` needs that no colour can stand for
# (#v2.8.0). `None` already means transparent, so "cancelled" and "open the
# picker" have to be values of their own or a cancelled export would silently
# write a transparent file.
CANCELLED = object()
CHOOSE = object()

# 1024 px a cell: one pixel of the drawing more than fills the pane, which is
# as far in as "zoom in on a single pixel" can mean (#v2.8.0). It used to stop
# at 48 because the view was rendered whole - a w*z by h*z bitmap, growing with
# the SQUARE of the zoom - and going further would have asked Tk for hundreds
# of megapixels. `_draw_main` renders only what is inside the pane now, so the
# cost of a repaint no longer depends on the zoom at all and the ceiling is
# free to be a number about the artist rather than about memory.
# 1 px a cell at the bottom: the artist asked to be able to pull all the way
# back to the sprite's own size, in every camera mode (#v2.8.0). 1024 at the
# top: one pixel more than fills the pane.
MIN_ZOOM, MAX_ZOOM = 1, 1024

# The stops a wheel notch lands on. A LADDER, not an arithmetic step, because
# a step computed from the current zoom is not reversible: `z + max(2, z//4)`
# took 16 up to 20, and 20 back down to 15. Wheel up then wheel down has to
# come back to where it was, or every stray notch leaves the artist slightly
# off the zoom they had chosen. Roughly geometric, so a notch feels the same
# size at 4 px a cell and at 400.
ZOOM_STOPS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128,
              192, 256, 384, 512, 768, 1024)
# ...and below 1 px a cell (#v2.8.0, third test pass: "sağ alttaki en küçük
# kısma kadar küçülme olsun hep"). A drawing hundreds of cells wide has to be
# able to shrink until it fits, down to the scale of its smallest picture in
# the corner (`min_zoom`). There a screen pixel is the AVERAGE of the n x n
# cells it stands for, as in that picture. Exact fractions, never floats: in
# floating point 3 // 0.1 is 29, and the pointer would paint the wrong cell.
ZOOM_OUT_STOPS = tuple(Fraction(1, n) for n in (64, 48, 32, 24, 16, 12, 8, 6, 4, 3, 2))
# What to assume the drawing pane is before Tk has laid it out. A real number
# matters: falling back to "render the whole drawing" would, at 1024 px a cell,
# ask for a bitmap of tens of gigabytes on the first paint of a window that has
# not been mapped yet. Every path that clips to the pane goes through
# `_viewport`, so one nominal size keeps all of them bounded.
NOMINAL_VIEW = (1200, 900)

# How the camera may move (#v2.8.0). The artists wanted the freedom, and then
# wanted to be able to give some of it back: a drawing worked left to right is
# easier to follow when the view cannot drift up and down, and the old
# top-left behaviour is what the muscle memory from #v2.7.0 expects.
#
# LOCK is the one mode that also holds the ZOOM (#v2.8.0, second test pass:
# "lock halinde kamera acisi sabit olmasi lazim" - a locked camera that still
# zoomed out was not locked). Under it nothing the artist does moves the view:
# not the wheel, not + / -, not FIT, not a pan, not a drag against the edge.
# Each drawing keeps its own frozen view for as long as LOCK stays on, and a
# pan or a zoom that LOCK swallowed blinks the LOCK button, so a dead wheel
# reads as "locked" rather than as a frozen app. Every other mode leaves the
# zoom free.
CAM_FREE = "free"              # anywhere, as long as a cell stays on screen
CAM_LOCK = "lock"              # frozen exactly where it was when LOCK was pressed
CAM_CENTRE = "centre"
CAM_LEFT = "left"
CAM_RIGHT = "right"
CAM_TOP_LEFT = "top_left"
CAM_TOP_RIGHT = "top_right"
CAM_BOTTOM_LEFT = "bottom_left"
CAM_BOTTOM_RIGHT = "bottom_right"

# Each mode is just where the view is allowed to sit on each axis, so there is
# one rule and ten names for it rather than ten special cases:
#
#   "free"  anywhere, down to the last cell (`_scroll_bounds`)
#   "hold"  frozen where the camera was standing when LOCK was pressed. Up to
#           #v2.8.0 there were two half-locks, one per axis, each centring the
#           axis it froze; an artist who has framed a view wants THAT view
#           held, not a centred one, and wants it held on both axes.
#   "min" / "mid" / "max"
#           free to roam INSIDE the drawing while the drawing is bigger than
#           the pane - which is what "you can still move around when you are
#           zoomed in" means - and parked against that edge once it is not.
#           Zoomed in they are indistinguishable; the alignment question only
#           exists when there is slack, so that is the only time they answer
#           it differently.
CAMERA_ANCHORS = {
    CAM_FREE: ("free", "free"),
    CAM_LOCK: ("hold", "hold"),
    CAM_LEFT: ("min", "mid"),
    CAM_CENTRE: ("mid", "mid"),
    CAM_RIGHT: ("max", "mid"),
    CAM_TOP_LEFT: ("min", "min"),
    CAM_TOP_RIGHT: ("max", "min"),
    CAM_BOTTOM_LEFT: ("min", "max"),
    CAM_BOTTOM_RIGHT: ("max", "max"),
}
CAMERA_MODES = tuple(CAMERA_ANCHORS)
CAMERA_NAMES = {
    CAM_FREE: "cam_free", CAM_LOCK: "cam_lock",
    CAM_LEFT: "cam_left", CAM_CENTRE: "cam_centre", CAM_RIGHT: "cam_right",
    CAM_TOP_LEFT: "cam_top_left", CAM_TOP_RIGHT: "cam_top_right",
    CAM_BOTTOM_LEFT: "cam_bottom_left", CAM_BOTTOM_RIGHT: "cam_bottom_right",
}
DEFAULT_ZOOM = 20
CHECKER = theme.CHECKER
# The ▾ list's arrow: at the words while shut, down while open (#v2.8.0).
# (Drawn as icons where Pillow is there; these are the text stand-ins, and
# U+25BA, not U+25B6, which a font may swap for an emoji.)
FILTER_SHUT, FILTER_OPEN = "\u25ba", "\u25bc"
CHECKER_CELLS = 2    # a square of the checkerboard is 2 x 2 cells ...
CHECKER_MIN_PX = 4   # ... and never under 4 px on screen: see `_checker_cells`
PREVIEW_ZOOM = 6  # the fixed "squint test" scale, independent of the editing zoom
THUMB_PX = 64     # a library thumbnail fits in this square (2x for 16-cell art)
ONE_X_BOX = 64    # the "1x" preview's box; a bigger drawing is shown at 1/2x, 1/3x...

ROW_BG = theme.PANEL
ROW_BG_SELECTED = theme.SELECTED_ROW

# The engine's palette letters, ONLY so the eyedropper can resolve a tone it
# picked up from an imported flower to a real colour. The artist never chooses
# letters directly — they draw in real colours; turning a finished drawing
# back into engine letters/palette is the developer's job, done in code.
SLOTS = [("d", "dark"), ("m", "mid"), ("l", "light"), ("C", "centre"),
         ("x", "bloom seam"), ("S", "stem"), ("G", "leaf"), ("k", "vein"),
         ("o", "plant seam")]

# Ready colours: Pixel Pomo's own theme tones plus a pixel-art staple range.
def _by_similarity(hexcodes):
    """The ready colours, ordered so neighbours in the grid look like
    neighbours (#v2.8.0).

    Hue first, in buckets rather than raw, so a marginally bluer blue cannot
    jump the queue on a rounding difference; then light to dark inside a hue,
    which is how a row of tints for one colour wants to read. Near-neutrals
    drop to the end as a single white-to-black ramp: a grey sitting between a
    red and an orange teaches the eye nothing, and it is the greys an artist
    reaches for by name rather than by neighbourhood.

    Neutral is judged by CHROMA - how far the channels spread - not by HSV
    saturation. Saturation is chroma divided by value, so it reports a
    near-black like #1E1E2E as a third saturated and would file it among the
    violets; the spread between its channels is sixteen values out of 255,
    which is what the eye actually sees.

    Sorted here rather than written out in order, because the list is edited
    by hand and a hand-sorted list is one careless paste away from wrong."""
    def key(hexcode):
        h = hexcode.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        hue, _sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        chroma = (max(r, g, b) - min(r, g, b)) / 255
        neutral = chroma < 0.12
        return (1 if neutral else 0, 0 if neutral else round(hue * 24), -val, hexcode)
    return sorted(hexcodes, key=key)


# Six rows of eight (#v2.8.0, was four rows short of that): the two the
# artists asked for fill the gaps the first set left - skin and terracotta,
# the teals and cyans between green and blue, an olive, and the pinks and
# plums either side of magenta.
READY = _by_similarity([
    # reds, warm oranges, yellows
    "FF5A5F", "CC2A3D", "9C1B2E", "F2994A", "F2C94C", "F7EFDD",
    "FFC9B5", "D98E73", "7A3B2E", "FFD166", "BFA100", "FF9F1C",
    # greens
    "5FBF4A", "3E8E36", "1E5A24", "27AE60", "6FCF97", "A7C957", "4B5D2A",
    # teal to blue
    "1B7A57", "2EC4B6", "0E7490", "56CCF2", "A9D6E5",
    "2D9CDB", "2F80ED", "1B4F72",
    # violet, pink, plum
    "8E4FE0", "BB6BD9", "6B2FA0", "6C5CE7", "3A2E6B",
    "D9A7E0", "F4A6C0", "FF77A9", "7F1D4B",
    # browns
    "8B5A2B", "5D4037", "3E2723",
    # neutrals
    "CDD6F4", "E8E2D0", "B0BEC5", "9AA0B5", "5C6178", "1E1E2E",
    "000000", "808080", "FFFFFF",
])

# The tools pane. Every horizontal thing in it — swatch grids, the colour
# panel, the previews — is INNER_W wide, so their left and right edges line up
# (#v2.4.0, item 4).
TOOLS_W = 274
PAD = 8
SCROLLBAR_W = 14  # the tools pane scrolls (#v2.6.0); its bar is the right margin
INNER_W = TOOLS_W - 1 - PAD - SCROLLBAR_W  # minus the separator line, the left pad, the bar
# Eight swatches a row (#v2.5.0, was six): the symmetry block moved under
# the colour panel and the pane has to fit an 820px-tall window.
SWATCH_COLS = 8
PICKER_W, SV_H, HUE_H = INNER_W, 100, 14
LIBRARY_W = 220
LIBRARY_RAIL = 18  # hamburger + scrollbar column (#v2.7.0, item 11)
# The four edges of the grid are its resize grabs (#v2.8.0). Up to #v2.7.0
# there was one, on the bottom-right corner, drawn as an accent triangle, and
# it changed the ZOOM - which is not what a corner grab means anywhere else.
EDGE_GRAB = 10     # px OUTSIDE an edge that still count as grabbing it
# ...and at most this far INSIDE it (#v2.8.0, second test pass). The band
# used to be EDGE_GRAB on both sides, which at 24 px a cell covered 40% of
# every edge cell and at 8 px more than all of it: painting along the border
# kept turning into a resize. Outside there is nothing to paint, so the band
# there stays generous; inside, every pixel belongs to an edge cell, so the
# band is a sliver - an eighth of a cell, never more than this, and nothing
# at all below 8 px a cell.
EDGE_GRAB_INSIDE = 3
# What the pointer looks like over each grab. The corners are the diagonal
# arrows every editor uses, so a corner reads as a corner without a marker.
_EDGE_CURSORS = {
    ("left",): "sb_h_double_arrow", ("right",): "sb_h_double_arrow",
    ("top",): "sb_v_double_arrow", ("bottom",): "sb_v_double_arrow",
    ("left", "top"): "top_left_corner", ("right", "top"): "top_right_corner",
    ("left", "bottom"): "bottom_left_corner", ("right", "bottom"): "bottom_right_corner",
}
EDGES = ("left", "right", "top", "bottom")

NEW_SIZE = 32  # new drawings: room for the trees and pets that are coming
# Drawing sizes have no cap (#v2.8.0, second test pass: "o limiti tamamen
# kaldıralım, tamamen custom yapalım"). Up to then a side stopped at 64 cells,
# the biggest tree. What is left guards the machine, not the art:
BIG_CELLS = 512 * 512   # beyond this many cells the size dialog asks first -
                        # every stroke saves and re-renders the whole grid
HUGE_SIDE = 4096        # and beyond this many a side it says no: 60000 typed
                        # for 600 would ask for billions of cells and take
                        # the window down with it
ERASER_MAX = 64         # the eraser's own footprint, which is no drawing size

TOOLS = ("draw", "erase", "fill", "select")
AUTOSCROLL_MARGIN = 24  # px from the canvas edge at which a drag starts scrolling (#v2.6.0)


def _lighten(hexcol, amount=0.25):
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = (int(v + (255 - v) * amount) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _pads(value):
    """A pack padding as (left, right), however Tk hands it back: a number,
    a pair, or the string "8 14"."""
    if isinstance(value, (tuple, list)):
        parts = [int(float(str(v))) for v in value]
    else:
        parts = [int(float(v)) for v in str(value).split()]
    return (parts[0], parts[-1]) if parts else (0, 0)


def _darken(hexcol, amount=0.25):
    h = hexcol.lstrip("#")
    r, g, b = (int(int(h[i:i + 2], 16) * (1 - amount)) for i in (0, 2, 4))
    return f"#{r:02x}{g:02x}{b:02x}"


def base_dir():
    """Where the app keeps `library/`, `exports/` and `settings.json`.

    - Frozen on **macOS**: `~/Documents/PixelPomoArtKit/`.
    - Frozen on **Windows**: `%LOCALAPPDATA%\\PixelPomoArtKit\\` (#v2.5.0 —
      it used to be beside the .exe, and moving or re-downloading the .exe
      left the drawings behind).
    - From source: the repo root.

    Never inside or beside the program, on either platform: a program is the
    thing that gets moved, replaced and deleted, and the drawings must survive
    all three. See `paths.py` for the whole argument (and #v2.1.1 for the
    macOS half of it: `sys.executable` is INSIDE the .app bundle there).
    """
    return paths.data_dir()


def fallback_dir():
    """Where a frozen macOS build writes when `~/Documents` is refused.

    macOS asks the user, on first access, whether an app may touch Documents;
    an unsigned app that gets a "Don't Allow" (or runs before the prompt is
    answered) raises PermissionError on every save — and until #v2.4.0 that
    traceback went to a stderr nobody sees, so the kit looked like it saved
    and had not ("kapatinca kaydetmiyor"). Application Support needs no
    permission. Windows and source runs never need this."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PixelPomoArtKit"
    return base_dir()


def engine_sprite_dir():
    """Where the export dialog opens. Deliberately NOT the game's asset folder:
    pixel_pomo is read-only to this app, and defaulting there risks overwriting
    a shipped flower_*.png (the very files the byte-equality tests trust). The
    artist browses over by hand if they really mean to update the game."""
    return base_dir() / "exports"


ENGINE_SPRITE_DIR = engine_sprite_dir()  # the older name, for callers that import it


def _hex(px):
    r, g, b, _a = px
    return f"#{r:02x}{g:02x}{b:02x}"


def is_test_build(root):
    """Is this the TEST build (`run_art_kit_test.py`)? Its window class says
    so - the one thing it patches that the kit can see."""
    return bool(getattr(root, "_artkit_test_window", False))


STATUS_MAX = 48   # characters: a longer message is cut in the MIDDLE, not at its start


def _shorten(text, limit=STATUS_MAX):
    text = str(text)
    if len(text) <= limit:
        return text
    keep = limit - 1
    return text[:keep - keep // 2] + "\u2026" + text[len(text) - keep // 2:]


def _line_cells(c0, r0, c1, r1):
    """Every cell on the straight line from (c0,r0) to (c1,r1), inclusive.

    Integer Bresenham. A fast drag hands tkinter sparse motion events — cells
    apart — and painting only the reported cells leaves a dotted trail where
    the artist drew a stroke."""
    cells = []
    dc, dr = abs(c1 - c0), -abs(r1 - r0)
    sc, sr = (1 if c0 < c1 else -1), (1 if r0 < r1 else -1)
    err = dc + dr
    while True:
        cells.append((c0, r0))
        if c0 == c1 and r0 == r1:
            return cells
        e2 = 2 * err
        if e2 >= dr:
            err += dr
            c0 += sc
        if e2 <= dc:
            err += dc
            r0 += sr


def size_presets():
    """(label, cols, rows) for the new-drawing / resize dialog (#v2.4.0, item
    13). Read from the engine where the engine has an opinion — a flower's
    height, a tree's tiles — so the dialog cannot drift from what exports."""
    g = engine_io.gen_objects()
    presets = [(t("preset_flower"), 16, 16), (t("preset_bug"), 8, 8),
               (t("preset_bush"), 16, 16), (t("preset_rock"), 16, 16)]
    for tiles in sorted(set(g.TREE_TILES)):
        px = tiles * g.TREE_PX_PER_TILE
        presets.append((t("preset_tree", n=tiles), px, px))
    return presets


class ArtKitApp:
    def __init__(self, root, library, settings=None, check_updates=None):
        self.root = root
        self.library = library
        self.settings = settings or Settings(library.root.parent / "settings.json")
        self.tool = self.settings.tool if self.settings.tool in TOOLS else "draw"
        self.ink = hex_to_rgba("D93645")  # a real colour; letters are engine-side
        self.zoom_level = DEFAULT_ZOOM
        self._histories = {}
        self._painting = False
        self._last_cell = None
        self._stroke_cells = []   # what the fast path has to paint for this event
        self.history = None
        self._selected = None  # the library-registered Drawing, see module docstring
        self._rows = {}        # id(drawing) -> row widgets, built once (item 7)
        self._images = {}      # every PhotoImage on screen, kept alive here
        self._save_error_shown = False
        # symmetry (#v2.4.0 item 14, redesigned #v2.5.0: three modes)
        sym = self.settings.symmetry
        self.symmetry_mode = sym.get("mode") if sym.get("mode") in symmetry.MODES else symmetry.OFF
        self.symmetry_bar = None
        self._sym_orientation = (sym.get("orientation") if sym.get("orientation") in symmetry.ORIENTATIONS
                                 else symmetry.VERTICAL)
        self._sym_length = int(sym.get("length", 5))
        self._placing_bar = self.symmetry_mode == symmetry.MIRROR  # a bar has to be placed first
        self._dragging_bar = None  # (dcol, drow) grab offset while the bar is being moved
        self._resizing_bar = None  # the fixed end's axis coordinate while an end is dragged (#v2.6.0)
        self._help = None
        self._update_release = None  # the newer Release, once a check has found one
        # #v2.6.0
        self.show_grid = self.settings.show_grid
        eraser = self.settings.eraser
        self.eraser_size = (eraser["w"], eraser["h"])
        self.selection = None      # (c0, r0, c1, r1) inclusive, normalised
        self._selecting = None     # the anchor cell while a selection is being dragged out
        self.clipboard = None      # (cells, w, h) from Ctrl+C / Ctrl+X
        self.floating = None       # {"cells", "w", "h", "col", "row"}: a pasted/lifted block
        self._dragging_float = None
        self._filter = None        # the \u25be ticks: None is ALL, else {(kind, name)} (#v2.8.0)
        self._filter_open = False  # the \u25be list is showing
        self._hover_cell = None
        self._paste_armed = False  # after Ctrl+C, the next click pastes (#v2.7.0, item 7)
        self._library_collapsed = bool(self.settings.library_collapsed)
        self._edge_drag = None     # {"edge", "from"}: a grid edge being dragged
        # #v2.8.0: the zoom's undo lives in the drawing's History now, in
        # order with the strokes, so Ctrl+Z means "the last thing that
        # happened" whichever kind of thing it was.
        self._float_lift = False   # the floating block was lifted, and its stroke is still open
        self.camera_mode = self.settings.camera
        self._locked_at = None     # the canvas point LOCK froze the view at
        self._lock_frames = {}     # id(drawing) -> (zoom, point): each drawing's frozen view
        self._sym_frames = {}      # id(drawing) -> (mode, bar, placing): each drawing's symmetry
        self.looking = False       # LOOK: the art as it looks, and nothing drawn (#v2.8.0)
        self._status_fade = None   # the pending dim of a flashed status message
        self._fitted = False       # a real (not nominal) pane has been fitted to
        self._fit_held = False     # the view IS the fit, and follows the pane (`_redraw_viewport`)
        self._fit_pane = None      # the pane size that fit was made for
        self._grid_preview = None  # {"c1"|"c2": hex} while the grid colour picker is open
        self._content_version = 0  # bumped whenever the open drawing's cells may have changed
        self._totals_key = None    # what `_totals` was counted for
        self._totals = (0, 0)
        self._render_key = None    # what `_render_image` was rendered for
        self._render_image = None  # the open drawing, rendered whole (a Pillow image)
        self._tile_box = None      # (col, row, cells a pixel) of the view's picture
        self._panning = False      # space is held: a left-drag moves the camera
        self._pan_from = None      # where a pan grab started
        i18n.set_language(self.settings.language)

        theme.setup(root)
        branding.apply_window_icon(root)
        root.title("Pixel Pomo Art Kit")
        self._build()
        self._pin_chrome()
        root.protocol("WM_DELETE_WINDOW", self.close)
        if theme.IS_MAC:
            # Cmd+Q bypasses WM_DELETE_WINDOW on macOS; this is the hook Tk
            # gives for it, and without it a quit skips the final save.
            try:
                root.createcommand("::tk::mac::Quit", self.close)
            except tk.TclError:
                pass
        if library.drawings:
            self.select(library.drawings[0])
        # A frozen build looks for a newer release once, quietly, after the
        # window is up. From source (and in tests) only the UPDATE button asks.
        if check_updates is None:
            check_updates = bool(getattr(sys, "frozen", False))
        if check_updates:
            root.after(2500, lambda: self.check_for_update(silent=True))

    # ---- updates (#v2.5.0) ---------------------------------------------------
    def check_for_update(self, silent=False):
        """Ask GitHub for the latest release on a worker thread; report on
        the Tk thread. `silent` is the startup check: failures and "already
        current" say nothing, only a newer release lights the button up."""
        if not silent:
            self._set_status(t("checking"))

        def work():
            try:
                release = updater.check()
                error = None
            except Exception as exc:  # network, JSON, anything: never crash the kit
                release, error = None, exc
            self.root.after(0, lambda: self._on_update_result(release, error, silent))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_result(self, release, error, silent):
        if error is not None:
            if not silent:
                self._set_status(t("check_failed"), error=True)
                dialogs.showwarning(
                    "Pixel Pomo Art Kit",
                    t("update_unreachable", error=error, url=updater.RELEASES_PAGE),
                    parent=self.root)
            return
        if not release.is_newer:
            self._update_release = None
            if not silent:
                self._set_status(t("is_current", v=VERSION), flash=True)
                dialogs.showinfo("Pixel Pomo Art Kit", t("update_latest", v=VERSION),
                                 parent=self.root)
            return
        self._update_release = release
        self._show_update_available()
        self._set_status(t("available", tag=release.tag), flash=True)
        if not silent:
            self.offer_update(release)

    def _show_update_available(self):
        """UPDATE lit up with the new tag - again after a language change,
        which re-texts the button to plain UPDATE."""
        release = self._update_release
        if release is not None:
            self._update_button.configure(text=f"{t('update')} \u25cf {release.tag}",
                                          bg=theme.WORK, fg=theme.ON_ACCENT,
                                          activebackground=theme.ACCENT)

    def offer_update(self, release):
        """The dialog. Windows swaps the .exe itself; everywhere else the
        release page opens in the browser."""
        data = str(self.library.root.parent)
        if updater.can_self_update():
            if dialogs.askyesno(
                    "Pixel Pomo Art Kit",
                    t("update_offer_self", tag=release.tag, v=VERSION, data=data),
                    parent=self.root):
                self._apply_windows_update(release)
            return
        if dialogs.askyesno(
                "Pixel Pomo Art Kit",
                t("update_offer_page", tag=release.tag, v=VERSION, data=data),
                parent=self.root):
            webbrowser.open(release.url)

    def _apply_windows_update(self, release):
        url = release.assets.get(updater.WINDOWS_ASSET)
        if not url:
            dialogs.showerror("Pixel Pomo Art Kit",
                              t("update_no_windows", tag=release.tag, url=release.url),
                              parent=self.root)
            return
        self._update_button.configure(state="disabled")
        dest = updater.temp_download_path(release.tag)

        def progress(done, total):
            pct = f"{100 * done // total}%" if total else f"{done // 1024} KB"
            self.root.after(0, lambda: self._set_status(t("downloading", pct=pct)))

        def work():
            try:
                updater.download(url, dest, progress)
                self.root.after(0, lambda: self._finish_windows_update(release, dest))
            except Exception as exc:
                self.root.after(0, lambda: self._update_failed(exc))

        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self, exc):
        self._update_button.configure(state="normal")
        self._set_status(t("update_failed"), error=True)
        dialogs.showerror("Pixel Pomo Art Kit",
                          t("update_error", error=exc, url=updater.RELEASES_PAGE),
                          parent=self.root)

    def _finish_windows_update(self, release, zip_path):
        """Downloaded: back the library up, stage the new .exe, hand off, quit."""
        try:
            backup = updater.backup_library(self.library.root.parent, release.tag)
            _new_exe, script = updater.stage_windows(zip_path)
            self._set_status(t("restarting"))
            updater.launch_handoff(script)
        except Exception as exc:
            self._update_failed(exc)
            return
        if backup is not None:
            self._set_status(t("backup", name=backup.name))
        self.close()

    # ---- state ---------------------------------------------------------
    def select(self, drawing):
        previous = self._selected
        if self.floating is not None and previous is not None:
            self.commit_floating()  # a block in the air lands before the drawing changes
        if previous is not None and self._camera_frozen():
            # Under LOCK every drawing keeps the view it was frozen at, so
            # looking at another one and coming back finds this one exactly
            # as it was left (#v2.8.0).
            self._lock_frames[id(previous)] = (self.zoom_level, self._locked_at)
        if previous is not None and previous is not drawing:
            self._switch_symmetry(previous, drawing)
        self.selection = None
        self._selecting = None
        self._selected = drawing
        self.history = self._histories.setdefault(id(drawing), History(drawing))
        self._content_version += 1  # a drawing that died may leave its id to this one
        self.root.title(f"Pixel Pomo Art Kit — {drawing.name}")
        if previous is not None and id(previous) in self._rows:
            self._highlight_row(previous, False)
        if id(drawing) not in self._rows:
            self._rebuild_list()
        self._highlight_row(drawing, True)
        self._refresh_ink_ui()
        self._refresh_size_label()
        self._redraw()
        self._refresh_counter()
        self._refresh_colour_strip()
        # Once the window has real dimensions, make the grid fill the middle.
        self._fitted = False
        if self.camera_mode == CAM_LOCK and self._pane_known():
            # Straight to this drawing's frozen view. Waiting the 80ms would
            # show it for that long at the OTHER drawing's frozen point.
            self.zoom_to_fit()
        else:
            self.root.after(80, self.zoom_to_fit)

    def zoom_to_fit(self):
        """Pick the zoom that makes the whole grid fill the canvas pane.

        Through `fit_zoom`, which is the one place that arithmetic lives.
        This used to read `winfo_width` itself while every other camera
        method went through `_viewport`, so the two disagreed exactly when
        the pane was not laid out yet - and that is the moment FIT runs, 80ms
        after a drawing is opened (#v2.8.0).

        Under LOCK this is "frame the open drawing", which is not a fit at
        all once it has a frozen view - see `_frame_locked`. The FIT button
        goes through `fit_pressed`, which says why it did nothing."""
        if self.history is None:
            return
        if self.camera_mode == CAM_LOCK:
            self._frame_locked()
            return
        self.zoom_level = self.fit_zoom()
        self._fitted = self._pane_known()
        # Held until the artist zooms or pans (#v2.8.0, sixth test pass): a
        # pane that changes size under a fitted view - the ☰, a maximise - is
        # fitted again, rather than leaving the art off-centre or overflowing.
        self._fit_held, self._fit_pane = True, self._viewport()
        self.home_view()  # wherever the current mode calls home

    def _release_fit(self):
        """The artist moved the camera: the view is theirs now, not the fit."""
        self._fit_held = False

    def fit_pressed(self):
        """The FIT button: a fit, unless LOCK is holding the camera."""
        if self._camera_frozen():
            self._refuse_camera()
            return
        self.zoom_to_fit()

    def _frame_locked(self):
        """Where LOCK puts the open drawing, and at what zoom (#v2.8.0).

        Frozen already, it stays exactly as it is: FIT, a resize from the Size
        dialog and a relayout of the window move nothing. A drawing LOCK saw
        earlier this session gets back the view it was frozen at. Anything
        else - the first drawing after starting up in LOCK, the first look at
        one opened under it - is fitted and centred, and THAT is frozen: the
        view the artist is shown is the one they get to keep. Up to the
        second test pass a start in LOCK held the canvas origin instead,
        which pinned the art to the top-left corner of the pane.

        The one thing that does re-frame a frozen view is losing the drawing
        altogether: a shrink that leaves nothing of it inside the frame would
        otherwise leave an empty pane that only leaving LOCK could fix."""
        if (self._fitted and self._locked_at is not None
                and self._frame_shows_art(self.zoom_level, self._locked_at)):
            self.home_view()
            return
        saved = self._lock_frames.get(id(self._selected))
        if (saved is not None and self._pane_known()
                and self._frame_shows_art(*saved)):
            self.zoom_level, self._locked_at = saved
            self._fitted = True
            self.home_view()
            return
        self.zoom_level = self.fit_zoom()
        self._fitted = self._pane_known()
        d, z = self.history.current, self.zoom_level
        cw, ch = self._viewport()
        self._locked_at = (self._anchor_at(d.width * z, cw, "mid"),
                           self._anchor_at(d.height * z, ch, "mid"))
        self.home_view()

    def _frame_shows_art(self, zoom, at):
        """Would a view with its corner at canvas point `at`, at `zoom`, have
        any of the open drawing inside it?"""
        d = self.history.current
        cw, ch = self._viewport()
        x, y = at
        return x < d.width * zoom and x + cw > 0 and y < d.height * zoom and y + ch > 0

    def _camera_frozen(self):
        """LOCK is on and has a view to hold: no pan and no zoom."""
        return self.camera_mode == CAM_LOCK and self._locked_at is not None

    def _refuse_camera(self):
        """A zoom or a pan arrived while LOCK is holding the camera.

        Nothing moves - that is the lock - and the status corner says so,
        because a wheel that silently does nothing reads as a frozen app.
        Words only, held steady for as long as the wheel keeps turning: the
        first version also blinked the LOCK button, and under a spinning
        wheel that flicker read as LOCK and the zoom fighting each other."""
        self._set_status(t("cam_locked"), flash=True)

    def _pane_known(self):
        """Has Tk laid the drawing pane out yet? `_viewport` answers with
        NOMINAL_VIEW until it has, which is a guess, not a measurement."""
        return self.canvas.winfo_width() > 1 and self.canvas.winfo_height() > 1

    def set_tool(self, name):
        if name not in TOOLS:
            raise ValueError(f"tool must be one of {TOOLS}, got {name!r}")
        if name == "fill" and self.selection is not None:
            # SELECT then FILL fills the rectangle, which is what the button
            # reads as — not "switch to the flood tool and wait for a click"
            # (#v2.7.0, item 8).
            self.fill_selection()
            self.clear_selection()
        if name == "select" and self.tool == "select":
            # Clicking SELECT again dismisses the stuck rectangle.
            self.commit_floating()
            self.clear_selection()
            self._refresh_tool_buttons()
            return
        if self.tool == "select" and name != "select":
            self.commit_floating()
            if name != "fill":
                self.clear_selection()
        self.tool = name
        self.settings.tool = name  # the last tool used is the one selected next time (item 12)
        self._refresh_tool_buttons()
        self.canvas.delete("ghost")

    def set_eraser_size(self, w, h):
        """The eraser's footprint in cells, centred on the pointer (#v2.6.0)."""
        w = max(1, min(ERASER_MAX, int(w)))
        h = max(1, min(ERASER_MAX, int(h)))
        if (w, h) != tuple(self.eraser_size):
            self._record_state(self.ERASER)
        self.eraser_size = (w, h)
        self.settings.set_eraser(w, h)
        self._refresh_eraser_ui()

    # ---- state the window owns, on the drawing's own undo timeline -------
    #
    # Not artwork, but the artist changed it on purpose and expects Ctrl+Z to
    # take it back (#v2.8.0 - "I changed the grid, pressed Ctrl+Z, nothing
    # happened"). Recorded as history entries so they queue with the strokes
    # instead of being a second, jumping-the-line stack.

    GRID, BAR, INK, ERASER, FAVOURITES = "grid", "bar", "ink", "eraser", "favourites"

    def _grid_state(self):
        g = self.settings.grid
        return (g["c1"], g["c2"], self.show_grid)

    def _bar_state(self):
        bar = self.symmetry_bar
        return (self.symmetry_mode, self._sym_orientation, self._sym_length,
                None if bar is None else (bar.col, bar.row), self._placing_bar)

    def _state_now(self):
        return {self.GRID: self._grid_state(), self.BAR: self._bar_state(),
                self.INK: self.ink, self.ERASER: tuple(self.eraser_size),
                self.FAVOURITES: tuple(self.settings.favourites)}

    def _record_state(self, kind, coalesce=False):
        """Note how `kind` looks BEFORE it is changed. Call it first.

        `coalesce` folds this change into the entry already on top when that
        entry is the same kind - for a gesture that fires continuously, like
        dragging across the shade square, which would otherwise leave one undo
        step per pixel of mouse travel. The entry already there holds the value
        from before the gesture started, which is the one Ctrl+Z should give
        back."""
        if self.history is None:
            return
        if coalesce and self.history.last_kind() == kind:
            return
        self.history.push_state(kind, self._state_now()[kind])

    def _restore_state(self, kind, value):
        if value is None:
            return
        if kind == self.INK:
            self.ink = value
            self._refresh_ink_ui()
            self._draw_main()
            return
        if kind == self.ERASER:
            self.eraser_size = tuple(value)
            self.settings.set_eraser(*value)
            self._refresh_eraser_ui()
            self._draw_main()
            return
        if kind == self.FAVOURITES:
            self.settings.data["favourites"] = list(value)
            self.settings.save()
            self._refresh_favourites()
            return
        if kind == self.GRID:
            c1, c2, show = value
            self.settings.set_grid(c1, c2)
            self.show_grid = bool(show)
            self.settings.show_grid = self.show_grid
            self._refresh_grid_ui()
        elif kind == self.BAR:
            mode, orientation, length, at, placing = value
            self.symmetry_mode = mode
            self._sym_orientation, self._sym_length = orientation, length
            self.symmetry_bar = (None if at is None else
                                 symmetry.Bar(orientation, length, at[0], at[1]))
            self._placing_bar = placing
            self.settings.set_symmetry(orientation, length, mode)
            self._refresh_symmetry_ui()
        self._draw_main()

    def set_show_grid(self, on):
        if bool(on) == self.show_grid:
            return
        self._record_state(self.GRID)
        self.show_grid = bool(on)
        self.settings.show_grid = self.show_grid
        self._refresh_grid_ui()
        self._draw_main()

    def set_grid_colours(self, c1=None, c2=None):
        """The two checkerboard tones behind the art (#v2.6.0, item 7)."""
        before = self._grid_state()
        self._record_state(self.GRID)
        self.settings.set_grid(c1, c2)
        if self._grid_state() == before and self.history is not None:
            self.history.drop_last(self.GRID)      # a code that did not parse
        self._refresh_grid_ui()
        self._draw_main()

    def reset_grid_colours(self):
        before = self._grid_state()
        self._record_state(self.GRID)
        self.settings.reset_grid()
        if self._grid_state() == before and self.history is not None:
            self.history.drop_last(self.GRID)
        self._refresh_grid_ui()
        self._draw_main()

    def grid_colours(self):
        g = dict(self.settings.grid)
        if self._grid_preview:
            g.update(self._grid_preview)  # the grid picker is open and being dragged
        return (f"#{g['c1'].lower()}", f"#{g['c2'].lower()}")

    def grid_line_colour(self):
        """Lighter than the ground - or darker, on a light one: WHITE's lines
        lightened would be white on white (#v2.8.0, ninth test pass)."""
        tone = self.grid_colours()[1]
        if theme.readable_on(tone) == "#ffffff":    # a dark ground
            return _lighten(tone, 0.28)
        return _darken(tone, 0.28)

    def set_ink(self, value, coalesce=False):
        # render() silently drops anything that isn't a palette letter or an
        # RGBA 4-tuple, so a bad ink would vanish from the canvas with no error.
        # Catch it here, at the public boundary, instead.
        ok = ((isinstance(value, str) and value in LETTERS)
              or (isinstance(value, tuple) and len(value) == 4
                  and all(isinstance(n, int) for n in value)))
        if not ok:
            raise ValueError(f"ink must be a palette letter or an RGBA tuple, got {value!r}")
        if value == self.ink:
            return
        # Picking a colour is a step like any other (#v2.8.0): the eyedropper,
        # a swatch, a typed code and the shade square all go through here, and
        # Ctrl+Z has to take any of them back.
        self._record_state(self.INK, coalesce=coalesce)
        self.ink = value
        self._refresh_ink_ui()

    def ink_rgba(self):
        """The ink as a real colour — a letter resolves through the open
        drawing's palette, or to grey if nothing is open."""
        if isinstance(self.ink, str):
            if self.history is not None:
                return self.history.current.palette.colors()[self.ink]
            return (128, 128, 128, 255)
        return self.ink

    def set_ink_hex(self, text):
        """The hex entry's contract: '#RRGGBB' or 'RRGGBB', any case. Returns
        False (and changes nothing) for anything else."""
        text = text.strip().lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
            return False
        self.set_ink(hex_to_rgba(text))
        return True

    # ---- the camera (#v2.8.0) -------------------------------------------
    #
    # Up to #v2.7.0 the scroll region WAS the art: (0, 0, w*z, h*z). That
    # pinned the view to the drawing's top-left corner, so zooming in always
    # crawled away towards the bottom-right and the artist had to chase it
    # with the scrollbars. The region is wider than the art now, by a whole
    # viewport less one cell on each side, which buys two things at once:
    # the view can sit anywhere, and it can never sit NOWHERE - at least one
    # cell of the drawing is always inside the frame, because that is exactly
    # where the region stops.

    def _viewport(self):
        """The drawing pane's size in pixels - NOMINAL_VIEW until Tk knows."""
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (cw if cw > 1 else NOMINAL_VIEW[0]), (ch if ch > 1 else NOMINAL_VIEW[1])

    def _scroll_bounds(self):
        """The scroll region: (x0, y0, x1, y1) in canvas pixels."""
        d = self.history.current
        z = self.zoom_level
        wpx, hpx = d.width * z, d.height * z
        cw, ch = self._viewport()
        ax, ay = CAMERA_ANCHORS[self.camera_mode]
        held = self._locked_at or (0, 0)
        x0, x1 = self._axis_bounds(wpx, cw, ax, held[0])
        y0, y1 = self._axis_bounds(hpx, ch, ay, held[1])
        # Whole pixels: under 1 px a cell the arithmetic is in fractions, and
        # a fraction handed to Tk arrives as the string "7/2".
        return (math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1))

    def _axis_bounds(self, span, view, anchor, held=0):
        """One axis of the scroll region, for one anchor. See CAMERA_ANCHORS."""
        z = self.zoom_level
        if anchor == "hold":
            return held, held + view
        # One cell of the drawing stays on screen - or, below 1 px a cell,
        # one pixel: a cell is a third of a pixel at 1/3x, and a third of a
        # pixel floored to a whole one is none (the region's far end then
        # showed nothing of the drawing at all).
        unit = max(1, z)
        if anchor == "free":
            # The leading edge may range over [unit - view, span - unit]: at
            # either end exactly one cell of the drawing is inside the frame.
            lo, hi = unit - view, span - unit
            if hi < lo:                     # one cell is wider than the pane
                lo = hi = (lo + hi) // 2
            return lo, hi + view
        if span > view:
            # There is more drawing than pane: the alignment has nothing to
            # say, and what the artist wants is to look around - including
            # past the edges, or a zoom about a pointer near one could not
            # keep its cell under the pointer. Same one-cell rule as free.
            lo, hi = unit - view, span - unit
            if hi < lo:
                lo = hi = (lo + hi) // 2
            return lo, hi + view
        # The drawing fits: NOW the alignment is the whole question, and the
        # view is parked against that edge with no range at all.
        lo = hi = self._anchor_at(span, view, anchor)
        return lo, hi + view

    @staticmethod
    def _anchor_at(span, view, anchor):
        """Where the view's leading edge parks for `anchor`. With the drawing
        smaller than the pane, `span - view` is NEGATIVE: that is the edge
        sitting left of the art, which is exactly what pushes the art to the
        far side of the pane."""
        if anchor == "min":
            return 0
        if anchor == "max":
            return span - view
        return (span - view) // 2

    def home_view(self):
        """Put the camera where the current mode says home is."""
        if self.history is None:
            return
        d = self.history.current
        z = self.zoom_level
        cw, ch = self._viewport()
        ax, ay = CAMERA_ANCHORS[self.camera_mode]
        self._apply_scrollregion()
        if self.camera_mode == CAM_LOCK and self._locked_at is not None:
            self._scroll_to(*self._locked_at)   # home is where it was frozen
        else:
            home = {"free": "mid"}
            self._scroll_to(self._anchor_at(d.width * z, cw, home.get(ax, ax)),
                            self._anchor_at(d.height * z, ch, home.get(ay, ay)))
        self._redraw_viewport()

    def _apply_scrollregion(self):
        x0, y0, x1, y1 = self._scroll_bounds()
        # One pixel per scroll unit: the autoscroll asks for `z` of them, and
        # a whole-cell increment would quantise the camera and make a
        # zoom-under-the-pointer land a cell off.
        self.canvas.configure(scrollregion=(x0, y0, x1, y1),
                              xscrollincrement=1, yscrollincrement=1)

    def _scroll_to(self, vx, vy):
        """Put the viewport's top-left corner at canvas point (vx, vy), as
        near as the bounds allow."""
        x0, y0, x1, y1 = self._scroll_bounds()
        self.canvas.xview_moveto(float((vx - x0) / max(1, x1 - x0)))
        self.canvas.yview_moveto(float((vy - y0) / max(1, y1 - y0)))

    def _view_origin(self):
        return self.canvas.canvasx(0), self.canvas.canvasy(0)

    def centre_view(self):
        """Put the whole drawing in the middle of the pane.

        Kept as the name other code calls; where the camera actually goes is
        the MODE's business now (#v2.8.0), and CAM_CENTRE is the mode that
        means this. `home_view` is the general form."""
        self.home_view()

    def _visible_cells(self):
        """The cell rectangle inside the viewport, clamped to the drawing.

        Returns (c0, r0, c1, r1) inclusive, or None when the drawing is
        entirely off-screen (which the bounds above make impossible in
        practice, but a Configure can arrive mid-move)."""
        d = self.history.current
        z = self.zoom_level
        cw, ch = self._viewport()
        vx, vy = (int(v) for v in self._view_origin())  # int // Fraction is exact
        c0, r0 = max(0, int(vx // z)), max(0, int(vy // z))
        c1 = min(d.width - 1, int((vx + cw) // z))
        r1 = min(d.height - 1, int((vy + ch) // z))
        if c1 < c0 or r1 < r0:
            return None
        return (c0, r0, c1, r1)

    def _xview(self, *args):
        if self._camera_frozen():
            return  # LOCK's scroll region is the view itself: nowhere to go
        self._release_fit()
        self.canvas.xview(*args)
        self._redraw_viewport()

    def _yview(self, *args):
        if self._camera_frozen():
            return
        self._release_fit()
        self.canvas.yview(*args)
        self._redraw_viewport()

    def _wheel_pan(self, dx, dy):
        if self._camera_frozen():
            self._refuse_camera()
            return
        self._release_fit()
        step = max(1, round(self.zoom_level))  # a cell a notch - never under a pixel
        if dx:
            self.canvas.xview_scroll(-dx * step, "units")
        if dy:
            self.canvas.yview_scroll(-dy * step, "units")
        self._redraw_viewport()

    def _space_down(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)):
            return  # a space typed into the hex box is a space
        # Still "panning" under LOCK, so a click with space held does not
        # paint - but without the move cursor, which would promise a pan.
        self._panning = True
        if not self._camera_frozen():
            self.canvas.configure(cursor="fleur")

    def _space_up(self, _event=None):
        self._panning = False
        self._pan_from = None
        self.canvas.configure(cursor="")

    def _pan_start(self, event):
        if self._camera_frozen():
            self._pan_from = None
            self._refuse_camera()
            return
        self._release_fit()
        self._pan_from = (event.x, event.y)
        self.canvas.scan_mark(event.x, event.y)

    def _pan_move(self, event):
        if self._pan_from is None:
            return
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self._redraw_viewport()

    def fit_zoom(self):
        """The zoom at which the whole drawing fills the pane - under 1 px a
        cell for one bigger than the pane at 1x (#v2.8.0): the largest 1/n
        at which it fits."""
        if self.history is None:
            return MIN_ZOOM
        d = self.history.current
        cw, ch = self._viewport()
        whole = min(cw // d.width, ch // d.height)
        if whole >= 1:
            return max(MIN_ZOOM, min(MAX_ZOOM, whole))
        n = max(-(-d.width // max(1, cw)), -(-d.height // max(1, ch)))
        return max(self.min_zoom(), Fraction(1, n))

    def min_zoom(self):
        """How far OUT the open drawing may be zoomed: to the scale of its
        smallest picture in the corner - 1x for anything the 1x box holds,
        and 1/n x for a drawing too big for it, the very 1/n x that picture
        is labelled with (#v2.8.0, third test pass).

        It once stopped at `fit_zoom`, on the reading that there was no point
        going smaller than the pane; there is - 1x is the sprite at the size
        the game draws it. Below 1x the same holds for a drawing too big to
        see whole: the artist asked to be able to pull back to what the
        corner shows. The camera cannot get lost down there - the bounds keep
        a cell on screen at every zoom."""
        if self.history is None:
            return MIN_ZOOM
        d = self.history.current
        n = -(-max(d.width, d.height) // ONE_X_BOX)
        return MIN_ZOOM if n <= 1 else Fraction(1, n)

    def max_zoom(self):
        """How far the open drawing may be zoomed in.

        The same for every drawing (#v2.8.0). Between #v2.7.0 and the viewport
        renderer this was computed per drawing, because a big grid at a high
        zoom meant a huge bitmap; now that a repaint costs a paneful whatever
        the zoom is, a 64x64 tree can go exactly as far in as a 16x19 flower.
        Kept as a method because the rest of the app asks through it."""
        return MAX_ZOOM

    def _clamp_zoom(self, z):
        """`z` in the ladder's own terms - whole px a cell from 1 up, 1/n
        below it - and inside this drawing's range."""
        z = Fraction(z)
        if z >= 1:
            z = int(z)
        elif z > 0:
            z = Fraction(1, math.ceil(1 / z))
        return max(self.min_zoom(), min(self.max_zoom(), z))

    def zoom_stops(self):
        """The ladder, trimmed to what this drawing allows, its own floor
        always on it - so the wheel lands exactly on the corner's 1/n x."""
        lo, hi = self.min_zoom(), self.max_zoom()
        return sorted({z for z in ZOOM_OUT_STOPS + ZOOM_STOPS if lo <= z <= hi} | {lo})

    def next_zoom(self, delta):
        """The stop one notch up (`delta > 0`) or down from the current zoom.

        Strictly past the current level, so a zoom sitting BETWEEN two stops -
        which is what the corner handle leaves behind - moves to the next one
        instead of snapping backwards."""
        stops = self.zoom_stops()
        if delta > 0:
            return next((z for z in stops if z > self.zoom_level), stops[-1])
        return next((z for z in reversed(stops) if z < self.zoom_level), stops[0])

    def zoom(self, delta, focus=None):
        """One wheel notch, about `focus` (a point in canvas-widget pixels).

        Zooms about the POINTER (#v2.8.0) - the cell under the cursor is the
        one the artist is looking at, and it stays put. The notch itself is a
        step along `ZOOM_STOPS`, so up-then-down returns exactly.

        The wheel and + / - both come here, so this is where LOCK says no."""
        if self._camera_frozen():
            self._refuse_camera()
            return
        self._zoom_about(self._clamp_zoom(self.next_zoom(delta)), focus)

    def _zoom_about(self, new, focus=None):
        """Change the zoom, keeping whatever is under `focus` under it. With
        no focus the centre of the pane holds still. Never under LOCK, whoever
        asks."""
        old = self.zoom_level
        if new == old or self.history is None or self._camera_frozen():
            return
        self._release_fit()
        cw, ch = self._viewport()
        if focus is None:
            focus = (cw / 2, ch / 2)
        fx, fy = focus
        # where that point is in CELL coordinates, before the zoom
        vx, vy = self._view_origin()
        cx, cy = (vx + fx) / old, (vy + fy) / old
        self.zoom_level = new
        self._apply_scrollregion()
        self._scroll_to(cx * new - fx, cy * new - fy)
        self._draw_main()  # previews are fixed-scale; only the main view depends on zoom

    def set_zoom(self, z):
        """Set the cell size in pixels, about the middle of the pane.

        Not undoable, and nothing else is either: the zoom is navigation, not
        work. #v2.7.0 made the corner-handle drag undoable because it was the
        one zoom you could trigger by accident while reaching for the canvas;
        that handle is gone (#v2.8.0 - the four edges resize the drawing
        instead), and with a free camera Ctrl+Z giving back a viewpoint rather
        than a brush stroke would be a worse surprise than the one it fixed."""
        z = self._clamp_zoom(z)
        if z == self.zoom_level:
            return
        self._zoom_about(z)

    def undo(self):
        """Ctrl+Z: one step back along the drawing's own timeline.

        A block still in the air is the first thing to go. It is half of an
        edit that has not landed - the lift already cleared the cells, and the
        stamp has not happened - so undoing it means dropping the block AND
        putting those cells back, in one press. Carrying on into the stack
        from there would undo a stroke the artist never saw fail."""
        if self._painting or self.history is None or self._look_refuses():
            return
        if self.floating is not None:
            self._drop_floating()
            return
        shift = self.history.current.shift
        self._apply_timeline(self.history.undo(self._state_now()), shift)

    def redo(self):
        if self.history is None or self._painting or self._look_refuses():
            return
        shift = self.history.current.shift
        self._apply_timeline(self.history.redo(self._state_now()), shift)

    def _apply_timeline(self, entry, shift=(0, 0)):
        """Act on what `History.undo`/`redo` handed back. Anything that is not
        a cells entry is the window's own state, which history carries but
        never interprets. `shift` is the drawing's `shift` from before the
        step, for `_follow_shift`."""
        if entry is None:
            return
        kind, value = entry
        if kind != History.CELLS:
            self._restore_state(kind, value)
            return
        self._follow_shift(shift)
        self._after_change()

    def _follow_shift(self, was):
        """Cells came or went on the LEFT or TOP edge - a drag in progress, or
        the undo or redo of one - so the art just moved in canvas coordinates
        (`Drawing.shift` says how far, against `was`). Move the view by as
        much, and LOCK's frozen point with it, so the drawing holds still on
        screen (#v2.8.0). Before, only the drag itself did this: an undone
        left-edge grow jumped the art sideways by the columns it took back -
        under LOCK, with no way to pan it back."""
        now = self.history.current.shift
        z = self.zoom_level
        dx, dy = (now[0] - was[0]) * z, (now[1] - was[1]) * z
        if not dx and not dy:
            return
        self._release_fit()
        vx, vy = self._view_origin()
        if self._camera_frozen():
            lx, ly = self._locked_at
            self._locked_at = (lx + dx, ly + dy)
        self._apply_scrollregion()
        self._scroll_to(vx + dx, vy + dy)

    def _drop_floating(self):
        """Undo with a block in the air: it goes, and a lift goes with it."""
        lifted = self._float_lift
        self.floating = None
        self._float_lift = False
        if lifted and self.history.abort_stroke():
            self._after_change()
        self._draw_overlays()
        self._refresh_counter()

    def save(self):
        """The SAVE button / Ctrl+S. Every stroke is already written the moment
        it ends, so this is the artist's reassurance more than a mechanism —
        but it is also the one save that reports failure loudly (item 1, 9)."""
        if self._selected is None:
            return False
        ok = self._save(self._selected)
        if ok:
            self._set_status(t("saved"), flash=True)
        return ok

    def close(self):
        """Window close / Cmd+Q: finish any stroke, save everything, quit."""
        if self._painting:
            self.on_canvas_release()
        # A lifted block holds an OPEN stroke (#v2.8.0): quitting with one in
        # the air would write the cleared cells to disk with no undo entry
        # behind them. Landing it first makes the move a finished edit.
        self.commit_floating()
        for drawing in self.library.drawings:
            hist = self._histories.get(id(drawing))
            if hist is None or not (hist.can_undo() or hist.can_redo()):
                continue  # never touched this session: nothing to write
            if hist.current is not drawing:
                drawing.cells = [list(row) for row in hist.current.cells]
            self._save(drawing, quiet=True)
        self.settings.save()
        self.root.destroy()

    # ---- symmetry (#v2.4.0 item 14, #v2.5.0 modes) -------------------------------
    @property
    def symmetry_on(self):
        """Older name: is the MIRROR bar in effect?"""
        return self.symmetry_mode == symmetry.MIRROR

    def set_symmetry(self, on):
        """Older API: MIRROR on/off."""
        self.set_symmetry_mode(symmetry.MIRROR if on else symmetry.OFF)

    def set_symmetry_mode(self, mode):
        if mode not in symmetry.MODES:
            raise ValueError(f"mode must be one of {symmetry.MODES}, got {mode!r}")
        if mode == self.symmetry_mode:
            return
        self._record_state(self.BAR)
        self.symmetry_mode = mode
        # MIRROR and STICK share a between-pixel line. With no line yet the
        # next canvas click places it instead of painting (#v2.7.0, item 12).
        self._placing_bar = mode in (symmetry.MIRROR, symmetry.STICK) and self.symmetry_bar is None
        self._dragging_bar = None
        self.settings.set_symmetry(self._sym_orientation, self._sym_length, mode)
        self._refresh_symmetry_ui()
        self._draw_main()

    def cycle_symmetry_mode(self):
        """The `m` key: OFF -> MIRROR -> STICK -> OFF."""
        i = symmetry.MODES.index(self.symmetry_mode)
        self.set_symmetry_mode(symmetry.MODES[(i + 1) % len(symmetry.MODES)])

    def arm_symmetry_placement(self):
        """PLACE BAR: the next click moves the line (or places it)."""
        if self.symmetry_mode in (symmetry.MIRROR, symmetry.STICK):
            self._placing_bar = True
            self._refresh_symmetry_ui()

    def set_symmetry_orientation(self, orientation):
        if orientation not in symmetry.ORIENTATIONS:
            raise ValueError(orientation)
        self._sym_orientation = orientation
        if self.symmetry_bar is not None:
            self.symmetry_bar = symmetry.Bar(orientation, self._sym_length,
                                             self.symmetry_bar.col, self.symmetry_bar.row)
        self.settings.set_symmetry(self._sym_orientation, self._sym_length, self.symmetry_mode)
        self._refresh_symmetry_ui()
        self._draw_main()

    def set_symmetry_length(self, length):
        length = max(symmetry.MIN_LENGTH, min(symmetry.MAX_LENGTH, int(length)))
        self._sym_length = length
        if self.symmetry_bar is not None:
            self.symmetry_bar = symmetry.Bar(self._sym_orientation, length,
                                             self.symmetry_bar.col, self.symmetry_bar.row)
        self.settings.set_symmetry(self._sym_orientation, self._sym_length, self.symmetry_mode)
        self._refresh_symmetry_ui()
        self._draw_main()

    def place_symmetry_bar(self, col, row):
        self._record_state(self.BAR)
        self.symmetry_bar = symmetry.Bar(self._sym_orientation, self._sym_length, col, row)
        self._placing_bar = False
        if self.symmetry_mode == symmetry.STICK:
            self._stamp_stick()
        self._refresh_symmetry_ui()
        self._draw_main()

    def move_symmetry_bar(self, col, row):
        """Drag: re-centre the bar without changing its shape."""
        if self.symmetry_bar is None:
            self.place_symmetry_bar(col, row)
            return
        d = self.history.current if self.history else None
        if d is not None:
            col = max(0, min(d.width - 1, col))
            row = max(0, min(d.height - 1, row))
        if (col, row) != (self.symmetry_bar.col, self.symmetry_bar.row):
            self.symmetry_bar = self.symmetry_bar.moved_to(col, row)
            self._draw_main()

    def _stamp_stick(self):
        """STICK: copy the length-span across the line as one undo step."""
        if self.history is None or self.symmetry_bar is None:
            return
        self.history.begin_stroke()
        symmetry.stamp_across(self.history.current, self.symmetry_bar)
        self.history.end_stroke()
        if self.history.can_undo():
            self._after_change()

    def _active_bar(self):
        return self.symmetry_bar if self.symmetry_mode in (symmetry.MIRROR, symmetry.STICK) else None

    # ---- LOOK (#v2.8.0, eighth test pass) -------------------------------------
    def toggle_looking(self):
        self.set_looking(not self.looking)

    def set_looking(self, on):
        """LOOK: the drawing on the canvas as it LOOKS - no checkerboard, no
        cell lines, no symmetry line, no eraser outline - and nothing drawn
        until it is unticked. The camera still moves, the eyedropper still
        picks; a press on the art says why it did nothing, the way LOCK does.

        "Squint görüntüsü ... arkadaki tasarım tamamen yok oluyor": the corner
        picture is the shape on a plain ground, which is the point of it, and
        the artist wanted the big view able to show the same."""
        on = bool(on)
        if on == self.looking:
            return
        if on:
            if self._painting:
                self.on_canvas_release()     # a stroke in progress lands first
            self.commit_floating()
            self.clear_selection()
        self.looking = on
        self.canvas.configure(cursor="")
        self._refresh_look_ui()
        self._draw_main()

    def _refresh_look_ui(self):
        btn = getattr(self, "_look_button", None)
        if btn is None:
            return
        tick = dialogs.TICKED if self.looking else dialogs.UNTICKED
        colour = theme.ACCENT if self.looking else theme.ON_DIM
        btn.configure(text=f"{tick} {t('look')}", fg=colour, activeforeground=colour)

    def _look_refuses(self):
        """Under LOOK an edit is refused, and the status corner says why."""
        if self.looking:
            self._set_status(t("look_only"), flash=True)
        return self.looking

    def _under_tones(self):
        """The two tones under the empty cells, as RGBA: the checkerboard's -
        or, under LOOK, the canvas's own colour twice, so the shape stands
        on a plain ground."""
        if self.looking:
            plain = hex_to_rgba(theme.CANVAS_BG)
            return [plain, plain]
        return [hex_to_rgba(tone) for tone in self.grid_colours()]

    def _switch_symmetry(self, previous, drawing):
        """Each drawing keeps its own symmetry (#v2.8.0, eighth test pass:
        "mirror ve stick açık kalıyor, farklı bir ekrana geçince ... alanın
        dışında kalmış"). The mode and the line were the kit's, not the
        drawing's, so they followed the artist into the next drawing - the
        line sitting off its edge whenever that one was smaller. Now the line
        stays with the drawing it was placed on and comes back with it; a
        drawing never given one opens with symmetry OFF."""
        self._sym_frames[id(previous)] = (self.symmetry_mode, self.symmetry_bar, self._placing_bar)
        mode, bar, placing = self._sym_frames.get(id(drawing), (symmetry.OFF, None, False))
        self.symmetry_mode, self.symmetry_bar, self._placing_bar = mode, bar, placing
        self._dragging_bar = self._resizing_bar = None
        if bar is not None:
            self._sym_orientation, self._sym_length = bar.orientation, bar.length
        self.settings.set_symmetry(self._sym_orientation, self._sym_length, mode)
        self._refresh_symmetry_ui()

    def _keep_bar_inside(self):
        """A line left outside the drawing - it shrank, or an undo took the
        cells it stood by - is taken away, the mode waiting for a click to
        place it again, rather than drawn off in the dark past the edge."""
        bar = self.symmetry_bar
        if bar is None or self.history is None:
            return
        d = self.history.current
        first, last = bar.span()
        if bar.orientation == symmetry.VERTICAL:
            inside = 0 <= bar.col <= d.width and last >= 0 and first < d.height
        else:
            inside = 0 <= bar.row <= d.height and last >= 0 and first < d.width
        if not inside:
            self.symmetry_bar = None
            self._placing_bar = self.symmetry_mode in (symmetry.MIRROR, symmetry.STICK)
            self._refresh_symmetry_ui()

    def _on_bar(self, col, row):
        bar = self._active_bar()
        return bar is not None and bar.touches(col, row)

    def _on_bar_end(self, col, row):
        """Is (col, row) at either end of a line long enough to grab?
        Dragging one resizes the line (#v2.6.0, item 9); the middle still
        moves it. Either neighbouring cell of an end counts, because the
        line sits between pixels (#v2.7.0)."""
        bar = self._active_bar()
        if bar is None or bar.length < 3:
            return None
        first, last = bar.cells()[0], bar.cells()[-1]
        if bar.orientation == symmetry.VERTICAL:
            firsts = {first, (first[0] - 1, first[1])}
            lasts = {last, (last[0] - 1, last[1])}
        else:
            firsts = {first, (first[0], first[1] - 1)}
            lasts = {last, (last[0], last[1] - 1)}
        if (col, row) in firsts:
            return "first"
        if (col, row) in lasts:
            return "last"
        return None

    def resize_symmetry_bar_to(self, col, row):
        """While an end is being dragged: the other end stays put, the length
        follows the pointer along the bar's axis."""
        if self._resizing_bar is None or self.symmetry_bar is None:
            return
        bar = self.symmetry_bar
        fixed = self._resizing_bar
        p = row if bar.orientation == symmetry.VERTICAL else col
        length = max(symmetry.MIN_LENGTH, min(symmetry.MAX_LENGTH, abs(p - fixed) + 1))
        first = min(fixed, p)
        centre = first + (length - 1) // 2
        if bar.orientation == symmetry.VERTICAL:
            new = symmetry.Bar(bar.orientation, length, bar.col, centre)
        else:
            new = symmetry.Bar(bar.orientation, length, centre, bar.row)
        if (new.length, new.col, new.row) != (bar.length, bar.col, bar.row):
            self.symmetry_bar = new
            self._sym_length = new.length
            self._refresh_symmetry_ui()
            self._draw_main()

    # ---- pointer, in GRID coordinates ----------------------------------
    def on_canvas_press(self, col, row):
        if self.history is None:
            return
        d = self.history.current
        # The eraser counts as on the drawing wherever its footprint is: a
        # big one clears the border with the pointer past the edge (#v2.8.0).
        if not d._inside(col, row) and not self._eraser_reaches(col, row):
            if self.floating is not None:
                self.commit_floating()
            elif self.selection is not None:
                self.clear_selection()
            return
        if self._placing_bar:
            self.place_symmetry_bar(col, row)
            return
        if self._paste_armed and self.clipboard is not None and self.floating is None:
            # after Ctrl+C, a click pastes at that cell (#v2.7.0, item 7)
            if not (self.tool == "select" and self.selection is not None
                    and self._in_selection(col, row)):
                self.paste_at(col, row)
                return
        if self.floating is not None:
            if self._in_floating(col, row):
                self._dragging_float = (self.floating["col"] - col, self.floating["row"] - row)
            else:
                self.commit_floating()  # a click outside drops the block where it is
            return
        end = self._on_bar_end(col, row)
        if end is not None:
            cells = self.symmetry_bar.cells()
            other = cells[-1] if end == "first" else cells[0]
            self._resizing_bar = other[1] if self.symmetry_bar.orientation == symmetry.VERTICAL else other[0]
            return
        if self._on_bar(col, row):
            # Pressing ON the line picks it up: drag to move, release to drop.
            bar = self.symmetry_bar
            self._dragging_bar = (bar.col - col, bar.row - row)
            return
        if self.tool == "select":
            if self.selection is not None and self._in_selection(col, row):
                self.lift_selection()
                self._dragging_float = (self.floating["col"] - col, self.floating["row"] - row)
                return
            self._selecting = (col, row)
            self.selection = self._normalised(col, row, col, row)
            self._draw_overlays()
            return
        self.history.begin_stroke()
        self._painting = True
        self._last_cell = (col, row)
        self._stroke_cells = []
        self._apply(col, row)
        if self.tool == "fill":
            self._redraw()  # a flood touches too much for the fast path
        else:
            self._paint_fast()

    def on_canvas_drag(self, col, row):
        if self._dragging_float is not None:
            dc, dr = self._dragging_float
            self.move_floating(col + dc, row + dr)
            return
        if self._resizing_bar is not None:
            self.resize_symmetry_bar_to(col, row)
            return
        if self._dragging_bar is not None:
            dc, dr = self._dragging_bar
            self.move_symmetry_bar(col + dc, row + dr)
            return
        if self._selecting is not None:
            d = self.history.current
            col = max(0, min(d.width - 1, col))
            row = max(0, min(d.height - 1, row))
            self.selection = self._normalised(*self._selecting, col, row)
            self._draw_overlays()
            self._refresh_counter()
            return
        if not self._painting:
            return
        # Walk the whole line from the last reported cell, so a quick stroke
        # is a stroke, not a trail of dots (see _line_cells).
        self._stroke_cells = []
        for c, r in _line_cells(*self._last_cell, col, row)[1:]:
            self._apply(c, r)
        self._last_cell = (col, row)
        if self.tool == "fill":
            self._redraw()
        else:
            self._paint_fast()

    def on_canvas_release(self):
        if self._dragging_float is not None:
            self._dragging_float = None
            return
        if self._resizing_bar is not None:
            self._resizing_bar = None
            self.settings.set_symmetry(self._sym_orientation, self._sym_length, self.symmetry_mode)
            self._refresh_symmetry_ui()
            return
        if self._dragging_bar is not None:
            self._dragging_bar = None
            self._refresh_symmetry_ui()
            return
        if self._selecting is not None:
            self._selecting = None
            self._refresh_counter()
            return
        if not self._painting:
            return
        self._painting = False
        self._last_cell = None
        self.history.end_stroke()
        self._after_change()

    # ---- selection, copy / paste (#v2.6.0, item 11) ----------------------------
    @staticmethod
    def _normalised(c0, r0, c1, r1):
        return (min(c0, c1), min(r0, r1), max(c0, c1), max(r0, r1))

    def _in_selection(self, col, row):
        c0, r0, c1, r1 = self.selection
        return c0 <= col <= c1 and r0 <= row <= r1

    def _in_floating(self, col, row):
        f = self.floating
        return f["col"] <= col < f["col"] + f["w"] and f["row"] <= row < f["row"] + f["h"]

    def select_region(self, c0, r0, c1, r1):
        """Set the selection rectangle directly (the tool's drag does the same)."""
        self.selection = self._normalised(c0, r0, c1, r1)
        self._draw_overlays()
        self._refresh_counter()

    def clear_selection(self):
        self.selection = None
        self._draw_overlays()
        self._refresh_counter()

    def copy_selection(self):
        """Ctrl+C: the selected cells onto the kit's clipboard. Returns True
        if there was something to copy."""
        if self.history is None or self.selection is None:
            return False
        cells, w, h = self.history.current.region(*self.selection)
        self.clipboard = (cells, w, h)
        self._paste_armed = True
        self._set_status(t("copied", w=w, h=h) + " \u00b7 " + t("paste_hint", mod=theme.modifier_label()),
                         flash=True)
        return True

    def cut_selection(self):
        """Ctrl+X: copy, then clear the region as one undo step."""
        if self._look_refuses() or not self.copy_selection():
            return False
        d = self.history.current
        self.history.begin_stroke()
        d.clear_region(*self.selection)
        self.history.end_stroke()
        self._after_change()
        self._set_status(t("cut"), flash=True)
        return True

    def delete_selection(self):
        """Delete / Backspace: clear the selected cells (one undo step); a
        floating block is dropped instead."""
        if self._look_refuses():
            return
        if self.floating is not None:
            # Delete with a block in the air throws the block away. If it was
            # lifted off this drawing, that lift IS the delete, so its open
            # stroke is closed here rather than aborted - one undo puts the
            # cells back.
            self.floating = None
            if self._float_lift:
                self._float_lift = False
                if self.history is not None and self.history.end_stroke():
                    self._after_change()
            self._draw_overlays()
            self._refresh_counter()
            return True
        if self.history is None or self.selection is None:
            return False
        d = self.history.current
        self.history.begin_stroke()
        d.clear_region(*self.selection)
        self.history.end_stroke()
        self._after_change()
        return True

    def paste(self, col=None, row=None):
        """Ctrl+V: the clipboard becomes a floating block — at the selection's
        corner, or where asked, or at the top-left of what is on screen —
        that follows the mouse until it is committed."""
        if self.history is None or self.clipboard is None or self._look_refuses():
            return False
        if self.floating is not None:
            self.commit_floating()
        cells, w, h = self.clipboard
        if col is None or row is None:
            if self.selection is not None:
                col, row = self.selection[0], self.selection[1]
            else:
                z = self.zoom_level
                col = int(self.canvas.canvasx(0)) // z
                row = int(self.canvas.canvasy(0)) // z
        self.floating = {"cells": [list(r) for r in cells], "w": w, "h": h, "col": col, "row": row}
        self.selection = None
        self._paste_armed = False
        if self.tool != "select":
            self.set_tool("select")
        self._draw_overlays()
        self._refresh_counter()
        self._set_status(t("paste_drag"), flash=True)
        return True

    def paste_at(self, col, row):
        """Click-to-paste: stamp the clipboard at (col, row) as one undo step
        (#v2.7.0, item 7). Works across drawings because the clipboard lives
        on the window, not on the drawing."""
        if self.history is None or self.clipboard is None:
            return False
        cells, w, h = self.clipboard
        self.history.begin_stroke()
        self.history.current.stamp(cells, col, row)
        self.history.end_stroke()
        self._paste_armed = False
        self.selection = self._normalised(col, row, col + w - 1, row + h - 1)
        self._after_change()
        return True

    def fill_selection(self):
        """FILL with a selection active: paint the whole rectangle (#v2.7.0)."""
        if self.history is None or self.selection is None:
            return False
        self.history.begin_stroke()
        self.history.current.fill_region(*self.selection, self.ink)
        self.history.end_stroke()
        self._after_change()
        return True

    def lift_selection(self):
        """Pick the selected cells up off the drawing as a floating block.

        The stroke is begun and deliberately LEFT OPEN until the block lands
        (#v2.8.0). Moving something is one edit, and the artist judges it by
        where the block ends up; closing the stroke here made the lift and the
        drop two undo entries, so the first Ctrl+Z after a move undid the drop
        and left the cells deleted - further from the original, not back to
        it. `commit_floating` closes it, `_drop_floating` throws it away, and
        nothing else can begin a stroke while a block is in the air (every
        path that could lands it first)."""
        if self.history is None or self.selection is None:
            return False
        d = self.history.current
        c0, r0, c1, r1 = self.selection
        cells, w, h = d.region(c0, r0, c1, r1)
        self.history.begin_stroke()
        d.clear_region(c0, r0, c1, r1)
        self._float_lift = True
        self._after_change()
        self.floating = {"cells": cells, "w": w, "h": h, "col": c0, "row": r0}
        self.selection = None
        self._draw_overlays()
        self._refresh_counter()
        return True

    def move_floating(self, col, row):
        if self.floating is None:
            return
        if (col, row) != (self.floating["col"], self.floating["row"]):
            self.floating["col"], self.floating["row"] = col, row
            self._draw_overlays()

    def nudge_floating(self, dc, dr):
        if self.floating is not None:
            self.move_floating(self.floating["col"] + dc, self.floating["row"] + dr)

    def commit_floating(self):
        """Enter / click outside: stamp the floating block onto the drawing as
        one undo step; the placed area stays selected so it can be lifted
        again."""
        f = self.floating
        if f is None or self.history is None:
            return False
        d = self.history.current
        if not self._float_lift:
            self.history.begin_stroke()  # a pasted block: an edit of its own
        d.stamp(f["cells"], f["col"], f["row"])
        self.history.end_stroke()        # closes the lift's stroke, if that is what it is
        self._float_lift = False
        self.floating = None
        self.selection = self._normalised(f["col"], f["row"], f["col"] + f["w"] - 1, f["row"] + f["h"] - 1)
        self._after_change()
        return True

    def on_canvas_pick(self, col, row):
        """Eyedropper: the cell under the cursor becomes the ink.

        On a letter drawing the tones are close enough that the eye cannot
        tell d from m from l — this is how the artist continues in the same
        tone without guessing. An empty cell changes nothing (picking
        "nothing" reads as a misclick, not as reaching for the eraser)."""
        if self.history is None:
            return
        cell = self.history.current.get(col, row)
        if cell is not None:
            self.set_ink(cell)

    def _target_cells(self, col, row):
        """The cells one pointer cell turns into under the current symmetry
        mode: itself and its mirror twin (MIRROR and STICK), or just itself."""
        return symmetry.expand(self._active_bar(), [(col, row)])

    def _eraser_cells(self, col, row):
        """The eraser's footprint centred on (col, row) (#v2.6.0, item 8)."""
        w, h = self.eraser_size
        c0, r0 = col - w // 2, row - h // 2
        return [(c, r) for r in range(r0, r0 + h) for c in range(c0, c0 + w)]

    def _apply(self, col, row):
        drawing = self.history.current
        self._content_version += 1  # mid-stroke too: a zoomed-out repaint must show it
        for c, r in self._target_cells(col, row):
            if self.tool == "erase":
                # Only what is really there: a 16 x 16 eraser dragged one cell
                # re-covers 240 cells it has already cleared, and every one of
                # them used to be erased and repainted again (#v2.8.0).
                for ec, er in self._eraser_cells(c, r):
                    if drawing.get(ec, er) is not None:
                        drawing.erase(ec, er)
                        self._stroke_cells.append((ec, er))
                continue
            elif self.tool == "fill":
                drawing.flood(c, r, self.ink)
            else:
                drawing.paint(c, r, self.ink)
            self._stroke_cells.append((c, r))

    def _after_change(self):
        live = self.history.current
        self._content_version += 1
        self._keep_bar_inside()
        if live is not self._selected:
            # undo/redo swapped `.current` to a snapshot copy; fold its content
            # back onto the object the library actually knows how to save.
            # (`kind` follows the cells automatically — it's a derived property.)
            self._selected.cells = [list(row) for row in live.cells]
        self._save(self._selected)
        # The thumbnail and the previews share one render (`_rendered_image`);
        # the main view renders only what is on screen (`_tile`).
        self._refresh_row(self._selected)
        self._refresh_size_label()
        self._draw_main()
        self._draw_previews()
        self._refresh_counter()
        self._refresh_colour_strip()

    def _rendered_image(self):
        """The open drawing rendered whole, as a Pillow image - once per change.

        Every zoomed-out repaint, both corner pictures and the thumbnail cut
        and average THIS, in C (#v2.8.0, third test pass: "fit kısmı çok
        büyüklerde çalışmıyor"). FIT on a 4096-wide drawing took seven
        seconds, nearly all of it turning the same millions of cells into
        pixels again for each picture; it is a crop and an average now.
        Keyed on the content version, which every change bumps - a stroke
        included - so no picture shows the drawing as it was. None without
        Pillow, and the callers fall back to their grids."""
        d = self.history.current
        key = (id(d), d.width, d.height, self._content_version)
        if self._render_key != key:
            if self._pixel_totals()[1] == 0:
                # Nothing painted - a new drawing: an empty picture, without
                # rendering millions of empty cells to find that out.
                self._render_image = raster.blank_image(d.width, d.height)
            else:
                self._render_image = raster.to_image(engine_io.render(d))
            self._render_key = key
        return self._render_image

    def _save(self, drawing, quiet=False):
        """library.save, with the failure shown instead of lost in a traceback
        nobody reads (the macOS Documents-permission case, see fallback_dir)."""
        try:
            self.library.save(drawing)
        except OSError as exc:
            self._set_status(t("save_failed"), error=True)
            if not quiet and not self._save_error_shown:
                self._save_error_shown = True
                dialogs.showerror(
                    "Pixel Pomo Art Kit",
                    t("save_error", name=drawing.name, error=exc, folder=self.library.root),
                    parent=self.root)
            return False
        self._set_status(t("saved_at", time=time.strftime('%H:%M:%S')))
        return True

    # ---- building the window -------------------------------------------
    def _build(self):
        # Library and tools claim their fixed-width edges first; the canvas
        # pane is packed last so it expands into whatever is left between them.
        self._build_library_pane(self.root)
        self._build_tools_pane(self.root)
        self._build_canvas_pane(self.root)
        self._bind_keys()

    def _build_library_pane(self, parent):
        outer = theme.frame(parent, width=LIBRARY_W)
        outer.pack(side="left", fill="y")
        outer.pack_propagate(False)
        self._library_outer = outer

        # Right rail: hamburger above the scrollbar, sharing the same right
        # edge so the ☰ sits in the corner of ALL and does not overhang
        # (#v2.7.0, item 11).
        rail = theme.frame(outer, width=LIBRARY_RAIL)
        rail.pack(side="right", fill="y")
        rail.pack_propagate(False)
        self._library_rail = rail
        self._library_toggle = theme.button(rail, "\u2630", self.toggle_library,
                                           padx=1, pady=4, font=theme.FONT_BOLD)
        # Same top margin as the ALL filter beside it and the FIT strip over
        # the canvas, so the three sit on one line (#v2.8.0).
        self._library_toggle.pack(side="top", fill="x", pady=(PAD, 4))
        scrollbar = theme.scrollbar(rail, "vertical")
        scrollbar.pack(side="top", fill="both", expand=True)
        self._library_scrollbar = scrollbar

        body = theme.frame(outer)
        body.pack(side="left", fill="both", expand=True)
        self._library_body = body

        import_btn = theme.button(body, t("import_png"), self._import_dialog)
        import_btn.pack(side="bottom", fill="x", padx=PAD, pady=(0, PAD))
        self._import_button = import_btn
        new_btn = theme.button(body, t("new_drawing"), self._new_drawing_dialog,
                               bg=theme.WORK, fg=theme.ON_ACCENT,
                               activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT)
        new_btn.pack(side="bottom", fill="x", padx=PAD, pady=(PAD, 4))
        self._new_button = new_btn

        filter_row = theme.frame(body)
        filter_row.pack(side="top", fill="x", padx=PAD, pady=(PAD, 4))
        self._filter_button = theme.button(filter_row, "", self._post_filter_menu, anchor="w")
        self._filter_button.pack(fill="x")
        # The arrow as a drawn triangle (#v2.8.0, ninth test pass: "aşağı
        # doğru okay ama yana doğru değil"): the font's ▶ could come out as an
        # emoji, bigger than the ▼ beside it and a different shape.
        self._filter_icons = {False: theme.icon("right", 10, theme.ON_SURFACE, master=self.root),
                              True: theme.icon("down", 10, theme.ON_SURFACE, master=self.root)}
        self._refresh_filter_button()

        self._list_canvas = tk.Canvas(body, highlightthickness=0, bg=theme.BG)
        self._list_canvas.pack(side="left", fill="both", expand=True)
        self._list_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=self._list_canvas.yview)

        self._list_frame = theme.frame(self._list_canvas)
        self._list_window = self._list_canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw")
        self._list_frame.bind(
            "<Configure>",
            lambda e: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")))
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfigure(self._list_window, width=e.width))
        for widget in (self._list_canvas, self._list_frame):
            widget.bind("<MouseWheel>", self._on_list_wheel)
            widget.bind("<Button-4>", lambda e: self._list_canvas.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: self._list_canvas.yview_scroll(1, "units"))
        self._rebuild_list()
        if self._library_collapsed:
            self._apply_library_collapsed()

    def toggle_library(self):
        self.set_library_collapsed(not self._library_collapsed)

    def set_library_collapsed(self, collapsed):
        self._library_collapsed = bool(collapsed)
        self.settings.library_collapsed = self._library_collapsed
        self._apply_library_collapsed()

    def _apply_library_collapsed(self):
        """Fold the library to its ☰ rail, or open it again (#v2.7.0).

        Folded, the list's scrollbar goes too (#v2.8.0, third test pass): it
        stayed on the rail under the ☰, scrolling a list nobody could see.

        And the whole reflow happens behind `theme.held_paint`: the canvas
        pane slides 200 px, and repainted widget by widget it showed the
        camera strip cut apart and joined back ("kesiliyormuş ve geri
        birleşiyormuş gibi"). Held, everything that depends on the new width
        - the strip's scrollbar, the drawing - is settled first, unseen, and
        the result appears in one frame."""
        if not hasattr(self, "_library_body"):
            return
        with theme.held_paint(self.root):
            if self._library_collapsed:
                self._library_body.pack_forget()
                self._library_scrollbar.pack_forget()
                self._library_outer.configure(width=LIBRARY_RAIL)
            else:
                self._library_scrollbar.pack(side="top", fill="both", expand=True)
                self._library_body.pack(side="left", fill="both", expand=True)
                self._library_outer.configure(width=LIBRARY_W)
            if not hasattr(self, "_cam_strip"):
                return                        # still building the window: nothing to settle
            self.root.update_idletasks()      # the new layout, measured
            self._sync_camera_bar()           # its scrollbar, if the strip no longer fits
            self.root.update_idletasks()
            self._redraw_viewport()           # the drawing, at the pane's new width
            self.root.update_idletasks()

    def _on_list_wheel(self, event):
        step = -1 if event.delta > 0 else 1
        self._list_canvas.yview_scroll(step, "units")

    # ---- the ▾ list: labels and artists, one checklist (#v2.6.0, #v2.8.0) ----
    #
    # One set of ticks over the labels AND the artists (#v2.8.0, sixth test
    # pass: "ben hangi şeyin tikini seçtiysem onlar gözüksün"). The list shows
    # every drawing whose label OR whose artist is ticked: Hero, then OTHER,
    # is Hero's drawings and every OTHER one besides. None is ALL - every row
    # ticked, every drawing listed. From ALL a click ticks just that row ("I
    # want to see only these"); after it, each click ticks one row on or off,
    # and the ticks are always exactly what is listed.
    #
    # Up to the fifth pass the two groups were filters of their own, combined
    # with AND, each with its own ALL: an artist picked from ALL left every
    # label ticked above a list of one artist's work, and NO ARTIST picked
    # from ALL unticked the other artists while every label stayed ticked.

    LABEL, ARTIST = "label", "artist"

    def set_label(self, drawing, label):
        """Tag a drawing. Empty clears it. Saved at once."""
        label = (label or "").strip()
        if label == drawing.label:
            return
        drawing.label = label
        self._save(drawing)
        self._refresh_row(drawing)
        self._refilter()

    def set_artist(self, drawing, artist):
        """Name who drew `drawing` (#v2.8.0). Empty clears it. Saved at once;
        a new artist is given a colour of their own the moment they appear."""
        artist = (artist or "").strip()
        if artist == drawing.artist:
            return
        drawing.artist = artist
        self._save(drawing)
        self._refresh_row(drawing)
        self._refilter()

    def _refilter(self):
        """A drawing's label or artist changed under the ticks: a tick whose
        row has gone is dropped, and ticks that list nothing are ALL again."""
        self.set_filter(self._filter)

    def _filter_keys(self):
        """Every row the ▾ list offers, as (kind, name): each label and each
        artist in use, "" standing for none."""
        keys = set()
        for d in self.library.drawings:
            keys.add((self.LABEL, d.label))
            keys.add((self.ARTIST, d.artist))
        return keys

    def set_filter(self, items):
        """None is ALL. Otherwise the (kind, name) rows to tick. A row no
        drawing carries is dropped; nothing ticked, or everything, is ALL - a
        filter that lists nothing, or everything, is none."""
        if items is not None:
            keys = self._filter_keys()
            items = frozenset(items) & keys
            if not items or keys <= items:
                items = None
        self._filter = items
        self._refresh_filter_button()
        self.apply_filter()

    def toggle_filter(self, kind, name):
        """One click on a row of the ▾ checklist."""
        item = (kind, name)
        f = self._filter
        self.set_filter({item} if f is None else f ^ {item})

    def filter_ticked(self, kind, name):
        """Is that row ticked? Every row is, under ALL."""
        return self._filter is None or (kind, name) in self._filter

    def clear_filters(self):
        """ALL: every row ticked, every drawing listed."""
        self.set_filter(None)

    def _ticked(self, kind):
        """The names of one kind the ticks name - None under ALL."""
        f = self._filter
        return None if f is None else {name for k, name in f if k == kind}

    # One kind at a time: the older callers' shape, kept.
    def toggle_label_filter(self, label):
        self.toggle_filter(self.LABEL, label)

    def toggle_artist_filter(self, artist):
        self.toggle_filter(self.ARTIST, artist)

    def set_label_filter(self, labels):
        """Just these labels ticked - one as a string ("" the unlabelled) or
        several - and nothing else; None is ALL."""
        self._set_one_kind(self.LABEL, labels)

    def set_artist_filter(self, artists):
        """`set_label_filter`, for artists."""
        self._set_one_kind(self.ARTIST, artists)

    def _set_one_kind(self, kind, names):
        if names is None:
            self.set_filter(None)
            return
        names = [names] if isinstance(names, str) else names
        self.set_filter({(kind, n) for n in names})

    def label_shown(self, label):
        """Is `label` ticked in the ▾ checklist?"""
        return self.filter_ticked(self.LABEL, label)

    def artist_shown(self, artist):
        return self.filter_ticked(self.ARTIST, artist)

    def visible_drawings(self):
        """Every drawing whose label OR whose artist is ticked; all of them
        under ALL."""
        f = self._filter
        if f is None:
            return list(self.library.drawings)
        return [d for d in self.library.drawings
                if (self.LABEL, d.label) in f or (self.ARTIST, d.artist) in f]

    def apply_filter(self):
        """Show only the rows that match, in the library's order; rows are
        kept, just hidden.

        A row that comes back is packed at the END - that is what pack does
        with a window it is not managing - so every change of filter used to
        shuffle the list: the rows that stayed moved up, the ones that came
        back went to the bottom (#v2.8.0, sixth test pass: "karışıyorlar
        birbirlerine"). Rows on show out of order are all taken off and put
        back in it."""
        if not hasattr(self, "_rows"):
            return
        wanted = {id(d) for d in self.visible_drawings()}
        order = [self._rows[id(d)]["row"] for d in self.library.drawings
                 if id(d) in wanted and id(d) in self._rows]
        rows = {str(widgets["row"]) for widgets in self._rows.values()}
        shown = [w for w in self._list_frame.pack_slaves() if str(w) in rows]
        if shown != order:
            for row in shown:
                row.pack_forget()
            for row in order:
                row.pack(fill="x", pady=1, padx=(PAD, 2))
        self._list_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    def _refresh_filter_button(self):
        """"▶  ALL · 74", or what is ticked; the arrow points at the words
        while the list is shut and turns down while it is open (#v2.8.0)."""
        btn = getattr(self, "_filter_button", None)
        if btn is None:
            return
        f = self._filter
        if f is None:
            text = f"{t('all')}  ·  {len(self.library.drawings)}"
        else:
            def shown(item):
                kind, name = item
                if name == "":
                    return t("no_label") if kind == self.LABEL else t("no_artist")
                return name.upper()

            order = sorted(f, key=lambda i: (i[0] != self.LABEL, i[1] == "", i[1].lower()))
            names = [shown(i) for i in order]
            name = " + ".join(names)
            if len(names) > 1 and len(name) > 16:          # the button is one pane wide
                kinds = {k for k, _n in f}
                key = ("n_labels" if kinds == {self.LABEL} else
                       "n_artists" if kinds == {self.ARTIST} else "n_chosen")
                name = t(key, n=len(names))
            text = f"{name}  ·  {len(self.visible_drawings())}"
        icon = getattr(self, "_filter_icons", {}).get(self._filter_open)
        if icon is not None:
            btn.configure(image=icon, compound="left", text=f"  {text}")
        else:
            arrow = FILTER_OPEN if self._filter_open else FILTER_SHUT
            btn.configure(text=f"{arrow}  {text}")

    def _post_filter_menu(self):
        """The ▾ checklist: ALL, every label with its count, the unlabelled,
        then every artist in their own colour and the drawings with none."""
        menu = self._filter_menu = dialogs.PopupMenu(self.root, tearoff=False,
                                                     on_close=self._filter_menu_closed)
        counts, by_artist = {}, {}
        for d in self.library.drawings:
            counts[d.label] = counts.get(d.label, 0) + 1
            by_artist[d.artist] = by_artist.get(d.artist, 0) + 1
        menu.add_checkbutton(label=f"{t('all')}  ·  {len(self.library.drawings)}",
                             checked=lambda: self._filter is None, command=self.clear_filters)
        menu.add_separator()
        for label in self.library.labels():
            menu.add_checkbutton(label=f"{label}  ·  {counts.get(label, 0)}",
                                 checked=lambda l=label: self.filter_ticked(self.LABEL, l),
                                 command=lambda l=label: self.toggle_filter(self.LABEL, l))
        if counts.get("", 0):
            menu.add_separator()
            menu.add_checkbutton(label=f"{t('no_label')}  ·  {counts['']}",
                                 checked=lambda: self.filter_ticked(self.LABEL, ""),
                                 command=lambda: self.toggle_filter(self.LABEL, ""))
        if self.library.artists():
            menu.add_separator()
            menu.add_caption(t("artists"))
            for artist in self.library.artists():
                colour = f"#{self.settings.artist_colour(artist).lower()}"
                menu.add_checkbutton(label=f"{artist}  ·  {by_artist.get(artist, 0)}",
                                     checked=lambda a=artist: self.filter_ticked(self.ARTIST, a),
                                     command=lambda a=artist: self.toggle_filter(self.ARTIST, a),
                                     fg=colour)
            if by_artist.get("", 0):
                menu.add_checkbutton(label=f"{t('no_artist')}  ·  {by_artist['']}",
                                     checked=lambda: self.filter_ticked(self.ARTIST, ""),
                                     command=lambda: self.toggle_filter(self.ARTIST, ""))
        btn = self._filter_button
        self._filter_open = True
        self._refresh_filter_button()
        menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height(),
                      flip_y=btn.winfo_rooty())

    def _filter_menu_closed(self):
        self._filter_open = False
        self._refresh_filter_button()

    def _label_dialog(self, drawing):
        LabelDialog(self.root, drawing, self.library.labels(),
                    lambda text: self.set_label(drawing, text), names_of=self.library.labels,
                    on_rename=self.rename_label, on_delete=self.delete_label)

    def _artist_dialog(self, drawing):
        LabelDialog(self.root, drawing, self.library.artists(),
                    lambda text: self.set_artist(drawing, text), kind="artist",
                    colour_of=lambda name: f"#{self.settings.artist_colour(name).lower()}",
                    names_of=self.library.artists,
                    on_rename=self.rename_artist, on_delete=self.delete_artist)

    # ---- a label or an artist, renamed or taken off everywhere (#v2.8.0) ----
    def rename_label(self, old, new):
        """Every drawing labelled `old` is labelled `new`; returns how many."""
        return self._rename_everywhere(self.LABEL, old, new)

    def rename_artist(self, old, new):
        """Every drawing by `old` is by `new`, and `old`'s colour goes with it."""
        return self._rename_everywhere(self.ARTIST, old, new)

    def delete_label(self, name, parent=None):
        """Take the label off every drawing that has it - asked first."""
        return self._take_off_everywhere(self.LABEL, name, parent)

    def delete_artist(self, name, parent=None):
        """Take the artist off every drawing they drew - asked first."""
        return self._take_off_everywhere(self.ARTIST, name, parent)

    def _rename_everywhere(self, kind, old, new):
        new = (new or "").strip()
        if not new or new == old:
            return 0
        carriers = [d for d in self.library.drawings if getattr(d, kind) == old]
        if kind == self.ARTIST:
            # First, or the rows below would ask for the new name's colour
            # and be handed a fresh one before the old one could move over.
            self.settings.rename_artist(old, new)
        for d in carriers:
            setattr(d, kind, new)
            self._save(d)
            self._refresh_row(d)
        f = self._filter
        if f is not None and (kind, old) in f:
            self._filter = (f - {(kind, old)}) | {(kind, new)}
        self._refilter()
        return len(carriers)

    def _take_off_everywhere(self, kind, name, parent=None):
        carriers = [d for d in self.library.drawings if getattr(d, kind) == name]
        key = "delete_artist_confirm" if kind == self.ARTIST else "delete_label_confirm"
        if not carriers or not dialogs.askyesno(
                dialogs.TITLE, t(key, name=name, n=len(carriers)), icon="warning",
                parent=parent or self.root):
            return False
        for d in carriers:
            setattr(d, kind, "")
            self._save(d)
            self._refresh_row(d)
        if kind == self.ARTIST:
            self.settings.forget_artist(name)
        self._refilter()
        return True

    def _build_canvas_pane(self, parent):
        frame = theme.frame(parent)
        frame.pack(side="left", fill="both", expand=True)

        # The strip under the canvas (#v2.6.0, items 2 and 5): how many
        # pixels, the colours in the drawing left to right, the cell and
        # colour under the cursor.
        bar = theme.frame(frame)
        bar.pack(side="bottom", fill="x", padx=PAD, pady=(0, PAD))
        self._counter_label = theme.label(bar, "", dim=True, anchor="w", font=theme.FONT_MONO)
        self._counter_label.pack(side="left")
        self._cursor_label = theme.label(bar, "", dim=True, anchor="e", font=theme.FONT_MONO)
        self._cursor_label.pack(side="right")
        self._colour_strip = ColourStrip(bar, on_pick=lambda h: self.set_ink(hex_to_rgba(h)))
        self._colour_strip.pack(side="left", fill="x", expand=True, padx=12)

        self._build_camera_bar(frame)

        # Scrollbars, because 16 cells x zoom 48 is wider than the pane — the
        # edge pixels of a sprite must stay reachable at every zoom.
        wrap = theme.frame(frame)
        wrap.pack(side="left", fill="both", expand=True, padx=PAD, pady=PAD)
        vbar = theme.scrollbar(wrap, "vertical")
        vbar.pack(side="right", fill="y")
        hbar = theme.scrollbar(wrap, "horizontal")
        hbar.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(wrap, highlightthickness=0, bg=theme.CANVAS_BG,
                                yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        # Through wrappers: the main view only renders the cells inside the
        # viewport now, so every scroll has to redraw that tile (#v2.8.0).
        vbar.configure(command=self._yview)
        hbar.configure(command=self._xview)
        self.canvas.bind("<Configure>", lambda e: self._redraw_viewport())
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        for seq in theme.right_click_events():
            self.canvas.bind(seq, self._on_pick)
        self.canvas.bind("<MouseWheel>",
                         lambda e: self.zoom(1 if e.delta > 0 else -1, focus=(e.x, e.y)))
        self.canvas.bind("<Button-4>", lambda e: self.zoom(+1, focus=(e.x, e.y)))  # X11 wheel
        self.canvas.bind("<Button-5>", lambda e: self.zoom(-1, focus=(e.x, e.y)))
        self.canvas.bind("<Shift-MouseWheel>",
                         lambda e: self._wheel_pan(1 if e.delta > 0 else -1, 0))
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        # Panning (#v2.8.0). Space+drag is the one every paint program has;
        # the middle button is the one every mouse has - except on macOS,
        # where Tk reports a RIGHT click as Button-2 or Button-3 depending on
        # its version, and both are the eyedropper (`theme.right_click_events`).
        # There the pan is Space+drag alone. (The first try bound a "Button-9"
        # instead: Tk 8.6 knows buttons 1 to 5 only, and on a Mac the window
        # failed to build at all - caught by the v2.8.0 release's Mac tests.)
        if not theme.IS_MAC:
            self.canvas.bind("<ButtonPress-2>", self._pan_start)
            self.canvas.bind("<B2-Motion>", self._pan_move)
        self.root.bind("<KeyPress-space>", self._space_down)
        self.root.bind("<KeyRelease-space>", self._space_up)

    def _build_camera_bar(self, parent):
        """The strip over the drawing (#v2.8.0): where the view goes, and how
        free it is to go there. Above the art rather than in the tools pane
        because it is about the canvas, and because the empty band over the
        canvas was the one piece of chrome with nothing in it."""
        outer = theme.frame(parent)
        outer.pack(side="top", fill="x", padx=PAD, pady=(PAD, 4))

        # The scrollbar is packed on `outer` FIRST and spans the whole strip,
        # like every other scrolled pane in the kit. Packing it after the row
        # left it as wide as the buttons and no wider - a bar that stopped
        # short of the right-hand edge and read as unfinished (#v2.8.0).
        self._cam_hbar = theme.scrollbar(outer, "horizontal")
        self._cam_hbar_shown = False

        row = theme.frame(outer)
        row.pack(side="top", fill="x")

        # The artist's feedback line - "saved", "copied 3x4", "SAVE FAILED" -
        # lives here now, in the top right corner. It used to sit beside the
        # SAVE button and cost it fourteen characters of width; up here it is
        # out of the tools pane and in the corner the eye goes to. Outside the
        # scroller on purpose: a message must not scroll away. As wide as the
        # message (sixth test pass): a fixed fourteen characters cut the START
        # off anything longer - "exported House3.png" read "rted House3.png".
        self._status = theme.label(row, "", dim=True, anchor="e")
        self._status.pack(side="right", padx=(8, 0))

        # The buttons ride on a canvas that scrolls sideways, because eleven
        # of them do not fit a narrow window and chrome that simply vanishes
        # off the edge is worse than chrome you have to scroll to.
        scroller = tk.Canvas(row, highlightthickness=0, bg=theme.BG)
        scroller.pack(side="left", fill="x", expand=True)
        self._cam_scroller = scroller
        self._cam_hbar.configure(command=scroller.xview)
        scroller.configure(xscrollcommand=self._cam_hbar.set)

        bar = theme.frame(scroller)
        self._cam_strip = bar
        scroller.create_window((0, 0), window=bar, anchor="nw")
        bar.bind("<Configure>", self._sync_camera_bar)
        scroller.bind("<Configure>", self._sync_camera_bar)
        for widget in (scroller, bar):
            widget.bind("<MouseWheel>", self._on_camera_wheel)
            widget.bind("<Button-4>", lambda e: self._cam_scroller.xview_scroll(-3, "units"))
            widget.bind("<Button-5>", lambda e: self._cam_scroller.xview_scroll(3, "units"))

        self._cam_fit_button = theme.button(bar, t("cam_fit"), self.fit_pressed, padx=8)
        self._cam_fit_button.pack(side="left")
        theme.separator(bar, "vertical").pack(side="left", fill="y", padx=8)

        # Ten buttons in a strip over the drawing, so the glyph IS the label:
        # an arrow pointing at a corner needs no word and no translation, and
        # eight translated words would not fit across the pane in German. The
        # caption on the right says which one is on, in the artist's language.
        self._cam_mode_buttons = {}
        groups = (
            ((CAM_FREE, t("cam_free")), (CAM_LOCK, t("cam_lock"))),
            ((CAM_TOP_LEFT, "\u2196"), (CAM_TOP_RIGHT, "\u2197"),
             (CAM_BOTTOM_LEFT, "\u2199"), (CAM_BOTTOM_RIGHT, "\u2198")),
            ((CAM_LEFT, "\u2190"), (CAM_CENTRE, "\u00b7"), (CAM_RIGHT, "\u2192")),
        )
        for i, group in enumerate(groups):
            if i:
                theme.separator(bar, "vertical").pack(side="left", fill="y", padx=6)
            for mode, label in group:
                btn = theme.button(bar, label, lambda m=mode: self.set_camera_mode(m),
                                   padx=6 if len(label) > 1 else 8)
                btn.pack(side="left", padx=(0, 3))
                self._cam_mode_buttons[mode] = btn

        self._cam_name_label = theme.label(bar, "", dim=True)
        self._cam_name_label.pack(side="left", padx=(10, 0))
        self._sync_camera_bar()

    def _sync_camera_bar(self, _event=None):
        """Size the strip's canvas to it, and show the scrollbar only when the
        buttons actually overflow the window."""
        strip, scroller = self._cam_strip, self._cam_scroller
        strip.update_idletasks()
        need_w, need_h = strip.winfo_reqwidth(), strip.winfo_reqheight()
        if int(scroller.cget("height")) != need_h:
            scroller.configure(height=need_h)
        scroller.configure(scrollregion=(0, 0, need_w, need_h))
        have = scroller.winfo_width()
        overflows = have > 1 and need_w > have
        if overflows and not self._cam_hbar_shown:
            self._cam_hbar.pack(side="bottom", fill="x", pady=(2, 0))
        elif not overflows and self._cam_hbar_shown:
            self._cam_hbar.pack_forget()
            self._cam_scroller.xview_moveto(0)
        self._cam_hbar_shown = overflows

    def _on_camera_wheel(self, event):
        self._cam_scroller.xview_scroll(-3 if event.delta > 0 else 3, "units")

    def set_camera_mode(self, mode):
        if mode not in CAMERA_MODES:
            raise ValueError(f"camera mode must be one of {CAMERA_MODES}, got {mode!r}")
        if mode == CAM_LOCK:
            # Freeze the view exactly where it is standing right now - which
            # is the whole gesture: frame it, then press LOCK.
            self._locked_at = tuple(int(v) for v in self._view_origin())
        else:
            # Leaving LOCK ends it for every drawing: the next LOCK freezes
            # whatever the artist frames then, not views from before.
            self._locked_at = None
            self._lock_frames.clear()
        self.camera_mode = mode
        self.settings.camera = mode
        self._refresh_camera_ui()
        # Straight to that mode's home, rather than waiting for the next
        # scroll to clamp: pressing a button has to show what it did.
        self.home_view()

    def _refresh_camera_ui(self):
        for mode, btn in getattr(self, "_cam_mode_buttons", {}).items():
            theme.set_pressed(btn, mode == self.camera_mode)
        fit = getattr(self, "_cam_fit_button", None)
        if fit is not None:
            # Dimmed, not disabled, under LOCK: a press still has to say why
            # it did nothing (`fit_pressed`).
            tone = theme.ON_DIM if self._camera_frozen() else theme.ON_SURFACE
            fit.configure(fg=tone, activeforeground=tone)
        label = getattr(self, "_zoom_label", None)
        if label is not None:
            label.configure(text=f"{self.zoom_level} px")
        name = getattr(self, "_cam_name_label", None)
        if name is not None:
            name.configure(text=t(CAMERA_NAMES[self.camera_mode]))

    def _build_tools_pane(self, parent):
        outer = theme.frame(parent, width=TOOLS_W)
        outer.pack(side="right", fill="y")
        outer.pack_propagate(False)
        # The straight line, top to bottom, that fences the tools off from
        # the drawing (item 3).
        theme.separator(outer, "vertical").pack(side="left", fill="y")
        column = theme.frame(outer)
        column.pack(side="left", fill="both", expand=True, padx=(PAD, 0))

        # --- bottom-right block, packed first so it owns the bottom (item 3, 13, 15)
        bottom = theme.frame(column)
        bottom.pack(side="bottom", fill="x", pady=(0, PAD), padx=(0, SCROLLBAR_W))
        self._tools_bottom = bottom

        # --- everything else scrolls (#v2.6.0: the pane outgrew an 820px window)
        scroller = tk.Canvas(column, highlightthickness=0, bg=theme.BG, width=INNER_W)
        tbar = theme.scrollbar(column, "vertical")
        # Packed only when the pane actually overflows (#v2.8.0). It used to
        # be there always, so a maximised window showed a full-height bar with
        # nothing to scroll - and took INNER_W's worth of width to do it.
        self._tools_bar = tbar
        self._tools_bar_shown = False
        scroller.pack(side="left", fill="both", expand=True)
        scroller.configure(yscrollcommand=tbar.set)
        tbar.configure(command=scroller.yview)
        frame = theme.frame(scroller)
        window = scroller.create_window((0, 0), window=frame, anchor="nw", width=INNER_W)
        # INNER_W wide always, and centred in what the pane has spare (#v2.8.0,
        # ninth test pass: "kenarlardan kısaltılsın eşit olsun"): the rows used
        # to stretch into the room the hidden scrollbar leaves, and ran 14 px
        # past the colour grids and the colour panel, which cannot stretch.
        self._tools_window = window
        frame.bind("<Configure>", self._sync_tools_pane)
        scroller.bind("<Configure>", lambda e: self._sync_tools_pane())
        self._tools_frame = frame
        self._tools_scroller = scroller
        # Pack from the window bottom up so UPDATE/HELP sit on the bottom
        # edge and grid lines sit immediately above them (#v2.7.0, item 2).
        foot = theme.frame(bottom)
        foot.pack(side="bottom", fill="x")
        self._size_label = theme.label(foot, "", fg=theme.ON_SURFACE, cursor="hand2",
                                       font=theme.FONT_BOLD)
        self._size_label.pack(side="left")
        self._size_label.bind("<Button-1>", lambda e: self._set_size(self._selected))
        # GUIDE since the eighth test pass ("Help'in adı Guide olsun"): a word
        # longer than HELP, so a little less padding keeps the row inside
        # the pane with a three-digit size beside it.
        self._help_button = theme.button(foot, t("help"), self.toggle_help, padx=8)
        self._help_button.pack(side="right")
        self._update_button = theme.button(foot, t("update"), self.check_for_update, padx=8)
        self._update_button.pack(side="right", padx=(0, 4))
        self._lang_button = theme.button(foot, t("language"), self._post_language_menu, padx=6)
        self._lang_button.pack(side="right", padx=(0, 4))

        lines_row = theme.frame(bottom)
        lines_row.pack(side="bottom", fill="x", pady=(0, 6))
        self._grid_buttons = {
            True: theme.button(lines_row, t("with_grid"), lambda: self.set_show_grid(True), padx=4),
            False: theme.button(lines_row, t("without_grid"), lambda: self.set_show_grid(False), padx=4),
        }
        self._grid_buttons[True].pack(side="left", expand=True, fill="x")
        self._grid_buttons[False].pack(side="left", expand=True, fill="x", padx=(2, 0))

        previews = theme.frame(bottom)
        previews.pack(side="bottom", fill="x", pady=(0, 6))
        col1 = theme.frame(previews)
        col1.pack(side="left", anchor="s")
        # The zoom, in the gap over the 1x preview (#v2.8.0): a number the
        # artist checks constantly, in the corner already given to "how big
        # is this really", and costing no row of its own.
        self._current_label = theme.label(col1, t("current"), dim=True)
        self._current_label.pack(anchor="w")
        self._zoom_label = theme.label(col1, "", dim=True, anchor="w", font=theme.FONT_MONO)
        self._zoom_label.pack(anchor="w")
        self._one_x_label = theme.label(col1, "1x", dim=True)
        self._one_x_label.pack()
        self.preview_1x = tk.Canvas(col1, highlightthickness=0, bg=theme.BG)
        self.preview_1x.pack()
        col2 = theme.frame(previews)
        col2.pack(side="right", anchor="s")
        head = theme.frame(col2)
        head.pack(fill="x")
        self._squint_label = theme.label(head, t("squint"), dim=True)
        self._squint_label.pack(side="left")
        # LOOK, beside the other picture that is for looking (#v2.8.0, eighth
        # test pass: "squint ... sağına check Look ekleyelim, orada çizim
        # kapalı olsun, sadece bakma için"): see `set_looking`.
        self._look_button = theme.button(head, "", self.toggle_looking, padx=3, pady=0,
                                         font=theme.FONT_SMALL, bg=theme.BG,
                                         activebackground=theme.PANEL_HI, anchor="e")
        self._look_button.pack(side="right", padx=(8, 0))
        self.preview_squint = tk.Canvas(col2, highlightthickness=0, bg=theme.BG)
        self.preview_squint.pack()
        self._refresh_look_ui()

        # --- top block
        save_row = theme.frame(frame)
        save_row.pack(fill="x", pady=(0, 2))  # flush with the top of the pane
        self._save_button = theme.button(save_row, t("save"), self.save, bg=theme.WORK,
                                         fg=theme.ON_ACCENT, activebackground=theme.ACCENT,
                                         activeforeground=theme.ON_ACCENT)
        # The full width of the pane (#v2.8.0). It used to give fourteen
        # characters to a status label; that message is in the camera bar's
        # right-hand corner now, where it is nearer the artist's eye and does
        # not cost the one button they press most its size.
        self._save_button.pack(side="left", fill="x", expand=True)

        tool_row = theme.frame(frame)
        tool_row.pack(fill="x", pady=2)
        self._tool_buttons = {
            "draw": theme.button(tool_row, t("draw"), lambda: self.set_tool("draw")),
            "erase": theme.button(tool_row, t("erase"), lambda: self.set_tool("erase")),
            "fill": theme.button(tool_row, t("fill"), lambda: self.set_tool("fill")),
            "select": theme.button(tool_row, t("select"), lambda: self.set_tool("select")),
        }
        for i, btn in enumerate(self._tool_buttons.values()):
            btn.pack(side="left", expand=True, fill="x", padx=(0 if i == 0 else 2, 0))

        undo_row = theme.frame(frame)
        undo_row.pack(fill="x", pady=2)
        self._undo_button = theme.button(undo_row, t("undo"), self.undo)
        self._undo_button.pack(side="left", expand=True, fill="x")
        self._redo_button = theme.button(undo_row, t("redo"), self.redo)
        self._redo_button.pack(side="left", expand=True, fill="x", padx=(2, 0))

        # Eraser footprint (#v2.6.0, item 8)
        eraser_row = theme.frame(frame)
        eraser_row.pack(fill="x", pady=2)
        self._eraser_label = theme.label(eraser_row, t("eraser"), dim=True)
        self._eraser_label.pack(side="left")
        self._eraser_w = self._spinbox(eraser_row, 1, ERASER_MAX, self._on_eraser_size)
        self._eraser_h = self._spinbox(eraser_row, 1, ERASER_MAX, self._on_eraser_size)
        self._eraser_cells_label = theme.label(eraser_row, t("cells"), dim=True)
        self._eraser_cells_label.pack(side="right", padx=(4, 0))
        self._eraser_h.pack(side="right", ipady=2)
        theme.label(eraser_row, "\u00d7", dim=True).pack(side="right", padx=3)
        self._eraser_w.pack(side="right", ipady=2)
        self._eraser_wh_label = theme.label(eraser_row, t("wxh"), dim=True)
        self._eraser_wh_label.pack(side="right", padx=(0, 6))
        theme.separator(frame, "horizontal").pack(fill="x", pady=(3, 1))

        # Grid colours (#v2.6.0, item 7): the two checkerboard tones. Type a
        # code, or click the swatch button for the system colour picker.
        #
        # Laid out on a grid rather than nested packs (#v2.8.0): the two
        # captions moved UP onto the "Grid" line and DEFAULT moved DOWN under
        # the entries, which is what lets the two colour fields have the full
        # width of the pane between them - DEFAULT used to take a third of the
        # row - and leaves the block room to grow.
        # Four columns since the ninth test pass ("colour 1 ve 2 üç nokta
        # hizasına çekilsin ... boş olan yere iki tane hazır stil gelsin, üste
        # White, alta Black"): Grid / DEFAULT, then the two ready grounds -
        # WHITE over BLACK, both tones at once - then each colour, its caption
        # right beside its … and its field under both, the two the same width.
        block = theme.frame(frame)
        block.pack(fill="x", pady=(3, 0))
        block.grid_columnconfigure(2, weight=1, uniform="grid")
        block.grid_columnconfigure(3, weight=1, uniform="grid")
        self._grid_title = theme.label(block, t("grid"), dim=True)
        self._grid_title.grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._grid_presets = {}
        for row, (key, tone) in enumerate((("grid_white", "FFFFFF"), ("grid_black", "000000"))):
            btn = theme.button(block, t(key), lambda h=tone: self.set_grid_colours(c1=h, c2=h),
                               padx=3, pady=2)
            btn.grid(row=row, column=1, sticky="ew", padx=(0, 4), pady=(0, 2) if not row else 0)
            self._grid_presets[key] = btn
        self._grid_captions = {}
        self._grid_entries = {}
        self._grid_pickers = {}
        for i, (key, caption) in enumerate((("c1", "colour_1"), ("c2", "colour_2"))):
            head = theme.frame(block)
            head.grid(row=0, column=2 + i, sticky="ew", padx=(4 if i else 0, 0))
            # The picker sits on the CAPTION line beside the name it opens,
            # not next to the entry (#v2.8.0), and the name sits right up
            # against it - flush right, the pair one unit over the field.
            picker = theme.button(head, "\u2026", lambda k=key: self._pick_grid_colour(k),
                                  padx=3, pady=0)
            picker.pack(side="right")
            self._grid_pickers[key] = picker
            label = theme.label(head, t(caption), dim=True, font=theme.FONT_SMALL)
            label.pack(side="right", padx=(0, 1))
            self._grid_captions[key] = (label, caption)
            entry = theme.entry(block, justify="center", width=7)
            entry.grid(row=1, column=2 + i, sticky="ew", padx=(4 if i else 0, 0), ipady=2)
            entry.bind("<Return>", lambda e, k=key: self._on_grid_entry(k))
            entry.bind("<KP_Enter>", lambda e, k=key: self._on_grid_entry(k))
            entry.bind("<FocusOut>", lambda e, k=key: self._on_grid_entry(k))
            entry.bind("<Double-Button-1>", self._select_all_in_entry)
            self._grid_entries[key] = entry
        # Under the word "Grid", in the corner the caption row leaves empty.
        self._grid_default_button = theme.button(
            block, t("default"), self.reset_grid_colours, padx=3, pady=2)
        self._grid_default_button.grid(row=1, column=0, sticky="ew", padx=(0, 4))

        # What the next click will paint — the one piece of state the artist
        # otherwise has to keep in their head. An Entry, so the code can be
        # copied (double-click selects it all) or typed over (item 5).
        self._ink_title = theme.label(frame, t("ink"), dim=True)
        self._ink_title.pack(pady=(4, 0), anchor="w")
        ink_row = theme.frame(frame)
        ink_row.pack(fill="x")
        self._ink_entry = theme.entry(ink_row, justify="center")
        self._ink_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self._ink_entry.bind("<Return>", self._on_ink_entry_commit)
        self._ink_entry.bind("<KP_Enter>", self._on_ink_entry_commit)
        self._ink_entry.bind("<FocusOut>", self._on_ink_entry_commit)
        self._ink_entry.bind("<Escape>", lambda e: self._refresh_ink_ui() or self.canvas.focus_set())
        self._ink_entry.bind("<Double-Button-1>", self._on_ink_entry_double)
        self._ink_swatch = self._ink_entry  # the name older code and tests know
        theme.button(ink_row, "+", self._add_ink_to_favourites, padx=8,
                     font=theme.FONT_BOLD).pack(side="left", padx=(4, 0))

        self._fav_title = theme.label(frame, t("favourites"), dim=True)
        self._fav_title.pack(pady=(4, 0), anchor="w")
        self._favourites = SwatchGrid(frame, INNER_W, SWATCH_COLS,
                                      on_pick=lambda h: self.set_ink(hex_to_rgba(h)),
                                      on_context=self._favourite_menu)
        self._favourites.pack(fill="x")
        self._refresh_favourites()

        self._ready_title = theme.label(frame, t("ready"), dim=True)
        self._ready_title.pack(pady=(4, 0), anchor="w")
        self._ready = SwatchGrid(frame, INNER_W, SWATCH_COLS,
                                 on_pick=lambda h: self.set_ink(hex_to_rgba(h)))
        self._ready.pack(fill="x")
        self._ready.set_colours(READY)

        self._build_picker(frame)
        self._build_symmetry_block(frame)

        self._bind_tools_wheel(frame)
        self._refresh_tool_buttons()
        self._refresh_symmetry_ui()
        self._refresh_eraser_ui()
        self._refresh_grid_ui()
        self._refresh_ink_ui()

    def _sync_tools_pane(self, _event=None):
        """Scroll region, and the bar only while there is something to scroll.

        The content is INNER_W wide and, while the bar is hidden, stands
        with even margins between the pane's dividing line and the window's
        edge; the block at the bottom lines up under it."""
        scroller = self._tools_scroller
        width = scroller.winfo_width()
        if width > 1:
            x0 = max(0, (PAD + width - INNER_W) // 2 - PAD)
            if scroller.coords(self._tools_window)[:1] != [float(x0)]:
                scroller.coords(self._tools_window, x0, 0)
            bottom = getattr(self, "_tools_bottom", None)
            spare = width + (SCROLLBAR_W if self._tools_bar_shown else 0) - INNER_W
            pads = (x0, max(0, spare - x0))
            if bottom is not None and _pads(bottom.pack_info().get("padx", 0)) != pads:
                bottom.pack_configure(padx=pads)
        scroller.configure(scrollregion=scroller.bbox("all"))
        need = self._tools_frame.winfo_reqheight()
        have = scroller.winfo_height()
        overflows = have > 1 and need > have
        if overflows and not self._tools_bar_shown:
            self._tools_bar.pack(side="right", fill="y", before=scroller)
        elif not overflows and self._tools_bar_shown:
            self._tools_bar.pack_forget()
            scroller.yview_moveto(0)
        self._tools_bar_shown = overflows

    def _spinbox(self, parent, lo, hi, command, width=3):
        var = tk.StringVar()
        spin = tk.Spinbox(parent, from_=lo, to=hi, width=width, textvariable=var, command=command,
                          bg=theme.PANEL, fg=theme.ON_SURFACE, buttonbackground=theme.PANEL_HI,
                          relief="flat", bd=0, highlightthickness=1, highlightbackground=theme.SHADOW,
                          insertbackground=theme.ON_SURFACE, font=theme.FONT_MONO, justify="center")
        spin.var = var
        spin.bind("<Return>", lambda e: command())
        spin.bind("<FocusOut>", lambda e: command())
        return spin

    def _bind_tools_wheel(self, widget):
        """The wheel scrolls the tools pane wherever the pointer is over it
        (the spinboxes keep the wheel for their own value)."""
        if isinstance(widget, tk.Spinbox):
            return
        widget.bind("<MouseWheel>", self._on_tools_wheel)
        widget.bind("<Button-4>", lambda e: self._tools_scroller.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: self._tools_scroller.yview_scroll(1, "units"))
        for child in widget.winfo_children():
            self._bind_tools_wheel(child)

    def _on_tools_wheel(self, event):
        self._tools_scroller.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_eraser_size(self):
        try:
            self.set_eraser_size(int(self._eraser_w.var.get()), int(self._eraser_h.var.get()))
        except ValueError:
            self._refresh_eraser_ui()

    def _refresh_eraser_ui(self):
        if not hasattr(self, "_eraser_w"):
            return
        w, h = self.eraser_size
        if self._eraser_w.var.get() != str(w):
            self._eraser_w.var.set(str(w))
        if self._eraser_h.var.get() != str(h):
            self._eraser_h.var.set(str(h))

    def _on_grid_entry(self, key):
        text = self._grid_entries[key].get().strip().lstrip("#")
        if re.fullmatch(r"[0-9a-fA-F]{6}", text):
            self.set_grid_colours(**{key: text})
        else:
            self._refresh_grid_ui()

    def _pick_grid_colour(self, key):
        """The … beside a grid colour: the kit's own picker (#v2.8.0), and
        the checkerboard behind the art follows it live while it is open, the
        way the export background's preview does. CANCEL puts the colour
        back; OK is ONE undo step, however far the picker was dragged -
        nothing is written to the settings until then."""
        current = self.grid_colours()[0 if key == "c1" else 1]

        def preview(hexcol):
            self._grid_preview = {key: hexcol.lstrip("#")}
            self._draw_main()

        caption = t("colour_1" if key == "c1" else "colour_2")
        try:
            hexcol = ask_colour(self.root, current, title=f"{t('grid')} · {caption}",
                                on_change=preview)
        finally:
            self._grid_preview = None
        if hexcol:
            self.set_grid_colours(**{key: hexcol})  # a no-op records nothing
        else:
            self._draw_main()
        self.canvas.focus_set()

    def _refresh_grid_ui(self):
        if not hasattr(self, "_grid_entries"):
            return
        for key, hexcol in zip(("c1", "c2"), self.grid_colours()):
            entry = self._grid_entries[key]
            entry.delete(0, "end")
            entry.insert(0, hexcol)
            entry.configure(bg=hexcol, fg=theme.readable_on(hexcol),
                            insertbackground=theme.readable_on(hexcol))
        if hasattr(self, "_grid_buttons"):
            for on, btn in self._grid_buttons.items():
                theme.set_pressed(btn, on == self.show_grid)

    def _select_all_in_entry(self, event):
        event.widget.focus_set()
        event.widget.select_range(0, "end")
        event.widget.icursor("end")
        return "break"

    def _build_symmetry_block(self, frame):
        """Under the colour panel (#v2.5.0): a mode row, a shape row, a hint.

        OFF     — plain painting.
        MIRROR  — the placed bar; painting along it is mirrored across it.
                  Press on the bar to drag it, or PLACE BAR to click it
                  somewhere new.
        STICK   — every click paints `length` cells in the bar's direction.
        """
        self._sym_title = theme.label(frame, t("symmetry"), dim=True)
        self._sym_title.pack(pady=(4, 0), anchor="w")
        modes = theme.frame(frame)
        modes.pack(fill="x", pady=2)
        self._sym_mode_buttons = {}
        for i, (mode, key) in enumerate(((symmetry.OFF, "off"), (symmetry.MIRROR, "mirror"),
                                          (symmetry.STICK, "stick"))):
            btn = theme.button(modes, t(key), lambda m=mode: self.set_symmetry_mode(m), padx=4)
            btn.pack(side="left", expand=True, fill="x", padx=(0 if i == 0 else 2, 0))
            self._sym_mode_buttons[mode] = btn

        shape = theme.frame(frame)
        shape.pack(fill="x", pady=2)
        self._sym_orient_button = theme.button(
            shape, "", self._toggle_symmetry_orientation, padx=5)
        self._sym_orient_button.pack(side="left", expand=True, fill="x")
        self._sym_length_label = theme.label(shape, t("length"), dim=True)
        self._sym_length_label.pack(side="left", padx=(6, 2))
        self._sym_length_var = tk.StringVar(value=str(self._sym_length))
        self._sym_length_spin = tk.Spinbox(
            shape, from_=symmetry.MIN_LENGTH, to=symmetry.MAX_LENGTH, width=3,
            textvariable=self._sym_length_var, command=self._on_symmetry_length,
            bg=theme.PANEL, fg=theme.ON_SURFACE, buttonbackground=theme.PANEL_HI,
            relief="flat", bd=0, highlightthickness=1, highlightbackground=theme.SHADOW,
            insertbackground=theme.ON_SURFACE, font=theme.FONT_MONO, justify="center")
        self._sym_length_spin.pack(side="left", ipady=2)
        self._sym_length_spin.bind("<Return>", self._on_symmetry_length)
        self._sym_length_spin.bind("<FocusOut>", self._on_symmetry_length)
        self._sym_place_button = theme.button(shape, t("place_bar"), self.arm_symmetry_placement, padx=5)
        self._sym_place_button.pack(side="left", padx=(2, 0))

        self._sym_hint = theme.label(frame, "", dim=True, anchor="w", wraplength=INNER_W,
                                     justify="left")
        self._sym_hint.pack(fill="x")
        # the old single toggle, kept as a name for anything that still asks
        self._sym_button = self._sym_mode_buttons[symmetry.MIRROR]

    def _toggle_symmetry_orientation(self):
        other = (symmetry.HORIZONTAL if self._sym_orientation == symmetry.VERTICAL
                 else symmetry.VERTICAL)
        self.set_symmetry_orientation(other)

    def _on_symmetry_length(self, _event=None):
        try:
            self.set_symmetry_length(int(self._sym_length_var.get()))
        except ValueError:
            self._sym_length_var.set(str(self._sym_length))
        if _event is not None and getattr(_event, "keysym", "") == "Return":
            self.canvas.focus_set()

    def _refresh_symmetry_ui(self):
        if not hasattr(self, "_sym_mode_buttons"):
            return
        for mode, btn in self._sym_mode_buttons.items():
            theme.set_pressed(btn, mode == self.symmetry_mode)
        vertical = self._sym_orientation == symmetry.VERTICAL
        self._sym_orient_button.configure(text="\u2502 90\u00b0" if vertical else "\u2500 180\u00b0")
        if self._sym_length_var.get() != str(self._sym_length):
            self._sym_length_var.set(str(self._sym_length))
        lined = self.symmetry_mode in (symmetry.MIRROR, symmetry.STICK)
        self._sym_place_button.configure(state="normal" if lined else "disabled",
                                         fg=theme.ON_SURFACE if lined else theme.ON_DIM)
        theme.set_pressed(self._sym_place_button, lined and self._placing_bar)
        if self.symmetry_mode == symmetry.OFF:
            self._sym_hint.configure(text="", fg=theme.ON_DIM)
        elif self.symmetry_mode == symmetry.STICK:
            axis = t("stick_axis_rows") if vertical else t("stick_axis_cols")
            self._sym_hint.configure(text=t("stick_hint", n=self._sym_length, axis=axis),
                                     fg=theme.ON_DIM)
        elif self._placing_bar:
            self._sym_hint.configure(text=t("mirror_place"), fg=theme.ACCENT)
        else:
            self._sym_hint.configure(text=t("mirror_hint"), fg=theme.ON_DIM)

    def _build_picker(self, frame):
        """The full colour panel, embedded \u2014 a hue strip over a shade square,
        the way a phone app does it. No popup, no extra window."""
        self._colour_title = theme.label(frame, t("colour"), dim=True)
        self._colour_title.pack(pady=(4, 0), anchor="w")
        self._picker = ColourPicker(
            frame, PICKER_W, SV_H, HUE_H,
            on_pick=lambda rgb, more=False: self.set_ink(rgb + (255,), coalesce=more))
        self._picker.pack(anchor="w")
        # The names the rest of the app and the tests already know.
        self._hue_strip = self._picker.hue_strip
        self._sv_square = self._picker.sv_square

    @property
    def _hue(self):
        return self._picker.hue

    def _draw_sv_square(self):
        self._picker.draw_shades()

    def _on_hue(self, event):
        self._picker.pick_hue(event)

    def _on_sv(self, event):
        self._picker.pick_shade(event)

    def _bind_keys(self):
        """Ctrl on Windows/Linux, Cmd on macOS — both are bound on a Mac, since
        plenty of people there reach for Ctrl out of habit (item 2)."""
        mods = ["Control", "Command"] if theme.IS_MAC else ["Control"]
        for mod in mods:
            self.root.bind(f"<{mod}-z>", lambda e: self.undo())
            self.root.bind(f"<{mod}-y>", lambda e: self.redo())
            self.root.bind(f"<{mod}-Shift-Z>", lambda e: self.redo())
            self.root.bind(f"<{mod}-Shift-z>", lambda e: self.redo())
            self.root.bind(f"<{mod}-s>", lambda e: self.save())
            self.root.bind(f"<{mod}-n>", lambda e: self._new_drawing_dialog())
            # copy / cut / paste (#v2.6.0) — not while typing in an entry
            self.root.bind(f"<{mod}-c>", self._typing_guard(self.copy_selection))
            self.root.bind(f"<{mod}-x>", self._typing_guard(self.cut_selection))
            self.root.bind(f"<{mod}-v>", self._typing_guard(self.paste))
        # Single letters must not fire while the artist is typing a hex code.
        self.root.bind("<Key-e>", self._typing_guard(lambda: self.set_tool("erase")))
        self.root.bind("<Key-b>", self._typing_guard(lambda: self.set_tool("draw")))
        self.root.bind("<Key-f>", self._typing_guard(lambda: self.set_tool("fill")))
        self.root.bind("<Key-s>", self._typing_guard(lambda: self.set_tool("select")))
        self.root.bind("<Key-m>", self._typing_guard(self.cycle_symmetry_mode))
        self.root.bind("<Return>", self._typing_guard(self.commit_floating))
        self.root.bind("<KP_Enter>", self._typing_guard(self.commit_floating))
        self.root.bind("<Delete>", self._typing_guard(self.delete_selection))
        self.root.bind("<BackSpace>", self._typing_guard(self.delete_selection))
        self.root.bind("<Left>", self._typing_guard(lambda: self.nudge_floating(-1, 0)))
        self.root.bind("<Right>", self._typing_guard(lambda: self.nudge_floating(1, 0)))
        self.root.bind("<Up>", self._typing_guard(lambda: self.nudge_floating(0, -1)))
        self.root.bind("<Down>", self._typing_guard(lambda: self.nudge_floating(0, 1)))
        self.root.bind("<plus>", self._typing_guard(lambda: self.zoom(+1)))
        self.root.bind("<KP_Add>", self._typing_guard(lambda: self.zoom(+1)))
        self.root.bind("<minus>", self._typing_guard(lambda: self.zoom(-1)))
        self.root.bind("<KP_Subtract>", self._typing_guard(lambda: self.zoom(-1)))
        self.root.bind("<F1>", lambda e: self.toggle_help())
        # A tool for testing, so the TEST build's only (sixth test pass:
        # "snapshot sadece test modunda olsun"). On every window of the kit, a
        # dialog or a menu included: the moment worth a picture is often one
        # with something open over the canvas.
        if is_test_build(self.root):
            self.root.bind_all("<F12>", self.take_snapshot)
        self.root.bind("<Escape>", self._on_escape)

    def _typing_guard(self, fn):
        def handler(_event):
            focus = self.root.focus_get()
            if isinstance(focus, (tk.Entry, tk.Spinbox)):
                return None
            fn()
            return "break"
        return handler

    def _on_escape(self, _event=None):
        if self._help is not None:
            self.toggle_help()
        elif isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)):
            self.canvas.focus_set()
        elif self.floating is not None:
            self.commit_floating()  # never destructive: Esc drops it where it is
        elif self.selection is not None:
            self.clear_selection()

    # ---- canvas <-> grid glue -------------------------------------------
    def _grid_at(self, event):
        # canvasx/canvasy fold the scroll offset in; raw event coords would be
        # off by exactly the scrolled distance.
        return (int(self.canvas.canvasx(event.x)) // self.zoom_level,
                int(self.canvas.canvasy(event.y)) // self.zoom_level)

    def _on_press(self, event):
        self.canvas.focus_set()  # take focus back from the hex entry
        if self._panning:
            self._pan_start(event)
            return
        if self._look_refuses():
            return
        edges = self._hit_edge(event)
        if edges:
            # One stroke for the whole drag, so the resize undoes in one press
            # however many cells it moved (#v2.8.0). The reference is the
            # pointer's SCREEN position and the size at press - see _drag_edge
            # for why measuring against the live edge does not work.
            d = self.history.current
            self.history.begin_stroke()
            self._edge_drag = {"edges": edges, "x": event.x, "y": event.y,
                               "w": d.width, "h": d.height}
            return
        self.on_canvas_press(*self._grid_at(event))

    def _on_drag(self, event):
        if self._panning:
            self._pan_move(event)
            return
        if self.looking:
            return
        if self._edge_drag is not None:
            self._drag_edge(event)
            return
        self._autoscroll(event)
        cell = self._grid_at(event)
        self.on_canvas_drag(*cell)
        self._hover_cell = cell
        self._draw_ghost()  # the footprint rides along with the stroke

    def _on_release(self, event):
        if self._panning:
            self._pan_from = None
            return
        if self._edge_drag is not None:
            self._edge_drag = None
            if self.history.end_stroke():
                self._after_change()
            self.canvas.configure(cursor="")
            return
        self.on_canvas_release()

    def _hit_edge(self, event):
        """Which edges of the drawing the pointer is grabbing.

        A tuple, because the corners belong to two of them at once (#v2.8.0):
        grabbing the top-left moves the top and the left together, the way a
        corner handle works in any editor. Empty when the pointer is not on an
        edge at all.

        The four edges of the grid resize it the way a note or an image app
        resizes its canvas (#v2.8.0): drag one in and the pixel lines on that
        side go, drag it out and empty ones arrive. It replaces the accent
        triangle that used to sit on the bottom-right corner - one grab, in
        one place, that changed the ZOOM rather than the drawing.

        Nothing is drawn for these: the cursor is the affordance. The band
        lies almost wholly OUTSIDE the art - EDGE_GRAB beyond the edge, only
        `EDGE_GRAB_INSIDE` at most within it - so a stroke along the border
        stays a stroke."""
        if self.history is None or self._painting or self.floating is not None or self.looking:
            return ()
        d = self.history.current
        z = self.zoom_level
        # A drawing this small on screen has no edge worth aiming at - a
        # 16x19 sprite at 1x is 16 px across, less than two bands - so the
        # grabs are off and every press paints. Zoom in to resize.
        if min(d.width, d.height) * z < 4 * EDGE_GRAB:
            return ()
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        # An eraser whose footprint still covers some of the drawing is
        # ERASING, whatever band the pointer is in: with half of it past the
        # edge, the press used to catch on the grab and resize instead.
        if self._eraser_reaches(int(x) // z, int(y) // z):
            return ()
        w, h = d.width * z, d.height * z
        inside = min(EDGE_GRAB_INSIDE, z // 8)
        # Within the drawing's span on the other axis, give or take the band,
        # so the corners belong to both edges rather than to neither.
        near_y = -EDGE_GRAB <= y <= h + EDGE_GRAB
        near_x = -EDGE_GRAB <= x <= w + EDGE_GRAB
        edges = []
        if near_y and -EDGE_GRAB <= x < inside:
            edges.append("left")
        elif near_y and w - inside <= x <= w + EDGE_GRAB:
            edges.append("right")
        if near_x and -EDGE_GRAB <= y < inside:
            edges.append("top")
        elif near_x and h - inside <= y <= h + EDGE_GRAB:
            edges.append("bottom")
        return tuple(edges)

    def _drag_edge(self, event):
        """Move the grabbed edge(s) to wherever the pointer is, in whole cells.

        Measured from where the gesture STARTED, in screen pixels, against the
        size the drawing had then. The first version measured each step
        against the live edge, and for the left and the top that runs away:
        growing there inserts cells at the origin, so every cell added shifts
        the whole drawing in canvas coordinates, the "distance to the edge"
        changes without the pointer moving, and the next event adds more. Two
        pixels of travel became a dozen columns (#v2.8.0).

        Screen pixels are the stable frame only if the untouched art holds
        still on screen while the origin moves under it, so a left or top
        resize scrolls the view by exactly what it inserted (`_follow_shift`,
        which moves LOCK's frozen point along with it: held where it was, the
        art would jump a cell for every cell added and the edge would stay put
        under a pointer walking away from it)."""
        drag = self._edge_drag
        if drag is None:
            return
        self._release_fit()  # the drawing is changing size under the artist's hand
        z = self.zoom_level
        d = self.history.current
        shift = d.shift
        for edge in drag["edges"]:
            horizontal = edge in ("left", "right")
            travel = (event.x - drag["x"]) if horizontal else (event.y - drag["y"])
            if edge in ("left", "top"):
                travel = -travel        # dragging the near edge OUT grows the grid
            was = drag["w"] if horizontal else drag["h"]
            now = d.width if horizontal else d.height
            d.resize_edge(edge, min(HUGE_SIDE, was + int(round(travel / z))) - now)
        self._follow_shift(shift)
        self.selection = None
        self._refresh_size_label()
        self._draw_main()

    def _autoscroll(self, event):
        """Dragging against the edge of the visible area scrolls the canvas
        that way, one cell at a time (#v2.6.0, item 6) — so a line can be
        continued past the edge while zoomed in, without letting go.

        Not under LOCK: nothing could scroll, and the repaint below would
        still run on every motion event of a stroke near the edge."""
        if self._camera_frozen():
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 40 or h < 40:
            return
        # A scroll unit is one pixel, so a cell is `z` of them - and never
        # less than one pixel, below 1 px a cell.
        z = max(1, round(self.zoom_level))
        moved = False
        if event.x < AUTOSCROLL_MARGIN:
            self.canvas.xview_scroll(-z, "units"); moved = True
        elif event.x > w - AUTOSCROLL_MARGIN:
            self.canvas.xview_scroll(z, "units"); moved = True
        if event.y < AUTOSCROLL_MARGIN:
            self.canvas.yview_scroll(-z, "units"); moved = True
        elif event.y > h - AUTOSCROLL_MARGIN:
            self.canvas.yview_scroll(z, "units"); moved = True
        if moved:
            self._release_fit()
            # Mid-stroke `_paint_fast` only touches the cells under the
            # pointer, so the strip that just scrolled into view would come up
            # blank. Re-rendering the tile costs a viewport, not a drawing
            # (#v2.8.0), which is cheap enough to do on every scroll step.
            self._draw_main()

    def _on_pick(self, event):
        self.on_canvas_pick(*self._grid_at(event))

    def _on_leave(self, _event=None):
        self.canvas.delete("ghost")
        self._hover_cell = None
        self._refresh_cursor_label()
        self._refresh_counter()

    def _on_motion(self, event):
        """Ghosts under the cursor (the bar being placed, the stick, the
        eraser's footprint), the move cursor over the bar, and the cell /
        colour readout in the strip below."""
        self.canvas.delete("ghost")
        if self.history is None:
            return
        col, row = self._grid_at(event)
        self._hover_cell = (col, row)
        self._refresh_cursor_label()
        self._refresh_counter()
        self._draw_ghost()
        if self.looking:
            self.canvas.configure(cursor="")    # nothing to grab: it is for looking
            return
        if self.floating is not None and self._in_floating(col, row):
            self.canvas.configure(cursor="fleur")
            return
        if self._on_bar_end(col, row) is not None:
            vertical = self.symmetry_bar.orientation == symmetry.VERTICAL
            self.canvas.configure(cursor="sb_v_double_arrow" if vertical else "sb_h_double_arrow")
            return
        if self._on_bar(col, row):
            self.canvas.configure(cursor="fleur")
            return
        if self.tool == "select" and self.selection is not None and self._in_selection(col, row):
            self.canvas.configure(cursor="fleur")
            return
        edges = self._hit_edge(event)
        if edges:
            self.canvas.configure(cursor=_EDGE_CURSORS[edges])
            return
        self.canvas.configure(cursor="")

    def _draw_ghost(self):
        """What follows the pointer: the bar about to be placed, or the
        eraser's footprint.

        Drawn after every repaint and on every step of a stroke, too
        (#v2.8.0, third test pass): the eraser's outline used to be skipped
        while erasing, so it vanished the moment erasing began - or, until
        the next repaint cleared it, stayed stuck where the stroke started."""
        self.canvas.delete("ghost")
        if self.history is None or self._hover_cell is None or self.looking:
            return
        col, row = self._hover_cell
        if self._placing_bar:
            ghost = symmetry.Bar(self._sym_orientation, self._sym_length, col, row)
            self._draw_bar(ghost, tag="ghost", colour=theme.ON_DIM)
        elif self.tool == "erase" and tuple(self.eraser_size) != (1, 1):
            self._ghost_cells(self._eraser_cells(col, row), self.zoom_level)

    def _eraser_reaches(self, col, row):
        """Does the eraser, centred on (col, row), cover any of the drawing?
        A big eraser erases the border cells with the pointer beyond them."""
        if self.history is None or self.tool != "erase":
            return False
        d = self.history.current
        w, h = self.eraser_size
        c0, r0 = col - w // 2, row - h // 2
        return c0 < d.width and c0 + w > 0 and r0 < d.height and r0 + h > 0

    def _ghost_cells(self, cells, z):
        x0, y0 = float(min(c for c, _ in cells) * z), float(min(r for _, r in cells) * z)
        x1, y1 = float((max(c for c, _ in cells) + 1) * z), float((max(r for _, r in cells) + 1) * z)
        self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=theme.ON_DIM,
                                     width=1, tags="ghost")

    # ---- the strip under the canvas (#v2.6.0, items 2 and 5) --------------------
    def _pixel_totals(self):
        """(empty, painted) for the open drawing, counted once per change.

        The strip asks on every mouse move, and the answer only moves when the
        art does - `_after_change` and `select` bump `_content_version`, and a
        live edge drag changes the size, which is in the key too. Counted
        afresh each time, a 1024-wide drawing spent longer on this than on the
        move itself (#v2.8.0)."""
        d = self.history.current
        key = (id(d), d.width, d.height, self._content_version)
        if self._totals_key != key:
            painted = d.count()
            self._totals = (d.width * d.height - painted, painted)
            self._totals_key = key
        return self._totals

    def _refresh_counter(self):
        label = getattr(self, "_counter_label", None)
        if label is None:
            return
        if self.history is None:
            label.configure(text="")
            return
        d = self.history.current
        empty, painted = self._pixel_totals()
        parts = [t("total_pixels", n=empty + painted), t("empty_pixels", n=empty),
                 t("pixels", n=painted)]
        if self.selection is not None:
            c0, r0, c1, r1 = self.selection
            cells, w, h = d.region(c0, r0, c1, r1)
            n = sum(1 for line in cells for c in line if c is not None)
            parts.append(t("selection", w=w, h=h, n=n))
        elif self._hover_cell is not None:
            col, row = self._hover_cell
            if d._inside(col, row):
                parts.append(t("row_count", row=row, n=d.row_count(row)))
                parts.append(t("col_count", col=col, n=d.col_count(col)))
        label.configure(text=" \u00b7 ".join(parts))

    def _refresh_cursor_label(self):
        label = getattr(self, "_cursor_label", None)
        if label is None:
            return
        if self.history is None or self._hover_cell is None:
            label.configure(text="")
            return
        col, row = self._hover_cell
        d = self.history.current
        if not d._inside(col, row):
            label.configure(text="")
            return
        cell = d.get(col, row)
        if cell is None:
            colour = t("empty_cell")
        elif isinstance(cell, str):
            colour = _hex(d.palette.colors()[cell])
        else:
            colour = _hex(cell)
        label.configure(text=f"x {col}  y {row}   {colour}")

    def _refresh_colour_strip(self):
        strip = getattr(self, "_colour_strip", None)
        if strip is None:
            return
        if self.history is None:
            strip.set_colours([])
            return
        d = self.history.current
        if self._pixel_totals()[1] == 0:
            strip.set_colours([])  # nothing painted, nothing to count
            return
        palette = d.palette.colors()
        # Counted by cell VALUE first - `Counter.update` runs in C - and only
        # then named, one hex code per colour rather than one per cell: the
        # difference matters on every stroke of a drawing 512 wide (#v2.8.0).
        cells = Counter()
        for line in d.cells:
            cells.update(line)
        cells.pop(None, None)
        counts = {}
        for cell, n in cells.items():
            key = _hex(palette[cell] if isinstance(cell, str) else cell)[1:].upper()
            counts[key] = counts.get(key, 0) + n
        # left to right by how much of the drawing each colour covers
        strip.set_colours(sorted(counts.items(), key=lambda kv: -kv[1]))

    # ---- the ink entry (item 5) -----------------------------------------------
    def _on_ink_entry_commit(self, _event=None):
        text = self._ink_entry.get()
        if not self.set_ink_hex(text):
            self._refresh_ink_ui()  # not a colour: put the real one back
        if _event is not None and getattr(_event, "keysym", "") in ("Return", "KP_Enter"):
            self.canvas.focus_set()

    def _on_ink_entry_double(self, _event=None):
        self._ink_entry.focus_set()
        self._ink_entry.select_range(0, "end")
        self._ink_entry.icursor("end")
        return "break"

    def _add_ink_to_favourites(self):
        hexcode = _hex(self.ink_rgba())[1:]
        self._record_state(self.FAVOURITES)
        if self.settings.add_favourite(hexcode):
            self._refresh_favourites()
            self._set_status(t("added_fav"), flash=True)
        else:
            self.history.drop_last(self.FAVOURITES)   # it was already there
            self._set_status(t("already_fav"), flash=True)

    def remove_favourite(self, hexcode):
        self._record_state(self.FAVOURITES)
        if self.settings.remove_favourite(hexcode):
            self._refresh_favourites()
        else:
            self.history.drop_last(self.FAVOURITES)

    def _favourite_menu(self, hexcode, event):
        menu = dialogs.PopupMenu(self.root, tearoff=False)
        menu.add_command(label=t("fav_use", hex=hexcode),
                         command=lambda: self.set_ink(hex_to_rgba(hexcode)))
        menu.add_command(label=t("fav_remove"), command=lambda: self.remove_favourite(hexcode))
        menu.tk_popup(event.x_root, event.y_root)

    def _refresh_favourites(self):
        if hasattr(self, "_favourites"):
            self._favourites.set_colours(self.settings.favourites)

    # ---- the library list (item 7: built once, updated in place) -----------------
    def _rebuild_list(self):
        # Rebuilding resets the scroll; put it back where the artist left it,
        # or every stroke on flower #20 jumps the list to the top.
        offset = self._list_canvas.yview()[0]
        for child in self._list_frame.winfo_children():
            child.destroy()
        self._rows = {}
        for drawing in self.library.drawings:
            self._build_row(drawing)
        self.apply_filter()
        self._refresh_filter_button()
        self._list_canvas.yview_moveto(offset)

    def _refresh_list(self):
        """Kept for callers that mean 'the set of drawings changed'."""
        self._rebuild_list()

    def _build_row(self, drawing):
        selected = drawing is self._selected
        bg = ROW_BG_SELECTED if selected else ROW_BG
        row = tk.Frame(self._list_frame, bg=bg)
        row.pack(fill="x", pady=1, padx=(PAD, 2))

        thumb = tk.Label(row, bg=bg, bd=0)
        thumb.pack(side="left", padx=4, pady=3)

        # The name is packed LAST (below), so the ⋮ and the label chip keep
        # their width and a long name is what gets clipped.
        label = tk.Label(row, text=drawing.name, anchor="w", bg=bg, fg=theme.ON_SURFACE,
                         font=theme.FONT)

        # Labels as keys, read when the menu opens: the menu is built once per
        # row, and a language chosen since must show in it (sixth test pass:
        # "soldaki üç noktalı menü ve uzantıları farklı dillerde çalışmıyor").
        menu = dialogs.PopupMenu(row, tearoff=False)

        def item(key, command):
            menu.add_command(label=lambda: t(key), command=command)

        item("duplicate", lambda: self._duplicate(drawing))
        item("export_png", lambda: self._export_png(drawing))
        item("export_png_grid", lambda: self._export_png(drawing, grid=True))
        item("export_svg", lambda: self._export_svg(drawing))
        item("export_svg_grid", lambda: self._export_svg(drawing, grid=True))
        item("export_jpg", lambda: self._export_jpg(drawing))
        item("export_jpg_grid", lambda: self._export_jpg(drawing, grid=True))
        item("export_json", lambda: self._export_json(drawing))
        item("export_engine", lambda: self._export_engine_sprite(drawing))
        menu.add_separator()
        item("open_location", lambda: self._open_location(drawing))
        menu.add_separator()
        item("rename", lambda: self._rename(drawing))
        item("label", lambda: self._label_dialog(drawing))
        item("artist", lambda: self._artist_dialog(drawing))
        item("size", lambda: self._set_size(drawing))
        menu.add_separator()
        item("delete", lambda: self._delete(drawing))
        # A bigger glyph in the same footprint (#v2.8.0): the dots were
        # 7x15 px inside a 19x19 button and too small to aim at. Three
        # points up, with the padding wound back to match, is 14x21 inside
        # 20x21 - the row is 44px tall and the thumbnail sets that, so
        # nothing in the list moves.
        menu_btn = theme.button(row, "\u22ee", None, bg=bg, activebackground=theme.PANEL_HI,
                                padx=3, pady=0, font=theme.bold(theme.FONT_SIZE + 3))
        menu_btn.configure(command=lambda: menu.tk_popup(
            menu_btn.winfo_rootx(), menu_btn.winfo_rooty() + menu_btn.winfo_height(),
            flip_y=menu_btn.winfo_rooty()))
        menu_btn.pack(side="right", padx=(0, 4))
        # The artist's initial, between the label chip and ⋮ (#v2.8.0): a
        # layer of its own, in the artist's own colour - two artists who share
        # a letter still differ. Packed only while there is an artist.
        artist = theme.button(row, "", lambda: self._artist_dialog(drawing), bg=bg,
                              activebackground=theme.PANEL_HI, font=theme.FONT_SMALL_BOLD,
                              padx=3, pady=2)
        artist.pack(side="right")
        # The label chip, left of the initial (#v2.6.0): click it to change the label.
        chip = theme.button(row, "", lambda: self._label_dialog(drawing), bg=bg,
                            fg=theme.ON_DIM, activebackground=theme.PANEL_HI, font=theme.FONT_SMALL,
                            padx=4, pady=2)
        chip.pack(side="right")
        label.pack(side="left", fill="x", expand=True)

        for widget in (row, label, thumb):
            widget.bind("<Button-1>", lambda e: self.select(drawing))
            widget.bind("<MouseWheel>", self._on_list_wheel)
        self._rows[id(drawing)] = {"row": row, "thumb": thumb, "label": label, "menu": menu_btn,
                                   "popup": menu, "chip": chip, "artist": artist}
        self._refresh_row(drawing)

    def _refresh_row(self, drawing, grid=None):
        """Redraw one row's thumbnail and name — the per-stroke cost, in
        place of rebuilding the whole list. `grid` is the drawing already
        rendered, if the caller has it."""
        widgets = self._rows.get(id(drawing))
        if widgets is None:
            return
        shared = (self._rendered_image() if grid is None and self.history is not None
                  and drawing is self._selected else None)
        if shared is not None:
            # The open drawing: from the one render the previews use too.
            small = raster.reduce_image(shared, -(-max(shared.size) // THUMB_PX))
            scale = max(1, min(2, THUMB_PX // small.width, THUMB_PX // small.height))
            img = raster.image_photo(small, scale, master=self.root)
        elif grid is None and drawing.count() == 0:
            # An empty drawing's thumbnail is an empty picture of its shape.
            n = -(-max(drawing.width, drawing.height) // THUMB_PX)
            w, h = -(-drawing.width // n), -(-drawing.height // n)
            scale = max(1, min(2, THUMB_PX // w, THUMB_PX // h))
            img = raster.photo([[None] * w for _ in range(h)], scale, master=self.root)
        else:
            grid, _n = raster.shrink(grid if grid is not None else engine_io.render(drawing),
                                     THUMB_PX)
            scale = raster.fit_scale(grid, THUMB_PX, 2)
            img = raster.photo(grid, scale, master=self.root)
        self._images[("thumb", id(drawing))] = img
        widgets["thumb"].configure(image=img)
        widgets["label"].configure(text=drawing.name)
        widgets["chip"].configure(text=drawing.label or "\u2013",
                                  fg=theme.WORK if drawing.label else theme.ON_DIM)
        initial = widgets["artist"]
        if drawing.artist:
            colour = f"#{self.settings.artist_colour(drawing.artist).lower()}"
            initial.configure(text=drawing.artist[0].upper(), fg=colour, activeforeground=colour)
            if not initial.winfo_manager():
                initial.pack(side="right", before=widgets["chip"])
        elif initial.winfo_manager():
            initial.pack_forget()

    def _highlight_row(self, drawing, selected):
        widgets = self._rows.get(id(drawing))
        if widgets is None:
            return
        bg = ROW_BG_SELECTED if selected else ROW_BG
        for key in ("row", "thumb", "label", "menu", "chip", "artist"):
            widgets[key].configure(bg=bg)
        for key in ("menu", "chip", "artist"):
            widgets[key].configure(highlightbackground=bg)
        if selected:
            self._scroll_row_into_view(widgets["row"])

    def _scroll_row_into_view(self, row):
        self._list_frame.update_idletasks()
        total = self._list_frame.winfo_height()
        if total <= 0:
            return
        top, bottom = self._list_canvas.yview()
        y0 = row.winfo_y() / total
        y1 = (row.winfo_y() + row.winfo_height()) / total
        if y0 < top:
            self._list_canvas.yview_moveto(y0)
        elif y1 > bottom:
            self._list_canvas.yview_moveto(y1 - (bottom - top))

    # ---- new drawing / resize (item 13) ----------------------------------------
    def new_drawing(self, cols=NEW_SIZE, rows=NEW_SIZE):
        """A blank drawing of the given size, added and opened."""
        cols = max(1, min(HUGE_SIDE, int(cols)))
        rows = max(1, min(HUGE_SIDE, int(rows)))
        base = self._selected or (self.library.drawings[0] if self.library.drawings else None)
        if base is not None:
            palette, species, model = base.palette, base.species, base.model
        else:
            palette = Palette(d="2E2E2E", m="6E6E6E", l="B0B0B0", centre="F2C94C", rim="1A1A1A")
            species, model = "", 0
        # A new drawing takes the label ticked, if just one is, or the open
        # one's - and the artist ticked, if just one is, since a new drawing
        # is nobody's until someone says (#v2.8.0).
        labels, artists = self._ticked(self.LABEL), self._ticked(self.ARTIST)
        label = next(iter(labels)) if labels and len(labels) == 1 else (base.label if base else "")
        artist = next(iter(artists)) if artists and len(artists) == 1 else ""
        drawing = Drawing.blank(cols, rows, palette, species=species, model=model, label=label,
                                artist=artist)
        self.library.add(drawing)
        self._add_row(drawing)
        self.select(drawing)
        return drawing

    def _add_row(self, drawing):
        """A row for a drawing that just joined the library. If the ticks
        would hide it, its label is ticked too — a drawing the artist just
        made must not vanish, and the rows they ticked stay ticked (up to the
        second test pass the whole filter was dropped)."""
        self._build_row(drawing)
        if not (self.label_shown(drawing.label) or self.artist_shown(drawing.artist)):
            self.set_filter(self._filter | {(self.LABEL, drawing.label)})
        else:
            self.apply_filter()
            self._refresh_filter_button()

    def _new_drawing(self):
        """Older name, kept: a default-size blank drawing, no dialog."""
        return self.new_drawing()

    def _new_drawing_dialog(self):
        SizeDialog(self.root, t("new_title"), (NEW_SIZE, NEW_SIZE), size_presets(),
                   self.new_drawing, verb=t("create"))

    # ---- import (#v2.5.0) -------------------------------------------------------
    def import_png(self, path):
        """One outside PNG -> a drawing in the library, saved. Returns
        (drawing, notes); raises engine_io.ImportRefused."""
        drawing, notes = engine_io.import_png(path)
        drawing.species = drawing.species or ""
        self.library.add(drawing)
        self._add_row(drawing)
        return drawing, notes

    def _import_dialog(self):
        files = filedialog.askopenfilenames(
            parent=self.root, title=t("import_title"),
            filetypes=[(t("type_png"), "*.png"), (t("type_all"), "*.*")])
        if not files:
            return
        report, last = [], None
        for path in files:
            try:
                drawing, notes = self.import_png(path)
            except (engine_io.ImportRefused, OSError) as exc:
                report.append(f"\u2717 {Path(path).name}: {exc}")
                continue
            last = drawing
            line = f"\u2713 {drawing.name} ({drawing.width}\u00d7{drawing.height})"
            if notes:
                line += "\n    " + "\n    ".join(notes)
            report.append(line)
        if last is not None:
            self.select(last)
        dialogs.showinfo("Pixel Pomo Art Kit", t("imported") + "\n\n" + "\n".join(report),
                         parent=self.root)

    def _duplicate(self, drawing):
        clone = self.library.duplicate(drawing)
        self._add_row(clone)
        self.select(clone)

    def _rename(self, drawing):
        name = dialogs.askstring(
            "Pixel Pomo Art Kit", t("rename_prompt"), initialvalue=drawing.name, parent=self.root)
        if name:
            drawing.name = name
            # `drawing` always came from `library.drawings`, so it is always the
            # object the library registered - safe to save regardless of
            # whether it is the one currently open for editing.
            self._save(drawing)
            if drawing is self._selected:
                self.root.title(f"Pixel Pomo Art Kit — {name}")
            self._refresh_row(drawing)

    def _set_size(self, drawing):
        if drawing is None:
            return
        if drawing is not self._selected:
            self.select(drawing)
        d = self.history.current
        SizeDialog(self.root, t("resize_title", name=drawing.name), (d.width, d.height),
                   size_presets(), self.resize, verb=t("resize"))

    def resize(self, cols, rows):
        """Change the open drawing's size as ONE undoable stroke."""
        if self.history is None:
            return
        self.commit_floating()  # a block in the air owns the open stroke
        d = self.history.current
        cols = max(1, min(HUGE_SIDE, int(cols)))
        rows = max(1, min(HUGE_SIDE, int(rows)))
        if (cols, rows) == (d.width, d.height):
            return
        # A resize is a stroke: one undo puts the cropped cells back.
        self.history.begin_stroke()
        d.resize(cols, rows)
        self.history.end_stroke()
        self._after_change()
        self.zoom_to_fit()

    def _delete(self, drawing):
        if not dialogs.askyesno(
                "Pixel Pomo Art Kit", t("delete_confirm", name=drawing.name),
                icon="warning", parent=self.root):
            return
        was_selected = drawing is self._selected
        self.library.remove(drawing)
        self._histories.pop(id(drawing), None)
        self._lock_frames.pop(id(drawing), None)
        widgets = self._rows.pop(id(drawing), None)
        if widgets is not None:
            widgets["row"].destroy()
            self._list_frame.update_idletasks()
            self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        self._images.pop(("thumb", id(drawing)), None)
        if was_selected:
            self.history = None
            self._selected = None
            if self.library.drawings:
                self.select(self.library.drawings[0])
                return
            self.root.title("Pixel Pomo Art Kit")
        self._refresh_size_label()
        self._redraw()

    def _open_location(self, drawing):
        """Show this drawing's own file, selected, in the file manager
        (#v2.8.0). The library's data folder moved out from beside the .exe in
        #v2.5.0 and nobody can be expected to know where %LOCALAPPDATA% is;
        HELP's OPEN FOLDER opens the folder, this opens it with the right file
        already highlighted."""
        path = self.library.path_for(drawing)
        if path is None:
            # Only reachable for a drawing that was never added to a library.
            self._set_status(t("save_failed"), flash=True, error=True)
            return
        if not paths.reveal(path):
            dialogs.showerror("Pixel Pomo Art Kit", str(Path(path).parent), parent=self.root)

    # ---- export ------------------------------------------------------
    def _ask_export_background(self, drawing, grid=False, allow_transparent=True,
                               title=None):
        """The background question, asked BEFORE the save dialog (#v2.8.0).

        Before, so that backing out of it costs nothing: asking after the
        artist had already named a file would mean either writing a file they
        cancelled or throwing away the name they typed. Returns `CANCELLED`,
        which the caller must treat as "do not export", or None / a hex
        colour - and remembers the answer for next time.

        `grid` is the caller's own with-grid flag, passed through so the
        preview shows the lines when the export will draw them.
        `allow_transparent` is False for JPEG, which has no alpha to offer."""
        dialog = BackgroundDialog(
            self.root, self.settings.export_background, drawing=drawing,
            grid=self.grid_line_colour() if grid else None,
            allow_transparent=allow_transparent, title=title,
            last_colour=self.settings.export_colour,
            signature=self.settings.export_signature,
            metadata=self.settings.export_metadata,
            log=self.settings.export_log)
        self.root.wait_window(dialog)
        if dialog.result is CANCELLED:
            return CANCELLED
        self.settings.export_background = dialog.result
        # The artist's mark is asked in the same dialog and kept the same way.
        self.settings.export_signature = dialog.signature
        self.settings.export_metadata = dialog.metadata
        self.settings.export_log = dialog.log
        # Whatever was mixed is kept even if it was not the answer in the end.
        self.settings.export_colour = dialog._custom
        return dialog.result

    def _export_png(self, drawing, grid=False):
        title = t("export_png_grid") if grid else t("export_png")
        background = self._ask_export_background(drawing, grid, title=title)
        if background is CANCELLED:
            return
        suffix = " (grid)" if grid else ""
        path = filedialog.asksaveasfilename(
            parent=self.root, title=title,
            defaultextension=".png", initialfile=f"{drawing.name}{suffix}.png",
            filetypes=[(t("type_png"), "*.png")])
        if not path:
            return
        mark = self._export_mark(drawing)
        try:
            engine_io.export_png(drawing, path, grid=self.grid_line_colour() if grid else None,
                                 background=background, mark=mark)
        except (engine_io.ExportRefused, OSError) as exc:
            dialogs.showerror("Pixel Pomo Art Kit", str(exc), parent=self.root)
            return
        self._log_export(path, "png", drawing, mark)
        self._set_status(t("exported", name=Path(path).name), flash=True)

    def _export_svg(self, drawing, grid=False):
        """Vector export: one rect per cell, sharp at any zoom (#v2.7.0)."""
        title = t("export_svg_grid") if grid else t("export_svg")
        background = self._ask_export_background(drawing, grid, title=title)
        if background is CANCELLED:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title=title,
            defaultextension=".svg", initialfile=f"{drawing.name}.svg",
            filetypes=[(t("type_svg"), "*.svg")])
        if not path:
            return
        mark = self._export_mark(drawing)
        try:
            engine_io.export_svg(drawing, path, grid=self.grid_line_colour() if grid else None,
                                 background=background, mark=mark)
        except (engine_io.ExportRefused, OSError) as exc:
            dialogs.showerror("Pixel Pomo Art Kit", str(exc), parent=self.root)
            return
        self._log_export(path, "svg", drawing, mark)
        self._set_status(t("exported", name=Path(path).name), flash=True)

    def _export_json(self, drawing):
        """The kit's own drawing file — this is what the library stores, and
        what survives an update. Engine sprites are PNG; the game does not
        read these JSON files (#v2.7.0, item 14)."""
        path = filedialog.asksaveasfilename(
            parent=self.root, title=t("export_json"),
            defaultextension=".json", initialfile=f"{drawing.name}.json",
            filetypes=[(t("type_json"), "*.json")])
        if not path:
            return
        try:
            store.save(drawing, Path(path))
        except OSError as exc:
            dialogs.showerror("Pixel Pomo Art Kit", str(exc), parent=self.root)
            return
        self._log_export(path, "json", drawing)
        self._set_status(t("exported", name=Path(path).name), flash=True)

    def _export_jpg(self, drawing, grid=False):
        """JPEG, with or without the cell lines (#v2.8.0).

        The background question is asked here too, but without the
        transparent answer: JPEG has no alpha channel, so "transparent" would
        silently become white anyway. Saying so in the dialog beats letting
        the artist pick it and find a white sheet in the file."""
        title = t("export_jpg_grid") if grid else t("export_jpg")
        background = self._ask_export_background(drawing, grid, allow_transparent=False,
                                                 title=title)
        if background is CANCELLED:
            return
        suffix = " (grid)" if grid else ""
        path = filedialog.asksaveasfilename(
            parent=self.root, title=title, defaultextension=".jpg",
            initialfile=f"{drawing.name}{suffix}.jpg", filetypes=[(t("type_jpg"), "*.jpg")])
        if not path:
            return
        mark = self._export_mark(drawing)
        try:
            engine_io.export_jpg(drawing, path, background=background,
                                 grid=self.grid_line_colour() if grid else None, mark=mark)
        except (engine_io.ExportRefused, OSError) as exc:
            dialogs.showerror("Pixel Pomo Art Kit", str(exc), parent=self.root)
            return
        self._log_export(path, "jpg", drawing, mark)
        self._set_status(t("exported", name=Path(path).name), flash=True)

    def _export_engine_sprite(self, drawing):
        """The x16 engine-scale sprite, any size, to a file the artist names
        (#v2.6.0, items 4 and 10). One ordinary save dialog: the name is
        editable there, and "replace?" is the system's own question — no
        second confirmation, no 16-wide refusal. Sizing and naming a sprite
        for the garden is the developer's job afterwards, as with palettes."""
        folder = engine_sprite_dir()
        folder.mkdir(parents=True, exist_ok=True)  # so the picker opens somewhere real
        path = filedialog.asksaveasfilename(
            parent=self.root, title=t("export_engine"), defaultextension=".png",
            initialdir=str(folder), initialfile=engine_io.suggested_sprite_name(drawing),
            filetypes=[(t("type_sprite"), "*.png")])
        if not path:
            return
        try:
            written = engine_io.export_sprite(drawing, path)
        except (engine_io.ExportRefused, OSError) as exc:
            dialogs.showerror("Pixel Pomo Art Kit", str(exc), parent=self.root)
            return
        # Recorded, but not marked: the sprite is the game's build input.
        self._log_export(written, "engine", drawing)
        self._set_status(t("exported", name=Path(written).name), flash=True)

    def _export_mark(self, drawing):
        """What an image export says about who made it (#v2.8.0): the choices
        from the export dialog, and the digest of the drawing's own file, so a
        picture found later can be matched to the drawing it came from."""
        saved = self.library.path_for(drawing)
        try:
            drawing_id = provenance.digest(Path(saved).read_bytes()) if saved else ""
        except OSError:
            drawing_id = ""
        return provenance.Mark(title=drawing.name, artist=drawing.artist,
                               signature=self.settings.export_signature,
                               metadata=self.settings.export_metadata, drawing_id=drawing_id)

    def export_log_path(self):
        """`export-log.jsonl`, beside the library and the settings."""
        return self.library.root.parent / provenance.LOG_NAME

    def _log_export(self, path, kind, drawing, mark=None):
        """Write the export down (#v2.8.0) - if the artist keeps the record,
        which is theirs to turn off in the export dialog. A record that cannot
        be written is not worth an error box: the file asked for is on disk."""
        if not self.settings.export_log:
            return
        try:
            provenance.record(self.export_log_path(), path, kind, drawing, mark)
        except (OSError, ValueError):
            pass

    # ---- drawing --------------------------------------------------------
    def _redraw(self):
        self._draw_main()
        self._draw_previews()

    def _draw_main(self):
        """Repaint the main view.

        Only the cells INSIDE the viewport are rendered (#v2.8.0). The art is
        one PhotoImage that Tk zooms, and `zoom()` multiplies both of its
        sides, so the bitmap grew with the SQUARE of the zoom: at 256 px a
        cell, a 16x19 flower asked Tk for a 4096x4864 image - twenty
        megapixels, a tenth of a second, on every wheel notch, to show the
        nine hundred by seven hundred the artist can actually see. Clipping to
        the viewport makes the cost of a repaint depend on the size of the
        PANE and nothing else, which is what makes zooming smooth however far
        in it goes."""
        self.canvas.delete("all")
        if self.history is None:
            return
        drawing = self.history.current
        z = self.zoom_level
        w, h = drawing.width, drawing.height
        self._apply_scrollregion()
        # No checker items: the tile below carries the checkerboard in its own
        # empty pixels, and covers every visible cell of the drawing.
        view = self._visible_cells()
        self._tile_box = None
        if view is not None:
            c0, r0, c1, r1 = view
            if z < 1:
                # 1/n: blocks of n x n cells, each one screen pixel, laid on
                # the pixel grid so they do not straddle two pixels.
                n = round(1 / z)
                c0, r0 = c0 - c0 % n, r0 - r0 % n
                small = self._tile_image(drawing, (c0, r0, c1, r1), n)
                if small is not None:
                    img = raster.image_photo(small, master=self.root)
                else:
                    img = raster.photo(self._tile(drawing, (c0, r0, c1, r1), n), 1,
                                       master=self.root)
            else:
                img = raster.photo(self._tile(drawing, view), z, master=self.root)
            self._images["main"] = img
            # Where that picture starts, in cells, and how many cells a pixel
            # of it is: a stroke writes its cells straight into it.
            self._tile_box = (c0, r0, round(1 / z) if z < 1 else 1)
            self.canvas.create_image(float(c0 * z), float(r0 * z), image=img, anchor="nw",
                                     tags="art")
            if z >= 8 and self.show_grid and not self.looking:
                self._draw_grid_lines(w, h, z, view)
        bar = None if self.looking else self._active_bar()
        if bar is not None:
            self._draw_bar(bar, tag="symmetry", colour=theme.ACCENT)
        self._draw_overlays()
        self._draw_ghost()
        self._refresh_camera_ui()

    def _tile(self, drawing, view, n=1):
        """The cells inside `view` as the garden draws them, laid on the
        checkerboard: an image with not one see-through pixel in it. With
        `n` above 1 (zoomed out past 1 px a cell) every n x n block becomes
        one pixel, the average of its cells (`raster.reduce`) laid on the
        checker tone of the block.

        Only those cells are RENDERED (#v2.8.0, second test pass), not just
        shown: a rim depends on the cells beside it and on nothing further,
        so the view plus a one-cell margin, rendered and trimmed, is exactly
        the whole drawing's render cut down to the view - at the price of
        what is on screen, not of the drawing, which matters now that a
        drawing may be hundreds of cells wide.

        The empty cells carry their checker tone instead of being holes onto
        a checkerboard behind: Tk builds a transparency mask for any photo with
        see-through pixels, and for scattered pixel art that mask took more
        than a second on a 256-cell square. The same square opaque is two
        milliseconds. The tone is the one `_checker_tone` gives a cell, so a
        stroke's fast-path rectangles match what the next repaint shows."""
        c0, r0, c1, r1 = view
        d = drawing
        if n > 1:
            small = self._tile_image(drawing, view, n)
            if small is not None:
                return raster.image_to_grid(small)
        m0, n0 = max(0, c0 - 1), max(0, r0 - 1)
        m1, n1 = min(d.width - 1, c1 + 1), min(d.height - 1, r1 + 1)
        part = Drawing(name=d.name, species=d.species, model=d.model, palette=d.palette,
                       cells=[row[m0:m1 + 1] for row in d.cells[n0:n1 + 1]])
        rendered = engine_io.render(part)
        tones = self._under_tones()
        cols, dc, dr = c1 - c0 + 1, c0 - m0, r0 - n0
        art = [line[dc:dc + cols] for line in rendered[dr:dr + r1 - r0 + 1]]
        if n > 1:
            art = raster.reduce(art, n)
        k = self._checker_cells(Fraction(1, n) if n > 1 else None)
        across = [(c0 + i * n) // k for i in range(len(art[0]))]
        tile = []
        for j, line in enumerate(art):
            down = (r0 + j * n) // k
            under = [tones[(a + down) % 2] for a in across]
            if n == 1:
                tile.append([px if px[3] else tone for px, tone in zip(line, under)])
            else:  # an average: partly covered pixels exist, and mix
                tile.append([raster.over(px, tone) for px, tone in zip(line, under)])
        return tile

    def _tile_image(self, drawing, view, n):
        """`_tile` below 1 px a cell, done in Pillow: the view cut from the
        shared render, averaged n x n, laid on the checker. None when there is
        no shared render to cut (no Pillow, or not the open drawing)."""
        if self.history is None or drawing is not self.history.current:
            return None
        whole = self._rendered_image()
        if whole is None:
            return None
        from PIL import Image, ImageDraw
        c0, r0, c1, r1 = view
        art = raster.reduce_image(whole.crop((c0, r0, c1 + 1, r1 + 1)), n)
        # The checker under it: a tone per n x n block, from the block's first
        # cell as `_checker_tone` has it - a few dozen rectangles, not pixels.
        sw, sh = art.size
        tones = self._under_tones()
        k = self._checker_cells(Fraction(1, n))

        def runs(start, count):
            out, begin = [], 0
            for i in range(1, count + 1):
                if i == count or (start + i * n) // k != (start + begin * n) // k:
                    out.append((begin, i, (start + begin * n) // k))
                    begin = i
            return out

        under = Image.new("RGBA", (sw, sh), tones[0])
        pen = ImageDraw.Draw(under)
        for x0, x1, a in runs(c0, sw):
            for y0, y1, b in runs(r0, sh):
                if (a + b) % 2:
                    pen.rectangle((x0, y0, x1 - 1, y1 - 1), fill=tones[1])
        return Image.alpha_composite(under, art)

    def _redraw_viewport(self):
        """A pan, a resize, a scrollbar: the art has not changed, but a
        different part of it is on screen."""
        if self.history is None or self._painting:
            return
        if not self._fitted and self._pane_known():
            # The fit that ran before Tk had laid the pane out was against
            # NOMINAL_VIEW. This is the first time the real size is known.
            self.zoom_to_fit()
            return
        if (self._fit_held and self.camera_mode != CAM_LOCK and self._pane_known()
                and self._viewport() != self._fit_pane):
            # The pane changed size under a view that was the fit, and nobody
            # has zoomed or panned since ("fit halen düzgün değil", #v2.8.0):
            # it is fitted again, as a press of FIT would. Up to the fifth
            # test pass FIT was a one-off - fold the library away and the art
            # sat off-centre in the wider pane; unfold it and the fit made for
            # the wide pane ran off the edge of the narrow one.
            self.zoom_to_fit()
            return
        if self._camera_frozen() and not self._frame_shows_art(self.zoom_level, self._locked_at):
            # The window shrank until the frozen view held none of the
            # drawing: re-frame it, rather than lock the artist out of it.
            self.zoom_to_fit()
            return
        self._draw_main()

    def _draw_overlays(self):
        """The selection rectangle and the floating block (#v2.6.0) — redrawn
        on their own while they move, so the drawing underneath is not
        re-rendered for every pixel of a drag."""
        self.canvas.delete("selection")
        self.canvas.delete("floating")
        if self.history is None:
            return
        z = self.zoom_level
        if self.floating is not None:
            f = self.floating
            palette = self.history.current.palette.colors()
            grid = [[(palette[c] if isinstance(c, str) else c) if c is not None else None
                     for c in line] for line in f["cells"]]
            x0, y0 = f["col"] * z, f["row"] * z
            # Clipped to the pane, for the same reason the art is: a 48-cell
            # block at 1024 px a cell is a 49152-pixel-square image nobody can
            # see more than a corner of (#v2.8.0).
            tile = self._clip_to_view(grid, f["col"], f["row"])
            if tile is not None:
                cells, tc, tr = tile
                if z < 1:
                    img = raster.photo(raster.reduce(cells, round(1 / z)), 1, master=self.root)
                else:
                    img = raster.photo(cells, z, master=self.root)
                self._images["floating"] = img
                self.canvas.create_image(float(tc * z), float(tr * z), image=img, anchor="nw",
                                         tags="floating")
            self.canvas.create_rectangle(float(x0), float(y0), float(x0 + f["w"] * z),
                                         float(y0 + f["h"] * z), outline=theme.ACCENT, width=2,
                                         dash=(6, 3), tags="floating")
        if self.selection is not None:
            c0, r0, c1, r1 = self.selection
            self.canvas.create_rectangle(float(c0 * z + 1), float(r0 * z + 1),
                                         float((c1 + 1) * z - 1), float((r1 + 1) * z - 1),
                                         outline=theme.WORK, width=2, dash=(6, 3), tags="selection")

    def _clip_to_view(self, grid, col, row):
        """`grid`, a block of cells whose top-left sits at cell (col, row),
        cut down to the part inside the pane.

        Returns (cells, col, row) for the piece that is actually visible - its
        own new origin in cell coordinates - or None if none of it is."""
        h = len(grid)
        w = len(grid[0]) if h else 0
        if not w or not h:
            return None
        z = self.zoom_level
        cw, ch = self._viewport()
        vx, vy = (int(v) for v in self._view_origin())  # int // Fraction is exact
        c0 = max(0, int(vx // z) - col)
        r0 = max(0, int(vy // z) - row)
        c1 = min(w - 1, int((vx + cw) // z) - col)
        r1 = min(h - 1, int((vy + ch) // z) - row)
        if c1 < c0 or r1 < r0:
            return None
        return ([line[c0:c1 + 1] for line in grid[r0:r1 + 1]], col + c0, row + r0)

    def _checker_cells(self, zoom=None):
        """How many cells a side one square of the checkerboard is.

        Two: the 2 x 2 squares the artists know from every version before
        (#v2.8.0, sixth test pass: "arkadaki gridlerin 2x2 2x2'den farklı bir
        şekle geçmiş"). The board used to be ten squares a side of whatever
        size the drawing was; since the fourth test pass the art tile carries
        it cut to whole cells, and ten into sixteen cells comes out 2, 2, 1,
        2, 1... wide - and ten into a 160 x 60 banner, as 16 x 6 slabs. Now
        every square is the same whole number of cells, on every drawing.

        Never under CHECKER_MIN_PX on screen, though: zoomed out, 2 x 2 cells
        would be a grey shimmer, so the square doubles until it is visible -
        and below 1 px a cell it is exactly that many pixels of blocks."""
        z = self.zoom_level if zoom is None else zoom
        if z < 1:
            return round(1 / z) * CHECKER_MIN_PX
        k = CHECKER_CELLS
        while k * z < CHECKER_MIN_PX:
            k *= 2
        return k

    def _checker_tone(self, col, row):
        """The checker tone (hex) under cell (col, row) at the current zoom."""
        k = self._checker_cells()
        return self.grid_colours()[(col // k + row // k) % 2]

    def _paint_fast(self):
        """Mid-stroke: put the cells this event changed straight into the
        view's picture, instead of re-rendering the drawing. The full render
        happens once, at release. (A letter ink shows its palette colour here
        without the engine's rim — that appears on release.)

        Into the picture, not onto the canvas (#v2.8.0, sixth test pass:
        "eraser çalışırken ... çok fps düşüyor"): every cell used to be a
        rectangle item of its own, and a 16 x 16 eraser left more than 38,000
        of them on the canvas in one stroke across a 160-cell drawing - which
        Tk then redrew, all of them, on every move. `PhotoImage.put` fills a
        rectangle of the picture in C and adds nothing. Below 1 px a cell a
        cell is part of a pixel, and that pixel takes the new colour until the
        release averages it properly."""
        cells, self._stroke_cells = set(self._stroke_cells), []
        img, box = self._images.get("main"), self._tile_box
        if not cells or img is None or box is None:
            return
        z = self.zoom_level
        d = self.history.current
        fill = None if self.tool == "erase" else _hex(self.ink_rgba())
        c0, r0, n = box
        k = self._checker_cells()
        tones = self.grid_colours()
        size = max(1, int(z))                   # pixels a cell - or 1 for a block
        width, height = img.width(), img.height()
        done = set()
        for c, r in cells:
            if not d._inside(c, r):
                continue
            x, y = ((c - c0) * size, (r - r0) * size) if n == 1 else ((c - c0) // n, (r - r0) // n)
            if not (0 <= x < width and 0 <= y < height) or (x, y) in done:
                continue
            done.add((x, y))
            colour = fill or tones[(c // k + r // k) % 2]
            img.put(colour, to=(x, y, x + size, y + size))

    def _draw_previews(self, grid=None):
        """The 1x and squint pictures. `grid` is the drawing already rendered,
        when the caller has it - `_after_change` renders once for this and
        the library thumbnail both.

        A drawing bigger than a preview's box is shown every n-th cell
        (#v2.8.0, once the 64-cell cap went), and the 1x caption then says
        1/2x, 1/3x...: a half-size picture called "1x" would be a lie about
        the one thing that preview is for."""
        self.preview_1x.delete("all")
        self.preview_squint.delete("all")
        if self.history is None:
            self.preview_1x.configure(width=1, height=1)
            self.preview_squint.configure(width=1, height=1)
            return
        # Both sit on the pane's own colour, so it is baked in rather than
        # shown through: see `raster.on_colour`.
        under = hex_to_rgba(theme.BG)
        img = self._rendered_image() if grid is None else None
        if img is not None:
            self._draw_previews_from(img, under)
            return
        if grid is None:
            grid = engine_io.render(self.history.current)
        small, n = raster.shrink(grid, ONE_X_BOX)
        self._one_x_label.configure(text="1x" if n == 1 else f"1/{n}x")
        one = raster.photo(raster.on_colour(small, under), 1, master=self.root)
        squint_grid, _n = raster.shrink(grid, INNER_W - 72)
        squint_scale = raster.fit_scale(squint_grid, INNER_W - 72, PREVIEW_ZOOM)
        squint = raster.photo(raster.on_colour(squint_grid, under), squint_scale, master=self.root)
        self._images["preview_1x"], self._images["preview_squint"] = one, squint
        self.preview_1x.configure(width=len(small[0]), height=len(small))
        self.preview_1x.create_image(0, 0, image=one, anchor="nw")
        self.preview_squint.configure(width=len(squint_grid[0]) * squint_scale,
                                      height=len(squint_grid) * squint_scale)
        self.preview_squint.create_image(0, 0, image=squint, anchor="nw")

    def _draw_previews_from(self, img, under):
        """`_draw_previews` done in Pillow, from the one shared render."""
        w, h = img.size
        n = -(-max(w, h) // ONE_X_BOX)
        self._one_x_label.configure(text="1x" if n <= 1 else f"1/{n}x")
        small = raster.on_image(raster.reduce_image(img, n), under)
        box = INNER_W - 72
        squint_img = raster.on_image(raster.reduce_image(img, -(-max(w, h) // box)), under)
        sw, sh = squint_img.size
        squint_scale = max(1, min(PREVIEW_ZOOM, box // sw, box // sh))
        one = raster.image_photo(small, master=self.root)
        squint = raster.image_photo(squint_img, squint_scale, master=self.root)
        self._images["preview_1x"], self._images["preview_squint"] = one, squint
        self.preview_1x.configure(width=small.width, height=small.height)
        self.preview_1x.create_image(0, 0, image=one, anchor="nw")
        self.preview_squint.configure(width=sw * squint_scale, height=sh * squint_scale)
        self.preview_squint.create_image(0, 0, image=squint, anchor="nw")

    def _draw_grid_lines(self, width, height, z, view=None):
        # The last line is pulled one pixel in, or it falls on the far side
        # of the scroll region and is never seen (#v2.6.0).
        #
        # Only the lines around the visible cells are drawn (#v2.8.0) - a
        # 512-wide grid is a thousand canvas items otherwise, rebuilt on every
        # pan, and all but a handful of them off-screen.
        colour = self.grid_line_colour()
        wpx, hpx = width * z, height * z
        c0, r0, c1, r1 = view if view is not None else (0, 0, width - 1, height - 1)
        y_from, y_to = r0 * z, min((r1 + 1) * z, hpx - 1)
        x_from, x_to = c0 * z, min((c1 + 1) * z, wpx - 1)
        for c in range(c0, c1 + 2):
            x = min(c * z, wpx - 1)
            self.canvas.create_line(x, y_from, x, y_to, fill=colour, tags="grid")
        for r in range(r0, r1 + 2):
            y = min(r * z, hpx - 1)
            self.canvas.create_line(x_from, y, x_to, y, fill=colour, tags="grid")

    def _draw_bar(self, bar, tag, colour):
        """A bright line sitting on a grid edge, between cells (#v2.7.0)."""
        z = self.zoom_level
        first, last = bar.span()
        if bar.orientation == symmetry.VERTICAL:
            x = float(bar.col * z)
            y0, y1 = float(first * z), float((last + 1) * z)
            self.canvas.create_line(x, y0, x, y1, fill=colour, width=2, tags=tag)
        else:
            y = float(bar.row * z)
            x0, x1 = float(first * z), float((last + 1) * z)
            self.canvas.create_line(x0, y, x1, y, fill=colour, width=2, tags=tag)

    # ---- help (item 15) -------------------------------------------------------
    def toggle_help(self):
        if self._help is not None:
            self._help.destroy()
            self._help = None
            return
        self._help = HelpOverlay(self.root, self.toggle_help, self.library.root.parent,
                                 test_build=is_test_build(self.root))

    # ---- keeping the tools pane in sync ---------------------------------
    def _refresh_tool_buttons(self):
        for name, btn in self._tool_buttons.items():
            theme.set_pressed(btn, name == self.tool)

    def _refresh_ink_ui(self):
        entry = getattr(self, "_ink_entry", None)
        if entry is None:
            return  # tools pane not built yet
        rgba = self.ink_rgba()
        hexcode = _hex(rgba)
        entry.delete(0, "end")
        entry.insert(0, hexcode)
        entry.configure(bg=hexcode, fg=theme.readable_on(hexcode),
                        insertbackground=theme.readable_on(hexcode))

    def _refresh_size_label(self):
        label = getattr(self, "_size_label", None)
        if label is None:
            return
        if self.history is None:
            label.configure(text="")
            return
        d = self.history.current
        label.configure(text=f"{d.width} \u00d7 {d.height}")

    def _post_language_menu(self):
        menu = dialogs.PopupMenu(self.root, tearoff=False)
        current = i18n.language()
        for code in i18n.LANGS:
            label = i18n.NAMES[code]
            if code == current:
                label = f"\u2713  {label}"
            menu.add_command(label=label, command=lambda c=code: self.set_language(c))
        btn = self._lang_button
        menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height(),
                      flip_y=btn.winfo_rooty())

    def set_language(self, code):
        code = i18n.set_language(code)
        self.settings.language = code
        self._apply_language()

    def _chrome_pairs(self):
        """Every chrome button whose text is a translated string, with its key.

        One list, used twice: `_pin_chrome` freezes these boxes and
        `_apply_language` re-texts them. Two lists would drift, and a button
        that was re-texted but never pinned is exactly the one that jumps."""
        pairs = [
            (getattr(self, "_save_button", None), "save"),
            (self._tool_buttons.get("draw") if hasattr(self, "_tool_buttons") else None, "draw"),
            (self._tool_buttons.get("erase") if hasattr(self, "_tool_buttons") else None, "erase"),
            (self._tool_buttons.get("fill") if hasattr(self, "_tool_buttons") else None, "fill"),
            (self._tool_buttons.get("select") if hasattr(self, "_tool_buttons") else None, "select"),
            (getattr(self, "_undo_button", None), "undo"),
            (getattr(self, "_redo_button", None), "redo"),
            (getattr(self, "_update_button", None), "update"),
            (getattr(self, "_help_button", None), "help"),
            (getattr(self, "_lang_button", None), "language"),
            (getattr(self, "_new_button", None), "new_drawing"),
            (getattr(self, "_import_button", None), "import_png"),
            (self._sym_mode_buttons.get(symmetry.OFF) if hasattr(self, "_sym_mode_buttons") else None, "off"),
            (self._sym_mode_buttons.get(symmetry.MIRROR) if hasattr(self, "_sym_mode_buttons") else None, "mirror"),
            (self._sym_mode_buttons.get(symmetry.STICK) if hasattr(self, "_sym_mode_buttons") else None, "stick"),
            (getattr(self, "_sym_place_button", None), "place_bar"),
            (self._grid_buttons.get(True) if hasattr(self, "_grid_buttons") else None, "with_grid"),
            (self._grid_buttons.get(False) if hasattr(self, "_grid_buttons") else None, "without_grid"),
            (getattr(self, "_cam_fit_button", None), "cam_fit"),
            (self._cam_mode_buttons.get(CAM_FREE) if hasattr(self, "_cam_mode_buttons") else None, "cam_free"),
            (self._cam_mode_buttons.get(CAM_LOCK) if hasattr(self, "_cam_mode_buttons") else None, "cam_lock"),
            (getattr(self, "_grid_default_button", None), "default"),
            (getattr(self, "_grid_presets", {}).get("grid_white"), "grid_white"),
            (getattr(self, "_grid_presets", {}).get("grid_black"), "grid_black"),
        ]
        return [(btn, key) for btn, key in pairs if btn is not None]

    def _pin_chrome(self):
        """Freeze every chrome button's box, measured in ENGLISH (#v2.8.0).

        Measured in English rather than in whatever language the artist last
        used, so the boxes are the same pixels for everyone: a kit started in
        German would otherwise keep German-sized buttons for the rest of its
        life, and switching to English would leave the chrome roomy. The
        English pass is never drawn — the layout is settled with
        `update_idletasks`, not with an event loop — and `_apply_language`
        puts the real text straight back."""
        pairs = self._chrome_pairs()
        for btn, key in pairs:
            tk.Label.configure(btn, text=i18n.STRINGS[i18n.EN].get(key, t(key)),
                               font=theme.FONT_BOLD)
        self.root.update_idletasks()
        for btn, _key in pairs:
            btn.pin_box()
        self._apply_language()

    def _apply_language(self):
        """Retext chrome without rebuilding. The boxes were pinned at build
        time, so a longer translation shrinks its own point size inside one
        and nothing in the chrome moves (#v2.8.0)."""
        for btn, key in self._chrome_pairs():
            btn.configure(text=t(key), font=i18n.font_for(key))
        for label, key in (
                (getattr(self, "_eraser_label", None), "eraser"),
                (getattr(self, "_eraser_cells_label", None), "cells"),
                (getattr(self, "_eraser_wh_label", None), "wxh"),
                (getattr(self, "_sym_length_label", None), "length"),
                (getattr(self, "_grid_title", None), "grid"),
                (getattr(self, "_current_label", None), "current"),
                # Every heading in the tools pane (sixth test pass: "symmetry,
                # squint, colour, ready colours, favourite colours, ink ...
                # farklı dillerde çalışmıyor") - built in the language the kit
                # started in and never told when it changed.
                (getattr(self, "_squint_label", None), "squint"),
                (getattr(self, "_ink_title", None), "ink"),
                (getattr(self, "_fav_title", None), "favourites"),
                (getattr(self, "_ready_title", None), "ready"),
                (getattr(self, "_colour_title", None), "colour"),
                (getattr(self, "_sym_title", None), "symmetry"),
        ):
            if label is not None:
                label.configure(text=t(key))
        for label, key in getattr(self, "_grid_captions", {}).values():
            label.configure(text=t(key))
        self._refresh_filter_button()
        self._refresh_camera_ui()
        self._refresh_symmetry_ui()
        self._refresh_tool_buttons()
        self._refresh_grid_ui()
        self._refresh_counter()
        if hasattr(self, "_update_button"):
            self._show_update_available()
        self._refresh_look_ui()
        if self._help is not None:
            self.toggle_help()
            self.toggle_help()

    # ---- F12 (#v2.8.0, sixth test pass) ---------------------------------------
    def take_snapshot(self, _event=None):
        """F12: the window as it is, and the numbers behind it, into the data
        folder's `snapshots/` - so a report can be read rather than guessed at.
        See `snapshot`."""
        self.root.update_idletasks()   # the picture is of what is painted
        folder = self.library.root.parent / snapshot.FOLDER
        try:
            base, error = snapshot.save(self.root, folder, self._snapshot_state())
        except OSError:
            self._set_status(t("snapshot_failed"), error=True)
            return "break"
        if error:
            self._set_status(t("snapshot_failed"), error=True)
        else:
            self._set_status(t("snapshot_saved", name=base.name), flash=True)
        return "break"

    def _snapshot_state(self):
        """Everything about the view a screenshot cannot say by itself."""
        root = self.root
        d = self.history.current if self.history is not None else None

        def chosen(f):
            return "ALL" if f is None else sorted(f)

        try:
            tk_scaling = float(root.tk.call("tk", "scaling"))
        except (tk.TclError, ValueError):
            tk_scaling = None
        state = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "kit": VERSION,
            "test_build": bool(getattr(tk.Tk, "_artkit_test_window", False)),
            "window": {"geometry": root.winfo_geometry(), "state": root.state(),
                       "screen": [root.winfo_screenwidth(), root.winfo_screenheight()],
                       "tk_scaling": tk_scaling},
            "language": i18n.language(),
            "library": {"drawings": len(self.library.drawings),
                        "listed": len(self.visible_drawings()),
                        "labels": chosen(self._ticked(self.LABEL)),
                        "artists": chosen(self._ticked(self.ARTIST)),
                        "folded": self._library_collapsed},
            "tool": self.tool, "eraser": list(self.eraser_size),
            "symmetry": self.symmetry_mode, "grid_lines": self.show_grid,
            "grid_colours": list(self.grid_colours()),
        }
        if d is not None:
            state["drawing"] = {"name": d.name, "cells": [d.width, d.height], "label": d.label,
                                "artist": d.artist, "painted": d.count()}
            state["camera"] = {
                "mode": self.camera_mode, "pane": list(self._viewport()),
                "zoom": str(self.zoom_level), "fit_zoom": str(self.fit_zoom()),
                "min_zoom": str(self.min_zoom()), "fit_held": self._fit_held,
                "view_origin": [float(v) for v in self._view_origin()],
                "scrollregion": self.canvas.cget("scrollregion"),
                "visible_cells": self._visible_cells(),
                "locked_at": self._locked_at, "checker_cells": self._checker_cells(),
            }
        return state

    def _set_status(self, text, flash=False, error=False):
        status = getattr(self, "_status", None)
        if status is None:
            return
        status.configure(text=_shorten(text),
                         fg=theme.BREAK if error else (theme.ACCENT if flash else theme.ON_DIM))
        # One pending fade at a time (#v2.8.0). A message repeated faster than
        # it fades - the wheel under LOCK - used to flicker, every old fade
        # landing between two new flashes; and a fade left over from an
        # earlier flash could dim an error that had replaced it.
        if self._status_fade is not None:
            self.root.after_cancel(self._status_fade)
            self._status_fade = None
        if flash:
            def fade():
                self._status_fade = None
                status.configure(fg=theme.ON_DIM)
            self._status_fade = self.root.after(1500, fade)


class ColourPicker(tk.Frame):
    """A hue strip over a shade square, the way a phone app does it.

    Lifted out of `ArtKitApp` in #v2.8.0 so the export background dialog can
    embed the same control instead of opening the system colour chooser. That
    chooser is a second window with its own modal grab, its own typeface and
    its own idea of what a colour is - and, being modal, it hid the very
    preview the artist opened it to judge. One picker, in the panel, live.

    `on_pick(rgb)` fires on every click and every drag step, so whatever is
    watching updates as the finger moves rather than on an OK button.
    """

    def __init__(self, parent, width, sv_height, hue_height, on_pick, hue=0.0):
        super().__init__(parent, bg=theme.BG)
        # (not `_w`: tkinter keeps the widget's Tk path name in that slot)
        self._width, self._sv_h, self._hue_h = width, sv_height, hue_height
        self._on_pick = on_pick
        self.hue = hue
        self._sv_image = None  # the canvas shows it only while a reference lives

        self.hue_strip = tk.Canvas(self, width=width, height=hue_height,
                                   highlightthickness=0, cursor="crosshair", bg=theme.BG)
        self.hue_strip.pack()
        for x in range(width):
            r, g, b = colorsys.hsv_to_rgb(x / width, 1, 1)
            self.hue_strip.create_line(
                x, 0, x, hue_height,
                fill=f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
        self.hue_strip.bind("<Button-1>", self.pick_hue)
        self.hue_strip.bind("<B1-Motion>", self.pick_hue)

        self.sv_square = tk.Canvas(self, width=width, height=sv_height,
                                   highlightthickness=0, cursor="crosshair", bg=theme.BG)
        self.sv_square.pack(pady=(4, 0))
        self.sv_square.bind("<Button-1>", self.pick_shade)
        # Motion is a CONTINUATION of the press: one undo entry for the whole
        # drag, not one per pixel the pointer crosses.
        self.sv_square.bind("<B1-Motion>", lambda e: self.pick_shade(e, continuing=True))
        self.draw_shades()

    def draw_shades(self):
        rows = []
        for y in range(self._sv_h):
            v = 1 - y / self._sv_h
            row = []
            for x in range(self._width):
                r, g, b = colorsys.hsv_to_rgb(self.hue, x / self._width, v)
                row.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
            rows.append("{" + " ".join(row) + "}")
        self._sv_image = tk.PhotoImage(width=self._width, height=self._sv_h, master=self)
        self._sv_image.put(" ".join(rows))
        self.sv_square.delete("all")
        self.sv_square.create_image(0, 0, image=self._sv_image, anchor="nw")

    def pick_hue(self, event):
        self.hue = min(1.0, max(0.0, event.x / self._width))
        self.draw_shades()

    def pick_shade(self, event, continuing=False):
        s = min(1.0, max(0.0, event.x / self._width))
        v = min(1.0, max(0.0, 1 - event.y / self._sv_h))
        r, g, b = colorsys.hsv_to_rgb(self.hue, s, v)
        self._on_pick((int(r * 255), int(g * 255), int(b * 255)), continuing)

    def show(self, hexcode):
        """Move the strip to `hexcode`'s hue and redraw, without firing
        `on_pick` - for opening the picker already on the current colour."""
        r, g, b = engine_io.rgb_of(hexcode)
        self.hue = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0]
        self.draw_shades()


class ColourDialog(dialogs.Dialog):
    """One colour, picked with the kit's own hue strip and shade square
    (#v2.8.0) instead of the system colour chooser - a grey Windows dialog in
    another typeface, which reported nothing until its OK was pressed.

    `on_change(hexcol)` fires on every click, every drag step and every valid
    code typed, so whatever the colour is FOR can follow it live. `run()`
    returns the colour as `#rrggbb`, or None if the artist cancelled."""

    def __init__(self, parent, current, title=dialogs.TITLE, on_change=None):
        super().__init__(parent, title)
        self._on_change = on_change
        self.colour = "#" + current.lstrip("#").lower()
        self.picker = ColourPicker(self.body, PICKER_W, SV_H, HUE_H, on_pick=self._picked)
        self.picker.pack()
        self.picker.show(self.colour)
        row = theme.frame(self.body)
        row.pack(fill="x", pady=(8, 0))
        self.swatch = tk.Label(row, bg=self.colour, width=6, height=2, bd=0,
                               highlightthickness=1, highlightbackground=theme.SHADOW)
        self.swatch.pack(side="left")
        self.entry = theme.entry(row, justify="center", width=9)
        self.entry.pack(side="left", padx=(8, 0), ipady=3)
        self.entry.bind("<KeyRelease>", self._typed)
        self._show(self.colour, notify=False)
        self.buttons((t("cancel"), self.cancel, False),
                     (t("ok"), lambda: self.finish(self.colour), True))
        self.bind("<Return>", lambda e: self.finish(self.colour))

    def _picked(self, rgb, _continuing=False):
        self._show("#%02x%02x%02x" % rgb)

    def _typed(self, _event=None):
        text = self.entry.get().strip().lstrip("#")
        if re.fullmatch(r"[0-9a-fA-F]{6}", text) and "#" + text.lower() != self.colour:
            self._show("#" + text.lower(), from_entry=True)
            self.picker.show(self.colour)  # the strip follows a typed hue too

    def _show(self, hexcol, from_entry=False, notify=True):
        self.colour = hexcol
        self.swatch.configure(bg=hexcol)
        if not from_entry:
            self.entry.delete(0, "end")
            self.entry.insert(0, hexcol)
        if notify and self._on_change is not None:
            self._on_change(hexcol)


def ask_colour(parent, current, title=dialogs.TITLE, on_change=None):
    """`ColourDialog`, run: `#rrggbb`, or None if cancelled."""
    return ColourDialog(parent, current, title, on_change).run()


class SwatchGrid(tk.Canvas):
    """A grid of colour squares on one canvas (item 4, 9).

    One widget, however many colours, sized so the grid is exactly `width`
    pixels wide — which is what lines its edges up with the colour panel
    under it. A canvas rather than a row of buttons because macOS buttons
    ignore `bg` and painted every colour white.
    """

    def __init__(self, parent, width, cols, on_pick, on_context=None):
        super().__init__(parent, width=width, height=1, highlightthickness=0, bg=theme.BG,
                         cursor="hand2")
        # (not `_w`: tkinter keeps the widget's Tk path name in that slot)
        self._cols = cols
        self._cell = width // cols
        self._on_pick, self._on_context = on_pick, on_context
        self.colours = []
        self.bind("<Button-1>", self._click)
        for seq in theme.right_click_events():
            self.bind(seq, self._context)

    def set_colours(self, hexcodes):
        self.colours = [h.lstrip("#").upper() for h in hexcodes]
        rows = max(1, -(-len(self.colours) // self._cols))
        self.configure(height=rows * self._cell)
        self.delete("all")
        gap = 2
        for i, h in enumerate(self.colours):
            c, r = i % self._cols, i // self._cols
            x0, y0 = c * self._cell, r * self._cell
            self.create_rectangle(x0 + gap, y0 + gap, x0 + self._cell - gap, y0 + self._cell - gap,
                                  fill=f"#{h.lower()}", outline=theme.SHADOW)

    def _at(self, event):
        c, r = int(event.x) // self._cell, int(event.y) // self._cell
        i = r * self._cols + c
        if c < self._cols and 0 <= i < len(self.colours):
            return self.colours[i]
        return None

    def _click(self, event):
        h = self._at(event)
        if h is not None:
            self._on_pick(h)

    def _context(self, event):
        h = self._at(event)
        if h is not None and self._on_context is not None:
            self._on_context(h, event)


class ColourStrip(tk.Canvas):
    """The colours in the open drawing, left to right, most-used first, each
    with its code and cell count; click one to make it the ink (#v2.6.0,
    item 2). When they overflow, an ellipsis after the last one shows there
    is more, and a pair of arrows pages through it (#v2.7.0, item 9) - at
    the strip's far right, as solid triangles (#v2.8.0, sixth test pass: "sağ
    sol en sağda olsun ve biraz daha belirgin olsun"), where they had
    trailed the last colour as two thin bracket glyphs."""

    SWATCH, GAP, H = 16, 6, 30
    ARROW_W = 22      # px: each arrow's box, the click target
    ARROW_H = 12      # px: each triangle, tip to base

    def __init__(self, parent, on_pick):
        super().__init__(parent, height=self.H, highlightthickness=0, bg=theme.BG, cursor="hand2")
        self._on_pick = on_pick
        # Drawn once, smooth (ninth test pass: "alttaki sağ sol oku pikselli
        # duruyor" - a canvas polygon has no antialiasing on Windows).
        self._arrows = {(d, live): theme.icon("left" if d < 0 else "right", self.ARROW_H + 2,
                                             theme.ACCENT if live else theme.PANEL_HI, master=self)
                        for d in (-1, 1) for live in (True, False)}
        self._hits = []  # (x0, x1, hexcode or "prev"/"next")
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda e: self._paint())
        self._items = []
        self._offset = 0

    def set_colours(self, items):
        """`items`: [(hexcode, count), ...] in display order."""
        self._items = list(items)
        if self._offset >= len(self._items):
            self._offset = 0
        self._paint()

    def _paint(self):
        self.delete("all")
        self._hits = []
        width = max(1, self.winfo_width())
        items = self._items
        if not items:
            return
        offset = max(0, min(self._offset, max(0, len(items) - 1)))
        self._offset = offset
        more_before = offset > 0
        pager = self.ARROW_W * 2 + 4      # the two arrows, kept free at the far right
        # reserve room for the ellipsis and the arrows if anything is clipped
        x = 0
        shown = 0
        last_fit = offset
        for i in range(offset, len(items)):
            hexcode, count = items[i]
            text = f"#{hexcode.lower()} \u00b7 {count}"
            approx = self.SWATCH + 4 + 7 * len(text) + self.GAP
            room = width - (pager + 16 if (more_before or i < len(items) - 1) else 0)
            if x + approx > room and shown:
                break
            self.create_rectangle(x, (self.H - self.SWATCH) // 2, x + self.SWATCH,
                                  (self.H + self.SWATCH) // 2, fill=f"#{hexcode.lower()}",
                                  outline=theme.SHADOW)
            item = self.create_text(x + self.SWATCH + 4, self.H // 2, text=text, fill=theme.ON_DIM,
                                    anchor="w", font=theme.FONT_SMALL)
            x1 = self.bbox(item)[2]
            self._hits.append((x, x1, hexcode))
            x = x1 + self.GAP
            shown += 1
            last_fit = i
        more_after = last_fit < len(items) - 1
        if more_before or more_after:
            self.create_text(x, self.H // 2, text="\u2026", fill=theme.ON_DIM, anchor="w",
                             font=theme.FONT_SMALL)
            next_x = width - self.ARROW_W
            prev_x = next_x - self.ARROW_W
            self._arrow(prev_x, -1, more_before)
            self._arrow(next_x, +1, more_after)
            self._hits.append((prev_x, prev_x + self.ARROW_W, "prev"))
            self._hits.append((next_x, next_x + self.ARROW_W, "next"))

    def _arrow(self, x0, direction, live):
        """A solid triangle in its ARROW_W box, pointing left (-1) or right;
        the accent while there is somewhere to go, dim when there is not."""
        cx, cy = x0 + self.ARROW_W / 2, self.H / 2
        icon = self._arrows.get((direction, live))
        if icon is not None:
            self.create_image(round(cx), round(cy), image=icon, tags="arrow")
            return
        half, reach = self.ARROW_H / 2, self.ARROW_H * 0.45
        tip, base = cx + direction * reach, cx - direction * reach
        self.create_polygon(base, cy - half, base, cy + half, tip, cy,
                            fill=theme.ACCENT if live else theme.PANEL_HI, outline="",
                            tags="arrow")

    def _click(self, event):
        for x0, x1, what in self._hits:
            if x0 <= event.x <= x1:
                if what == "prev":
                    self._offset = max(0, self._offset - max(1, self._page_size()))
                    self._paint()
                elif what == "next":
                    self._offset = min(len(self._items) - 1, self._offset + max(1, self._page_size()))
                    self._paint()
                else:
                    self._on_pick(what)
                return

    def _page_size(self):
        shown = sum(1 for *_, what in self._hits if what not in ("prev", "next"))
        return shown or 1


class BackgroundDialog(tk.Toplevel):
    """"What sits behind the empty pixels?", with a preview (#v2.8.0).

    An export out of the kit has always been transparent, which is right for a
    sprite and wrong for a work-in-progress pasted into a chat window, where
    the viewer's own background shows through and a dark drawing vanishes.
    Three answers: keep it transparent, lay white down, or pick a colour.

    COLOUR opens a `ColourPicker` UNDER the three buttons rather than the
    system colour chooser (#v2.8.0). The chooser was a second modal window,
    which covered the preview the artist opened it to judge and only reported
    a colour once they pressed its OK; the embedded picker repaints the
    preview on every drag step, which is the whole point of having one.

    The preview on the right is built by `engine_io.composed` - the very
    function the exporters write - so it cannot drift from the file. Only the
    scale differs, and the checkerboard behind a transparent choice is the one
    thing drawn here and not written to disk: a see-through PNG shown against
    a flat panel would look identical to an opaque one of the same colour.

    Modal, and it reports through `self.result`: None for transparent, a hex
    string for a colour, or CANCELLED if the artist backed out - which is NOT
    the same as transparent, and the caller must not export on it.

    Under the background, the artist's mark (#v2.8.0, sixth test pass): the
    name ON the picture - in the corner, as a watermark, or both ("ikisini de
    yapma olsun") - which the preview shows; the name INSIDE the file; and
    whether the export is written down in export-log.jsonl. They come back as
    `self.signature`, `self.metadata` and `self.log`. A drawing with no artist
    cannot be signed, and says how to name one; the choice itself is kept
    for the next drawing that can.
    """

    PREVIEW = 168     # px, the side of the preview box
    PICKER_W = 186    # px, the embedded picker's width
    PICKER_SV = 74    # px, the height of its shade square
    PICKER_HUE = 12   # px, the height of its hue strip
    FALLBACK = "808080"  # the colour COLOUR opens on, first time

    def __init__(self, parent, initial=None, drawing=None, grid=None,
                 allow_transparent=True, title=None, last_colour=None,
                 signature=provenance.NONE, metadata=True, log=True):
        super().__init__(parent, bg=theme.BG)
        theme.unseen(self)  # shown once placed: no flash in the top-left corner
        self.title(title or t("bg_title"))
        self.transient(parent)
        self.resizable(False, False)
        theme.dark_title_bar(self)
        self.result = CANCELLED
        self._drawing, self._grid = drawing, grid
        self._allow_transparent = allow_transparent
        # JPEG cannot hold alpha, so a transparent choice there would be a
        # promise the format breaks: white is the honest default instead.
        self._choice = initial if (allow_transparent or initial is not None) else "FFFFFF"
        # The remembered colour survives an export that chose transparent or
        # white (#v2.8.0), so COLOUR always opens where the artist left it.
        self._custom = (initial if initial not in (None, "FFFFFF") else None) or last_colour
        self._image = None  # the PhotoImage, kept alive here
        self._artist = drawing.artist if drawing is not None else ""
        self.signature = signature if signature in provenance.MODES else provenance.NONE
        self.metadata = bool(metadata)
        self.log = bool(log)

        body = theme.frame(self)
        body.pack(padx=16, pady=12)
        theme.label(body, t("bg_title"), font=theme.FONT_BOLD).pack(anchor="w")
        theme.label(body, t("bg_question"), dim=True).pack(anchor="w", pady=(0, 10))

        columns = theme.frame(body)
        columns.pack(fill="x")
        choices = theme.frame(columns)
        choices.pack(side="left", anchor="n")

        self._buttons = {}
        for key, hint, value in (
                ("bg_transparent", "bg_transparent_hint", None),
                ("bg_white", "bg_white_hint", "FFFFFF"),
                ("bg_colour", "bg_colour_hint", CHOOSE)):
            row = theme.frame(choices)
            row.pack(fill="x", pady=2)
            btn = theme.button(row, t(key), lambda v=value: self._choose(v),
                               pady=6, width=14)
            btn.pack(side="left")
            hint_text = t(hint)
            if value is CHOOSE:
                # The remembered colour, as a swatch beside the button: one
                # click goes straight back to it without opening the picker.
                self._last_swatch = tk.Label(row, width=2, bd=0, highlightthickness=1,
                                             highlightbackground=theme.SHADOW, cursor="hand2")
                self._last_swatch.pack(side="left", padx=(6, 0), fill="y")
                self._last_swatch.bind("<Button-1>",
                                       lambda _e: self._choose(self._custom or self.FALLBACK))
            if value is None and not allow_transparent:
                btn.configure(state="disabled", cursor="")
                hint_text = t("bg_no_transparent")
            theme.label(row, hint_text, dim=True, wraplength=150, justify="left",
                        anchor="w").pack(side="left", padx=(10, 0))
            self._buttons[value] = btn

        # Packed now, shown only while COLOUR is the choice: building it once
        # keeps the hue the artist landed on when they flick to WHITE and back.
        self._picker_shown = False
        self._picker_box = theme.frame(choices)
        self._picker = ColourPicker(self._picker_box, self.PICKER_W, self.PICKER_SV,
                                    self.PICKER_HUE, on_pick=self._picked)
        self._picker.pack(anchor="w")
        hex_row = theme.frame(self._picker_box)
        hex_row.pack(fill="x", pady=(4, 0))
        self._hex = theme.entry(hex_row, justify="center", width=9)
        self._hex.pack(side="left", ipady=2)
        self._hex.bind("<Return>", self._on_hex)
        self._hex.bind("<KP_Enter>", self._on_hex)
        self._hex.bind("<FocusOut>", self._on_hex)
        self._swatch = tk.Label(hex_row, width=3, bg=theme.PANEL, relief="flat", bd=0,
                                highlightthickness=1, highlightbackground=theme.SHADOW)
        self._swatch.pack(side="left", padx=(6, 0), fill="y")

        preview_col = theme.frame(columns)
        preview_col.pack(side="right", anchor="n", padx=(16, 0))
        theme.label(preview_col, t("bg_preview"), dim=True).pack(anchor="w")
        self._canvas = tk.Canvas(preview_col, width=self.PREVIEW, height=self.PREVIEW,
                                 highlightthickness=1, highlightbackground=theme.SHADOW,
                                 bg=theme.CANVAS_BG)
        self._canvas.pack()

        # The artist's mark: on the picture, and inside the file.
        theme.label(body, t("sign_title"), font=theme.FONT_BOLD).pack(anchor="w", pady=(14, 0))
        theme.label(body, t("sign_question"), dim=True).pack(anchor="w", pady=(0, 6))
        # Two switches, not three answers: the corner and the watermark are
        # independent, so either, neither or both.
        self._sign_buttons, self._sign_hints = {}, {}
        for part, key in ((provenance.CORNER, "sign_corner"),
                          (provenance.WATERMARK, "sign_watermark")):
            row = theme.frame(body)
            row.pack(fill="x", pady=2)
            btn = theme.button(row, t(key), lambda p=part: self._sign(p), pady=6, width=14)
            btn.pack(side="left")
            hint = theme.label(row, "", dim=True, anchor="w", justify="left", wraplength=340)
            hint.pack(side="left", padx=(10, 0))
            self._sign_buttons[part], self._sign_hints[part] = btn, hint
        self._sign_note = theme.label(body, "", fg=theme.WARNING, anchor="w", justify="left",
                                      wraplength=460)
        self._sign_note.pack(fill="x", pady=(4, 0))
        self._meta_button = theme.button(body, "", self._toggle_metadata, anchor="w",
                                         padx=4, pady=3, font=theme.FONT)
        self._meta_button.pack(anchor="w", pady=(6, 0))
        # The record, the artist's to keep or not (sixth test pass: "tikli
        # olsun, yani kullanıcıya kalsın tercih").
        self._log_button = theme.button(body, "", self._toggle_log, anchor="w",
                                        padx=4, pady=3, font=theme.FONT)
        self._log_button.pack(anchor="w")

        buttons = theme.frame(body)
        buttons.pack(fill="x", pady=(14, 0))
        theme.button(buttons, t("cancel"), self.destroy).pack(side="right")
        theme.button(buttons, t("export"), self._confirm, bg=theme.WORK,
                     fg=theme.ON_ACCENT, activebackground=theme.ACCENT,
                     activeforeground=theme.ON_ACCENT).pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self.destroy())

        self._refresh()
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.update_idletasks()
        theme.reveal(self)
        self.grab_set()

    # ---- choosing ---------------------------------------------------------
    def _choose(self, value):
        if value is CHOOSE:
            value = self._custom or self.FALLBACK
            self._custom = value
            self._picker.show(value)
        if value is None and not self._allow_transparent:
            self.bell()
            return
        self._choice = value
        self._refresh()

    def _picked(self, rgb, _continuing=False):
        """Every click and every drag step inside the embedded picker."""
        self._choice = self._custom = "%02X%02X%02X" % rgb
        self._refresh()

    def _on_hex(self, _event=None):
        """A code typed into the box beside the picker. An unreadable one puts
        the current colour back rather than refusing with a dialog - the entry
        is a convenience, not a form to be validated at."""
        text = self._hex.get().strip().lstrip("#").upper()
        try:
            engine_io.rgb_of(text)
        except engine_io.ExportRefused:
            self._refresh()
            return
        self._choice = self._custom = text
        self._picker.show(text)
        self._refresh()

    def _sign(self, part):
        """Switch one mark - the corner or the watermark - on or off."""
        if not self._can_sign():
            self.bell()
            return
        on = provenance.parts(self.signature) ^ {part}
        self.signature = provenance.signature_of(provenance.CORNER in on,
                                                 provenance.WATERMARK in on)
        self._refresh()

    def _toggle_metadata(self):
        self.metadata = not self.metadata
        self._refresh()

    def _toggle_log(self):
        self.log = not self.log
        self._refresh()

    def _can_sign(self):
        return bool(provenance.pixel_name(self._artist))

    def _mark(self):
        """The mark as the export will make it, for the preview."""
        return provenance.Mark(title=self._drawing.name if self._drawing else "",
                               artist=self._artist, signature=self.signature,
                               metadata=self.metadata)

    def _confirm(self):
        self.result = self._choice
        self.destroy()

    # ---- the preview ------------------------------------------------------
    def _refresh(self):
        for value, btn in self._buttons.items():
            if value is CHOOSE:
                pressed = self._choice not in (None, "FFFFFF")
            else:
                pressed = value == self._choice
            theme.set_pressed(btn, pressed)
            if value is None and not self._allow_transparent:
                btn.configure(state="disabled", fg=theme.ON_DIM,
                              bg=theme.PANEL, activebackground=theme.PANEL)
        swatch = getattr(self, "_last_swatch", None)
        if swatch is not None:
            swatch.configure(bg=f"#{self._custom or self.FALLBACK}")
        custom = self._choice not in (None, "FFFFFF")
        # A flag, not `winfo_ismapped`: that answers False for every child of a
        # Toplevel that has not been mapped yet, so the first _refresh (which
        # runs from __init__) would pack a second copy the moment it is.
        if custom and not self._picker_shown:
            self._picker_box.pack(fill="x", pady=(6, 0))
        elif not custom and self._picker_shown:
            self._picker_box.pack_forget()
        self._picker_shown = custom
        if custom:
            if self._hex.get().strip().lstrip("#").upper() != self._choice:
                self._hex.delete(0, "end")
                self._hex.insert(0, self._choice)
            self._swatch.configure(bg=f"#{self._choice}")
            self._hex.configure(bg=f"#{self._choice}", fg=theme.readable_on(self._choice),
                                insertbackground=theme.readable_on(self._choice))
        self._refresh_mark()
        self._draw_preview()

    def _refresh_mark(self):
        can = self._can_sign()
        on = provenance.parts(self.signature) if can else set()
        notice = f"\u00a9 {datetime.now().year} {self._artist}"
        for part, btn in self._sign_buttons.items():
            theme.set_pressed(btn, part in on)
            btn.configure(state="normal" if can else "disabled", cursor="hand2" if can else "")
            if not can:
                btn.configure(fg=theme.ON_DIM, bg=theme.PANEL, activebackground=theme.PANEL)
            self._sign_hints[part].configure(
                text=t(f"sign_{part}_hint", notice=notice) if can else "")
        note = ""
        if not can:
            note = t("sign_no_artist")
        elif on and self._drawing is not None:
            # Measured at the size the file will be, not the preview's.
            d = self._drawing
            if not provenance.stamp(d.width * 16, d.height * 16, self._mark()):
                note = t("sign_too_small")
        self._sign_note.configure(text=note)
        if note:
            self._sign_note.pack(fill="x", pady=(4, 0), before=self._meta_button)
        else:
            self._sign_note.pack_forget()
        def ticked(on):
            return dialogs.TICKED if on else dialogs.UNTICKED
        self._meta_button.configure(text=f"{ticked(self.metadata)}  {t('meta_toggle')}")
        self._log_button.configure(text=f"{ticked(self.log)}  {t('log_toggle')}")

    def _draw_preview(self):
        canvas = self._canvas
        canvas.delete("all")
        side = self.PREVIEW
        if self._drawing is None:
            return
        rows, cols = self._drawing.height, self._drawing.width
        # A whole number of pixels per cell, so the preview stays as crisp as
        # the art it previews. At least 1: a 64-wide tree in 168px is 2.
        scale = max(1, min(side // max(1, cols), side // max(1, rows)))
        big = engine_io.composed(self._drawing, scale, self._grid, self._choice)
        if len(big[0]) > side or len(big) > side:
            # Wider than the box even at 1 px a cell: averaged down into it,
            # the way the corner pictures are, rather than cut off.
            big, _n = raster.shrink(big, side)
        # The signature, laid on at the preview's own size - the stamp sizes
        # itself to the picture, so it sits where and how the file will have it.
        big = provenance.apply(big, provenance.stamp(len(big[0]), len(big), self._mark()))
        w, h = len(big[0]), len(big)
        x, y = (side - w) // 2, (side - h) // 2
        if self._choice is None:
            # The checkerboard is the ONLY thing here the export does not
            # write: it is how "see-through" is shown at all.
            step = max(4, scale)
            for r in range(0, h, step):
                for c in range(0, w, step):
                    tone = theme.CHECKER[((r // step) + (c // step)) % 2]
                    canvas.create_rectangle(
                        x + c, y + r, min(x + c + step, x + w), min(y + r + step, y + h),
                        fill=tone, outline="")
        self._image = raster.photo(big, master=canvas)
        canvas.create_image(x, y, image=self._image, anchor="nw")
        canvas.create_rectangle(x, y, x + w, y + h, outline=theme.SHADOW)


class LabelDialog(tk.Toplevel):
    """Pick or type a label for one drawing (#v2.6.0, item 1) - or, with
    `kind="artist"`, who drew it (#v2.8.0): the same gesture for the other
    layer, each name shown in the colour `colour_of` gives it."""

    # i18n keys: the noun, the heading, the hint, and the button that clears it
    TEXTS = {
        "label": ("label_noun", "label_heading", "label_hint", "no_label"),
        "artist": ("artist_noun", "artist_heading", "artist_hint", "no_artist"),
    }

    def __init__(self, parent, drawing, existing, on_ok, kind="label", colour_of=None,
                 names_of=None, on_rename=None, on_delete=None):
        super().__init__(parent, bg=theme.BG)
        theme.unseen(self)  # shown once placed: no flash in the top-left corner
        keys = self.TEXTS[kind]
        self._kind, self._colour_of = kind, colour_of
        self._names_of = names_of or (lambda: list(existing))
        self._on_rename, self._on_delete = on_rename, on_delete
        noun, hint, clear = t(keys[0]), t(keys[2]), t(keys[3])
        heading = t(keys[1], name=drawing.name)
        current = drawing.artist if kind == "artist" else drawing.label
        self.title(f"{noun} \u2014 {drawing.name}")
        self.transient(parent)
        self.resizable(False, False)
        theme.dark_title_bar(self)
        self._on_ok = on_ok
        body = theme.frame(self)
        body.pack(padx=16, pady=12)
        theme.label(body, heading, font=theme.FONT_BOLD).pack(anchor="w")
        theme.label(body, hint, dim=True, wraplength=360, justify="left").pack(
            anchor="w", pady=(0, 8))
        self._current = current
        self._grid = theme.frame(body)
        self._grid.pack(fill="x")
        self._fill_names()
        row = theme.frame(body)
        row.pack(fill="x", pady=(10, 0))
        theme.label(row, t("type_new"), dim=True).pack(side="left")
        self._entry = theme.entry(row, width=18)
        self._entry.insert(0, current)
        self._entry.pack(side="left", padx=(8, 0), ipady=2, fill="x", expand=True)
        buttons = theme.frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        theme.button(buttons, t("cancel"), self.destroy).pack(side="right")
        theme.button(buttons, clear, lambda: self._finish("")).pack(side="right", padx=(0, 6))
        theme.button(buttons, t("apply"), lambda: self._finish(self._entry.get()), bg=theme.WORK,
                     fg=theme.ON_ACCENT, activebackground=theme.ACCENT).pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda e: self._finish(self._entry.get()))
        self.bind("<Escape>", lambda e: self.destroy())
        self._entry.focus_set()
        self._entry.select_range(0, "end")
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.update_idletasks()
        theme.reveal(self)
        self.grab_set()

    def _fill_names(self):
        """The names in use, each a button that picks it - and, beside it, a
        ⋮ to rename it or take it off every drawing (#v2.8.0, ninth test pass:
        "artistlerin adını değiştirme ve silme opsiyonu gelsin, aynı şekilde
        labellarda da")."""
        for child in self._grid.winfo_children():
            child.destroy()
        for i, name in enumerate(self._names_of()):
            cell = theme.frame(self._grid)
            cell.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
            btn = theme.button(cell, name, lambda n=name: self._finish(n), pady=4)
            if self._colour_of is not None:
                btn.configure(fg=self._colour_of(name))
            if name == self._current:
                theme.set_pressed(btn, True)
            btn.pack(side="left", fill="x", expand=True)
            if self._on_rename is not None or self._on_delete is not None:
                dots = theme.button(cell, "\u22ee", None, padx=3, pady=3,
                                    font=theme.bold(theme.FONT_SIZE + 2))
                dots.configure(command=lambda n=name, w=dots: self._name_menu(n, w))
                dots.pack(side="left", fill="y", padx=(1, 0))
        for c in range(3):
            self._grid.grid_columnconfigure(c, weight=1)

    def _name_menu(self, name, widget):
        menu = self._menu = dialogs.PopupMenu(self, tearoff=False)
        if self._on_rename is not None:
            menu.add_command(label=t("rename"), command=lambda: self._rename(name))
        if self._on_delete is not None:
            menu.add_command(label=t("delete"), command=lambda: self._delete(name))
        menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height(),
                      flip_y=widget.winfo_rooty())

    def _rename(self, name):
        key = "rename_artist_prompt" if self._kind == "artist" else "rename_label_prompt"
        new = dialogs.askstring(dialogs.TITLE, t(key, name=name), initialvalue=name, parent=self)
        self._regrab()
        new = (new or "").strip()
        if not new or new == name:
            return
        self._on_rename(name, new)
        if self._current == name:
            self._current = new
            self._retext_entry(name, new)
        self._fill_names()

    def _delete(self, name):
        gone = self._on_delete(name, parent=self)
        self._regrab()
        if not gone:
            return
        if self._current == name:
            self._current = ""
            self._retext_entry(name, "")
        self._fill_names()

    def _retext_entry(self, old, new):
        if self._entry.get().strip() == old:
            self._entry.delete(0, "end")
            self._entry.insert(0, new)

    def _regrab(self):
        """A question asked over this dialog took the grab; take it back."""
        if self.winfo_exists():
            try:
                self.grab_set()
            except tk.TclError:
                pass

    def _finish(self, text):
        self.destroy()
        self._on_ok(text)


class SizeDialog(tk.Toplevel):
    """New drawing / resize: preset sizes the engine actually uses, or a
    custom width x height (item 13). Calls `on_ok(cols, rows)`."""

    def __init__(self, parent, title, initial, presets, on_ok, verb="OK"):
        super().__init__(parent, bg=theme.BG)
        theme.unseen(self)  # shown once placed: no flash in the top-left corner
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        theme.dark_title_bar(self)
        self._on_ok = on_ok
        body = theme.frame(self)
        body.pack(padx=16, pady=12)
        theme.label(body, title, font=theme.FONT_BOLD).pack(anchor="w")
        theme.label(body, t("size_hint"), dim=True).pack(anchor="w", pady=(0, 8))

        grid = theme.frame(body)
        grid.pack(fill="x")
        for i, (name, cols, rows) in enumerate(presets):
            btn = theme.button(grid, f"{name}\n{cols} \u00d7 {rows}", 
                               lambda c=cols, r=rows: self._finish(c, r), pady=6)
            btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1)

        custom = theme.frame(body)
        custom.pack(fill="x", pady=(10, 0))
        theme.label(custom, t("custom"), dim=True).pack(side="left")
        self._cols_entry = theme.entry(custom, width=4, justify="center")
        self._cols_entry.insert(0, str(initial[0]))
        self._cols_entry.pack(side="left", padx=(8, 2), ipady=2)
        theme.label(custom, "\u00d7").pack(side="left")
        self._rows_entry = theme.entry(custom, width=4, justify="center")
        self._rows_entry.insert(0, str(initial[1]))
        self._rows_entry.pack(side="left", padx=(2, 8), ipady=2)
        theme.label(custom, t("cells"), dim=True).pack(side="left")

        buttons = theme.frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        theme.button(buttons, t("cancel"), self.destroy).pack(side="right")
        theme.button(buttons, verb, self._custom, bg=theme.WORK, fg=theme.ON_ACCENT,
                     activebackground=theme.ACCENT).pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda e: self._custom())
        self.bind("<Escape>", lambda e: self.destroy())
        self._cols_entry.focus_set()
        self._cols_entry.select_range(0, "end")
        self.update_idletasks()
        # centre over the parent
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.update_idletasks()
        theme.reveal(self)
        self.grab_set()

    def _custom(self):
        """Any size (#v2.8.0), with the two guards `BIG_CELLS` and
        `HUGE_SIDE` describe - both asked in words, not with a bell."""
        try:
            cols, rows = int(self._cols_entry.get()), int(self._rows_entry.get())
        except ValueError:
            self.bell()
            return
        if cols < 1 or rows < 1:
            self.bell()
            return
        if max(cols, rows) > HUGE_SIDE:
            dialogs.showwarning(dialogs.TITLE, t("size_huge", w=cols, h=rows, max=HUGE_SIDE),
                                parent=self)
            self._regrab()
            return
        if cols * rows > BIG_CELLS:
            # A narrow space between the thousands reads right in all four
            # languages; a comma is a decimal point in three of them.
            n = f"{cols * rows:,}".replace(",", " ")
            sure = dialogs.askyesno(dialogs.TITLE, t("size_big", w=cols, h=rows, n=n),
                                    parent=self, icon="warning")
            self._regrab()
            if not sure:
                return
        self._finish(cols, rows)

    def _regrab(self):
        """Take the grab back from a question that was asked over this dialog -
        Tk hands a finished dialog's grab to nobody."""
        if self.winfo_exists():
            try:
                self.grab_set()
            except tk.TclError:
                pass
            self._cols_entry.focus_set()

    def _finish(self, cols, rows):
        self.destroy()
        self._on_ok(cols, rows)


HELP_TEXT = [
    ("BUTTONS", None),
    ("SAVE", "write the open drawing to disk now (every stroke is also autosaved)"),
    ("DRAW / ERASE / FILL", "paint one square · clear one square · flood the connected area"),
    ("SELECT", "drag a rectangle. Press inside it and drag to move those cells; "
               "{mod}+C copies, then click a cell (even in another drawing) to paste there; "
               "{mod}+X / {mod}+V cut / floating paste; Delete clears; Enter drops a floating block; "
               "Esc or clicking SELECT again dismisses the rectangle; FILL with a selection paints its inside"),
    ("UNDO / REDO", "step back / forward, one stroke at a time (a drag, a fill, a paste is one stroke)"),
    ("Eraser W × H", "how many cells the eraser clears at once, centred on the pointer. Its outline "
                     "follows it while it erases, and a big one clears the border cells with the "
                     "pointer past the edge (no resize grab while it covers the art)"),
    ("Grid colour 1 / 2", "the two checkerboard tones behind the art — type a code, or … for the kit's "
                          "colour picker (the grid follows it live; CANCEL puts it back). DEFAULT puts "
                          "the matcha tones back; WHITE and BLACK make both tones white, or black - a "
                          "plain ground to judge the art on"),
    ("#rrggbb  +", "the ink. Click to type a new code, double-click to select it, + adds it to favourites"),
    ("Favourite colours", "your own set — right-click a swatch to remove it"),
    ("Ready colours", "Pixel Pomo's theme tones plus pixel-art staples"),
    ("Colour", "hue strip on top, light/dark square below; click or drag"),
    ("Symmetry: OFF", "plain painting"),
    ("Symmetry: MIRROR", "a bright line sits BETWEEN pixels; painting along it is mirrored. "
                        "Drag the line to move it, drag an end to resize, or PLACE BAR and click a new spot"),
    ("Symmetry: STICK", "the same between-pixel line; placing it copies `length` rows (\u2502 90\u00b0) or columns "
                        "(\u2500 180\u00b0) across it \u2014 a strip symmetry stamp"),
    ("  \u2502 90\u00b0 / \u2500 180\u00b0", "the line's direction: standing or lying"),
    ("  length", "how many rows/columns the line covers. Drag either END to change it on the canvas"),
    ("WITH / WITHOUT GRID", "show or hide the cell lines over the drawing \u2014 sits just above UPDATE / GUIDE"),
    ("LANGUAGE", "English / T\u00fcrk\u00e7e / Polski / Deutsch. Button boxes keep their size; type shrinks if needed"),
    ("\u2630 (library)", "collapses the drawing list to the rail; click again to expand. Sits above the "
                         "scrollbar, on one line with ALL and FIT"),
    ("Under the canvas", "total, empty and painted pixel counts, the colours in the drawing "
                         "(click one to use it; \u2039 \u203a pages overflow), the cell and colour under the cursor"),
    ("Over the canvas", "the camera. FIT zooms until the whole drawing fills the pane - below 1 px a "
                        "cell for one bigger than the pane, and the wheel goes down to the scale of the "
                        "corner's smallest picture (1/10 px for a 600-wide drawing)"),
    ("  FREE", "the view goes anywhere: the wheel zooms about the pointer, Space+drag or the middle "
               "button pans"),
    ("  LOCK", "freezes the view exactly as it is framed now \u2014 the zoom AND the position. The wheel, "
               "+ / \u2212, FIT and panning do nothing (the corner says \u201ccamera locked\u201d); every "
               "drawing keeps its own frozen view until another mode is picked"),
    ("  \u2196 \u2197 \u2199 \u2198  \u2190 \u00b7 \u2192", "zoomed out, the drawing sits in that corner, on that "
                                             "side or in the middle; zoomed in, look around freely"),
    ("1x / squint", "the drawing at real size, and at squint-test distance (a drawing too big for the "
                    "corner shows as 1/2x, 1/3x\u2026 - every pixel of it the average of the cells it stands "
                    "for, so a one-cell line still shows)"),
    ("\u2610 LOOK", "beside squint: the canvas shows the drawing as it looks \u2014 no checkerboard, no cell "
               "lines, no symmetry line \u2014 and nothing is drawn, erased or resized until it is "
               "unticked. Zoom, pan and the eyedropper still work"),
    ("W \u00d7 H", "the drawing's size \u2014 click it to resize. Or drag an edge or a corner of the "
              "drawing on the canvas: out adds rows / columns, in takes them away; {mod}+Z undoes a "
              "whole drag at once. The grab lies just OUTSIDE the edge, so painting the border cells "
              "never turns into a resize"),
    ("UPDATE", "checks GitHub for a newer kit. Windows updates itself (your drawings are untouched, and "
               "backed up first); macOS opens the download page"),
    ("+ NEW DRAWING", "a blank drawing at a garden size: flower 16\u00d716, bug 8\u00d78, bush, rock, tree, or "
                      "any custom size (past 512 \u00d7 512 the kit asks first \u2014 big drawings are slower)"),
    ("IMPORT PNG…", "bring in art from Procreate/Aseprite/anything; it is saved into the library at once"),
    ("▸ ALL (top left)", "one checklist: every label (flower / tree / bush / rock / bugs / …) and, "
                         "under ARTISTS, every artist in their colour. What is ticked is what is "
                         "listed - a drawing shows if its label OR its artist is ticked. Under ALL "
                         "every row is ticked; from there a click ticks just that row, each click "
                         "after it ticks one on or off (the list stays open while you tick), and ALL "
                         "lists everything again"),
    ("label chip \u00b7 initial", "left of \u22ee on each row: the label (click to change it), then the "
                                 "artist's initial in that artist's own colour (click to name who drew "
                                 "it) - two artists who share a letter still differ by colour. In either "
                                 "dialog the \u22ee beside a name renames it, or takes it off, on every "
                                 "drawing at once"),
    ("\u22ee", "Duplicate, Export PNG / SVG (vector, sharp at any zoom) / JPG / JSON "
          "(the kit drawing file \u2014 what the library stores and what survives an update) / "
          "engine sprite (PNG the garden loads, x16), Rename, Label, Artist, Size, Delete"),
    ("JSON vs PNG", "the library is JSON in your data folder. An update replaces the program only. "
                    "Export engine sprite writes the PNG the game draws. Export SVG for sharing without "
                    "pixelation. Export JSON to send a drawing to another kit."),
    ("Signature", "the export dialog asks, under the background: the artist's name on the picture "
                  "(NONE, CORNER - small, bottom right - or WATERMARK - faint, all over, for sharing a "
                  "proof) and ☐ name and © inside the file (PNG text and XMP, JPEG EXIF, SVG "
                  "metadata). It needs an artist on the drawing: ⋮ → Artist…. Engine sprites "
                  "stay clean - they are the game's"),
    ("export-log.jsonl", "every export, written down in the data folder: when, which file and its "
                         "SHA-256, which drawing, whose, how it was signed. Each line holds the digest "
                         "of the one before, so an edit in the middle shows"),
    ("", None),
    ("KEYBOARD", None),
    ("{mod}+S", "save"),
    ("{mod}+Z / {mod}+Y", "undo / redo  ({mod}+Shift+Z also redoes) — strokes, colour picks, grid "
                          "and symmetry changes, in the order they happened"),
    ("{mod}+N", "new drawing"),
    ("B / E / F / S", "brush / eraser / fill / select"),
    ("{mod}+C / X / V", "copy / cut / paste \u2014 after copy, click a cell to paste there"),
    ("Enter \u00b7 Delete \u00b7 Esc \u00b7 arrows", "drop the floating block \u00b7 clear the selection \u00b7 dismiss selection \u00b7 nudge the block"),
    ("M", "symmetry: OFF → MIRROR → STICK"),
    ("+ / −  or mouse wheel", "zoom in / out (not under LOCK)"),
    ("Space+drag · middle button", "pan the view; Shift+wheel pans sideways (not under LOCK)"),
    ("Right-click on the canvas", "eyedropper: the colour under the cursor becomes the ink"),
    ("F1 / Esc", "open / close this guide"),
    ("F12", "TEST build only: a snapshot - the window as it is now and the numbers behind it "
            "(zoom, pane, camera, drawing), saved into snapshots/ in the data folder - for "
            "showing what went wrong"),
]
TEST_ONLY_HELP = {"F12"}   # rows the release build does not show: it has no such key

# The guide's last part: how the artist's work is protected (#v2.8.0, eighth
# test pass: "help kısmında en altta copyright önlemlerinin nasıl çalıştığını
# anlatan bir kısım"). In the four languages, unlike the rows above, which are
# still English: each is an i18n key, "gp_<name>_k" the left column and
# "gp_<name>" the right.
GUIDE_PROTECTION = ("limits", "corner", "watermark", "meta", "made", "log", "hash", "engine", "later")


def protection_rows():
    """The guide's protection rows, in the language of the moment."""
    rows = [("", None), (t("gp_title"), None)]
    return rows + [(t(f"gp_{name}_k"), t(f"gp_{name}")) for name in GUIDE_PROTECTION]


class HelpOverlay(tk.Frame):
    """Every button and key, on a panel over the main window; × or Esc closes
    it (item 15)."""

    def __init__(self, parent, on_close, data_dir=None, test_build=False):
        super().__init__(parent, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.ACCENT)
        self.place(relx=0.5, rely=0.5, anchor="center")
        head = theme.frame(self, bg=theme.PANEL)
        head.pack(fill="x", padx=14, pady=(10, 4))
        theme.label(head, t("help_title", version=VERSION), bg=theme.PANEL,
                    font=theme.FONT_BOLD).pack(side="left")
        # A drawn X, bigger and smooth where the 9-point × glyph was small and
        # jagged, its right edge on the scrollbar's (#v2.8.0, ninth test pass:
        # "x köşede pikselli duruyor, büyüt ve sağa endeksle scroll'un
        # hizasına"). `head` and the list below share their padding, so a
        # button packed flush right ends where the scrollbar does.
        self._close_icon = theme.icon("close", 14, theme.ON_SURFACE, master=self)
        close = theme.button(head, "" if self._close_icon else "\u00d7", on_close,
                             padx=3, pady=3, font=theme.bold(theme.FONT_SIZE + 4),
                             bg=theme.PANEL, activebackground=theme.PANEL_HI)
        if self._close_icon is not None:
            close.configure(image=self._close_icon)
        close.pack(side="right")
        if data_dir is not None:
            # Where the work is — so nobody hunts for it beside the program.
            # Packed before the body, at the bottom, so it is always visible
            # however long the list above gets.
            foot = theme.frame(self, bg=theme.PANEL)
            foot.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
            theme.label(foot, t("your_drawings"), bg=theme.PANEL, fg=theme.ACCENT,
                        font=theme.FONT_BOLD).pack(side="left")
            theme.label(foot, str(data_dir), bg=theme.PANEL, font=theme.FONT_MONO,
                        fg=theme.WORK).pack(side="left", padx=(8, 8))
            theme.button(foot, t("open_folder"), lambda: paths.open_in_file_manager(data_dir),
                         padx=6, pady=1).pack(side="left")
        # The list itself scrolls (#v2.6.0): it outgrew an 820px window.
        holder = theme.frame(self, bg=theme.PANEL)
        holder.pack(padx=14, pady=(0, 8), fill="both", expand=True)
        parent.update_idletasks()
        max_h = max(240, parent.winfo_height() - 150)
        scroller = tk.Canvas(holder, bg=theme.PANEL, highlightthickness=0, width=760, height=max_h)
        sbar = theme.scrollbar(holder, "vertical")
        sbar.pack(side="right", fill="y")
        scroller.pack(side="left", fill="both", expand=True)
        scroller.configure(yscrollcommand=sbar.set)
        sbar.configure(command=scroller.yview)
        body = theme.frame(scroller, bg=theme.PANEL)
        scroller.create_window((0, 0), window=body, anchor="nw")

        def _fit(_e=None):
            body.update_idletasks()
            req_h = body.winfo_reqheight()
            scroller.configure(scrollregion=(0, 0, body.winfo_reqwidth(), req_h),
                               height=min(max_h, req_h), width=body.winfo_reqwidth())
        body.bind("<Configure>", _fit)
        for w in (scroller, body, self):
            w.bind("<MouseWheel>", lambda e: scroller.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self._scroller = scroller
        mod = theme.modifier_label()
        # Each section under its heading, the heading flush left over an
        # accent line; each row flush left too - the sub-rows lost the two
        # spaces that indented them - and a hairline between one row and the
        # next, with the rows' own spacing kept round it (#v2.8.0, ninth test
        # pass: "her bölüm çizgi ile ayrılsın, aralardaki mesafe korunsun ve
        # başlıklar sola doğru entegre olsun").
        rows = [(k, v) for k, v in HELP_TEXT + protection_rows()
                if k and not (k in TEST_ONLY_HELP and not test_build)]
        r = 0
        for i, (key, text) in enumerate(rows):
            key = key.strip().replace("{mod}", mod)
            if text is None:
                theme.label(body, key, bg=theme.PANEL, fg=theme.ACCENT,
                            font=theme.FONT_BOLD, anchor="w").grid(
                    row=r, column=0, columnspan=2, sticky="w", pady=(14 if i else 2, 3))
                tk.Frame(body, bg=theme.ACCENT, height=1).grid(
                    row=r + 1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
                r += 2
                continue
            theme.label(body, key, bg=theme.PANEL, font=theme.FONT_MONO, fg=theme.WORK,
                        anchor="w", justify="left", wraplength=210).grid(
                row=r, column=0, sticky="nw", padx=(0, 12), pady=5)
            theme.label(body, text.replace("{mod}", mod), bg=theme.PANEL, anchor="w",
                        justify="left", wraplength=520).grid(row=r, column=1, sticky="w", pady=5)
            r += 1
            if i + 1 < len(rows) and rows[i + 1][1] is not None:
                tk.Frame(body, bg=theme.PANEL_HI, height=1).grid(
                    row=r, column=0, columnspan=2, sticky="ew")
                r += 1
        for child in body.winfo_children():
            child.bind("<MouseWheel>",
                       lambda e: scroller.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        _fit()
        self.lift()
