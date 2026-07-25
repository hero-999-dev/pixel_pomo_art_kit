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
"""
import re
import sys
import tkinter as tk
from dataclasses import replace
from tkinter import colorchooser, filedialog, messagebox, simpledialog
from pathlib import Path

from art_kit import engine_io
from art_kit.model import Drawing, History, LETTERS, Palette, hex_to_rgba

# Palette slot letter -> Palette field, for the right-click colour editor.
PALETTE_FIELD = {"d": "d", "m": "m", "l": "l", "C": "centre", "x": "rim",
                 "S": "stem", "G": "leaf", "k": "vein", "o": "plant_rim"}

MIN_ZOOM, MAX_ZOOM = 4, 48
DEFAULT_ZOOM = 20
CHECKER = ("#2b2b2b", "#343434")
PREVIEW_ZOOM = 8  # the fixed "squint test" scale, independent of the editing zoom

ROW_BG = "#262626"
ROW_BG_SELECTED = "#3a5f3a"

# The nine palette slots, in the order an artist reaches for them.
SLOTS = [("d", "dark"), ("m", "mid"), ("l", "light"), ("C", "centre"),
         ("x", "bloom seam"), ("S", "stem"), ("G", "leaf"), ("k", "vein"),
         ("o", "plant seam")]

# The app's own ready colours, from Pixel Pomo's themes.
READY = ["FF5A5F", "F2C94C", "5FBF4A", "3E8E36", "8E4FE0", "E02C6D",
         "F7EFDD", "1E1E2E", "CDD6F4", "FFFFFF"]

def base_dir():
    """Where the app keeps `library/` and `exports/`: beside the .exe when
    frozen by PyInstaller (a onefile exe unpacks its code to a temp dir, so
    `__file__` is not a place to write), else the repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


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


class ArtKitApp:
    def __init__(self, root, library):
        self.root = root
        self.library = library
        self.tool = "draw"
        self.ink = "m"
        self.mirror = False
        self.zoom_level = DEFAULT_ZOOM
        self._histories = {}
        self._painting = False
        self._last_cell = None
        self.history = None
        self._selected = None  # the library-registered Drawing, see module docstring
        root.title("Pixel Pomo Art Kit")
        self._build()
        if library.drawings:
            self.select(library.drawings[0])

    # ---- state ---------------------------------------------------------
    def select(self, drawing):
        self._selected = drawing
        self.history = self._histories.setdefault(id(drawing), History(drawing))
        self.root.title(f"Pixel Pomo Art Kit — {drawing.name}")
        self._refresh_list()
        self._refresh_palette()
        self._refresh_ink_ui()
        self._redraw()

    def set_tool(self, name):
        if name not in ("draw", "erase", "fill"):
            raise ValueError(f"tool must be 'draw', 'erase' or 'fill', got {name!r}")
        self.tool = name
        self._refresh_tool_buttons()

    def toggle_mirror(self):
        # Not a tool: mirroring composes with draw, erase AND fill, so it is a
        # switch beside them rather than a fourth mode.
        self.mirror = not self.mirror
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

    # ---- pointer, in GRID coordinates ----------------------------------
    def on_canvas_press(self, col, row):
        if self.history is None:
            return
        self.history.begin_stroke()
        self._painting = True
        self._last_cell = (col, row)
        self._apply(col, row)
        self._redraw()

    def on_canvas_drag(self, col, row):
        if not self._painting:
            return
        # Walk the whole line from the last reported cell, so a quick stroke
        # is a stroke, not a trail of dots (see _line_cells).
        for c, r in _line_cells(*self._last_cell, col, row)[1:]:
            self._apply(c, r)
        self._last_cell = (col, row)
        self._redraw()

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
        targets = [(col, row)]
        if self.mirror:
            targets.append((drawing.width - 1 - col, row))
        for c, r in targets:
            if self.tool == "erase":
                drawing.erase(c, r)
            elif self.tool == "fill":
                drawing.flood(c, r, self.ink)
            else:
                drawing.paint(c, r, self.ink)

    def _after_change(self):
        live = self.history.current
        if live is not self._selected:
            # undo/redo swapped `.current` to a snapshot copy; fold its content
            # back onto the object the library actually knows how to save.
            # (`kind` follows the cells automatically — it's a derived property.)
            self._selected.cells = [list(row) for row in live.cells]
        self.library.save(self._selected)
        self._refresh_list()
        self._redraw()

    # ---- building the window -------------------------------------------
    def _build(self):
        # Library and tools claim their fixed-width edges first; the canvas
        # pane is packed last so it expands into whatever is left between them.
        self._build_library_pane(self.root)
        self._build_tools_pane(self.root)
        self._build_canvas_pane(self.root)
        self._bind_keys()

    def _build_library_pane(self, parent):
        frame = tk.Frame(parent, width=220, bg="#1e1e1e")
        frame.pack(side="left", fill="y")
        frame.pack_propagate(False)

        new_btn = tk.Button(frame, text="+ NEW DRAWING", command=self._new_drawing)
        new_btn.pack(side="bottom", fill="x")

        scrollbar = tk.Scrollbar(frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self._list_canvas = tk.Canvas(frame, highlightthickness=0, bg="#1e1e1e")
        self._list_canvas.pack(side="left", fill="both", expand=True)
        self._list_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=self._list_canvas.yview)

        self._list_frame = tk.Frame(self._list_canvas, bg="#1e1e1e")
        self._list_canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        self._list_frame.bind(
            "<Configure>",
            lambda e: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")))

    def _build_canvas_pane(self, parent):
        frame = tk.Frame(parent, bg="#1e1e1e")
        frame.pack(side="left", fill="both", expand=True)

        # Fixed-size side column first, so the expanding editing canvas below
        # only claims what is left over (same packing-order rule as _build).
        side = tk.Frame(frame, bg="#1e1e1e")
        side.pack(side="right", fill="y", padx=8, pady=8)
        tk.Label(side, text="1x", bg="#1e1e1e", fg="#cccccc").pack()
        self.preview_1x = tk.Canvas(side, highlightthickness=0, bg="#1e1e1e")
        self.preview_1x.pack(pady=(0, 12))
        tk.Label(side, text="squint", bg="#1e1e1e", fg="#cccccc").pack()
        self.preview_squint = tk.Canvas(side, highlightthickness=0, bg="#1e1e1e")
        self.preview_squint.pack()

        # Scrollbars, because 16 cells x zoom 48 is wider than the pane — the
        # edge pixels of a sprite must stay reachable at every zoom.
        wrap = tk.Frame(frame, bg="#1e1e1e")
        wrap.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        vbar = tk.Scrollbar(wrap, orient="vertical")
        vbar.pack(side="right", fill="y")
        hbar = tk.Scrollbar(wrap, orient="horizontal")
        hbar.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(wrap, highlightthickness=0, bg="#1e1e1e",
                                yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vbar.configure(command=self.canvas.yview)
        hbar.configure(command=self.canvas.xview)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_pick)
        self.canvas.bind("<MouseWheel>", lambda e: self.zoom(1 if e.delta > 0 else -1))

    def _build_tools_pane(self, parent):
        frame = tk.Frame(parent, width=200, bg="#1e1e1e")
        frame.pack(side="right", fill="y")
        frame.pack_propagate(False)

        tool_row = tk.Frame(frame, bg="#1e1e1e")
        tool_row.pack(fill="x", padx=6, pady=(6, 2))
        self._tool_buttons = {
            "draw": tk.Button(tool_row, text="DRAW", command=lambda: self.set_tool("draw")),
            "erase": tk.Button(tool_row, text="ERASE", command=lambda: self.set_tool("erase")),
            "fill": tk.Button(tool_row, text="FILL", command=lambda: self.set_tool("fill")),
        }
        for btn in self._tool_buttons.values():
            btn.pack(side="left", expand=True, fill="x")

        self._mirror_button = tk.Button(frame, text="MIRROR X", command=self.toggle_mirror)
        self._mirror_button.pack(fill="x", padx=6, pady=2)

        undo_row = tk.Frame(frame, bg="#1e1e1e")
        undo_row.pack(fill="x", padx=6, pady=2)
        tk.Button(undo_row, text="UNDO", command=self.undo).pack(side="left", expand=True, fill="x")
        tk.Button(undo_row, text="REDO", command=self.redo).pack(side="left", expand=True, fill="x")

        # What the next click will paint — the one piece of state the artist
        # otherwise has to keep in their head.
        self._ink_swatch = tk.Label(frame, text="", bg="#1e1e1e", fg="#eeeeee")
        self._ink_swatch.pack(fill="x", padx=6, pady=(6, 0))

        tk.Label(frame, text="Palette", bg="#1e1e1e", fg="#cccccc").pack(pady=(10, 0))
        palette_frame = tk.Frame(frame, bg="#1e1e1e")
        palette_frame.pack(fill="x", padx=6)
        self._slot_buttons = {}
        for letter, label in SLOTS:
            btn = tk.Button(palette_frame, text=f"{label} ({letter})", anchor="w",
                             command=lambda letter=letter: self.set_ink(letter))
            btn.bind("<Button-3>",
                     lambda e, letter=letter: self._edit_palette_slot(letter))
            btn.pack(fill="x", pady=1)
            self._slot_buttons[letter] = btn
        tk.Label(frame, text="right-click a slot to edit its colour",
                 bg="#1e1e1e", fg="#777777").pack()

        tk.Label(frame, text="Ready colours", bg="#1e1e1e", fg="#cccccc").pack(pady=(10, 0))
        ready_frame = tk.Frame(frame, bg="#1e1e1e")
        ready_frame.pack(fill="x", padx=6)
        for i, hexcode in enumerate(READY):
            btn = tk.Button(ready_frame, bg=f"#{hexcode.lower()}", width=2,
                             command=lambda h=hexcode: self.set_ink(hex_to_rgba(h)))
            btn.grid(row=i // 5, column=i % 5, padx=1, pady=1, sticky="ew")

        tk.Button(frame, text="PICK COLOUR\u2026", command=self._pick_color).pack(
            fill="x", padx=6, pady=10)

        self._refresh_tool_buttons()
        self._refresh_ink_ui()

    def _bind_keys(self):
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-Shift-Z>", lambda e: self.redo())
        self.root.bind("<Key-e>", lambda e: self.set_tool("erase"))
        self.root.bind("<Key-b>", lambda e: self.set_tool("draw"))
        self.root.bind("<Key-f>", lambda e: self.set_tool("fill"))
        self.root.bind("<Key-x>", lambda e: self.toggle_mirror())
        self.root.bind("<plus>", lambda e: self.zoom(+1))
        self.root.bind("<KP_Add>", lambda e: self.zoom(+1))
        self.root.bind("<minus>", lambda e: self.zoom(-1))
        self.root.bind("<KP_Subtract>", lambda e: self.zoom(-1))

    # ---- canvas <-> grid glue -------------------------------------------
    def _grid_at(self, event):
        # canvasx/canvasy fold the scroll offset in; raw event coords would be
        # off by exactly the scrolled distance.
        return (int(self.canvas.canvasx(event.x)) // self.zoom_level,
                int(self.canvas.canvasy(event.y)) // self.zoom_level)

    def _on_press(self, event):
        self.on_canvas_press(*self._grid_at(event))

    def _on_drag(self, event):
        self.on_canvas_drag(*self._grid_at(event))

    def _on_release(self, _event):
        self.on_canvas_release()

    def _on_pick(self, event):
        self.on_canvas_pick(*self._grid_at(event))

    # ---- the library list ------------------------------------------------
    def _refresh_list(self):
        # Rebuilding resets the scroll; put it back where the artist left it,
        # or every stroke on flower #20 jumps the list to the top.
        offset = self._list_canvas.yview()[0]
        for child in self._list_frame.winfo_children():
            child.destroy()
        for drawing in self.library.drawings:
            self._build_row(drawing)
        self._list_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        self._list_canvas.yview_moveto(offset)

    def _build_row(self, drawing):
        selected = drawing is self._selected
        bg = ROW_BG_SELECTED if selected else ROW_BG
        row = tk.Frame(self._list_frame, bg=bg)
        row.pack(fill="x", pady=1)

        preview = tk.Canvas(row, highlightthickness=0, bg="#1e1e1e")
        preview.pack(side="left", padx=4, pady=2)
        self._draw_cells(preview, engine_io.render(drawing), 2)

        label = tk.Label(row, text=drawing.name, anchor="w", bg=bg, fg="#eeeeee")
        label.pack(side="left", fill="x", expand=True)

        menu_btn = tk.Menubutton(row, text="\u22ee", relief="raised")
        menu = tk.Menu(menu_btn, tearoff=False)
        menu.add_command(label="Duplicate", command=lambda: self._duplicate(drawing))
        menu.add_command(label="Export PNG\u2026", command=lambda: self._export_png(drawing))
        menu.add_command(label="Export JPG\u2026", command=lambda: self._export_jpg(drawing))
        menu.add_command(label="Export engine sprite\u2026",
                          command=lambda: self._export_engine_sprite(drawing))
        menu.add_command(label="Copy grid literal", command=lambda: self._copy_grid_literal(drawing))
        menu.add_command(label="Copy palette literal",
                          command=lambda: self._copy_palette_literal(drawing))
        menu.add_command(label="Rename\u2026", command=lambda: self._rename(drawing))
        menu.add_command(label="Species\u2026", command=lambda: self._set_species(drawing))
        menu.add_command(label="Rows\u2026", command=lambda: self._set_rows(drawing))
        menu.add_command(label="Delete", command=lambda: self._delete(drawing))
        menu_btn.menu = menu
        menu_btn.config(menu=menu)
        menu_btn.pack(side="right", padx=4)

        for widget in (row, label, preview):
            widget.bind("<Button-1>", lambda e: self.select(drawing))

    def _new_drawing(self):
        base = self._selected or (self.library.drawings[0] if self.library.drawings else None)
        if base is not None:
            palette, species, model = base.palette, base.species, base.model
        else:
            palette = Palette(d="2E2E2E", m="6E6E6E", l="B0B0B0", centre="F2C94C", rim="1A1A1A")
            species, model = "", 0
        drawing = Drawing.blank(16, 16, palette, species=species, model=model)
        self.library.add(drawing)
        self.select(drawing)

    def _duplicate(self, drawing):
        clone = self.library.duplicate(drawing)
        self.select(clone)

    def _rename(self, drawing):
        name = simpledialog.askstring(
            "Pixel Pomo Art Kit", "New name:", initialvalue=drawing.name, parent=self.root)
        if name:
            drawing.name = name
            # `drawing` always came from `library.drawings`, so it is always the
            # object the library registered - safe to save regardless of
            # whether it is the one currently open for editing.
            self.library.save(drawing)
            if drawing is self._selected:
                self.root.title(f"Pixel Pomo Art Kit — {name}")
            self._refresh_list()

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
        self.library.save(drawing)
        self._refresh_list()

    def _set_rows(self, drawing):
        if drawing is not self._selected:
            self.select(drawing)
        n = simpledialog.askinteger(
            "Pixel Pomo Art Kit", "Rows (width stays 16):",
            initialvalue=self.history.current.height,
            minvalue=1, maxvalue=64, parent=self.root)
        if not n or n == self.history.current.height:
            return
        # A resize is a stroke: one undo puts the cropped rows back.
        self.history.begin_stroke()
        self.history.current.resize_rows(n)
        self.history.end_stroke()
        self._after_change()

    def _edit_palette_slot(self, letter):
        if self.history is None:
            return
        pal = self.history.current.palette
        current = pal.colors()[letter]
        _rgb, hexcolor = colorchooser.askcolor(
            parent=self.root, title=f"Colour for {dict(SLOTS)[letter]} ({letter})",
            initialcolor=_hex(current))
        if not hexcolor:
            return
        new_pal = replace(pal, **{PALETTE_FIELD[letter]: hexcolor.lstrip("#").upper()})
        # Palette edits are deliberately not undoable strokes; repaint() keeps
        # every history snapshot on the new palette so undo can't revert it.
        self.history.repaint(new_pal)
        self._selected.palette = new_pal
        self.library.save(self._selected)
        self._refresh_palette()
        self._refresh_ink_ui()
        self._refresh_list()
        self._redraw()

    def _copy_palette_literal(self, drawing):
        try:
            text = engine_io.export_palette_literal(drawing)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _delete(self, drawing):
        if not messagebox.askyesno(
                "Pixel Pomo Art Kit", f"Delete '{drawing.name}'? This cannot be undone."):
            return
        was_selected = drawing is self._selected
        self.library.remove(drawing)
        self._histories.pop(id(drawing), None)
        if was_selected:
            self.history = None
            self._selected = None
            if self.library.drawings:
                self.select(self.library.drawings[0])
                return
            self.root.title("Pixel Pomo Art Kit")
        self._refresh_list()
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

    def _copy_grid_literal(self, drawing):
        try:
            text = engine_io.export_grid_literal(drawing)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ---- colour picking ------------------------------------------------
    def _pick_color(self):
        _rgb, hexcolor = colorchooser.askcolor(parent=self.root, title="Pick colour")
        if hexcolor:
            self.set_ink(hex_to_rgba(hexcolor))

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
        self._draw_cells(self.canvas, engine_io.render(drawing), z)
        if z >= 8:
            self._draw_grid_lines(w, h, z)
        self.canvas.configure(scrollregion=(0, 0, w * z, h * z))

    def _draw_previews(self):
        self.preview_1x.delete("all")
        self.preview_squint.delete("all")
        if self.history is None:
            return
        grid = engine_io.render(self.history.current)
        self._draw_cells(self.preview_1x, grid, 1)
        self._draw_cells(self.preview_squint, grid, PREVIEW_ZOOM)

    def _draw_cells(self, canvas, grid, cell_px):
        """One rectangle per opaque cell of `grid`, and size the canvas to fit it."""
        h = len(grid)
        w = len(grid[0]) if h else 0
        canvas.configure(width=max(1, w * cell_px), height=max(1, h * cell_px))
        for r in range(h):
            for c in range(w):
                px = grid[r][c]
                if not px or px[3] == 0:
                    continue
                x0, y0 = c * cell_px, r * cell_px
                canvas.create_rectangle(
                    x0, y0, x0 + cell_px, y0 + cell_px, fill=_hex(px), outline="")

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
                    x0, y0, x0 + cw, y0 + ch, fill=CHECKER[(rx + ry) % 2], outline="")

    def _draw_grid_lines(self, width, height, z):
        for c in range(width + 1):
            x = c * z
            self.canvas.create_line(x, 0, x, height * z, fill="gray40")
        for r in range(height + 1):
            y = r * z
            self.canvas.create_line(0, y, width * z, y, fill="gray40")

    # ---- keeping the tools pane in sync ---------------------------------
    def _refresh_tool_buttons(self):
        for name, btn in self._tool_buttons.items():
            btn.configure(relief="sunken" if name == self.tool else "raised")
        mirror_btn = getattr(self, "_mirror_button", None)
        if mirror_btn is not None:
            mirror_btn.configure(relief="sunken" if self.mirror else "raised")

    def _refresh_palette(self):
        if self.history is None:
            return
        colors = self.history.current.palette.colors()
        for letter, btn in self._slot_buttons.items():
            btn.configure(bg=_hex(colors[letter]), activebackground=_hex(colors[letter]))

    def _refresh_ink_ui(self):
        swatch = getattr(self, "_ink_swatch", None)
        if swatch is None:
            return  # tools pane not built yet
        ink = self.ink
        if isinstance(ink, str):
            rgba = (self.history.current.palette.colors()[ink]
                    if self.history else (128, 128, 128, 255))
            text = f"ink: {dict(SLOTS)[ink]} ({ink})"
        else:
            rgba = ink
            text = f"ink: {_hex(ink)}"
        r, g, b, _a = rgba
        fg = "#000000" if (r * 299 + g * 587 + b * 114) > 128000 else "#ffffff"
        swatch.configure(text=text, bg=_hex(rgba), fg=fg)
        for letter, btn in getattr(self, "_slot_buttons", {}).items():
            btn.configure(relief="sunken" if ink == letter else "raised")
