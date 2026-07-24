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
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog
from pathlib import Path

from art_kit import engine_io
from art_kit.model import Drawing, History, LETTERS, Palette, hex_to_rgba

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

# Where the export dialog opens. Deliberately NOT the game's asset folder:
# pixel_pomo is read-only to this app, and defaulting there risks overwriting a
# shipped flower_*.png (the very files the byte-equality tests trust). The
# artist browses over by hand if they really mean to update the game.
ENGINE_SPRITE_DIR = Path(__file__).resolve().parent.parent / "exports"


def _hex(px):
    r, g, b, _a = px
    return f"#{r:02x}{g:02x}{b:02x}"


def _engine_sprite_names(drawing):
    """The basenames `engine_io.export_engine_sprite` will write, for the confirm dialog."""
    names = [f"flower_{drawing.species}_{drawing.model}.png"]
    if drawing.model == 0:
        names.append(f"flower_{drawing.species}.png")
    return names


class ArtKitApp:
    def __init__(self, root, library):
        self.root = root
        self.library = library
        self.tool = "draw"
        self.ink = "m"
        self.zoom_level = DEFAULT_ZOOM
        self._histories = {}
        self._painting = False
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
        self._refresh_list()
        self._refresh_palette()
        self._redraw()

    def set_tool(self, name):
        self.tool = name
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
        self._apply(col, row)

    def on_canvas_drag(self, col, row):
        if self._painting:
            self._apply(col, row)

    def on_canvas_release(self):
        if not self._painting:
            return
        self._painting = False
        self.history.end_stroke()
        self._after_change()

    def _apply(self, col, row):
        drawing = self.history.current
        if self.tool == "erase":
            drawing.erase(col, row)
        else:
            drawing.paint(col, row, self.ink)
        self._redraw()

    def _after_change(self):
        live = self.history.current
        if live is not self._selected:
            # undo/redo swapped `.current` to a snapshot copy; fold its content
            # back onto the object the library actually knows how to save.
            self._selected.cells = [list(row) for row in live.cells]
            self._selected.kind = live.kind
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
        list_canvas = tk.Canvas(frame, highlightthickness=0, bg="#1e1e1e")
        list_canvas.pack(side="left", fill="both", expand=True)
        list_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=list_canvas.yview)

        self._list_frame = tk.Frame(list_canvas, bg="#1e1e1e")
        list_canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        self._list_frame.bind(
            "<Configure>",
            lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))

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

        self.canvas = tk.Canvas(frame, highlightthickness=0, bg="#1e1e1e")
        self.canvas.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
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
        }
        self._tool_buttons["draw"].pack(side="left", expand=True, fill="x")
        self._tool_buttons["erase"].pack(side="left", expand=True, fill="x")

        undo_row = tk.Frame(frame, bg="#1e1e1e")
        undo_row.pack(fill="x", padx=6, pady=2)
        tk.Button(undo_row, text="UNDO", command=self.undo).pack(side="left", expand=True, fill="x")
        tk.Button(undo_row, text="REDO", command=self.redo).pack(side="left", expand=True, fill="x")

        tk.Label(frame, text="Palette", bg="#1e1e1e", fg="#cccccc").pack(pady=(10, 0))
        palette_frame = tk.Frame(frame, bg="#1e1e1e")
        palette_frame.pack(fill="x", padx=6)
        self._slot_buttons = {}
        for letter, label in SLOTS:
            btn = tk.Button(palette_frame, text=f"{label} ({letter})", anchor="w",
                             command=lambda letter=letter: self.set_ink(letter))
            btn.pack(fill="x", pady=1)
            self._slot_buttons[letter] = btn

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

    def _bind_keys(self):
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-Shift-Z>", lambda e: self.redo())
        self.root.bind("<Key-e>", lambda e: self.set_tool("erase"))
        self.root.bind("<Key-b>", lambda e: self.set_tool("draw"))
        self.root.bind("<plus>", lambda e: self.zoom(+1))
        self.root.bind("<KP_Add>", lambda e: self.zoom(+1))
        self.root.bind("<minus>", lambda e: self.zoom(-1))
        self.root.bind("<KP_Subtract>", lambda e: self.zoom(-1))

    # ---- canvas <-> grid glue -------------------------------------------
    def _on_press(self, event):
        self.on_canvas_press(event.x // self.zoom_level, event.y // self.zoom_level)

    def _on_drag(self, event):
        self.on_canvas_drag(event.x // self.zoom_level, event.y // self.zoom_level)

    def _on_release(self, _event):
        self.on_canvas_release()

    # ---- the library list ------------------------------------------------
    def _refresh_list(self):
        for child in self._list_frame.winfo_children():
            child.destroy()
        for drawing in self.library.drawings:
            self._build_row(drawing)

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
        menu.add_command(label="Rename\u2026", command=lambda: self._rename(drawing))
        menu.add_command(label="Delete", command=lambda: self._delete(drawing))
        menu_btn.menu = menu
        menu_btn.config(menu=menu)
        menu_btn.pack(side="right", padx=4)

        for widget in (row, label, preview):
            widget.bind("<Button-1>", lambda e: self.select(drawing))

    def _new_drawing(self):
        base = self._selected or (self.library.drawings[0] if self.library.drawings else None)
        if base is not None:
            palette, species = base.palette, base.species
        else:
            palette = Palette(d="2E2E2E", m="6E6E6E", l="B0B0B0", centre="F2C94C", rim="1A1A1A")
            species = ""
        drawing = Drawing.blank(16, 16, palette, species=species)
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
            self._refresh_list()

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
        names = ", ".join(_engine_sprite_names(drawing))
        if not messagebox.askyesno(
                "Pixel Pomo Art Kit",
                f"This will overwrite:\n{names}\nin {out_dir}\n\nContinue?"):
            return
        try:
            engine_io.export_engine_sprite(drawing, out_dir)
        except engine_io.ExportRefused as exc:
            messagebox.showerror("Pixel Pomo Art Kit", str(exc))

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

    def _refresh_palette(self):
        if self.history is None:
            return
        colors = self.history.current.palette.colors()
        for letter, btn in self._slot_buttons.items():
            btn.configure(bg=_hex(colors[letter]), activebackground=_hex(colors[letter]))
