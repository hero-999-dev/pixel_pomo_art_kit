# Pixel Pomo Art Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows desktop pixel editor an art student can draw Pixel Pomo flowers in, whose exported sprite is byte-identical to what the game ships.

**Architecture:** The document is the engine's own format — a 16-wide grid of palette letters plus five hex colours, exactly `_FLOWER_BLOOMS[fid][v]` and `_FLOWER_PALS[fid]` from `pixel_pomo\flutter\tools\gen_objects.py`. The app imports that module rather than reimplementing it, so preview and export run the shipped `outline()`, `_rose_compose()`, `upscale()` and `write_png()`. Pure logic (grid, undo, codec, bridge) lives in three display-free modules; tkinter only draws them.

**Tech Stack:** Python 3.14, tkinter (stdlib), PIL/Pillow 12 (JPEG export only), `unittest` (stdlib).

## Global Constraints

- Repository root: `C:\Users\claude\drawing kit\`. All paths below are relative to it unless absolute.
- Python: 3.14.4, already installed. tkinter and PIL 12.2.0 already available. **No new dependencies.**
- The bridge module is the ONLY place allowed to import `gen_objects`. Everything else stays pure.
- `gen_objects.py` lives at `C:\Users\claude\pixel_pomo\flutter\tools\gen_objects.py` and is **read-only to this project** — never edit it from the art kit.
- A grid is a `list[list[tuple[int,int,int,int]]]` of RGBA rows, top row first, as `gen_objects` defines it.
- Letter alphabet, fixed: bloom `d` `m` `l` `C` `x`, plant `S` `G` `k` `o`, empty `.`.
- Engine sprites are 16 cells wide and upscaled ×16.
- Tests run with `python -m unittest discover -s tests -v` from the repo root.
- Commit messages: plain, no AI attribution trailer of any kind.
- App name in all user-facing strings and docs: **Pixel Pomo Art Kit**.

---

### Task 1: Package skeleton and the engine bridge's import path

**Files:**
- Create: `art_kit/__init__.py`
- Create: `art_kit/engine_io.py`
- Create: `tests/__init__.py`
- Create: `tests/test_engine_io.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `art_kit.engine_io.gen_objects()` returning the imported `gen_objects` module; `art_kit.engine_io.GEN_OBJECTS_DIR` (a `pathlib.Path`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_io.py`:

```python
import unittest

from art_kit import engine_io


class ImportBridgeTest(unittest.TestCase):
    def test_gen_objects_module_loads_with_the_pieces_we_rely_on(self):
        g = engine_io.gen_objects()
        for name in ("blank", "hexrgb", "upscale", "write_png", "outline",
                     "_rose_compose", "flower_variant", "rose_variant",
                     "_FLOWER_BLOOMS", "_FLOWER_PALS", "_flower_pal"):
            self.assertTrue(hasattr(g, name), f"gen_objects has no {name}")

    def test_the_module_is_cached_not_reimported(self):
        self.assertIs(engine_io.gen_objects(), engine_io.gen_objects())
```

Create empty `tests/__init__.py` and `art_kit/__init__.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_io -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'art_kit.engine_io'`

- [ ] **Step 3: Write minimal implementation**

Create `art_kit/engine_io.py`:

```python
"""The bridge to Pixel Pomo's sprite generator.

Everything the art kit knows about the engine's file format comes from
`gen_objects.py` itself — imported, never copied. A reimplementation would be a
second source of truth that drifts the first time either side is touched, and
the whole point of this app is that its output IS the shipped sprite.
"""
import functools
import importlib.util
import os
import sys
from pathlib import Path

# Overridable so a checkout somewhere else can still run the app.
GEN_OBJECTS_DIR = Path(
    os.environ.get("PIXEL_POMO_TOOLS", r"C:\Users\claude\pixel_pomo\flutter\tools")
)


@functools.lru_cache(maxsize=1)
def gen_objects():
    """The `gen_objects` module, imported from the Pixel Pomo checkout."""
    path = GEN_OBJECTS_DIR / "gen_objects.py"
    if not path.exists():
        raise FileNotFoundError(
            f"gen_objects.py not found at {path}. Point the PIXEL_POMO_TOOLS "
            f"environment variable at pixel_pomo\\flutter\\tools."
        )
    if str(GEN_OBJECTS_DIR) not in sys.path:
        sys.path.insert(0, str(GEN_OBJECTS_DIR))
    spec = importlib.util.spec_from_file_location("gen_objects", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_engine_io -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add art_kit tests
git commit -m "art kit: import bridge to gen_objects"
```

---

### Task 2: The drawing model — grid, palette, paint, erase

**Files:**
- Create: `art_kit/model.py`
- Create: `tests/test_model.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `Palette(d, m, l, centre, rim, plant_rim)` — a frozen dataclass of six hex strings without `#`; `Palette.colors()` returns `dict[str, tuple[int,int,int,int]]` for the nine letters.
  - `Drawing(name, species, model, cells, palette, kind)` where `cells` is `list[list[str | tuple[int,int,int,int] | None]]`, `kind` is `"letters"` or `"pixels"`.
  - `Drawing.blank(width, height, palette)`, `.width`, `.height`, `.paint(col, row, value)`, `.erase(col, row)`, `.get(col, row)`, `.copy()`, `.is_letters()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_model.py`:

```python
import unittest

from art_kit.model import Drawing, Palette

PAL = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C",
              rim="2E0810", plant_rim="1E5A24")


class PaletteTest(unittest.TestCase):
    def test_nine_letters_resolve_to_rgba(self):
        colors = PAL.colors()
        self.assertEqual(set(colors), set("dmlCxSGko"))
        self.assertEqual(colors["m"], (0xD9, 0x36, 0x45, 255))
        self.assertEqual(colors["x"], (0x2E, 0x08, 0x10, 255))  # bloom seam = rim
        self.assertEqual(colors["o"], (0x1E, 0x5A, 0x24, 255))  # plant seam


class DrawingTest(unittest.TestCase):
    def test_blank_is_empty_at_the_requested_size(self):
        d = Drawing.blank(16, 14, PAL)
        self.assertEqual((d.width, d.height), (16, 14))
        self.assertIsNone(d.get(0, 0))
        self.assertTrue(d.is_letters())

    def test_paint_and_erase_one_cell(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(1, 2, "m")
        self.assertEqual(d.get(1, 2), "m")
        d.erase(1, 2)
        self.assertIsNone(d.get(1, 2))

    def test_painting_a_raw_colour_makes_it_a_pixel_drawing(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(0, 0, (10, 20, 30, 255))
        self.assertFalse(d.is_letters())

    def test_out_of_bounds_paint_is_ignored_not_an_error(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(9, 9, "m")
        d.paint(-1, 0, "m")
        self.assertTrue(d.is_letters())

    def test_copy_does_not_share_rows(self):
        d = Drawing.blank(4, 3, PAL)
        clone = d.copy()
        clone.paint(0, 0, "d")
        self.assertIsNone(d.get(0, 0), "editing the copy must not touch the original")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_model -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'art_kit.model'`

- [ ] **Step 3: Write minimal implementation**

Create `art_kit/model.py`:

```python
"""The drawing itself: a grid of cells, a palette, and nothing that draws.

A cell is one of three things — a palette LETTER, a raw RGBA tuple, or None for
empty. Letters are what the engine stores, so a drawing made entirely of letters
can go back into `_FLOWER_BLOOMS`; one with a raw colour in it can still ship as
a PNG. Keeping both in one grid means the free colour picker is not a second
document format with its own bugs.
"""
from dataclasses import dataclass, field, replace

LETTERS = "dmlCxSGko"
BLOOM_LETTERS = "dmlCx"
PLANT_LETTERS = "SGko"
EMPTY = "."


def hex_to_rgba(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


@dataclass(frozen=True)
class Palette:
    """Six hex strings, the same five the engine keeps plus the plant rim.

    `x` and `o` are seam colours rather than tones of their own: the engine
    reuses the bloom rim for the bloom's interior seams and the plant rim for
    the plant's, so they are derived here instead of stored twice.
    """
    d: str
    m: str
    l: str
    centre: str
    rim: str
    plant_rim: str = "1E5A24"
    # Stem, leaf and vein are shared across every flower in the game.
    stem: str = "3E8E36"
    leaf: str = "5FBF4A"
    vein: str = "2C6E2A"

    def colors(self):
        return {
            "d": hex_to_rgba(self.d),
            "m": hex_to_rgba(self.m),
            "l": hex_to_rgba(self.l),
            "C": hex_to_rgba(self.centre),
            "x": hex_to_rgba(self.rim),
            "S": hex_to_rgba(self.stem),
            "G": hex_to_rgba(self.leaf),
            "k": hex_to_rgba(self.vein),
            "o": hex_to_rgba(self.plant_rim),
        }


@dataclass
class Drawing:
    name: str
    species: str
    model: int
    cells: list
    palette: Palette
    kind: str = "letters"

    @classmethod
    def blank(cls, width, height, palette, name="untitled", species="", model=0):
        cells = [[None] * width for _ in range(height)]
        return cls(name=name, species=species, model=model, cells=cells,
                   palette=palette, kind="letters")

    @property
    def height(self):
        return len(self.cells)

    @property
    def width(self):
        return len(self.cells[0]) if self.cells else 0

    def _inside(self, col, row):
        return 0 <= row < self.height and 0 <= col < self.width

    def get(self, col, row):
        return self.cells[row][col] if self._inside(col, row) else None

    def paint(self, col, row, value):
        if self._inside(col, row):
            self.cells[row][col] = value

    def erase(self, col, row):
        self.paint(col, row, None)

    def is_letters(self):
        return all(c is None or isinstance(c, str)
                   for row in self.cells for c in row)

    def copy(self):
        return replace(self, cells=[list(row) for row in self.cells])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_model -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add art_kit/model.py tests/test_model.py
git commit -m "art kit: drawing model with letter and raw-colour cells"
```

---

### Task 3: Undo and redo

**Files:**
- Modify: `art_kit/model.py`
- Modify: `tests/test_model.py`

**Interfaces:**
- Produces: `History(drawing, limit=200)` with `.begin_stroke()`, `.end_stroke()`, `.undo()`, `.redo()`, `.can_undo()`, `.can_redo()`, `.current` (the live `Drawing`).

**Why a stroke, not a cell:** dragging across ten pixels is one action to the person doing it. Pushing ten entries means ten undos to take it back, which reads as broken.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_model.py`:

```python
from art_kit.model import History


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.h = History(Drawing.blank(4, 3, PAL))

    def _stroke(self, *cells):
        self.h.begin_stroke()
        for col, row, val in cells:
            self.h.current.paint(col, row, val)
        self.h.end_stroke()

    def test_undo_restores_the_grid_before_the_stroke(self):
        self._stroke((0, 0, "d"), (1, 0, "d"))
        self.assertEqual(self.h.current.get(1, 0), "d")
        self.h.undo()
        self.assertIsNone(self.h.current.get(0, 0))
        self.assertIsNone(self.h.current.get(1, 0))

    def test_a_drag_is_one_undo_not_one_per_pixel(self):
        self._stroke((0, 0, "d"), (1, 0, "d"), (2, 0, "d"))
        self.h.undo()
        self.assertFalse(self.h.can_undo())

    def test_redo_puts_it_back_then_stops(self):
        self._stroke((0, 0, "d"))
        self.h.undo()
        self.h.redo()
        self.assertEqual(self.h.current.get(0, 0), "d")
        self.assertFalse(self.h.can_redo())

    def test_undo_at_the_start_and_redo_at_the_end_do_nothing(self):
        self.assertFalse(self.h.can_undo())
        self.h.undo()  # must not raise
        self.h.redo()  # must not raise
        self.assertEqual(self.h.current.get(0, 0), None)

    def test_a_new_stroke_after_an_undo_drops_the_redo_branch(self):
        self._stroke((0, 0, "d"))
        self.h.undo()
        self._stroke((1, 1, "m"))
        self.assertFalse(self.h.can_redo())
        self.assertEqual(self.h.current.get(1, 1), "m")

    def test_a_stroke_that_changed_nothing_is_not_recorded(self):
        self.h.begin_stroke()
        self.h.end_stroke()
        self.assertFalse(self.h.can_undo())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_model -v`
Expected: FAIL — `ImportError: cannot import name 'History'`

- [ ] **Step 3: Write minimal implementation**

Append to `art_kit/model.py`:

```python
class History:
    """Undo/redo over whole-grid snapshots, one entry per STROKE.

    A 16x19 grid is 304 cells — snapshotting it is nothing next to the cost of
    getting a diff-based stack subtly wrong, and a wrong undo loses the artist's
    work. Snapshots it is.
    """

    def __init__(self, drawing, limit=200):
        self.current = drawing
        self._undo = []
        self._redo = []
        self._pending = None
        self._limit = limit

    def begin_stroke(self):
        self._pending = self.current.copy()

    def end_stroke(self):
        if self._pending is None:
            return
        before, self._pending = self._pending, None
        if before.cells == self.current.cells:
            return  # nothing actually moved
        self._undo.append(before)
        del self._undo[:-self._limit]
        self._redo.clear()

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return
        self._redo.append(self.current.copy())
        self.current = self._undo.pop()

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self.current.copy())
        self.current = self._redo.pop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_model -v`
Expected: PASS, 12 tests

- [ ] **Step 5: Commit**

```bash
git add art_kit/model.py tests/test_model.py
git commit -m "art kit: stroke-level undo and redo"
```

---

### Task 4: Importing the shipped flowers

**Files:**
- Modify: `art_kit/engine_io.py`
- Modify: `tests/test_engine_io.py`

**Interfaces:**
- Consumes: `Drawing`, `Palette` from Task 2.
- Produces:
  - `engine_io.SPECIES` — the ordered list of 12 flower ids.
  - `engine_io.import_flower(species, model) -> Drawing`
  - `engine_io.import_all() -> list[Drawing]` (24 drawings, species order, model 0 then 1).

**Rose note:** `gul` is not in `_FLOWER_BLOOMS`. Its bloom and stem are separate arrays composed at a row offset, and they collide at two cells (`v0` row 11, `v1` row 9, columns 7–8), so it cannot become one letter grid. It imports as a raw-pixel drawing built from `rose_variant(v)` — the already-composed RGBA grid — which is exactly what gets written to disk anyway.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_io.py`:

```python
from art_kit.model import Drawing


class ImportFlowersTest(unittest.TestCase):
    def test_twelve_species_two_models_each(self):
        drawings = engine_io.import_all()
        self.assertEqual(len(drawings), 24)
        self.assertEqual(len(engine_io.SPECIES), 12)
        self.assertIn("gul", engine_io.SPECIES)
        self.assertIn("lale", engine_io.SPECIES)

    def test_a_letter_flower_keeps_its_letters_and_size(self):
        d = engine_io.import_flower("lale", 0)
        self.assertIsInstance(d, Drawing)
        self.assertEqual(d.kind, "letters")
        self.assertEqual(d.width, 16)
        self.assertTrue(d.is_letters())
        self.assertIn("m", {c for row in d.cells for c in row})

    def test_the_letters_match_the_engines_own_grid(self):
        g = engine_io.gen_objects()
        rows = g._FLOWER_BLOOMS["lale"][0]
        d = engine_io.import_flower("lale", 0)
        self.assertEqual(d.height, len(rows))
        for r, line in enumerate(rows):
            for c in range(16):
                expected = line[c] if c < len(line) and line[c] != "." else None
                self.assertEqual(d.get(c, r), expected, f"cell {c},{r}")

    def test_the_palette_comes_from_the_engine(self):
        g = engine_io.gen_objects()
        d, m, l, centre, rim = g._FLOWER_PALS["lale"]
        pal = engine_io.import_flower("lale", 0).palette
        self.assertEqual((pal.d, pal.m, pal.l, pal.centre, pal.rim), (d, m, l, centre, rim))

    def test_the_cactuses_use_their_own_green_plant_rim(self):
        self.assertEqual(engine_io.import_flower("kaktusf", 0).palette.plant_rim, "1E5A24")

    def test_the_rose_imports_as_raw_pixels(self):
        d = engine_io.import_flower("gul", 0)
        self.assertEqual(d.kind, "pixels")
        self.assertFalse(d.is_letters())
        self.assertEqual(d.width, 16)
        opaque = [c for row in d.cells for c in row if c is not None]
        self.assertTrue(opaque, "the rose should not import blank")
        self.assertTrue(all(isinstance(c, tuple) and len(c) == 4 for c in opaque))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_io -v`
Expected: FAIL — `AttributeError: module 'art_kit.engine_io' has no attribute 'import_all'`

- [ ] **Step 3: Write minimal implementation**

Append to `art_kit/engine_io.py` (and add `from art_kit.model import Drawing, Palette` at the top):

```python
# Catalogue order — the rose first, the way the shop lists them.
SPECIES = ["gul", "papatya", "lale", "kaktus", "kaktusf", "kaktusd",
           "kasimpati", "menekse", "nilufer", "orkide", "begonya", "kamelya"]


def _palette_for(species):
    g = gen_objects()
    if species == "gul":
        # The rose predates _FLOWER_PALS and keeps its tones in _ROSE_PAL as
        # RGBA. Rebuild the hex form so the editor can show real swatches.
        def hexof(letter):
            r, gg, b, _ = g._ROSE_PAL[letter]
            return f"{r:02X}{gg:02X}{b:02X}"
        return Palette(d=hexof("d"), m=hexof("m"), l=hexof("l"),
                       centre="F2C94C", rim=g._ROSE_RED_OL,
                       plant_rim=g._ROSE_GRN_OL)
    d, m, l, centre, rim = g._FLOWER_PALS[species]
    return Palette(d=d, m=m, l=l, centre=centre, rim=rim,
                   plant_rim=g._PLANT_OL.get(species, g._ROSE_GRN_OL))


def import_flower(species, model):
    """One shipped model as an editable drawing."""
    g = gen_objects()
    palette = _palette_for(species)
    name = f"{species}_{model}"
    if species == "gul":
        grid = g.rose_variant(model)  # already outlined and composited
        cells = [[px if px[3] else None for px in row] for row in grid]
        return Drawing(name=name, species=species, model=model, cells=cells,
                       palette=palette, kind="pixels")
    rows = g._FLOWER_BLOOMS[species][model]
    cells = []
    for line in rows:
        row = []
        for c in range(16):
            ch = line[c] if c < len(line) else "."
            row.append(ch if ch != "." else None)
        cells.append(row)
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette, kind="letters")


def import_all():
    return [import_flower(s, v) for s in SPECIES for v in (0, 1)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_engine_io -v`
Expected: PASS, 8 tests

- [ ] **Step 5: Commit**

```bash
git add art_kit/engine_io.py tests/test_engine_io.py
git commit -m "art kit: import the 24 shipped flower models"
```

---

### Task 5: Rendering a drawing the way the engine does

**Files:**
- Modify: `art_kit/engine_io.py`
- Modify: `tests/test_engine_io.py`

**Interfaces:**
- Produces: `engine_io.render(drawing) -> list[list[tuple]]` — the composed RGBA grid at 1×, rims included.

**How it works:** letters split into two layers by class exactly as `flower_variant()` does — `dmlCx` to the bloom, `SGko` to the plant — each is outlined in its own rim, then composited plant-behind-bloom. A raw-pixel drawing is already composed, so it renders as itself.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_io.py`:

```python
class RenderTest(unittest.TestCase):
    def test_a_letter_flower_renders_exactly_like_the_engine(self):
        g = engine_io.gen_objects()
        for species in ("lale", "papatya", "kasimpati", "kaktusf"):
            for model in (0, 1):
                with self.subTest(species=species, model=model):
                    mine = engine_io.render(engine_io.import_flower(species, model))
                    self.assertEqual(mine, g.flower_variant(species, model))

    def test_the_rose_renders_exactly_like_the_engine(self):
        g = engine_io.gen_objects()
        for model in (0, 1):
            mine = engine_io.render(engine_io.import_flower("gul", model))
            self.assertEqual(mine, g.rose_variant(model))

    def test_an_empty_drawing_renders_fully_transparent(self):
        from art_kit.model import Drawing, Palette
        pal = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C", rim="2E0810")
        grid = engine_io.render(Drawing.blank(16, 4, pal))
        self.assertTrue(all(px == (0, 0, 0, 0) for row in grid for px in row))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_io -v`
Expected: FAIL — `AttributeError: module 'art_kit.engine_io' has no attribute 'render'`

- [ ] **Step 3: Write minimal implementation**

Append to `art_kit/engine_io.py` (and add `from art_kit.model import BLOOM_LETTERS, PLANT_LETTERS` to the imports):

```python
def render(drawing):
    """The drawing as the garden will draw it: rims added, layers composited.

    This is `flower_variant()`'s body with the grid coming from the editor
    instead of `_FLOWER_BLOOMS`, so the preview cannot disagree with the export.
    """
    g = gen_objects()
    w, h = drawing.width, drawing.height
    colors = drawing.palette.colors()
    bloom = g.blank(w, h)
    plant = g.blank(w, h)
    raw = g.blank(w, h)
    for r in range(h):
        for c in range(w):
            cell = drawing.cells[r][c]
            if cell is None:
                continue
            if isinstance(cell, tuple):
                raw[r][c] = cell
            elif cell in BLOOM_LETTERS:
                bloom[r][c] = colors[cell]
            elif cell in PLANT_LETTERS:
                plant[r][c] = colors[cell]
    bloom = g.outline(bloom, drawing.palette.rim)
    plant = g.outline(plant, drawing.palette.plant_rim)
    return g._rose_compose([plant, bloom, raw])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_engine_io -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add art_kit/engine_io.py tests/test_engine_io.py
git commit -m "art kit: render a drawing through the engine's own compositing"
```

---

### Task 6: Exports — PNG, JPG, engine sprite, grid literal

**Files:**
- Modify: `art_kit/engine_io.py`
- Modify: `tests/test_engine_io.py`

**Interfaces:**
- Produces:
  - `engine_io.export_png(drawing, path, scale=16)`
  - `engine_io.export_jpg(drawing, path, scale=16, background=(255, 255, 255))`
  - `engine_io.export_engine_sprite(drawing, out_dir) -> list[Path]` — writes `flower_<species>_<model>.png`, plus `flower_<species>.png` when model is 0.
  - `engine_io.export_grid_literal(drawing) -> str`
  - `engine_io.ExportRefused` — raised with a readable reason.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_io.py` (add `import tempfile`, `from pathlib import Path` at the top):

```python
class ExportTest(unittest.TestCase):
    ASSETS = Path(r"C:\Users\claude\pixel_pomo\flutter\assets\objects")

    def test_an_untouched_flower_exports_byte_for_byte_as_shipped(self):
        for species, model in (("lale", 0), ("papatya", 1), ("gul", 0)):
            with self.subTest(species=species, model=model):
                shipped = (self.ASSETS / f"flower_{species}_{model}.png").read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    written = engine_io.export_engine_sprite(
                        engine_io.import_flower(species, model), Path(tmp))
                    mine = (Path(tmp) / f"flower_{species}_{model}.png").read_bytes()
                self.assertEqual(mine, shipped)
                self.assertTrue(written)

    def test_model_zero_also_writes_the_shop_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine_io.export_engine_sprite(engine_io.import_flower("lale", 0), Path(tmp))
            thumb = (Path(tmp) / "flower_lale.png").read_bytes()
            shipped = (self.ASSETS / "flower_lale.png").read_bytes()
        self.assertEqual(thumb, shipped)

    def test_model_one_does_not_overwrite_the_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine_io.export_engine_sprite(engine_io.import_flower("lale", 1), Path(tmp))
            self.assertFalse((Path(tmp) / "flower_lale.png").exists())

    def test_engine_export_refuses_a_grid_that_is_not_16_wide(self):
        from art_kit.model import Drawing
        d = engine_io.import_flower("lale", 0)
        narrow = Drawing.blank(12, 4, d.palette, species="lale")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(engine_io.ExportRefused):
                engine_io.export_engine_sprite(narrow, Path(tmp))

    def test_png_export_writes_a_readable_file_at_the_asked_scale(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.png"
            engine_io.export_png(d, out, scale=8)
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.size, (16 * 8, d.height * 8))
                self.assertEqual(im.mode, "RGBA")

    def test_jpg_export_flattens_onto_the_given_background(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.jpg"
            engine_io.export_jpg(d, out, scale=4, background=(255, 0, 0))
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.mode, "RGB")
                self.assertEqual(im.getpixel((0, 0)), (254, 0, 0))  # JPEG is lossy

    def test_grid_literal_round_trips_through_the_engines_own_format(self):
        g = engine_io.gen_objects()
        text = engine_io.export_grid_literal(engine_io.import_flower("lale", 0))
        rows = [line.strip().strip(",").strip('"') for line in text.splitlines() if '"' in line]
        self.assertEqual(rows, list(g._FLOWER_BLOOMS["lale"][0]))

    def test_grid_literal_is_refused_for_a_raw_pixel_drawing(self):
        with self.assertRaises(engine_io.ExportRefused):
            engine_io.export_grid_literal(engine_io.import_flower("gul", 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_io -v`
Expected: FAIL — `AttributeError: module 'art_kit.engine_io' has no attribute 'ExportRefused'`

- [ ] **Step 3: Write minimal implementation**

Append to `art_kit/engine_io.py`:

```python
class ExportRefused(Exception):
    """Raised instead of writing a file the engine could not use."""


def _scaled(drawing, scale):
    return gen_objects().upscale(render(drawing), scale)


def export_png(drawing, path, scale=16):
    gen_objects().write_png(str(path), _scaled(drawing, scale))
    return Path(path)


def export_jpg(drawing, path, scale=16, background=(255, 255, 255)):
    """JPEG has no alpha, so transparency is flattened onto `background`.

    The caller is told which colour that was rather than the app quietly
    picking one and the artist finding a white halo later.
    """
    from PIL import Image
    grid = _scaled(drawing, scale)
    h, w = len(grid), len(grid[0])
    rgba = Image.new("RGBA", (w, h))
    rgba.putdata([px for row in grid for px in row])
    flat = Image.new("RGB", (w, h), background)
    flat.paste(rgba, mask=rgba.split()[3])
    flat.save(str(path), "JPEG", quality=95, subsampling=0)
    return Path(path)


def export_engine_sprite(drawing, out_dir):
    """Write the sprite(s) the garden loads: ×16, RGBA, engine naming."""
    if drawing.width != 16:
        raise ExportRefused(
            f"engine sprites are 16 cells wide, this drawing is {drawing.width}")
    if not drawing.species:
        raise ExportRefused("give the drawing a species before exporting it")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    big = _scaled(drawing, 16)
    written = [out_dir / f"flower_{drawing.species}_{drawing.model}.png"]
    if drawing.model == 0:
        # model 0 doubles as the shop thumbnail, exactly as gen_objects does it
        written.append(out_dir / f"flower_{drawing.species}.png")
    for path in written:
        gen_objects().write_png(str(path), big)
    return written


def export_grid_literal(drawing):
    """The rows as Python source, ready to paste into _FLOWER_BLOOMS."""
    if not drawing.is_letters():
        raise ExportRefused(
            "this drawing has raw colours in it, so it has no letter grid — "
            "export it as a PNG instead")
    lines = [f"[  # {drawing.species} model {drawing.model}"]
    for row in drawing.cells:
        lines.append('    "' + "".join(c if c else "." for c in row) + '",')
    lines.append("],")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_engine_io -v`
Expected: PASS, 19 tests. The byte-for-byte case is the one that matters — if it fails, the bridge is wrong and no later task can paper over it.

- [ ] **Step 5: Commit**

```bash
git add art_kit/engine_io.py tests/test_engine_io.py
git commit -m "art kit: PNG, JPG, engine sprite and grid-literal export"
```

---

### Task 7: The library on disk

**Files:**
- Create: `art_kit/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Produces:
  - `store.to_dict(drawing) -> dict` / `store.from_dict(data) -> Drawing`
  - `store.save(drawing, path)` / `store.load(path)`
  - `store.Library(root)` with `.drawings` (list), `.load_all()`, `.add(drawing)`, `.remove(drawing)`, `.save(drawing)`, `.duplicate(drawing) -> Drawing`, `.seed_from_engine()`.
  - `store.CorruptDrawing` — raised by `from_dict` on unusable data.

**Format:** one JSON per drawing. Rows are strings when the drawing is all letters (readable and diffable, same shape as the engine's own source) and lists of `[r,g,b,a]` or `null` when it is not.

- [ ] **Step 1: Write the failing test**

Create `tests/test_store.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from art_kit import engine_io, store
from art_kit.model import Drawing, Palette

PAL = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C", rim="2E0810")


class CodecTest(unittest.TestCase):
    def test_a_letter_drawing_round_trips(self):
        original = engine_io.import_flower("lale", 0)
        clone = store.from_dict(store.to_dict(original))
        self.assertEqual(clone.cells, original.cells)
        self.assertEqual(clone.palette, original.palette)
        self.assertEqual((clone.species, clone.model, clone.kind),
                         ("lale", 0, "letters"))

    def test_a_letter_drawing_is_stored_as_readable_rows(self):
        data = store.to_dict(engine_io.import_flower("lale", 0))
        self.assertIsInstance(data["cells"][0], str)
        self.assertEqual(len(data["cells"][0]), 16)

    def test_a_raw_pixel_drawing_round_trips(self):
        original = engine_io.import_flower("gul", 0)
        clone = store.from_dict(store.to_dict(original))
        self.assertEqual(clone.cells, original.cells)
        self.assertEqual(clone.kind, "pixels")

    def test_a_mixed_drawing_round_trips(self):
        d = engine_io.import_flower("lale", 0)
        d.paint(0, 0, (1, 2, 3, 255))
        clone = store.from_dict(store.to_dict(d))
        self.assertEqual(clone.get(0, 0), (1, 2, 3, 255))
        self.assertEqual(clone.get(7, 1), d.get(7, 1))

    def test_missing_fields_raise_something_the_app_can_report(self):
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict({"name": "x"})

    def test_a_ragged_grid_is_refused_rather_than_half_loaded(self):
        data = store.to_dict(engine_io.import_flower("lale", 0))
        data["cells"][2] = "dm"
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = store.Library(Path(self.tmp.name))

    def test_seeding_writes_all_twenty_four_models(self):
        self.lib.seed_from_engine()
        self.assertEqual(len(self.lib.drawings), 24)
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.json"))), 24)

    def test_seeding_twice_does_not_duplicate(self):
        self.lib.seed_from_engine()
        self.lib.seed_from_engine()
        self.assertEqual(len(self.lib.drawings), 24)

    def test_reopening_the_library_finds_what_was_saved(self):
        self.lib.seed_from_engine()
        again = store.Library(Path(self.tmp.name))
        again.load_all()
        self.assertEqual(len(again.drawings), 24)

    def test_duplicate_makes_an_independent_copy_with_a_new_name(self):
        d = self.lib.add(Drawing.blank(16, 4, PAL, name="rose sketch", species="lale"))
        copy = self.lib.duplicate(d)
        self.assertNotEqual(copy.name, d.name)
        copy.paint(0, 0, "m")
        self.assertIsNone(d.get(0, 0))
        self.assertEqual(len(self.lib.drawings), 2)

    def test_remove_deletes_the_file_too(self):
        d = self.lib.add(Drawing.blank(16, 4, PAL, name="gone", species="lale"))
        self.lib.remove(d)
        self.assertEqual(self.lib.drawings, [])
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])

    def test_two_drawings_with_the_same_name_get_separate_files(self):
        self.lib.add(Drawing.blank(16, 4, PAL, name="same", species="lale"))
        self.lib.add(Drawing.blank(16, 4, PAL, name="same", species="lale"))
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.json"))), 2)

    def test_a_corrupt_file_is_skipped_not_fatal(self):
        self.lib.seed_from_engine()
        (Path(self.tmp.name) / "broken.json").write_text("{ not json", encoding="utf-8")
        again = store.Library(Path(self.tmp.name))
        skipped = again.load_all()
        self.assertEqual(len(again.drawings), 24)
        self.assertEqual(len(skipped), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_store -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'art_kit.store'`

- [ ] **Step 3: Write minimal implementation**

Create `art_kit/store.py`:

```python
"""Drawings on disk: one JSON file each.

Readable on purpose. If the app ever writes something wrong, the artist's work
is still sitting there in a text file they can open, which is not true of a
binary blob or a database.
"""
import json
import re
from dataclasses import asdict
from pathlib import Path

from art_kit.model import Drawing, Palette

FORMAT = 1


class CorruptDrawing(Exception):
    """A file that cannot be turned back into a drawing."""


def to_dict(drawing):
    if drawing.is_letters():
        cells = ["".join(c if c else "." for c in row) for row in drawing.cells]
    else:
        cells = [[list(c) if isinstance(c, tuple) else c for c in row]
                 for row in drawing.cells]
    return {
        "format": FORMAT,
        "name": drawing.name,
        "species": drawing.species,
        "model": drawing.model,
        "kind": drawing.kind,
        "palette": asdict(drawing.palette),
        "cells": cells,
    }


def from_dict(data):
    try:
        palette = Palette(**data["palette"])
        raw = data["cells"]
        name, species, model = data["name"], data["species"], data["model"]
    except (KeyError, TypeError) as exc:
        raise CorruptDrawing(f"missing or malformed field: {exc}") from exc
    if not raw:
        raise CorruptDrawing("no cells")
    cells = []
    for row in raw:
        if isinstance(row, str):
            cells.append([ch if ch != "." else None for ch in row])
        else:
            cells.append([tuple(c) if isinstance(c, list) else c for c in row])
    width = len(cells[0])
    if any(len(row) != width for row in cells):
        raise CorruptDrawing("rows are not all the same length")
    kind = data.get("kind", "letters")
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette, kind=kind)


def save(drawing, path):
    Path(path).write_text(json.dumps(to_dict(drawing), indent=1), encoding="utf-8")


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise CorruptDrawing(f"{path}: {exc}") from exc
    return from_dict(data)


def _slug(text):
    return re.sub(r"[^a-z0-9_-]+", "_", text.lower()).strip("_") or "drawing"


class Library:
    """The drawings folder. Knows nothing about widgets."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.drawings = []
        self._paths = {}

    def load_all(self):
        """Returns the files it could NOT read, so the app can say so."""
        self.drawings, self._paths, skipped = [], {}, []
        for path in sorted(self.root.glob("*.json")):
            try:
                drawing = load(path)
            except CorruptDrawing:
                skipped.append(path)
                continue
            self.drawings.append(drawing)
            self._paths[id(drawing)] = path
        return skipped

    def _free_path(self, drawing):
        base = _slug(f"{drawing.species}_{drawing.model}_{drawing.name}")
        path = self.root / f"{base}.json"
        n = 2
        while path.exists():
            path = self.root / f"{base}-{n}.json"
            n += 1
        return path

    def add(self, drawing):
        path = self._free_path(drawing)
        self._paths[id(drawing)] = path
        self.drawings.append(drawing)
        save(drawing, path)
        return drawing

    def save(self, drawing):
        save(drawing, self._paths[id(drawing)])

    def remove(self, drawing):
        path = self._paths.pop(id(drawing), None)
        if path and path.exists():
            path.unlink()
        if drawing in self.drawings:
            self.drawings.remove(drawing)

    def duplicate(self, drawing):
        clone = drawing.copy()
        clone.name = f"{drawing.name} copy"
        return self.add(clone)

    def seed_from_engine(self):
        """Fill an empty library with the shipped flowers. No-op if not empty."""
        if self.drawings:
            return self.drawings
        from art_kit import engine_io
        for drawing in engine_io.import_all():
            self.add(drawing)
        return self.drawings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_store -v`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add art_kit/store.py tests/test_store.py
git commit -m "art kit: JSON library on disk, seeded from the engine"
```

---

### Task 8: The window

**Files:**
- Create: `art_kit/app.py`
- Create: `art_kit/__main__.py`
- Create: `tests/test_app_smoke.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `app.ArtKitApp(root, library)` with `.select(drawing)`, `.on_canvas_press(col, row)`, `.on_canvas_drag(col, row)`, `.on_canvas_release()`, `.set_tool(name)`, `.set_ink(value)`, `.undo()`, `.redo()`, `.zoom(delta)`, and `.tool`, `.ink`, `.zoom_level`, `.history` as readable state.

**Why those methods exist:** the pointer handlers take grid coordinates, not tkinter events, so the whole interaction can be tested without a window. The event bindings only convert pixels to cells and call these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_smoke.py`:

```python
import tempfile
import unittest
from pathlib import Path

from art_kit import app, store


def _tk_or_skip():
    import tkinter
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:  # no display
        raise unittest.SkipTest(f"no Tk display: {exc}")
    root.withdraw()
    return root


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.root = _tk_or_skip()
        self.addCleanup(self.root.destroy)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = store.Library(Path(self.tmp.name))
        self.lib.seed_from_engine()
        self.ui = app.ArtKitApp(self.root, self.lib)

    def test_it_opens_on_the_first_drawing_with_all_twenty_four_listed(self):
        self.assertEqual(len(self.lib.drawings), 24)
        self.assertIsNotNone(self.ui.history.current)

    def test_a_drag_paints_a_run_of_cells_and_undoes_as_one(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_drag(1, 0)
        self.ui.on_canvas_drag(2, 0)
        self.ui.on_canvas_release()
        current = self.ui.history.current
        self.assertEqual([current.get(c, 0) for c in (0, 1, 2)], ["m", "m", "m"])
        self.ui.undo()
        self.assertNotEqual(self.ui.history.current.get(0, 0), "m")

    def test_the_eraser_clears_a_cell(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(3, 3)
        self.ui.on_canvas_release()
        self.ui.set_tool("erase")
        self.ui.on_canvas_press(3, 3)
        self.ui.on_canvas_release()
        self.assertIsNone(self.ui.history.current.get(3, 3))

    def test_switching_drawings_keeps_the_edit_on_the_first_one(self):
        first, second = self.lib.drawings[1], self.lib.drawings[2]
        self.ui.select(first)
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_release()
        self.ui.select(second)
        self.ui.select(first)
        self.assertEqual(self.ui.history.current.get(0, 0), "m")

    def test_zoom_stays_inside_its_limits(self):
        for _ in range(50):
            self.ui.zoom(+1)
        self.assertLessEqual(self.ui.zoom_level, app.MAX_ZOOM)
        for _ in range(100):
            self.ui.zoom(-1)
        self.assertGreaterEqual(self.ui.zoom_level, app.MIN_ZOOM)

    def test_a_raw_colour_ink_turns_a_letter_drawing_into_a_pixel_one(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.set_tool("draw")
        self.ui.set_ink((10, 20, 30, 255))
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_release()
        self.assertFalse(self.ui.history.current.is_letters())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_app_smoke -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'art_kit.app'`

- [ ] **Step 3: Write minimal implementation**

Create `art_kit/app.py`. Build it in this order — the three panes, then the bindings:

```python
"""The window. Three panes: the library, the canvas, the tools.

Pointer handling is deliberately split — `on_canvas_*` take GRID coordinates and
carry all the behaviour, while the tkinter bindings do nothing but turn a pixel
position into a cell. That is what lets the interaction be tested without a
display, and it keeps the interesting code out of the event handlers.
"""
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox
from pathlib import Path

from art_kit import engine_io, store
from art_kit.model import Drawing, History, LETTERS, Palette

MIN_ZOOM, MAX_ZOOM = 4, 48
DEFAULT_ZOOM = 20
CHECKER = ("#2b2b2b", "#343434")

# The nine palette slots, in the order an artist reaches for them.
SLOTS = [("d", "dark"), ("m", "mid"), ("l", "light"), ("C", "centre"),
         ("x", "bloom seam"), ("S", "stem"), ("G", "leaf"), ("k", "vein"),
         ("o", "plant seam")]

# The app's own ready colours, from Pixel Pomo's themes.
READY = ["FF5A5F", "F2C94C", "5FBF4A", "3E8E36", "8E4FE0", "E02C6D",
         "F7EFDD", "1E1E2E", "CDD6F4", "FFFFFF"]


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
        root.title("Pixel Pomo Art Kit")
        self._build()
        if library.drawings:
            self.select(library.drawings[0])

    # ---- state ---------------------------------------------------------
    def select(self, drawing):
        self.history = self._histories.setdefault(id(drawing), History(drawing))
        self._refresh_list()
        self._redraw()

    def set_tool(self, name):
        self.tool = name

    def set_ink(self, value):
        self.ink = value

    def zoom(self, delta):
        self.zoom_level = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom_level + delta * 2))
        self._redraw()

    def undo(self):
        self.history.undo()
        self._after_change()

    def redo(self):
        self.history.redo()
        self._after_change()

    # ---- pointer, in GRID coordinates ----------------------------------
    def on_canvas_press(self, col, row):
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
        self.library.save(self.history.current)
        self._refresh_list()
        self._redraw()
```

Then the panes, in the same file:

- `_build()` lays out three `tk.Frame`s in a row — library (width 220), canvas (expanding), tools (width 200).
- **Library pane:** a scrollable `tk.Frame` of rows; each row is the drawing's name, a small preview `tk.Canvas`, and a `⋮` `tk.Menubutton` whose menu has Duplicate / Export PNG… / Export JPG… / Export engine sprite… / Copy grid literal / Rename… / Delete. `+ NEW DRAWING` sits at the bottom and calls `_new_drawing()`, which adds `Drawing.blank(16, 16, palette_of_the_selected_species)`.
- **Canvas pane:** a `tk.Canvas`; `_redraw()` clears it and draws the checkerboard, then one rectangle per opaque cell of `engine_io.render(self.history.current)`, then 1px grid lines when `zoom_level >= 8`. Bindings: `<Button-1>` → `on_canvas_press`, `<B1-Motion>` → `on_canvas_drag`, `<ButtonRelease-1>` → `on_canvas_release`, `<MouseWheel>` → `zoom(+1/-1)`. Convert with `col = event.x // self.zoom_level`. Beside it draw the same render at 1× and at an 8×8 box downscale — the squint test.
- **Tools pane:** DRAW / ERASE buttons that call `set_tool`; UNDO / REDO calling `undo`/`redo`; the nine palette slots as coloured buttons calling `set_ink(letter)`; the ready colours as small squares calling `set_ink(hex_to_rgba(...))`; a `PICK COLOUR…` button opening `colorchooser.askcolor` and calling `set_ink` with the result.
- Keyboard: `<Control-z>` → undo, `<Control-y>` and `<Control-Shift-Z>` → redo, `e`/`b` → erase/draw, `+`/`-` → zoom.
- Exports use `filedialog.asksaveasfilename` (PNG/JPG) or `filedialog.askdirectory` (engine sprite, defaulting to `pixel_pomo\flutter\assets\objects`), wrapped in try/except on `engine_io.ExportRefused` → `messagebox.showerror(str(exc))`. The engine export confirms with `messagebox.askyesno` naming the exact files it will overwrite.

Create `art_kit/__main__.py`:

```python
"""python -m art_kit"""
import tkinter as tk
from pathlib import Path

from art_kit import store
from art_kit.app import ArtKitApp

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def main():
    library = store.Library(LIBRARY)
    skipped = library.load_all()
    library.seed_from_engine()
    root = tk.Tk()
    root.geometry("1280x820")
    ArtKitApp(root, library)
    if skipped:
        from tkinter import messagebox
        messagebox.showwarning(
            "Pixel Pomo Art Kit",
            f"{len(skipped)} drawing file(s) could not be read and were skipped.")
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests and the app**

Run: `python -m unittest tests.test_app_smoke -v`
Expected: PASS, 6 tests

Run: `python -m art_kit`
Expected: the window opens with 24 flowers listed, clicking one shows it, painting works, undo works, zoom works. Fix what does not before committing.

- [ ] **Step 5: Commit**

```bash
git add art_kit/app.py art_kit/__main__.py tests/test_app_smoke.py
git commit -m "art kit: the window - library, canvas, tools"
```

---

### Task 9: Documentation

**Files:**
- Create: `README.md`, `prompt.md`, `log.md`, `TESTING.md`

**Interfaces:** none.

- [ ] **Step 1: Write the four documents**

`README.md` — what it is, one screenshot-shaped description of the three panes, how to run it (`python -m art_kit`), what the exports mean and which one to hand back to the developer, and the one thing an artist must know: engine sprites are 16 cells wide and the palette letters are what makes a drawing bakeable.

`prompt.md` — the recreation prompt, in the shape Pixel Pomo's uses: a single quoted block describing the app well enough to rebuild it, then dated `## vN update` sections newest-first.

`log.md` — the round entry: date, the user's prompt in Turkish, what was built, the test count.

`TESTING.md` — how to run (`python -m unittest discover -s tests -v`), the count, a table of what each test file covers, and an explicit "not covered" section: how the window looks, whether tkinter behaves the same on another Windows machine, and the fact that `test_app_smoke` skips itself where there is no display.

- [ ] **Step 2: Verify the commands in the docs actually work**

Run: `python -m unittest discover -s tests -v`
Expected: PASS, 45+ tests. Put the real number in the docs, not an estimate.

- [ ] **Step 3: Commit**

```bash
git add README.md prompt.md log.md TESTING.md
git commit -m "art kit: README, prompt, log, testing notes"
```

---

### Task 10: Publish

**Files:** none.

- [ ] **Step 1: Confirm the whole suite is green from a clean state**

Run: `python -m unittest discover -s tests -v`
Expected: all pass, zero errors.

- [ ] **Step 2: Create the GitHub repository and push**

```bash
gh repo create pixel_pomo_art_kit --private --source=. --remote=origin --push
```

- [ ] **Step 3: Confirm it landed**

```bash
gh repo view pixel_pomo_art_kit --json name,visibility,defaultBranchRef
git --no-pager log --oneline -3
```

Expected: the repository exists, is private, and `main` matches local.

---

## Self-review notes

- **Spec coverage:** left pane with `+` and `⋮` (Task 8), canvas with click-to-place and zoom (Task 8), right pane with palette + free colour + draw/erase + undo/redo (Tasks 3, 8), all flower models loaded (Task 4), duplicate (Task 7), PNG/JPG/engine-sprite export (Task 6), four md files (Task 9), own repository (Tasks 1–10, published in 10). The 8×8 squint test and the live engine preview are in Task 8's canvas pane.
- **Deliberately absent:** PyInstaller packaging, layers, fill, eyedropper, editing non-flower objects. All listed as out of scope in the spec.
- **The load-bearing test** is Task 6's byte-for-byte comparison. If it ever fails, the app is lying about what it produces — treat it as a stop-work, not a flaky test.
