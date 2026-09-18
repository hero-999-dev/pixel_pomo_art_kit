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
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path

from art_kit import branding, engine_io, i18n, paths, raster, store, symmetry, theme, updater
from art_kit.i18n import t
from art_kit.model import Drawing, History, LETTERS, Palette, hex_to_rgba
from art_kit.settings import Settings
from art_kit.version import VERSION

MIN_ZOOM, MAX_ZOOM = 4, 48
DEFAULT_ZOOM = 20
CHECKER = theme.CHECKER
PREVIEW_ZOOM = 6  # the fixed "squint test" scale, independent of the editing zoom
THUMB_PX = 64     # a library thumbnail fits in this square (2x for 16-cell art)

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
READY = ["FF5A5F", "E02C6D", "9C1B2E", "F2994A", "F2C94C", "F7EFDD",
         "5FBF4A", "3E8E36", "1E5A24", "27AE60", "6FCF97", "56CCF2",
         "2D9CDB", "2F80ED", "1B4F72", "8E4FE0", "BB6BD9", "6B2FA0",
         "F4A6C0", "CC2A3D", "8B5A2B", "5D4037", "3E2723", "CDD6F4",
         "9AA0B5", "5C6178", "1E1E2E", "000000", "808080", "FFFFFF"]

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
ZOOM_HANDLE = 12   # px grab around the drawing's bottom-right corner (#v2.7.0, item 15)

NEW_SIZE = 32  # new drawings: room for the trees and pets that are coming
MAX_SIZE = 64

TOOLS = ("draw", "erase", "fill", "select")
AUTOSCROLL_MARGIN = 24  # px from the canvas edge at which a drag starts scrolling (#v2.6.0)


def _lighten(hexcol, amount=0.25):
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = (int(v + (255 - v) * amount) for v in (r, g, b))
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
    presets = [("Flower", 16, 16), ("Bug", 8, 8), ("Bush", 16, 16), ("Rock", 16, 16)]
    for tiles in sorted(set(g.TREE_TILES)):
        px = tiles * g.TREE_PX_PER_TILE
        presets.append((f"Tree \u00b7 {tiles} tiles", px, px))
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
        self._label_filter = None  # None = every drawing; "" = unlabelled; else that label
        self._hover_cell = None
        self._paste_armed = False  # after Ctrl+C, the next click pastes (#v2.7.0, item 7)
        self._library_collapsed = bool(self.settings.library_collapsed)
        self._zoom_drag = None     # (start_zoom,) while the corner handle is dragged
        self._view_undo = []       # previous zoom levels from the corner handle
        i18n.set_language(self.settings.language)

        theme.setup(root)
        branding.apply_window_icon(root)
        root.title("Pixel Pomo Art Kit")
        self._build()
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
            self._set_status("checking\u2026")

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
                self._set_status("check failed", error=True)
                messagebox.showwarning(
                    "Pixel Pomo Art Kit",
                    f"Could not reach GitHub to check for updates:\n{error}\n\n"
                    f"You can always look here:\n{updater.RELEASES_PAGE}", parent=self.root)
            return
        if not release.is_newer:
            self._update_release = None
            if not silent:
                self._set_status(f"v{VERSION} is current", flash=True)
                messagebox.showinfo("Pixel Pomo Art Kit",
                                    f"You have the latest version, v{VERSION}.", parent=self.root)
            return
        self._update_release = release
        self._update_button.configure(text=f"UPDATE \u25cf {release.tag}", bg=theme.WORK,
                                      fg=theme.ON_ACCENT, activebackground=theme.ACCENT)
        self._set_status(f"{release.tag} available", flash=True)
        if not silent:
            self.offer_update(release)

    def offer_update(self, release):
        """The dialog. Windows swaps the .exe itself; everywhere else the
        release page opens in the browser."""
        data = str(self.library.root.parent)
        if updater.can_self_update():
            if messagebox.askyesno(
                    "Pixel Pomo Art Kit",
                    f"Pixel Pomo Art Kit {release.tag} is available (you have v{VERSION}).\n\n"
                    f"Update now? The kit downloads the new version, closes, swaps itself and "
                    f"reopens.\n\nYour drawings are NOT touched — they live in\n{data}\n"
                    f"and a backup zip of the library is made first.", parent=self.root):
                self._apply_windows_update(release)
            return
        if messagebox.askyesno(
                "Pixel Pomo Art Kit",
                f"Pixel Pomo Art Kit {release.tag} is available (you have v{VERSION}).\n\n"
                f"Open the download page?\n\nYour drawings live in\n{data}\n"
                f"and are not affected by replacing the app.", parent=self.root):
            webbrowser.open(release.url)

    def _apply_windows_update(self, release):
        url = release.assets.get(updater.WINDOWS_ASSET)
        if not url:
            messagebox.showerror("Pixel Pomo Art Kit",
                                 f"{release.tag} has no Windows download yet. Try again in a few "
                                 f"minutes, or open\n{release.url}", parent=self.root)
            return
        self._update_button.configure(state="disabled")
        dest = updater.temp_download_path(release.tag)

        def progress(done, total):
            pct = f"{100 * done // total}%" if total else f"{done // 1024} KB"
            self.root.after(0, lambda: self._set_status(f"downloading {pct}"))

        def work():
            try:
                updater.download(url, dest, progress)
                self.root.after(0, lambda: self._finish_windows_update(release, dest))
            except Exception as exc:
                self.root.after(0, lambda: self._update_failed(exc))

        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self, exc):
        self._update_button.configure(state="normal")
        self._set_status("update failed", error=True)
        messagebox.showerror("Pixel Pomo Art Kit",
                             f"The update could not be applied:\n{exc}\n\nNothing was changed. "
                             f"You can download it by hand from\n{updater.RELEASES_PAGE}",
                             parent=self.root)

    def _finish_windows_update(self, release, zip_path):
        """Downloaded: back the library up, stage the new .exe, hand off, quit."""
        try:
            backup = updater.backup_library(self.library.root.parent, release.tag)
            _new_exe, script = updater.stage_windows(zip_path)
            self._set_status("restarting\u2026")
            updater.launch_handoff(script)
        except Exception as exc:
            self._update_failed(exc)
            return
        if backup is not None:
            self._set_status(f"backup: {backup.name}")
        self.close()

    # ---- state ---------------------------------------------------------
    def select(self, drawing):
        previous = self._selected
        if self.floating is not None and previous is not None:
            self.commit_floating()  # a block in the air lands before the drawing changes
        self.selection = None
        self._selecting = None
        self._selected = drawing
        self.history = self._histories.setdefault(id(drawing), History(drawing))
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
        self.root.after(80, self.zoom_to_fit)

    def zoom_to_fit(self):
        """Pick the zoom that makes the whole grid fill the canvas pane."""
        if self.history is None:
            return
        d = self.history.current
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 40 or ch < 40:
            return  # window not laid out yet (or headless tests)
        z = max(MIN_ZOOM, min(MAX_ZOOM, cw // d.width, ch // d.height))
        if z != self.zoom_level:
            self.zoom_level = z
            self._draw_main()

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
        w = max(1, min(MAX_SIZE, int(w)))
        h = max(1, min(MAX_SIZE, int(h)))
        self.eraser_size = (w, h)
        self.settings.set_eraser(w, h)
        self._refresh_eraser_ui()

    def set_show_grid(self, on):
        self.show_grid = bool(on)
        self.settings.show_grid = self.show_grid
        self._refresh_grid_ui()
        self._draw_main()

    def set_grid_colours(self, c1=None, c2=None):
        """The two checkerboard tones behind the art (#v2.6.0, item 7)."""
        self.settings.set_grid(c1, c2)
        self._refresh_grid_ui()
        self._draw_main()

    def reset_grid_colours(self):
        self.settings.reset_grid()
        self._refresh_grid_ui()
        self._draw_main()

    def grid_colours(self):
        g = self.settings.grid
        return (f"#{g['c1'].lower()}", f"#{g['c2'].lower()}")

    def grid_line_colour(self):
        return _lighten(self.grid_colours()[1], 0.28)

    def set_ink(self, value):
        # render() silently drops anything that isn't a palette letter or an
        # RGBA 4-tuple, so a bad ink would vanish from the canvas with no error.
        # Catch it here, at the public boundary, instead.
        ok = ((isinstance(value, str) and value in LETTERS)
              or (isinstance(value, tuple) and len(value) == 4
                  and all(isinstance(n, int) for n in value)))
        if not ok:
            raise ValueError(f"ink must be a palette letter or an RGBA tuple, got {value!r}")
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

    def zoom(self, delta):
        self.zoom_level = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom_level + delta * 2))
        self._draw_main()  # previews are fixed-scale; only the main view depends on zoom

    def set_zoom(self, z, undoable=False):
        """Set the cell size in pixels. A corner-drag records the previous
        zoom so Ctrl+Z puts it back (#v2.7.0, item 15)."""
        z = max(MIN_ZOOM, min(MAX_ZOOM, int(z)))
        if z == self.zoom_level:
            return
        if undoable:
            self._view_undo.append(self.zoom_level)
        self.zoom_level = z
        self._draw_main()

    def undo(self):
        if self._painting:
            return
        if self._view_undo:
            self.zoom_level = self._view_undo.pop()
            self._draw_main()
            return
        if self.history is None:
            return
        self.history.undo()
        self._after_change()

    def redo(self):
        if self.history is None or self._painting:
            return
        self.history.redo()
        self._after_change()

    def save(self):
        """The SAVE button / Ctrl+S. Every stroke is already written the moment
        it ends, so this is the artist's reassurance more than a mechanism —
        but it is also the one save that reports failure loudly (item 1, 9)."""
        if self._selected is None:
            return False
        ok = self._save(self._selected)
        if ok:
            self._set_status("saved", flash=True)
        return ok

    def close(self):
        """Window close / Cmd+Q: finish any stroke, save everything, quit."""
        if self._painting:
            self.on_canvas_release()
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
        if not d._inside(col, row):
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
        if not self.copy_selection():
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
        if self.floating is not None:
            self.floating = None
            self._draw_overlays()
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
        if self.history is None or self.clipboard is None:
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
        """Pick the selected cells up off the drawing (one undo step) as a
        floating block, so they can be moved."""
        if self.history is None or self.selection is None:
            return False
        d = self.history.current
        c0, r0, c1, r1 = self.selection
        cells, w, h = d.region(c0, r0, c1, r1)
        self.history.begin_stroke()
        d.clear_region(c0, r0, c1, r1)
        self.history.end_stroke()
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
        self.history.begin_stroke()
        d.stamp(f["cells"], f["col"], f["row"])
        self.history.end_stroke()
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
        for c, r in self._target_cells(col, row):
            if self.tool == "erase":
                for ec, er in self._eraser_cells(c, r):
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
        if live is not self._selected:
            # undo/redo swapped `.current` to a snapshot copy; fold its content
            # back onto the object the library actually knows how to save.
            # (`kind` follows the cells automatically — it's a derived property.)
            self._selected.cells = [list(row) for row in live.cells]
        self._save(self._selected)
        self._refresh_row(self._selected)
        self._refresh_size_label()
        self._redraw()
        self._refresh_counter()
        self._refresh_colour_strip()

    def _save(self, drawing, quiet=False):
        """library.save, with the failure shown instead of lost in a traceback
        nobody reads (the macOS Documents-permission case, see fallback_dir)."""
        try:
            self.library.save(drawing)
        except OSError as exc:
            self._set_status("SAVE FAILED", error=True)
            if not quiet and not self._save_error_shown:
                self._save_error_shown = True
                messagebox.showerror(
                    "Pixel Pomo Art Kit",
                    f"Could not save '{drawing.name}':\n{exc}\n\n"
                    f"Drawings live in {self.library.root}. Check that this app is "
                    f"allowed to write there (on macOS: System Settings → Privacy & "
                    f"Security → Files and Folders).")
            return False
        self._set_status(f"saved {time.strftime('%H:%M:%S')}")
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
                                           padx=1, pady=2, font=theme.FONT_BOLD)
        self._library_toggle.pack(side="top", fill="x")
        scrollbar = theme.scrollbar(rail, "vertical")
        scrollbar.pack(side="top", fill="both", expand=True)

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
        if not hasattr(self, "_library_body"):
            return
        if self._library_collapsed:
            self._library_body.pack_forget()
            self._library_outer.configure(width=LIBRARY_RAIL)
        else:
            self._library_body.pack(side="left", fill="both", expand=True)
            self._library_outer.configure(width=LIBRARY_W)

    def _on_list_wheel(self, event):
        step = -1 if event.delta > 0 else 1
        self._list_canvas.yview_scroll(step, "units")

    # ---- labels (#v2.6.0, item 1) ---------------------------------------------
    def set_label(self, drawing, label):
        """Tag a drawing. Empty clears it. Saved at once."""
        label = (label or "").strip()
        if label == drawing.label:
            return
        drawing.label = label
        self._save(drawing)
        self._refresh_row(drawing)
        self._refresh_filter_button()
        self.apply_filter()

    def set_label_filter(self, label):
        """None shows everything, "" only unlabelled drawings, else that label."""
        self._label_filter = label
        self._refresh_filter_button()
        self.apply_filter()

    def visible_drawings(self):
        f = self._label_filter
        if f is None:
            return list(self.library.drawings)
        return [d for d in self.library.drawings if d.label == f]

    def apply_filter(self):
        """Show only the rows that match; rows are kept, just hidden."""
        if not hasattr(self, "_rows"):
            return
        wanted = {id(d) for d in self.visible_drawings()}
        for drawing in self.library.drawings:
            widgets = self._rows.get(id(drawing))
            if widgets is None:
                continue
            row = widgets["row"]
            if id(drawing) in wanted:
                row.pack(fill="x", pady=1, padx=(PAD, 2))
            else:
                row.pack_forget()
        self._list_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))

    def _refresh_filter_button(self):
        btn = getattr(self, "_filter_button", None)
        if btn is None:
            return
        f = self._label_filter
        total = len(self.library.drawings)
        if f is None:
            text = f"{t('all')}  \u00b7  {total}"
        elif f == "":
            text = f"{t('no_label')}  \u00b7  {len(self.visible_drawings())}"
        else:
            text = f"{f.upper()}  \u00b7  {len(self.visible_drawings())}"
        btn.configure(text=f"\u25be  {text}")

    def _post_filter_menu(self):
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label=f"All ({len(self.library.drawings)})",
                         command=lambda: self.set_label_filter(None))
        counts = {}
        for d in self.library.drawings:
            counts[d.label] = counts.get(d.label, 0) + 1
        for label in self.library.labels():
            menu.add_command(label=f"{label} ({counts.get(label, 0)})",
                             command=lambda l=label: self.set_label_filter(l))
        if counts.get("", 0):
            menu.add_separator()
            menu.add_command(label=f"No label ({counts['']})",
                             command=lambda: self.set_label_filter(""))
        btn = self._filter_button
        menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

    def _label_dialog(self, drawing):
        LabelDialog(self.root, drawing, self.library.labels(),
                    lambda text: self.set_label(drawing, text))

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
        vbar.configure(command=self.canvas.yview)
        hbar.configure(command=self.canvas.xview)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        for seq in theme.right_click_events():
            self.canvas.bind(seq, self._on_pick)
        self.canvas.bind("<MouseWheel>", lambda e: self.zoom(1 if e.delta > 0 else -1))
        self.canvas.bind("<Button-4>", lambda e: self.zoom(+1))   # X11 wheel
        self.canvas.bind("<Button-5>", lambda e: self.zoom(-1))
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)

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
        bottom.pack(side="bottom", fill="x", pady=(0, PAD), padx=(0, PAD))

        # --- everything else scrolls (#v2.6.0: the pane outgrew an 820px window)
        scroller = tk.Canvas(column, highlightthickness=0, bg=theme.BG, width=INNER_W)
        tbar = theme.scrollbar(column, "vertical")
        tbar.pack(side="right", fill="y")
        scroller.pack(side="left", fill="both", expand=True)
        scroller.configure(yscrollcommand=tbar.set)
        tbar.configure(command=scroller.yview)
        frame = theme.frame(scroller)
        window = scroller.create_window((0, 0), window=frame, anchor="nw", width=INNER_W)
        frame.bind("<Configure>", lambda e: scroller.configure(scrollregion=scroller.bbox("all")))
        scroller.bind("<Configure>", lambda e: scroller.itemconfigure(window, width=e.width))
        self._tools_scroller = scroller
        # Pack from the window bottom up so UPDATE/HELP sit on the bottom
        # edge and grid lines sit immediately above them (#v2.7.0, item 2).
        foot = theme.frame(bottom)
        foot.pack(side="bottom", fill="x")
        self._size_label = theme.label(foot, "", fg=theme.ON_SURFACE, cursor="hand2",
                                       font=theme.FONT_BOLD)
        self._size_label.pack(side="left")
        self._size_label.bind("<Button-1>", lambda e: self._set_size(self._selected))
        self._help_button = theme.button(foot, t("help"), self.toggle_help, padx=10)
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
        previews.pack(fill="x", pady=(0, 6))
        col1 = theme.frame(previews)
        col1.pack(side="left", anchor="s")
        theme.label(col1, "1x", dim=True).pack()
        self.preview_1x = tk.Canvas(col1, highlightthickness=0, bg=theme.BG)
        self.preview_1x.pack()
        col2 = theme.frame(previews)
        col2.pack(side="right", anchor="s")
        theme.label(col2, "squint", dim=True).pack()
        self.preview_squint = tk.Canvas(col2, highlightthickness=0, bg=theme.BG)
        self.preview_squint.pack()

        # --- top block
        save_row = theme.frame(frame)
        save_row.pack(fill="x", pady=(PAD, 2))
        self._save_button = theme.button(save_row, t("save"), self.save, bg=theme.WORK,
                                         fg=theme.ON_ACCENT, activebackground=theme.ACCENT,
                                         activeforeground=theme.ON_ACCENT)
        self._save_button.pack(side="left", fill="x", expand=True)
        self._status = theme.label(save_row, "", dim=True, anchor="e", width=14)
        self._status.pack(side="right", padx=(4, 0))

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
        self._eraser_w = self._spinbox(eraser_row, 1, MAX_SIZE, self._on_eraser_size)
        self._eraser_h = self._spinbox(eraser_row, 1, MAX_SIZE, self._on_eraser_size)
        self._eraser_cells_label = theme.label(eraser_row, t("cells"), dim=True)
        self._eraser_cells_label.pack(side="right", padx=(4, 0))
        self._eraser_h.pack(side="right", ipady=2)
        theme.label(eraser_row, "\u00d7", dim=True).pack(side="right", padx=3)
        self._eraser_w.pack(side="right", ipady=2)
        self._eraser_wh_label = theme.label(eraser_row, t("wxh"), dim=True)
        self._eraser_wh_label.pack(side="right", padx=(0, 6))
        theme.separator(frame, "horizontal").pack(fill="x", pady=(6, 2))

        # Grid colours (#v2.6.0, item 7): the two checkerboard tones. Type a
        # code, or click the swatch button for the system colour picker.
        theme.label(frame, "Grid", dim=True).pack(pady=(PAD, 0), anchor="w")
        grid_row = theme.frame(frame)
        grid_row.pack(fill="x")
        self._grid_entries = {}
        for key, caption in (("c1", "colour 1"), ("c2", "colour 2")):
            cell = theme.frame(grid_row)
            cell.pack(side="left", expand=True, fill="x", padx=(0, 4))
            theme.label(cell, caption, dim=True).pack(anchor="w")
            row = theme.frame(cell)
            row.pack(fill="x")
            entry = theme.entry(row, justify="center", width=8)
            entry.pack(side="left", fill="x", expand=True, ipady=2)
            entry.bind("<Return>", lambda e, k=key: self._on_grid_entry(k))
            entry.bind("<KP_Enter>", lambda e, k=key: self._on_grid_entry(k))
            entry.bind("<FocusOut>", lambda e, k=key: self._on_grid_entry(k))
            entry.bind("<Double-Button-1>", self._select_all_in_entry)
            theme.button(row, "\u2026", lambda k=key: self._pick_grid_colour(k), padx=6,
                         pady=2).pack(side="left", padx=(2, 0))
            self._grid_entries[key] = entry
        default_cell = theme.frame(grid_row)
        default_cell.pack(side="left", anchor="s")
        theme.label(default_cell, " ", dim=True).pack(anchor="w")
        theme.button(default_cell, "DEFAULT", self.reset_grid_colours, padx=5, pady=2).pack()

        # What the next click will paint — the one piece of state the artist
        # otherwise has to keep in their head. An Entry, so the code can be
        # copied (double-click selects it all) or typed over (item 5).
        theme.label(frame, "Ink", dim=True).pack(pady=(PAD, 0), anchor="w")
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

        theme.label(frame, "Favourite colours", dim=True).pack(pady=(PAD, 0), anchor="w")
        self._favourites = SwatchGrid(frame, INNER_W, SWATCH_COLS,
                                      on_pick=lambda h: self.set_ink(hex_to_rgba(h)),
                                      on_context=self._favourite_menu)
        self._favourites.pack(fill="x")
        self._refresh_favourites()

        theme.label(frame, "Ready colours", dim=True).pack(pady=(PAD, 0), anchor="w")
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
        from tkinter import colorchooser
        current = self.grid_colours()[0 if key == "c1" else 1]
        _rgb, hexcol = colorchooser.askcolor(color=current, parent=self.root,
                                             title=f"Grid {key[-1]}")
        if hexcol:
            self.set_grid_colours(**{key: hexcol})
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
        theme.label(frame, t("symmetry"), dim=True).pack(pady=(PAD, 0), anchor="w")
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
        theme.label(frame, "Colour", dim=True).pack(pady=(PAD, 0), anchor="w")
        self._hue = 0.0
        self._hue_strip = tk.Canvas(frame, width=PICKER_W, height=HUE_H,
                                    highlightthickness=0, cursor="crosshair", bg=theme.BG)
        self._hue_strip.pack()
        for x in range(PICKER_W):
            r, g, b = colorsys.hsv_to_rgb(x / PICKER_W, 1, 1)
            self._hue_strip.create_line(
                x, 0, x, HUE_H,
                fill=f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
        self._hue_strip.bind("<Button-1>", self._on_hue)
        self._hue_strip.bind("<B1-Motion>", self._on_hue)
        self._sv_square = tk.Canvas(frame, width=PICKER_W, height=SV_H,
                                    highlightthickness=0, cursor="crosshair", bg=theme.BG)
        self._sv_square.pack(pady=(4, 0))
        self._sv_square.bind("<Button-1>", self._on_sv)
        self._sv_square.bind("<B1-Motion>", self._on_sv)
        self._draw_sv_square()

    def _draw_sv_square(self):
        rows = []
        for y in range(SV_H):
            v = 1 - y / SV_H
            row = []
            for x in range(PICKER_W):
                r, g, b = colorsys.hsv_to_rgb(self._hue, x / PICKER_W, v)
                row.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
            rows.append("{" + " ".join(row) + "}")
        # Kept on self: the canvas shows the image only while a reference lives.
        self._sv_image = tk.PhotoImage(width=PICKER_W, height=SV_H)
        self._sv_image.put(" ".join(rows))
        self._sv_square.delete("all")
        self._sv_square.create_image(0, 0, image=self._sv_image, anchor="nw")

    def _on_hue(self, event):
        self._hue = min(1.0, max(0.0, event.x / PICKER_W))
        self._draw_sv_square()

    def _on_sv(self, event):
        s = min(1.0, max(0.0, event.x / PICKER_W))
        v = min(1.0, max(0.0, 1 - event.y / SV_H))
        r, g, b = colorsys.hsv_to_rgb(self._hue, s, v)
        self.set_ink((int(r * 255), int(g * 255), int(b * 255), 255))

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
        if self._hit_zoom_handle(event):
            self._zoom_drag = self.zoom_level
            return
        self.on_canvas_press(*self._grid_at(event))

    def _on_drag(self, event):
        if self._zoom_drag is not None:
            self._drag_zoom(event)
            return
        self._autoscroll(event)
        self.on_canvas_drag(*self._grid_at(event))

    def _on_release(self, event):
        if self._zoom_drag is not None:
            start = self._zoom_drag
            self._zoom_drag = None
            if self.zoom_level != start:
                self._view_undo.append(start)
            return
        self.on_canvas_release()

    def _hit_zoom_handle(self, event):
        if self.history is None:
            return False
        d = self.history.current
        z = self.zoom_level
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        hx, hy = d.width * z, d.height * z
        return (hx - ZOOM_HANDLE <= x <= hx + ZOOM_HANDLE
                and hy - ZOOM_HANDLE <= y <= hy + ZOOM_HANDLE)

    def _drag_zoom(self, event):
        d = self.history.current
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        z = int(round(min(x / max(1, d.width), y / max(1, d.height))))
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if z != self.zoom_level:
            self.zoom_level = z
            self._draw_main()

    def _autoscroll(self, event):
        """Dragging against the edge of the visible area scrolls the canvas
        that way, one cell at a time (#v2.6.0, item 6) — so a line can be
        continued past the edge while zoomed in, without letting go."""
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 40 or h < 40:
            return
        if event.x < AUTOSCROLL_MARGIN:
            self.canvas.xview_scroll(-1, "units")
        elif event.x > w - AUTOSCROLL_MARGIN:
            self.canvas.xview_scroll(1, "units")
        if event.y < AUTOSCROLL_MARGIN:
            self.canvas.yview_scroll(-1, "units")
        elif event.y > h - AUTOSCROLL_MARGIN:
            self.canvas.yview_scroll(1, "units")

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
        z = self.zoom_level
        if self._placing_bar:
            ghost = symmetry.Bar(self._sym_orientation, self._sym_length, col, row)
            self._draw_bar(ghost, tag="ghost", colour=theme.ON_DIM)
        elif self.tool == "erase" and self.eraser_size != (1, 1) and not self._painting:
            self._ghost_cells(self._eraser_cells(col, row), z)
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
        if self._hit_zoom_handle(event):
            self.canvas.configure(cursor="bottom_right_corner")
            return
        self.canvas.configure(cursor="")

    def _ghost_cells(self, cells, z):
        x0, y0 = min(c for c, _ in cells) * z, min(r for _, r in cells) * z
        x1, y1 = (max(c for c, _ in cells) + 1) * z, (max(r for _, r in cells) + 1) * z
        self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=theme.ON_DIM,
                                     width=1, tags="ghost")

    # ---- the strip under the canvas (#v2.6.0, items 2 and 5) --------------------
    def _refresh_counter(self):
        label = getattr(self, "_counter_label", None)
        if label is None:
            return
        if self.history is None:
            label.configure(text="")
            return
        d = self.history.current
        parts = [t("empty_pixels", n=d.empty_count()), t("pixels", n=d.count())]
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
            colour = "empty"
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
        counts = {}
        palette = d.palette.colors()
        for line in d.cells:
            for cell in line:
                if cell is None:
                    continue
                rgba = palette[cell] if isinstance(cell, str) else cell
                key = _hex(rgba)[1:].upper()
                counts[key] = counts.get(key, 0) + 1
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
        if self.settings.add_favourite(hexcode):
            self._refresh_favourites()
            self._set_status("added to favourites", flash=True)
        else:
            self._set_status("already a favourite", flash=True)

    def remove_favourite(self, hexcode):
        if self.settings.remove_favourite(hexcode):
            self._refresh_favourites()

    def _favourite_menu(self, hexcode, event):
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label=f"Use #{hexcode}", command=lambda: self.set_ink(hex_to_rgba(hexcode)))
        menu.add_command(label="Remove from favourites", command=lambda: self.remove_favourite(hexcode))
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

        menu = tk.Menu(row, tearoff=False)
        menu.add_command(label=t("duplicate"), command=lambda: self._duplicate(drawing))
        menu.add_command(label=t("export_png"), command=lambda: self._export_png(drawing))
        menu.add_command(label=t("export_png_grid"),
                         command=lambda: self._export_png(drawing, grid=True))
        menu.add_command(label=t("export_svg"), command=lambda: self._export_svg(drawing))
        menu.add_command(label=t("export_svg_grid"),
                         command=lambda: self._export_svg(drawing, grid=True))
        menu.add_command(label=t("export_jpg"), command=lambda: self._export_jpg(drawing))
        menu.add_command(label=t("export_json"), command=lambda: self._export_json(drawing))
        menu.add_command(label=t("export_engine"),
                         command=lambda: self._export_engine_sprite(drawing))
        menu.add_separator()
        menu.add_command(label=t("rename"), command=lambda: self._rename(drawing))
        menu.add_command(label=t("label"), command=lambda: self._label_dialog(drawing))
        menu.add_command(label=t("size"), command=lambda: self._set_size(drawing))
        menu.add_separator()
        menu.add_command(label=t("delete"), command=lambda: self._delete(drawing))
        menu_btn = theme.button(row, "\u22ee", None, bg=bg, activebackground=theme.PANEL_HI,
                                padx=6, pady=2)
        menu_btn.configure(command=lambda: menu.tk_popup(
            menu_btn.winfo_rootx(), menu_btn.winfo_rooty() + menu_btn.winfo_height()))
        menu_btn.pack(side="right", padx=(0, 4))
        # The label chip, left of ⋮ (#v2.6.0): click it to change the label.
        chip = theme.button(row, "", lambda: self._label_dialog(drawing), bg=bg,
                            fg=theme.ON_DIM, activebackground=theme.PANEL_HI, font=theme.FONT_SMALL,
                            padx=4, pady=2)
        chip.pack(side="right")
        label.pack(side="left", fill="x", expand=True)

        for widget in (row, label, thumb):
            widget.bind("<Button-1>", lambda e: self.select(drawing))
            widget.bind("<MouseWheel>", self._on_list_wheel)
        self._rows[id(drawing)] = {"row": row, "thumb": thumb, "label": label, "menu": menu_btn,
                                   "chip": chip}
        self._refresh_row(drawing)

    def _refresh_row(self, drawing):
        """Redraw one row's thumbnail and name — the per-stroke cost, in
        place of rebuilding the whole list."""
        widgets = self._rows.get(id(drawing))
        if widgets is None:
            return
        grid = engine_io.render(drawing)
        scale = raster.fit_scale(grid, THUMB_PX, 2)
        img = raster.photo(grid, scale, master=self.root)
        self._images[("thumb", id(drawing))] = img
        widgets["thumb"].configure(image=img)
        widgets["label"].configure(text=drawing.name)
        widgets["chip"].configure(text=drawing.label or "\u2013",
                                  fg=theme.WORK if drawing.label else theme.ON_DIM)

    def _highlight_row(self, drawing, selected):
        widgets = self._rows.get(id(drawing))
        if widgets is None:
            return
        bg = ROW_BG_SELECTED if selected else ROW_BG
        for key in ("row", "thumb", "label", "menu", "chip"):
            widgets[key].configure(bg=bg)
        widgets["menu"].configure(highlightbackground=bg)
        widgets["chip"].configure(highlightbackground=bg)
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
        cols = max(1, min(MAX_SIZE, int(cols)))
        rows = max(1, min(MAX_SIZE, int(rows)))
        base = self._selected or (self.library.drawings[0] if self.library.drawings else None)
        if base is not None:
            palette, species, model = base.palette, base.species, base.model
        else:
            palette = Palette(d="2E2E2E", m="6E6E6E", l="B0B0B0", centre="F2C94C", rim="1A1A1A")
            species, model = "", 0
        # A new drawing takes the label being filtered on, or the open one's.
        label = self._label_filter if self._label_filter else (base.label if base else "")
        drawing = Drawing.blank(cols, rows, palette, species=species, model=model, label=label)
        self.library.add(drawing)
        self._add_row(drawing)
        self.select(drawing)
        return drawing

    def _add_row(self, drawing):
        """A row for a drawing that just joined the library; if the current
        filter would hide it, the filter is dropped — a drawing the artist
        just made must not vanish."""
        self._build_row(drawing)
        if self._label_filter is not None and drawing.label != self._label_filter:
            self.set_label_filter(None)
        else:
            self.apply_filter()
            self._refresh_filter_button()

    def _new_drawing(self):
        """Older name, kept: a default-size blank drawing, no dialog."""
        return self.new_drawing()

    def _new_drawing_dialog(self):
        SizeDialog(self.root, "New drawing", (NEW_SIZE, NEW_SIZE), size_presets(),
                   self.new_drawing, verb="CREATE")

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
            parent=self.root, title="Import PNG",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")])
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
        messagebox.showinfo("Pixel Pomo Art Kit", "Imported into the library:\n\n" + "\n".join(report),
                            parent=self.root)

    def _duplicate(self, drawing):
        clone = self.library.duplicate(drawing)
        self._add_row(clone)
        self.select(clone)

    def _rename(self, drawing):
        name = simpledialog.askstring(
            "Pixel Pomo Art Kit", "New name:", initialvalue=drawing.name, parent=self.root)
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
        SizeDialog(self.root, f"Resize \u2014 {drawing.name}", (d.width, d.height),
                   size_presets(), self.resize, verb="RESIZE")

    def resize(self, cols, rows):
        """Change the open drawing's size as ONE undoable stroke."""
        if self.history is None:
            return
        d = self.history.current
        cols = max(1, min(MAX_SIZE, int(cols)))
        rows = max(1, min(MAX_SIZE, int(rows)))
        if (cols, rows) == (d.width, d.height):
            return
        # A resize is a stroke: one undo puts the cropped cells back.
        self.history.begin_stroke()
        d.resize(cols, rows)
        self.history.end_stroke()
        self._after_change()
        self.zoom_to_fit()

    def _delete(self, drawing):
        if not messagebox.askyesno(
                "Pixel Pomo Art Kit", f"Delete '{drawing.name}'? This cannot be undone."):
            return
        was_selected = drawing is self._selected
        self.library.remove(drawing)
        self._histories.pop(id(drawing), None)
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

    # ---- export ------------------------------------------------------
    def _export_png(self, drawing, grid=False):
        suffix = " (grid)" if grid else ""
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export PNG with grid" if grid else "Export PNG",
            defaultextension=".png", initialfile=f"{drawing.name}{suffix}.png",
            filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            engine_io.export_png(drawing, path, grid=self.grid_line_colour() if grid else None)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))

    def _export_svg(self, drawing, grid=False):
        """Vector export: one rect per cell, sharp at any zoom (#v2.7.0)."""
        path = filedialog.asksaveasfilename(
            parent=self.root, title=t("export_svg_grid") if grid else t("export_svg"),
            defaultextension=".svg", initialfile=f"{drawing.name}.svg",
            filetypes=[("SVG vector", "*.svg")])
        if not path:
            return
        try:
            engine_io.export_svg(drawing, path, grid=self.grid_line_colour() if grid else None)
        except (engine_io.ExportRefused, OSError) as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))
            return
        self._set_status(f"exported {Path(path).name}", flash=True)

    def _export_json(self, drawing):
        """The kit's own drawing file — this is what the library stores, and
        what survives an update. Engine sprites are PNG; the game does not
        read these JSON files (#v2.7.0, item 14)."""
        path = filedialog.asksaveasfilename(
            parent=self.root, title=t("export_json"),
            defaultextension=".json", initialfile=f"{drawing.name}.json",
            filetypes=[("Pixel Pomo drawing", "*.json")])
        if not path:
            return
        try:
            store.save(drawing, Path(path))
        except OSError as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))
            return
        self._set_status(f"exported {Path(path).name}", flash=True)

    def _export_jpg(self, drawing):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export JPG", defaultextension=".jpg",
            initialfile=f"{drawing.name}.jpg", filetypes=[("JPEG image", "*.jpg")])
        if not path:
            return
        try:
            engine_io.export_jpg(drawing, path)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))

    def _export_engine_sprite(self, drawing):
        """The x16 engine-scale sprite, any size, to a file the artist names
        (#v2.6.0, items 4 and 10). One ordinary save dialog: the name is
        editable there, and "replace?" is the system's own question — no
        second confirmation, no 16-wide refusal. Sizing and naming a sprite
        for the garden is the developer's job afterwards, as with palettes."""
        folder = engine_sprite_dir()
        folder.mkdir(parents=True, exist_ok=True)  # so the picker opens somewhere real
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export engine sprite (x16)", defaultextension=".png",
            initialdir=str(folder), initialfile=engine_io.suggested_sprite_name(drawing),
            filetypes=[("PNG sprite", "*.png")])
        if not path:
            return
        try:
            written = engine_io.export_sprite(drawing, path)
        except (engine_io.ExportRefused, OSError) as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))
            return
        self._set_status(f"exported {Path(written).name}", flash=True)

    # ---- drawing --------------------------------------------------------
    def _redraw(self):
        self._draw_main()
        self._draw_previews()

    def _draw_main(self):
        self.canvas.delete("all")
        if self.history is None:
            return
        drawing = self.history.current
        z = self.zoom_level
        w, h = drawing.width, drawing.height
        self._draw_checker(self.canvas, w * z, h * z)
        grid = engine_io.render(drawing)
        img = raster.photo(grid, z, master=self.root)
        self._images["main"] = img
        self.canvas.create_image(0, 0, image=img, anchor="nw", tags="art")
        if z >= 8 and self.show_grid:
            self._draw_grid_lines(w, h, z)
        bar = self._active_bar()
        if bar is not None:
            self._draw_bar(bar, tag="symmetry", colour=theme.ACCENT)
        self._draw_zoom_handle(w, h, z)
        self._draw_overlays()
        # one scroll "unit" is one cell, for the edge auto-scroll while dragging
        self.canvas.configure(scrollregion=(0, 0, w * z, h * z),
                              xscrollincrement=z, yscrollincrement=z)

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
            img = raster.photo(grid, z, master=self.root)
            self._images["floating"] = img
            x0, y0 = f["col"] * z, f["row"] * z
            self.canvas.create_image(x0, y0, image=img, anchor="nw", tags="floating")
            self.canvas.create_rectangle(x0, y0, x0 + f["w"] * z, y0 + f["h"] * z,
                                         outline=theme.ACCENT, width=2, dash=(6, 3), tags="floating")
        if self.selection is not None:
            c0, r0, c1, r1 = self.selection
            self.canvas.create_rectangle(c0 * z + 1, r0 * z + 1, (c1 + 1) * z - 1, (r1 + 1) * z - 1,
                                         outline=theme.WORK, width=2, dash=(6, 3), tags="selection")

    def _checker_at(self, x0, y0, wpx, hpx):
        """Which of the two checker tones sits under pixel (x0, y0)."""
        cols = rows = 10
        rx, ry = x0 * cols // max(1, wpx), y0 * rows // max(1, hpx)
        return self.grid_colours()[(rx + ry) % 2]

    def _paint_fast(self):
        """Mid-stroke: paint only the cells this event touched, as rectangles
        over the image, instead of re-rendering the whole drawing. The full
        render happens once, at release. (A letter ink shows its palette
        colour here without the engine's rim — that appears on release.)"""
        if not self._stroke_cells:
            return
        z = self.zoom_level
        d = self.history.current
        wpx, hpx = d.width * z, d.height * z
        if self.tool == "erase":
            fill = None
        else:
            fill = _hex(self.ink_rgba())
        for c, r in self._stroke_cells:
            if not d._inside(c, r):
                continue
            x0, y0 = c * z, r * z
            colour = fill or self._checker_at(x0, y0, wpx, hpx)
            self.canvas.create_rectangle(x0, y0, x0 + z, y0 + z, fill=colour,
                                         outline="", tags="stroke")
        # keep grid lines and the bar above the fresh cells
        self.canvas.tag_raise("grid")
        self.canvas.tag_raise("symmetry")
        self._stroke_cells = []

    def _draw_previews(self):
        self.preview_1x.delete("all")
        self.preview_squint.delete("all")
        if self.history is None:
            self.preview_1x.configure(width=1, height=1)
            self.preview_squint.configure(width=1, height=1)
            return
        grid = engine_io.render(self.history.current)
        h, w = len(grid), len(grid[0])
        one = raster.photo(grid, 1, master=self.root)
        squint_scale = raster.fit_scale(grid, INNER_W - 72, PREVIEW_ZOOM)
        squint = raster.photo(grid, squint_scale, master=self.root)
        self._images["preview_1x"], self._images["preview_squint"] = one, squint
        self.preview_1x.configure(width=w, height=h)
        self.preview_1x.create_image(0, 0, image=one, anchor="nw")
        self.preview_squint.configure(width=w * squint_scale, height=h * squint_scale)
        self.preview_squint.create_image(0, 0, image=squint, anchor="nw")

    def _draw_checker(self, canvas, width, height):
        # A fixed 10x10 grid of squares, however big the canvas is - a bounded
        # number of items so redrawing on every zoom tick stays cheap, rather
        # than a fixed square SIZE whose item count grows with zoom^2.
        #
        # Edges are integer partitions of the full width/height (#v2.6.0):
        # the old `width // cols` block size left an unpainted strip along the
        # right and bottom whenever the size was not a multiple of ten — the
        # "grid does not cover the corners" the artists saw.
        cols = rows = 10
        tones = self.grid_colours()
        for ry in range(rows):
            y0, y1 = ry * height // rows, (ry + 1) * height // rows
            for rx in range(cols):
                x0, x1 = rx * width // cols, (rx + 1) * width // cols
                canvas.create_rectangle(x0, y0, x1, y1, fill=tones[(rx + ry) % 2], outline="",
                                        tags="checker")

    def _draw_grid_lines(self, width, height, z):
        # The last line is pulled one pixel in, or it falls on the far side
        # of the scroll region and is never seen (#v2.6.0).
        colour = self.grid_line_colour()
        wpx, hpx = width * z, height * z
        for c in range(width + 1):
            x = min(c * z, wpx - 1)
            self.canvas.create_line(x, 0, x, hpx, fill=colour, tags="grid")
        for r in range(height + 1):
            y = min(r * z, hpx - 1)
            self.canvas.create_line(0, y, wpx, y, fill=colour, tags="grid")

    def _draw_bar(self, bar, tag, colour):
        """A bright line sitting on a grid edge, between cells (#v2.7.0)."""
        z = self.zoom_level
        first, last = bar.span()
        if bar.orientation == symmetry.VERTICAL:
            x = bar.col * z
            y0, y1 = first * z, (last + 1) * z
            self.canvas.create_line(x, y0, x, y1, fill=colour, width=2, tags=tag)
        else:
            y = bar.row * z
            x0, x1 = first * z, (last + 1) * z
            self.canvas.create_line(x0, y, x1, y, fill=colour, width=2, tags=tag)

    def _draw_zoom_handle(self, w, h, z):
        """The grab at the drawing's bottom-right corner (#v2.7.0, item 15)."""
        x, y = w * z, h * z
        s = 8
        self.canvas.create_polygon(x, y - s, x, y, x - s, y, fill=theme.ACCENT,
                                   outline=theme.ON_ACCENT, tags="zoomhandle")

    # ---- help (item 15) -------------------------------------------------------
    def toggle_help(self):
        if self._help is not None:
            self._help.destroy()
            self._help = None
            return
        self._help = HelpOverlay(self.root, self.toggle_help, self.library.root.parent)

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
        menu = tk.Menu(self.root, tearoff=False)
        current = i18n.language()
        for code in i18n.LANGS:
            label = i18n.NAMES[code]
            if code == current:
                label = f"\u2713  {label}"
            menu.add_command(label=label, command=lambda c=code: self.set_language(c))
        btn = self._lang_button
        menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

    def set_language(self, code):
        code = i18n.set_language(code)
        self.settings.language = code
        self._apply_language()

    def _apply_language(self):
        """Retext chrome without rebuilding (box sizes stay, fonts shrink)."""
        font = i18n.font_for
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
        ]
        for btn, key in pairs:
            if btn is None:
                continue
            btn.configure(text=t(key), font=font(key))
        for label, key in (
                (getattr(self, "_eraser_label", None), "eraser"),
                (getattr(self, "_eraser_cells_label", None), "cells"),
                (getattr(self, "_eraser_wh_label", None), "wxh"),
                (getattr(self, "_sym_length_label", None), "length"),
        ):
            if label is not None:
                label.configure(text=t(key))
        self._refresh_filter_button()
        self._refresh_symmetry_ui()
        self._refresh_tool_buttons()
        self._refresh_grid_ui()
        self._refresh_counter()
        if self._help is not None:
            self.toggle_help()
            self.toggle_help()

    def _set_status(self, text, flash=False, error=False):
        status = getattr(self, "_status", None)
        if status is None:
            return
        status.configure(text=text, fg=theme.BREAK if error else (theme.ACCENT if flash else theme.ON_DIM))
        if flash:
            self.root.after(1500, lambda: status.configure(fg=theme.ON_DIM))


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
    item 2). When they overflow, `< >` after the ellipsis pages the rest
    (#v2.7.0, item 9)."""

    SWATCH, GAP, H = 16, 6, 30
    ARROW_W = 16

    def __init__(self, parent, on_pick):
        super().__init__(parent, height=self.H, highlightthickness=0, bg=theme.BG, cursor="hand2")
        self._on_pick = on_pick
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
        # reserve room for `... < >` if anything is clipped
        x = 0
        shown = 0
        last_fit = offset
        for i in range(offset, len(items)):
            hexcode, count = items[i]
            text = f"#{hexcode.lower()} \u00b7 {count}"
            approx = self.SWATCH + 4 + 7 * len(text) + self.GAP
            room = width - (self.ARROW_W * 2 + 18 if (more_before or i < len(items) - 1) else 0)
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
            x += 12
            prev_x = x
            self.create_text(x, self.H // 2, text="\u2039", fill=theme.ACCENT if more_before else theme.ON_DIM,
                             anchor="w", font=theme.FONT_BOLD)
            self._hits.append((prev_x, prev_x + self.ARROW_W, "prev"))
            x += self.ARROW_W
            next_x = x
            self.create_text(x, self.H // 2, text="\u203a", fill=theme.ACCENT if more_after else theme.ON_DIM,
                             anchor="w", font=theme.FONT_BOLD)
            self._hits.append((next_x, next_x + self.ARROW_W, "next"))

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


class LabelDialog(tk.Toplevel):
    """Pick or type a label for one drawing (#v2.6.0, item 1)."""

    def __init__(self, parent, drawing, existing, on_ok):
        super().__init__(parent, bg=theme.BG)
        self.title(f"Label \u2014 {drawing.name}")
        self.transient(parent)
        self.resizable(False, False)
        theme.dark_title_bar(self)
        self._on_ok = on_ok
        body = theme.frame(self)
        body.pack(padx=16, pady=12)
        theme.label(body, f"Label for {drawing.name}", font=theme.FONT_BOLD).pack(anchor="w")
        theme.label(body, "Pick one in use, or type a new one. Labels filter the library.",
                    dim=True).pack(anchor="w", pady=(0, 8))
        if existing:
            grid = theme.frame(body)
            grid.pack(fill="x")
            for i, label in enumerate(existing):
                btn = theme.button(grid, label, lambda l=label: self._finish(l), pady=4)
                btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
                if label == drawing.label:
                    theme.set_pressed(btn, True)
            for c in range(3):
                grid.grid_columnconfigure(c, weight=1)
        row = theme.frame(body)
        row.pack(fill="x", pady=(10, 0))
        theme.label(row, "New", dim=True).pack(side="left")
        self._entry = theme.entry(row, width=18)
        self._entry.insert(0, drawing.label)
        self._entry.pack(side="left", padx=(8, 0), ipady=2, fill="x", expand=True)
        buttons = theme.frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        theme.button(buttons, "CANCEL", self.destroy).pack(side="right")
        theme.button(buttons, "NO LABEL", lambda: self._finish("")).pack(side="right", padx=(0, 6))
        theme.button(buttons, "APPLY", lambda: self._finish(self._entry.get()), bg=theme.WORK,
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
        self.grab_set()

    def _finish(self, text):
        self.destroy()
        self._on_ok(text)


class SizeDialog(tk.Toplevel):
    """New drawing / resize: preset sizes the engine actually uses, or a
    custom width x height (item 13). Calls `on_ok(cols, rows)`."""

    def __init__(self, parent, title, initial, presets, on_ok, verb="OK"):
        super().__init__(parent, bg=theme.BG)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        theme.dark_title_bar(self)
        self._on_ok = on_ok
        body = theme.frame(self)
        body.pack(padx=16, pady=12)
        theme.label(body, title, font=theme.FONT_BOLD).pack(anchor="w")
        theme.label(body, "Pick a size the garden uses, or type your own.", dim=True).pack(
            anchor="w", pady=(0, 8))

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
        theme.label(custom, "Custom", dim=True).pack(side="left")
        self._cols_entry = theme.entry(custom, width=4, justify="center")
        self._cols_entry.insert(0, str(initial[0]))
        self._cols_entry.pack(side="left", padx=(8, 2), ipady=2)
        theme.label(custom, "\u00d7").pack(side="left")
        self._rows_entry = theme.entry(custom, width=4, justify="center")
        self._rows_entry.insert(0, str(initial[1]))
        self._rows_entry.pack(side="left", padx=(2, 8), ipady=2)
        theme.label(custom, f"1\u2013{MAX_SIZE} cells", dim=True).pack(side="left")

        buttons = theme.frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        theme.button(buttons, "CANCEL", self.destroy).pack(side="right")
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
        self.grab_set()

    def _custom(self):
        try:
            cols, rows = int(self._cols_entry.get()), int(self._rows_entry.get())
        except ValueError:
            self.bell()
            return
        if not (1 <= cols <= MAX_SIZE and 1 <= rows <= MAX_SIZE):
            self.bell()
            return
        self._finish(cols, rows)

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
    ("Eraser W × H", "how many cells the eraser clears at once, centred on the pointer"),
    ("Grid colour 1 / 2", "the two checkerboard tones behind the art — type a code, … opens a colour "
                          "picker, DEFAULT puts the matcha tones back"),
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
    ("WITH / WITHOUT GRID", "show or hide the cell lines over the drawing \u2014 sits just above UPDATE / HELP"),
    ("LANGUAGE", "English / T\u00fcrk\u00e7e / Polski / Deutsch. Button boxes keep their size; type shrinks if needed"),
    ("\u2630 (library)", "collapses the drawing list to the rail; click again to expand. Sits above the scrollbar, aligned with ALL"),
    ("Under the canvas", "empty-pixel count, painted-pixel count, the colours in the drawing "
                         "(click one to use it; \u2039 \u203a pages overflow), the cell and colour under the cursor"),
    ("1x / squint", "the drawing at real size, and at squint-test distance"),
    ("W \u00d7 H", "the drawing's size \u2014 click it to resize. Drag the bottom-right corner of the "
              "drawing to enlarge on-screen pixels; {mod}+Z undoes that zoom"),
    ("UPDATE", "checks GitHub for a newer kit. Windows updates itself (your drawings are untouched, and "
               "backed up first); macOS opens the download page"),
    ("+ NEW DRAWING", "a blank drawing at a garden size: flower 16\u00d716, bug 8\u00d78, bush, rock, tree, or custom"),
    ("IMPORT PNG…", "bring in art from Procreate/Aseprite/anything; it is saved into the library at once"),
    ("▾ ALL (top left)", "filter the library by label (flower / tree / bush / rock / bugs / \u2026)"),
    ("label chip", "left of \u22ee on each row: click to change that drawing's label"),
    ("\u22ee", "Duplicate, Export PNG / SVG (vector, sharp at any zoom) / JPG / JSON "
          "(the kit drawing file \u2014 what the library stores and what survives an update) / "
          "engine sprite (PNG the garden loads, x16), Rename, Label, Size, Delete"),
    ("JSON vs PNG", "the library is JSON in your data folder. An update replaces the program only. "
                    "Export engine sprite writes the PNG the game draws. Export SVG for sharing without "
                    "pixelation. Export JSON to send a drawing to another kit."),
    ("", None),
    ("KEYBOARD", None),
    ("{mod}+S", "save"),
    ("{mod}+Z / {mod}+Y", "undo / redo  ({mod}+Shift+Z also redoes). Corner-zoom undoes first"),
    ("{mod}+N", "new drawing"),
    ("B / E / F / S", "brush / eraser / fill / select"),
    ("{mod}+C / X / V", "copy / cut / paste \u2014 after copy, click a cell to paste there"),
    ("Enter \u00b7 Delete \u00b7 Esc \u00b7 arrows", "drop the floating block \u00b7 clear the selection \u00b7 dismiss selection \u00b7 nudge the block"),
    ("M", "symmetry: OFF → MIRROR → STICK"),
    ("+ / −  or mouse wheel", "zoom in / out"),
    ("Right-click on the canvas", "eyedropper: the colour under the cursor becomes the ink"),
    ("F1 / Esc", "open / close this help"),
]


class HelpOverlay(tk.Frame):
    """Every button and key, on a panel over the main window; × or Esc closes
    it (item 15)."""

    def __init__(self, parent, on_close, data_dir=None):
        super().__init__(parent, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.ACCENT)
        self.place(relx=0.5, rely=0.5, anchor="center")
        head = theme.frame(self, bg=theme.PANEL)
        head.pack(fill="x", padx=14, pady=(10, 4))
        theme.label(head, f"Pixel Pomo Art Kit v{VERSION} \u2014 help", bg=theme.PANEL,
                    font=theme.FONT_BOLD).pack(side="left")
        theme.button(head, "\u00d7", on_close, padx=8, pady=0, font=theme.FONT_BOLD,
                     bg=theme.PANEL, activebackground=theme.PANEL_HI).pack(side="right")
        if data_dir is not None:
            # Where the work is — so nobody hunts for it beside the program.
            # Packed before the body, at the bottom, so it is always visible
            # however long the list above gets.
            foot = theme.frame(self, bg=theme.PANEL)
            foot.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
            theme.label(foot, "Your drawings:", bg=theme.PANEL, fg=theme.ACCENT,
                        font=theme.FONT_BOLD).pack(side="left")
            theme.label(foot, str(data_dir), bg=theme.PANEL, font=theme.FONT_MONO,
                        fg=theme.WORK).pack(side="left", padx=(8, 8))
            theme.button(foot, "OPEN FOLDER", lambda: paths.open_in_file_manager(data_dir),
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
        r = 0
        for key, text in HELP_TEXT:
            key = key.replace("{mod}", mod)
            if text is None:
                if key:
                    theme.label(body, key, bg=theme.PANEL, fg=theme.ACCENT,
                                font=theme.FONT_BOLD).grid(row=r, column=0, columnspan=2,
                                                            sticky="w", pady=(6, 2))
                else:
                    theme.frame(body, bg=theme.PANEL, height=4).grid(row=r, column=0)
            else:
                theme.label(body, key, bg=theme.PANEL, font=theme.FONT_MONO,
                            fg=theme.WORK).grid(row=r, column=0, sticky="nw", padx=(0, 12))
                theme.label(body, text.replace("{mod}", mod), bg=theme.PANEL,
                            justify="left", wraplength=520).grid(row=r, column=1, sticky="w")
            r += 1
        for child in body.winfo_children():
            child.bind("<MouseWheel>",
                       lambda e: scroller.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        _fit()
        self.lift()
