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
    # The artist's own tag — "flower", "tree", "wip", anything (#v2.6.0).
    # Free text, filterable in the library; nothing engine-side reads it.
    label: str = ""
    # Who drew it (#v2.8.0): a layer of its own beside the label, so "tree"
    # and "Mir" never compete for the one tag. Saved; empty until someone
    # says. The library shows the initial in the artist's own colour.
    artist: str = ""
    # How far this session's LEFT and TOP edge drags have pushed the art
    # right and down, in cells (#v2.8.0). Never saved and never compared: it
    # travels with the undo snapshots only so that an undo putting those
    # columns back can tell the window how far the art just moved, and the
    # view can move with it instead of letting the drawing jump.
    shift: tuple = field(default=(0, 0), compare=False, repr=False)

    @classmethod
    def blank(cls, width, height, palette, name="untitled", species="", model=0, label="",
              artist=""):
        cells = [[None] * width for _ in range(height)]
        return cls(name=name, species=species, model=model, cells=cells,
                   palette=palette, label=label, artist=artist)

    def count(self):
        """How many cells are painted.

        Counted with `list.count`, which runs in C (#v2.8.0): the strip under
        the canvas asks on every mouse move, and once drawings could be
        hundreds of cells wide a Python loop over all of them made the
        pointer itself lag."""
        return sum(len(row) - row.count(None) for row in self.cells)

    def empty_count(self):
        """How many cells are still empty (#v2.7.0, item 5)."""
        return self.width * self.height - self.count()

    def row_count(self, row):
        if not (0 <= row < self.height):
            return 0
        line = self.cells[row]
        return len(line) - line.count(None)

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

    def fill_region(self, c0, r0, c1, r1, value):
        """Paint every cell in the inclusive rectangle (#v2.7.0, item 8)."""
        c0, c1 = sorted((c0, c1))
        r0, r1 = sorted((r0, r1))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                self.paint(c, r, value)

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

    def colour_of(self, value):
        """What a cell value LOOKS like, as RGBA: a palette letter through the
        palette, a raw colour as itself, None for an empty cell."""
        if value is None:
            return None
        if isinstance(value, str):
            return self.palette.colors().get(value)
        return tuple(value)

    def cells_coloured(self, rgba, region=None):
        """Every (col, row) whose cell looks like `rgba` - however it is
        stored, letter or raw - inside `region` (c0, r0, c1, r1, inclusive)
        or the whole grid."""
        c0, r0, c1, r1 = region if region is not None else (0, 0, self.width - 1, self.height - 1)
        c0, r0 = max(0, c0), max(0, r0)
        c1, r1 = min(self.width - 1, c1), min(self.height - 1, r1)
        rgba = tuple(rgba)
        palette = self.palette.colors()
        looks = {}
        found = []
        for r in range(r0, r1 + 1):
            line = self.cells[r]
            for c in range(c0, c1 + 1):
                v = line[c]
                if v is None:
                    continue
                key = v if isinstance(v, str) else tuple(v)
                seen = looks.get(key)
                if seen is None:
                    seen = looks[key] = (palette.get(v) if isinstance(v, str) else key) == rgba
                if seen:
                    found.append((c, r))
        return found

    def swap_colour(self, rgba, value, region=None):
        """SWAP (#v2.9.0): every cell that looks like `rgba` becomes `value`.
        Returns how many cells were changed."""
        cells = self.cells_coloured(rgba, region)
        for c, r in cells:
            self.cells[r][c] = value
        return len(cells)

    def resize(self, cols, rows):
        """Pad with empty cells right/below, or crop right/below. Engine
        flowers stay 16 wide; trees and pets to come get whatever they need."""
        cols, rows = max(1, cols), max(1, rows)
        for row in self.cells:
            row.extend([None] * (cols - len(row)))  # nothing when it is wide enough
            del row[cols:]
        while len(self.cells) < rows:
            self.cells.append([None] * cols)
        del self.cells[rows:]

    def resize_edge(self, edge, delta):
        """Move one EDGE of the grid by `delta` cells (#v2.8.0).

        `resize` grows and crops at the right and the bottom, because that is
        where a size dialog's width and height go. Dragging the LEFT edge is a
        different thing: the cells that leave are the ones on the left, and
        the art that stays does not move relative to the edge the artist is
        not touching. A positive `delta` always grows.

        Returns the number of cells actually moved - the grid never goes below
        one cell on either axis, so a drag past that does nothing rather than
        emptying the drawing."""
        if edge not in ("left", "right", "top", "bottom"):
            raise ValueError(f"edge must be left/right/top/bottom, got {edge!r}")
        width, height = self.width, self.height
        limit = (width if edge in ("left", "right") else height) - 1
        delta = max(-limit, int(delta))
        if delta == 0:
            return 0
        if edge == "right":
            self.resize(width + delta, height)
        elif edge == "bottom":
            self.resize(width, height + delta)
        elif edge == "left":
            for row in self.cells:
                if delta > 0:
                    row[:0] = [None] * delta
                else:
                    del row[:-delta]
            self.shift = (self.shift[0] + delta, self.shift[1])
        else:  # top
            if delta > 0:
                self.cells[:0] = [[None] * width for _ in range(delta)]
            else:
                del self.cells[:-delta]
            self.shift = (self.shift[0], self.shift[1] + delta)
        return delta

    def is_letters(self):
        """No raw colour anywhere. Asked of the DISTINCT cell values - the
        union of the rows is built in C - since a blank 2000-cell square is
        four million Nones, and every autosave asks (#v2.8.0)."""
        return all(v is None or isinstance(v, str) for v in set().union(*self.cells))

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

    A 16x19 grid is 304 cells - snapshotting it is nothing next to the cost of
    getting a diff-based stack subtly wrong, and a wrong undo loses the artist's
    work. Snapshots it is.

    Entries are `(kind, value)`, oldest first, and there is ONE stack, not one
    per kind (#v2.8.0). Up to #v2.7.0 the window kept the zoom's undo in a
    separate list that `undo()` drained FIRST, so a corner-drag from ten
    strokes ago jumped the queue and Ctrl+Z gave back a zoom level instead of
    the last thing painted. Interleaving them is the only way the stack can
    mean "what happened, backwards":

    * `("cells", snapshot)` - the grid before a stroke. History owns these:
      it swaps `.current` itself.
    * any other kind - a piece of state the WINDOW owns, carried here only so
      it takes its turn in the right order. History never interprets the
      value; it hands the old one back and stores the current one, which the
      caller supplies, for redo. `("grid", ...)` and `("bar", ...)` are the
      two the kit uses (#v2.8.0): the checkerboard tones and the symmetry
      line. Changing a grid colour and pressing Ctrl+Z has to undo the grid
      colour, not the last brush stroke.
    """

    CELLS = "cells"
    # How many cells the undo stack's snapshots may hold between them
    # (#v2.8.0). Two hundred snapshots of a 64x64 tree are under a million;
    # with the size cap gone, two hundred of a 1024-wide drawing would be two
    # hundred million, and the machine would run out of memory long before
    # the artist ran out of strokes. Past the budget the OLDEST steps go, the
    # way the entry limit already drops them - a big drawing simply keeps a
    # shorter memory. Never the newest step.
    CELL_BUDGET = 24_000_000

    def __init__(self, drawing, limit=200):
        self.current = drawing
        self._undo = []
        self._redo = []
        self._pending = None
        self._limit = limit

    def begin_stroke(self):
        self._pending = self.current.copy()

    def end_stroke(self):
        """Close the open stroke. Returns True if it changed anything and so
        became an undo entry - callers that pair a stroke with something else
        need to know whether one was recorded."""
        if self._pending is None:
            return False
        before, self._pending = self._pending, None
        if before.cells == self.current.cells:
            return False  # nothing actually moved
        self._push((self.CELLS, before))
        return True

    def abort_stroke(self):
        """Throw away a stroke that was begun and never ended, putting the
        drawing back to how it was when it started (#v2.8.0).

        For an edit the artist walks away from half-done - a lifted block
        dropped with Ctrl+Z before it lands. It leaves NO undo entry, because
        the edit never became one. Returns True if there was a stroke open."""
        if self._pending is None:
            return False
        self.current, self._pending = self._pending, None
        return True

    def has_pending(self):
        return self._pending is not None

    def last_kind(self):
        """The kind of the newest undo entry, or None."""
        return self._undo[-1][0] if self._undo else None

    def drop_last(self, kind):
        """Remove the entry just pushed, for a change that turned out not to
        change anything. Cheaper and clearer than deciding in advance what a
        setter is going to do with its arguments."""
        if self._undo and self._undo[-1][0] == kind:
            self._undo.pop()
            return True
        return False

    def push_state(self, kind, value):
        """Record a change to something the window owns, in the same timeline
        as the strokes. `kind` is anything but CELLS; `value` is how it was
        BEFORE the change."""
        if kind == self.CELLS:
            raise ValueError("cells entries come from end_stroke()")
        self._push((kind, value))

    def _push(self, entry):
        self._undo.append(entry)
        del self._undo[:-self._limit]
        held = sum(v.width * v.height for k, v in self._undo if k == self.CELLS)
        while held > self.CELL_BUDGET and len(self._undo) > 1:
            kind, value = self._undo.pop(0)
            if kind == self.CELLS:
                held -= value.width * value.height
        self._redo.clear()

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def repaint(self, palette):
        """A palette edit is not a stroke: apply it to the live drawing AND
        every snapshot, so an undo never silently reverts the colours."""
        self.current.palette = palette
        for kind, value in self._undo + self._redo:
            if kind == self.CELLS:
                value.palette = palette
        if self._pending is not None:
            self._pending.palette = palette

    def undo(self, current=None):
        """Step back one entry.

        Returns `(kind, value)`: `("cells", None)` once `.current` has been
        swapped for the older grid, or `(kind, old_value)` for a piece of
        state the CALLER must restore - history does not own the window.
        None if there is nothing left. `current` maps those kinds to their
        value right now, so redo has something to come back to."""
        return self._step(self._undo, self._redo, current)

    def redo(self, current=None):
        """The mirror of `undo`, with the same return shape."""
        return self._step(self._redo, self._undo, current)

    def _step(self, source, target, current):
        if not source:
            return None
        kind, value = source.pop()
        if kind == self.CELLS:
            target.append((self.CELLS, self.current.copy()))
            self.current = value
            return (self.CELLS, None)
        target.append((kind, (current or {}).get(kind)))
        return (kind, value)
