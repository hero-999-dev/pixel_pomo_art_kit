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
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path

from art_kit import branding, engine_io, raster, symmetry, theme
from art_kit.model import Drawing, History, LETTERS, Palette, hex_to_rgba
from art_kit.settings import Settings

MIN_ZOOM, MAX_ZOOM = 4, 48
DEFAULT_ZOOM = 20
CHECKER = theme.CHECKER
PREVIEW_ZOOM = 8  # the fixed "squint test" scale, independent of the editing zoom
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
TOOLS_W = 268
PAD = 8
INNER_W = TOOLS_W - 2 * PAD - 1  # minus the separator line
SWATCH_COLS = 6
PICKER_W, SV_H, HUE_H = INNER_W, 120, 14
LIBRARY_W = 220

NEW_SIZE = 32  # new drawings: room for the trees and pets that are coming
MAX_SIZE = 64


def base_dir():
    """Where the app keeps `library/` and `exports/`.

    - Frozen on **macOS**: `~/Documents/PixelPomoArtKit/`.
    - Frozen on **Windows**: beside the .exe.
    - From source: the repo root.

    A onefile build unpacks its code to a temp dir, so `__file__` is never a
    place to write — hence `sys.executable` when frozen.

    macOS is the exception on purpose (#v2.1.0). There `sys.executable` lives at
    `PixelPomoArtKit.app/Contents/MacOS/`, i.e. INSIDE the bundle, which would
    put the artist's drawings somewhere Finder hides behind "Show Package
    Contents" — and, worse, dragging a new version over the old .app would
    delete every one of them. Gatekeeper's app translocation can also run a
    freshly-downloaded bundle from a randomised read-only path, so writing next
    to it is not even reliable. `~/Documents` is visible, stable, and survives
    replacing the app.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return Path.home() / "Documents" / "PixelPomoArtKit"
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


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


# Where the export dialog opens. Deliberately NOT the game's asset folder:
# pixel_pomo is read-only to this app, and defaulting there risks overwriting a
# shipped flower_*.png (the very files the byte-equality tests trust). The
# artist browses over by hand if they really mean to update the game.
ENGINE_SPRITE_DIR = base_dir() / "exports"


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
    flower_h = len(g._FLOWER_BLOOMS["lale"][0])
    presets = [("Flower", 16, flower_h), ("Bush", 16, 16), ("Rock", 16, 16)]
    for tiles in sorted(set(g.TREE_TILES)):
        px = tiles * g.TREE_PX_PER_TILE
        presets.append((f"Tree \u00b7 {tiles} tiles", px, px))
    return presets


class ArtKitApp:
    def __init__(self, root, library, settings=None):
        self.root = root
        self.library = library
        self.settings = settings or Settings(library.root.parent / "settings.json")
        self.tool = self.settings.tool if self.settings.tool in ("draw", "erase", "fill") else "draw"
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
        # symmetry (item 14)
        sym = self.settings.symmetry
        self.symmetry_on = False
        self.symmetry_bar = None
        self._sym_orientation = sym.get("orientation", symmetry.VERTICAL)
        self._sym_length = int(sym.get("length", 5))
        self._placing_bar = False
        self._help = None

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

    # ---- state ---------------------------------------------------------
    def select(self, drawing):
        previous = self._selected
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
        if name not in ("draw", "erase", "fill"):
            raise ValueError(f"tool must be 'draw', 'erase' or 'fill', got {name!r}")
        self.tool = name
        self.settings.tool = name  # the last tool used is the one selected next time (item 12)
        self._refresh_tool_buttons()

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

    def undo(self):
        if self.history is None or self._painting:
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

    # ---- symmetry (item 14) -----------------------------------------------
    def set_symmetry(self, on):
        self.symmetry_on = bool(on)
        # Switching it on with no bar placed arms placement: the next canvas
        # click puts the bar there instead of painting.
        self._placing_bar = self.symmetry_on and self.symmetry_bar is None
        self._refresh_symmetry_ui()
        self._draw_main()

    def arm_symmetry_placement(self):
        if self.symmetry_on:
            self._placing_bar = True
            self._refresh_symmetry_ui()

    def set_symmetry_orientation(self, orientation):
        if orientation not in symmetry.ORIENTATIONS:
            raise ValueError(orientation)
        self._sym_orientation = orientation
        if self.symmetry_bar is not None:
            self.symmetry_bar = symmetry.Bar(orientation, self._sym_length,
                                             self.symmetry_bar.col, self.symmetry_bar.row)
        self.settings.set_symmetry(self._sym_orientation, self._sym_length)
        self._refresh_symmetry_ui()
        self._draw_main()

    def set_symmetry_length(self, length):
        length = max(symmetry.MIN_LENGTH, min(symmetry.MAX_LENGTH, int(length)))
        self._sym_length = length
        if self.symmetry_bar is not None:
            self.symmetry_bar = symmetry.Bar(self._sym_orientation, length,
                                             self.symmetry_bar.col, self.symmetry_bar.row)
        self.settings.set_symmetry(self._sym_orientation, self._sym_length)
        self._refresh_symmetry_ui()
        self._draw_main()

    def place_symmetry_bar(self, col, row):
        self.symmetry_bar = symmetry.Bar(self._sym_orientation, self._sym_length, col, row)
        self._placing_bar = False
        self._refresh_symmetry_ui()
        self._draw_main()

    def _active_bar(self):
        return self.symmetry_bar if self.symmetry_on else None

    # ---- pointer, in GRID coordinates ----------------------------------
    def on_canvas_press(self, col, row):
        if self.history is None:
            return
        if self._placing_bar:
            self.place_symmetry_bar(col, row)
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
        if not self._painting:
            return
        self._painting = False
        self._last_cell = None
        self.history.end_stroke()
        self._after_change()

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

    def _apply(self, col, row):
        drawing = self.history.current
        for c, r in symmetry.expand(self._active_bar(), [(col, row)]):
            if self.tool == "erase":
                drawing.erase(c, r)
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
        frame = theme.frame(parent, width=LIBRARY_W)
        frame.pack(side="left", fill="y")
        frame.pack_propagate(False)

        new_btn = theme.button(frame, "+ NEW DRAWING", self._new_drawing_dialog,
                               bg=theme.WORK, fg=theme.ON_ACCENT,
                               activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT)
        new_btn.pack(side="bottom", fill="x", padx=PAD, pady=PAD)

        scrollbar = theme.scrollbar(frame, "vertical")
        scrollbar.pack(side="right", fill="y")
        self._list_canvas = tk.Canvas(frame, highlightthickness=0, bg=theme.BG)
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
        # Rows stretch to the pane's width, so a click anywhere on the row hits.
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfigure(self._list_window, width=e.width))
        for widget in (self._list_canvas, self._list_frame):
            widget.bind("<MouseWheel>", self._on_list_wheel)
            widget.bind("<Button-4>", lambda e: self._list_canvas.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: self._list_canvas.yview_scroll(1, "units"))
        self._rebuild_list()

    def _on_list_wheel(self, event):
        step = -1 if event.delta > 0 else 1
        self._list_canvas.yview_scroll(step, "units")

    def _build_canvas_pane(self, parent):
        frame = theme.frame(parent)
        frame.pack(side="left", fill="both", expand=True)

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
        self.canvas.bind("<Leave>", lambda e: self.canvas.delete("ghost"))

    def _build_tools_pane(self, parent):
        outer = theme.frame(parent, width=TOOLS_W)
        outer.pack(side="right", fill="y")
        outer.pack_propagate(False)
        # The straight line, top to bottom, that fences the tools off from
        # the drawing (item 3).
        theme.separator(outer, "vertical").pack(side="left", fill="y")
        frame = theme.frame(outer)
        frame.pack(side="left", fill="both", expand=True, padx=(PAD, PAD))

        # --- bottom-right block, packed first so it owns the bottom (item 3, 13, 15)
        bottom = theme.frame(frame)
        bottom.pack(side="bottom", fill="x", pady=(0, PAD))
        foot = theme.frame(bottom)
        foot.pack(fill="x")
        self._size_label = theme.label(foot, "", fg=theme.ON_SURFACE, cursor="hand2",
                                       font=theme.FONT_BOLD)
        self._size_label.pack(side="left")
        self._size_label.bind("<Button-1>", lambda e: self._set_size(self._selected))
        theme.label(foot, "  click to resize", dim=True).pack(side="left")
        theme.button(foot, "HELP", self.toggle_help, padx=10).pack(side="right")

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
        self._save_button = theme.button(save_row, "SAVE", self.save, bg=theme.WORK,
                                         fg=theme.ON_ACCENT, activebackground=theme.ACCENT,
                                         activeforeground=theme.ON_ACCENT)
        self._save_button.pack(side="left", fill="x", expand=True)
        self._status = theme.label(save_row, "", dim=True, anchor="e", width=14)
        self._status.pack(side="right", padx=(4, 0))

        tool_row = theme.frame(frame)
        tool_row.pack(fill="x", pady=2)
        self._tool_buttons = {
            "draw": theme.button(tool_row, "DRAW", lambda: self.set_tool("draw")),
            "erase": theme.button(tool_row, "ERASE", lambda: self.set_tool("erase")),
            "fill": theme.button(tool_row, "FILL", lambda: self.set_tool("fill")),
        }
        for i, btn in enumerate(self._tool_buttons.values()):
            btn.pack(side="left", expand=True, fill="x", padx=(0 if i == 0 else 2, 0))

        undo_row = theme.frame(frame)
        undo_row.pack(fill="x", pady=2)
        theme.button(undo_row, "UNDO", self.undo).pack(side="left", expand=True, fill="x")
        theme.button(undo_row, "REDO", self.redo).pack(side="left", expand=True, fill="x", padx=(2, 0))

        self._build_symmetry_row(frame)

        # What the next click will paint — the one piece of state the artist
        # otherwise has to keep in their head. An Entry, so the code can be
        # copied (double-click selects it all) or typed over (item 5).
        ink_row = theme.frame(frame)
        ink_row.pack(fill="x", pady=(PAD, 0))
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

        self._refresh_tool_buttons()
        self._refresh_symmetry_ui()
        self._refresh_ink_ui()

    def _build_symmetry_row(self, frame):
        row = theme.frame(frame)
        row.pack(fill="x", pady=2)
        self._sym_button = theme.button(row, "SYMMETRY",
                                        lambda: self.set_symmetry(not self.symmetry_on), padx=4)
        self._sym_button.pack(side="left", expand=True, fill="x")
        self._sym_orient_button = theme.button(
            row, "", self._toggle_symmetry_orientation, padx=5)
        self._sym_orient_button.pack(side="left", padx=(2, 0))
        self._sym_length_var = tk.StringVar(value=str(self._sym_length))
        self._sym_length_spin = tk.Spinbox(
            row, from_=symmetry.MIN_LENGTH, to=symmetry.MAX_LENGTH, width=3,
            textvariable=self._sym_length_var, command=self._on_symmetry_length,
            bg=theme.PANEL, fg=theme.ON_SURFACE, buttonbackground=theme.PANEL_HI,
            relief="flat", bd=0, highlightthickness=1, highlightbackground=theme.SHADOW,
            insertbackground=theme.ON_SURFACE, font=theme.FONT_MONO, justify="center")
        self._sym_length_spin.pack(side="left", padx=(2, 0), ipady=2)
        self._sym_length_spin.bind("<Return>", self._on_symmetry_length)
        self._sym_length_spin.bind("<FocusOut>", self._on_symmetry_length)
        self._sym_hint = theme.label(frame, "", dim=True, anchor="w")
        self._sym_hint.pack(fill="x")
        self._sym_hint.bind("<Button-1>", lambda e: self.arm_symmetry_placement())

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
        if not hasattr(self, "_sym_button"):
            return
        theme.set_pressed(self._sym_button, self.symmetry_on)
        glyph = "\u2502 90\u00b0" if self._sym_orientation == symmetry.VERTICAL else "\u2500 180\u00b0"
        self._sym_orient_button.configure(text=glyph)
        if self._sym_length_var.get() != str(self._sym_length):
            self._sym_length_var.set(str(self._sym_length))
        if not self.symmetry_on:
            self._sym_hint.configure(text="")
        elif self._placing_bar:
            self._sym_hint.configure(text="\u25b8 click the canvas to place the bar", fg=theme.ACCENT)
        else:
            self._sym_hint.configure(text="bar placed \u00b7 click here to move it", fg=theme.ON_DIM)

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
        # Single letters must not fire while the artist is typing a hex code.
        self.root.bind("<Key-e>", self._typing_guard(lambda: self.set_tool("erase")))
        self.root.bind("<Key-b>", self._typing_guard(lambda: self.set_tool("draw")))
        self.root.bind("<Key-f>", self._typing_guard(lambda: self.set_tool("fill")))
        self.root.bind("<Key-m>", self._typing_guard(lambda: self.set_symmetry(not self.symmetry_on)))
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

    # ---- canvas <-> grid glue -------------------------------------------
    def _grid_at(self, event):
        # canvasx/canvasy fold the scroll offset in; raw event coords would be
        # off by exactly the scrolled distance.
        return (int(self.canvas.canvasx(event.x)) // self.zoom_level,
                int(self.canvas.canvasy(event.y)) // self.zoom_level)

    def _on_press(self, event):
        self.canvas.focus_set()  # take focus back from the hex entry
        self.on_canvas_press(*self._grid_at(event))

    def _on_drag(self, event):
        self.on_canvas_drag(*self._grid_at(event))

    def _on_release(self, _event):
        self.on_canvas_release()

    def _on_pick(self, event):
        self.on_canvas_pick(*self._grid_at(event))

    def _on_motion(self, event):
        """While placing the symmetry bar, a ghost of it follows the cursor."""
        self.canvas.delete("ghost")
        if not (self._placing_bar and self.history is not None):
            return
        col, row = self._grid_at(event)
        ghost = symmetry.Bar(self._sym_orientation, self._sym_length, col, row)
        self._draw_bar(ghost, tag="ghost", colour=theme.ON_DIM)

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
        self._list_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
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

        label = tk.Label(row, text=drawing.name, anchor="w", bg=bg, fg=theme.ON_SURFACE,
                         font=theme.FONT)
        label.pack(side="left", fill="x", expand=True)

        menu = tk.Menu(row, tearoff=False)
        menu.add_command(label="Duplicate", command=lambda: self._duplicate(drawing))
        menu.add_command(label="Export PNG\u2026", command=lambda: self._export_png(drawing))
        menu.add_command(label="Export JPG\u2026", command=lambda: self._export_jpg(drawing))
        menu.add_command(label="Export engine sprite\u2026",
                         command=lambda: self._export_engine_sprite(drawing))
        menu.add_command(label="Rename\u2026", command=lambda: self._rename(drawing))
        menu.add_command(label="Species\u2026", command=lambda: self._set_species(drawing))
        menu.add_command(label="Size\u2026", command=lambda: self._set_size(drawing))
        menu.add_command(label="Delete", command=lambda: self._delete(drawing))
        menu_btn = theme.button(row, "\u22ee", None, bg=bg, activebackground=theme.PANEL_HI,
                                padx=6, pady=2)
        menu_btn.configure(command=lambda: menu.tk_popup(
            menu_btn.winfo_rootx(), menu_btn.winfo_rooty() + menu_btn.winfo_height()))
        menu_btn.pack(side="right", padx=4)

        for widget in (row, label, thumb):
            widget.bind("<Button-1>", lambda e: self.select(drawing))
            widget.bind("<MouseWheel>", self._on_list_wheel)
        self._rows[id(drawing)] = {"row": row, "thumb": thumb, "label": label, "menu": menu_btn}
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

    def _highlight_row(self, drawing, selected):
        widgets = self._rows.get(id(drawing))
        if widgets is None:
            return
        bg = ROW_BG_SELECTED if selected else ROW_BG
        for key in ("row", "thumb", "label", "menu"):
            widgets[key].configure(bg=bg)
        widgets["menu"].configure(highlightbackground=bg)
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
        drawing = Drawing.blank(cols, rows, palette, species=species, model=model)
        self.library.add(drawing)
        self._build_row(drawing)
        self._list_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        self.select(drawing)
        return drawing

    def _new_drawing(self):
        """Older name, kept: a default-size blank drawing, no dialog."""
        return self.new_drawing()

    def _new_drawing_dialog(self):
        SizeDialog(self.root, "New drawing", (NEW_SIZE, NEW_SIZE), size_presets(),
                   self.new_drawing, verb="CREATE")

    def _duplicate(self, drawing):
        clone = self.library.duplicate(drawing)
        self._build_row(clone)
        self._list_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
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

    def _set_species(self, drawing):
        """Name the species — what unlocks engine export for a new flower."""
        value = simpledialog.askstring(
            "Pixel Pomo Art Kit",
            "Species id (lowercase, as the engine names it, e.g. 'gonca'):",
            initialvalue=drawing.species, parent=self.root)
        if value is None:
            return
        value = value.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            messagebox.showerror(
                "Pixel Pomo Art Kit",
                "A species id is lowercase letters/digits/underscores and "
                "starts with a letter — it becomes the sprite's filename.")
            return
        drawing.species = value
        self._save(drawing)
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
    def _export_png(self, drawing):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export PNG", defaultextension=".png",
            initialfile=f"{drawing.name}.png", filetypes=[("PNG image", "*.png")])
        if not path:
            return
        try:
            engine_io.export_png(drawing, path)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))

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
        ENGINE_SPRITE_DIR.mkdir(parents=True, exist_ok=True)  # so the picker opens somewhere real
        out_dir = filedialog.askdirectory(
            parent=self.root, title="Export engine sprite",
            initialdir=str(ENGINE_SPRITE_DIR))
        if not out_dir:
            return
        names = ", ".join(engine_io.engine_sprite_names(drawing))
        if not messagebox.askyesno(
                "Pixel Pomo Art Kit",
                f"This will overwrite:\n{names}\nin {out_dir}\n\nContinue?"):
            return
        try:
            written = engine_io.export_engine_sprite(drawing, out_dir)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))
            return
        # Multi-file write into a browsed-to folder: say what landed where,
        # or a successful export is indistinguishable from a silent failure.
        messagebox.showinfo("Pixel Pomo Art Kit",
                            "Exported:\n" + "\n".join(str(p) for p in written))

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
        if z >= 8:
            self._draw_grid_lines(w, h, z)
        bar = self._active_bar()
        if bar is not None:
            self._draw_bar(bar, tag="symmetry", colour=theme.ACCENT)
        self.canvas.configure(scrollregion=(0, 0, w * z, h * z))

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
        cw, ch = max(1, wpx // 10), max(1, hpx // 10)
        if self.tool == "erase":
            fill = None
        else:
            fill = _hex(self.ink_rgba())
        for c, r in self._stroke_cells:
            if not d._inside(c, r):
                continue
            x0, y0 = c * z, r * z
            colour = fill or CHECKER[((x0 // cw) + (y0 // ch)) % 2]
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
        cols = rows = 10
        cw, ch = max(1, width // cols), max(1, height // rows)
        for ry in range(rows):
            for rx in range(cols):
                x0, y0 = rx * cw, ry * ch
                canvas.create_rectangle(
                    x0, y0, x0 + cw, y0 + ch, fill=CHECKER[(rx + ry) % 2], outline="",
                    tags="checker")

    def _draw_grid_lines(self, width, height, z):
        for c in range(width + 1):
            x = c * z
            self.canvas.create_line(x, 0, x, height * z, fill=theme.PANEL_HI, tags="grid")
        for r in range(height + 1):
            y = r * z
            self.canvas.create_line(0, y, width * z, y, fill=theme.PANEL_HI, tags="grid")

    def _draw_bar(self, bar, tag, colour):
        """The symmetry bar over the grid: a bright outline around the cells
        it lies on, and its axis through the middle."""
        z = self.zoom_level
        cells = bar.cells()
        cs = [c for c, _ in cells]
        rs = [r for _, r in cells]
        x0, y0 = min(cs) * z, min(rs) * z
        x1, y1 = (max(cs) + 1) * z, (max(rs) + 1) * z
        self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=colour,
                                     width=2, tags=tag)
        if bar.orientation == symmetry.VERTICAL:
            mid = bar.col * z + z // 2
            self.canvas.create_line(mid, y0, mid, y1, fill=colour, width=2, tags=tag)
        else:
            mid = bar.row * z + z // 2
            self.canvas.create_line(x0, mid, x1, mid, fill=colour, width=2, tags=tag)

    # ---- help (item 15) -------------------------------------------------------
    def toggle_help(self):
        if self._help is not None:
            self._help.destroy()
            self._help = None
            return
        self._help = HelpOverlay(self.root, self.toggle_help)

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
    ("UNDO / REDO", "step back / forward, one stroke at a time (a drag or a fill is one stroke)"),
    ("SYMMETRY", "place a bar on the canvas; anything painted along it is mirrored across it"),
    ("  │ 90° / ─ 180°", "the bar stands up (mirrors left↔right) or lies flat (mirrors top↔bottom)"),
    ("  length", "how many cells the bar covers, centred where you click"),
    ("#rrggbb  +", "the ink. Click to type a new code, double-click to select it, + adds it to favourites"),
    ("Favourite colours", "your own set — right-click a swatch to remove it"),
    ("Ready colours", "Pixel Pomo's theme tones plus pixel-art staples"),
    ("Colour", "hue strip on top, light/dark square below; click or drag"),
    ("1x / squint", "the drawing at real size, and at squint-test distance"),
    ("W × H", "the drawing's size — click it to resize (one undo step)"),
    ("+ NEW DRAWING", "a blank drawing at a garden size: flower, bush, rock, tree, or custom"),
    ("⋮", "on a library row: Duplicate, Export PNG/JPG/engine sprite, Rename, Species, Size, Delete"),
    ("", None),
    ("KEYBOARD", None),
    ("{mod}+S", "save"),
    ("{mod}+Z / {mod}+Y", "undo / redo  ({mod}+Shift+Z also redoes)"),
    ("{mod}+N", "new drawing"),
    ("B / E / F", "brush / eraser / fill"),
    ("M", "symmetry on / off"),
    ("+ / −  or mouse wheel", "zoom in / out"),
    ("Right-click on the canvas", "eyedropper: the colour under the cursor becomes the ink"),
    ("F1 / Esc", "open / close this help"),
]


class HelpOverlay(tk.Frame):
    """Every button and key, on a panel over the main window; × or Esc closes
    it (item 15)."""

    def __init__(self, parent, on_close):
        super().__init__(parent, bg=theme.PANEL, highlightthickness=1,
                         highlightbackground=theme.ACCENT)
        self.place(relx=0.5, rely=0.5, anchor="center")
        head = theme.frame(self, bg=theme.PANEL)
        head.pack(fill="x", padx=14, pady=(10, 4))
        theme.label(head, "Pixel Pomo Art Kit \u2014 help", bg=theme.PANEL,
                    font=theme.FONT_BOLD).pack(side="left")
        theme.button(head, "\u00d7", on_close, padx=8, pady=0, font=theme.FONT_BOLD,
                     bg=theme.PANEL, activebackground=theme.PANEL_HI).pack(side="right")
        body = theme.frame(self, bg=theme.PANEL)
        body.pack(padx=14, pady=(0, 12))
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
                            justify="left", wraplength=460).grid(row=r, column=1, sticky="w")
            r += 1
        self.lift()
