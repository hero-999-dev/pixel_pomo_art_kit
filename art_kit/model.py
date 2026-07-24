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
