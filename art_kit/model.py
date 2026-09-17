"""The drawing itself: a grid of cells, a palette, and nothing that draws.

A cell is one of three things — a palette LETTER, a raw RGBA tuple, or None for
empty. Letters are what the engine stores, so a drawing made entirely of letters
can go back into `_FLOWER_BLOOMS`; one with a raw colour in it can still ship as
a PNG. Keeping both in one grid means the free colour picker is not a second
document format with its own bugs.
"""
from dataclasses import dataclass, replace

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
    # The artist's own tag — "flower", "tree", "wip", anything (#v2.6.0).
    # Free text, filterable in the library; nothing engine-side reads it.
    label: str = ""

    @classmethod
    def blank(cls, width, height, palette, name="untitled", species="", model=0, label=""):
        cells = [[None] * width for _ in range(height)]
        return cls(name=name, species=species, model=model, cells=cells,
                   palette=palette, label=label)

    def count(self):
        """How many cells are painted."""
        return sum(1 for row in self.cells for c in row if c is not None)

    def row_count(self, row):
        return sum(1 for c in self.cells[row] if c is not None) if 0 <= row < self.height else 0

    def col_count(self, col):
        if not (0 <= col < self.width):
            return 0
        return sum(1 for r in self.cells if r[col] is not None)

    def region(self, c0, r0, c1, r1):
        """A copy of the cells in the inclusive rectangle, clipped to the
        grid, as (cells, width, height). Rows/cols outside come back as None."""
        c0, c1 = sorted((c0, c1))
        r0, r1 = sorted((r0, r1))
        out = [[self.get(c, r) for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]
        return out, c1 - c0 + 1, r1 - r0 + 1

    def stamp(self, cells, col, row, skip_empty=True):
        """Paint a block of cells with its top-left at (col, row). Empty
        cells in the block leave the drawing alone unless `skip_empty` is
        False. Cells that fall outside the grid are dropped."""
        for dr, line in enumerate(cells):
            for dc, value in enumerate(line):
                if value is None and skip_empty:
                    continue
                self.paint(col + dc, row + dr, value)

    def clear_region(self, c0, r0, c1, r1):
        c0, c1 = sorted((c0, c1))
        r0, r1 = sorted((r0, r1))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                self.erase(c, r)

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

    def flood(self, col, row, value):
        """Fill the connected region of cells equal to the start cell."""
        if not self._inside(col, row):
            return
        target = self.cells[row][col]
        if target == value:
            return
        stack = [(col, row)]
        while stack:
            c, r = stack.pop()
            if not self._inside(c, r) or self.cells[r][c] != target:
                continue
            self.cells[r][c] = value
            stack.extend([(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)])

    def resize(self, cols, rows):
        """Pad with empty cells right/below, or crop right/below. Engine
        flowers stay 16 wide; trees and pets to come get whatever they need."""
        cols, rows = max(1, cols), max(1, rows)
        for row in self.cells:
            while len(row) < cols:
                row.append(None)
            del row[cols:]
        while len(self.cells) < rows:
            self.cells.append([None] * cols)
        del self.cells[rows:]

    def is_letters(self):
        return all(c is None or isinstance(c, str)
                   for row in self.cells for c in row)

    @property
    def kind(self):
        """Derived, never stored: 'pixels' the moment a raw colour lands, else
        'letters'. A function of the cells can't fall out of sync the way a
        hand-updated field would."""
        return "letters" if self.is_letters() else "pixels"

    def copy(self):
        return replace(self, cells=[list(row) for row in self.cells])


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

    def repaint(self, palette):
        """A palette edit is not a stroke: apply it to the live drawing AND
        every snapshot, so an undo never silently reverts the colours."""
        self.current.palette = palette
        for snap in self._undo + self._redo:
            snap.palette = palette
        if self._pending is not None:
            self._pending.palette = palette

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
