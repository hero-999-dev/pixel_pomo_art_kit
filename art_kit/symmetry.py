"""The symmetry line (#v2.4.0, item 14; between-pixel lines #v2.7.0, item 12).

The artist places a short *line between cells* — vertical (90°) or horizontal
(180°), `length` cells long. The line sits on a grid edge, never covering a
cell, so it cannot be mistaken for a SELECT rectangle.

* a **vertical** line on the left edge of column `c` mirrors column `c - 1 - k`
  onto column `c + k` (neighbours across the line swap), for rows within the
  line's length;
* a **horizontal** line on the top edge of row `r` does the same for columns.

MIRROR paints both sides live. STICK uses the same line, and when it is
placed it copies the `length` rows (vertical) or columns (horizontal) from
one side onto the other — a strip symmetry stamp.
"""
from dataclasses import dataclass

VERTICAL = "vertical"      # the 90° line: mirrors left <-> right
HORIZONTAL = "horizontal"  # the 180° line: mirrors top <-> bottom
ORIENTATIONS = (VERTICAL, HORIZONTAL)

ANGLE = {VERTICAL: 90, HORIZONTAL: 180}
MIN_LENGTH, MAX_LENGTH = 1, 64


@dataclass
class Bar:
    orientation: str
    length: int
    col: int  # vertical: the line is the LEFT edge of this column
    row: int  # horizontal: the line is the TOP edge of this row
              # the other coordinate is the centre of the length span

    def __post_init__(self):
        if self.orientation not in ORIENTATIONS:
            raise ValueError(f"orientation must be one of {ORIENTATIONS}, got {self.orientation!r}")
        self.length = max(MIN_LENGTH, min(MAX_LENGTH, int(self.length)))

    @property
    def angle(self):
        return ANGLE[self.orientation]

    def span(self):
        """(first, last) index along the line, inclusive: the rows a vertical
        line covers, or the columns a horizontal one covers."""
        centre = self.row if self.orientation == VERTICAL else self.col
        half = (self.length - 1) // 2
        first = centre - half
        return first, first + self.length - 1

    def cells(self):
        """The length-run of cells on the positive side of the line (right of
        a vertical line, below a horizontal one) — used to centre and resize."""
        first, last = self.span()
        if self.orientation == VERTICAL:
            return [(self.col, r) for r in range(first, last + 1)]
        return [(c, self.row) for c in range(first, last + 1)]

    def touches(self, col, row):
        """True if (col, row) is adjacent to the line within its length —
        either side, so the line can be grabbed from both neighbouring cells."""
        first, last = self.span()
        if self.orientation == VERTICAL:
            if not (first <= row <= last):
                return False
            return col == self.col or col == self.col - 1
        if not (first <= col <= last):
            return False
        return row == self.row or row == self.row - 1

    def mirror(self, col, row):
        """The twin of (col, row) across the between-pixel line, or None if
        the cell is outside the line's reach."""
        first, last = self.span()
        if self.orientation == VERTICAL:
            if not (first <= row <= last):
                return None
            return (2 * self.col - 1 - col, row)
        if not (first <= col <= last):
            return None
        return (col, 2 * self.row - 1 - row)

    def moved_to(self, col, row):
        return Bar(self.orientation, self.length, col, row)


def stamp_across(drawing, bar):
    """Copy the `length` span across `bar`: left → right for a vertical line,
    top → bottom for a horizontal one. Empty cells wipe their twins, so the
    strip on the far side becomes the true mirror. Returns the cells written."""
    first, last = bar.span()
    written = []
    if bar.orientation == VERTICAL:
        for r in range(first, last + 1):
            for c in range(bar.col):
                twin = bar.mirror(c, r)
                if twin is None:
                    continue
                tc, tr = twin
                drawing.paint(tc, tr, drawing.get(c, r))
                written.append((tc, tr))
    else:
        for c in range(first, last + 1):
            for r in range(bar.row):
                twin = bar.mirror(c, r)
                if twin is None:
                    continue
                tc, tr = twin
                drawing.paint(tc, tr, drawing.get(c, r))
                written.append((tc, tr))
    return written


OFF, MIRROR, STICK = "off", "mirror", "stick"
MODES = (OFF, MIRROR, STICK)


def stick(orientation, length, col, row):
    """Kept for older tests: a run of `length` cells from the click. STICK
    in the editor is a between-pixel strip-mirror now (#v2.7.0); this helper
    is the previous paint-a-run geometry."""
    if orientation not in ORIENTATIONS:
        raise ValueError(f"orientation must be one of {ORIENTATIONS}, got {orientation!r}")
    length = max(MIN_LENGTH, min(MAX_LENGTH, int(length)))
    if orientation == HORIZONTAL:
        return [(col + i, row) for i in range(length)]
    return [(col, row + i) for i in range(length)]


def expand_stick(orientation, length, cells):
    """Every cell of `cells` grown into its stick, in order, no duplicates."""
    out = []
    seen = set()
    for c, r in cells:
        for cell in stick(orientation, length, c, r):
            if cell not in seen:
                seen.add(cell)
                out.append(cell)
    return out


def expand(bar, cells):
    """`cells` plus each one's twin across `bar` (or unchanged if no bar).
    Order is preserved and twins follow their originals, so a Bresenham
    stroke stays a stroke on both sides."""
    if bar is None:
        return list(cells)
    out = []
    seen = set()
    for c, r in cells:
        for cell in ((c, r), bar.mirror(c, r)):
            if cell is not None and cell not in seen:
                seen.add(cell)
                out.append(cell)
    return out
