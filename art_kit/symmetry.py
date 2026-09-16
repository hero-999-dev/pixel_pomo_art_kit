"""The symmetry bar (#v2.4.0, item 14). Pure geometry, no widgets.

The artist places a short bar on the grid — vertical (90°) or horizontal
(180°), `length` cells long, centred where they clicked. While it is there,
every cell painted within the bar's reach is mirrored across it:

* a **vertical** bar standing in column `c` mirrors column `c - k` onto
  `c + k`, for cells whose ROW lies within the bar's length;
* a **horizontal** bar lying in row `r` mirrors row `r - k` onto `r + k`, for
  cells whose COLUMN lies within the bar's length.

A cell on the bar itself has no twin. A cell outside the bar's length is
painted alone, so the bar can sit on one petal without ghosting the stem.
Sitting the axis ON a cell (rather than between two) is what makes "5 cells
long, centred on the click" mean the same thing for odd and even lengths,
and it is how an artist reads a bar drawn over the grid anyway.
"""
from dataclasses import dataclass

VERTICAL = "vertical"      # the 90° bar: mirrors left <-> right
HORIZONTAL = "horizontal"  # the 180° bar: mirrors top <-> bottom
ORIENTATIONS = (VERTICAL, HORIZONTAL)

ANGLE = {VERTICAL: 90, HORIZONTAL: 180}
MIN_LENGTH, MAX_LENGTH = 1, 64


@dataclass
class Bar:
    orientation: str
    length: int
    col: int  # the cell the bar is centred on
    row: int

    def __post_init__(self):
        if self.orientation not in ORIENTATIONS:
            raise ValueError(f"orientation must be one of {ORIENTATIONS}, got {self.orientation!r}")
        self.length = max(MIN_LENGTH, min(MAX_LENGTH, int(self.length)))

    @property
    def angle(self):
        return ANGLE[self.orientation]

    def span(self):
        """(first, last) index along the bar, inclusive: the rows a vertical
        bar covers, or the columns a horizontal one covers."""
        centre = self.row if self.orientation == VERTICAL else self.col
        half = (self.length - 1) // 2
        first = centre - half
        return first, first + self.length - 1

    def cells(self):
        """Every grid cell the bar lies on — what the canvas draws."""
        first, last = self.span()
        if self.orientation == VERTICAL:
            return [(self.col, r) for r in range(first, last + 1)]
        return [(c, self.row) for c in range(first, last + 1)]

    def mirror(self, col, row):
        """The twin of (col, row), or None if the cell is on the bar or
        outside its reach."""
        first, last = self.span()
        if self.orientation == VERTICAL:
            if not (first <= row <= last) or col == self.col:
                return None
            return (2 * self.col - col, row)
        if not (first <= col <= last) or row == self.row:
            return None
        return (col, 2 * self.row - row)

    def moved_to(self, col, row):
        return Bar(self.orientation, self.length, col, row)


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
