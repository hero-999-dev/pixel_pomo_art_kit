"""The symmetry line (#v2.4.0, item 14; between-pixel lines #v2.7.0, item 12).

The artist places a short *line between cells* — vertical (90°) or horizontal
(180°), `length` cells long. The line sits on a grid edge, never covering a
cell, so it cannot be mistaken for a SELECT rectangle.

* a **vertical** line on the left edge of column `c` mirrors column `c - 1 - k`
  onto column `c + k` (neighbours across the line swap), for rows within the
  line's length;
* a **horizontal** line on the top edge of row `r` does the same for columns.

MIRROR paints both sides live.

REVERSE (#v2.9.0, in STICK's place) needs no line: it takes the SELECT
rectangle, turns it over - across the X axis, the Y axis or both - and
copies it beside itself in one of eight directions, a chosen distance away.
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


OFF, MIRROR, REVERSE = "off", "mirror", "reverse"
MODES = (OFF, MIRROR, REVERSE)
# STICK was the third mode until #v2.9.0; a settings file may still name it,
# and the window opens with symmetry OFF when it does.


# ---- REVERSE (#v2.9.0) --------------------------------------------------------
#
# The axis the block is turned over ACROSS, as in "x eksenine göre": across
# the X axis the rows swap (upside down), across the Y axis the columns swap
# (left <-> right), across both it is turned half round.
AXIS_X, AXIS_Y, AXIS_XY = "x", "y", "xy"
AXES = (AXIS_X, AXIS_Y, AXIS_XY)

# Where the copy goes, as a step in (columns, rows): screen rows grow downward.
DIRECTIONS = {
    "up_left": (-1, -1), "up": (0, -1), "up_right": (1, -1),
    "left": (-1, 0), "right": (1, 0),
    "down_left": (-1, 1), "down": (0, 1), "down_right": (1, 1),
}

# How the distance is given: one number for both steps, or X and Y apart.
SPACING_SAME, SPACING_XY = "same", "xy"
SPACINGS = (SPACING_SAME, SPACING_XY)
MAX_GAP = 256


def turned(cells, axis):
    """`cells` (rows of values) turned over across `axis`, as a new block."""
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}, got {axis!r}")
    rows = [list(line) for line in cells]
    if axis in (AXIS_Y, AXIS_XY):
        rows = [line[::-1] for line in rows]
    if axis in (AXIS_X, AXIS_XY):
        rows = rows[::-1]
    return rows


def reverse_corner(selection, direction, gap_x, gap_y):
    """The top-left cell of the copy of `selection` (c0, r0, c1, r1,
    inclusive) sent toward `direction`, with `gap_x` empty columns and
    `gap_y` empty rows between it and the original. 0 is right beside it.
    A step that is 0 in one direction (a straight arrow) ignores that gap."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {tuple(DIRECTIONS)}, got {direction!r}")
    c0, r0, c1, r1 = selection
    w, h = c1 - c0 + 1, r1 - r0 + 1
    dc, dr = DIRECTIONS[direction]
    gap_x = max(0, min(MAX_GAP, int(gap_x)))
    gap_y = max(0, min(MAX_GAP, int(gap_y)))
    return c0 + dc * (w + gap_x), r0 + dr * (h + gap_y)


def reverse_copy(drawing, selection, axis, direction, gap_x, gap_y):
    """Stamp the turned-over copy of `selection` onto `drawing`. Empty cells
    of the block leave what is under them, as a paste does. Returns
    (col, row, w, h, dropped): where the copy went and how many of its
    painted cells fell outside the drawing."""
    cells, w, h = drawing.region(*selection)
    block = turned(cells, axis)
    col, row = reverse_corner(selection, direction, gap_x, gap_y)
    dropped = sum(1 for dr, line in enumerate(block) for dc, v in enumerate(line)
                  if v is not None and not drawing._inside(col + dc, row + dr))
    drawing.stamp(block, col, row)
    return col, row, w, h, dropped


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
