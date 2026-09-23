"""RGBA grids -> Tk images, fast (#v2.4.0, item 7).

Before this the canvas, both previews and every library thumbnail were drawn
as one `create_rectangle` per opaque cell. A 64x64 tree is up to 4096 canvas
items, and the whole library (59 drawings, twenty of them trees) was rebuilt
on EVERY stroke — tens of thousands of items destroyed and recreated per
click. That is the freeze the artist saw.

Now a grid becomes one PNG in memory (standard library only — Tk 8.6 decodes
PNG natively, alpha included) and one `PhotoImage`, which Tk scales with
`zoom()` in C. One canvas item per drawing, however big it is.
"""
import io
import struct
import tkinter as tk
import zlib
from itertools import chain

CLEAR = (0, 0, 0, 0)  # an empty pixel


def png_bytes(grid):
    """An RGBA grid as PNG bytes. Same layout `gen_objects.write_png` uses,
    kept here so a preview never needs a temp file. Empty cells (None or
    alpha 0) come out fully transparent.

    A row with no None in it - every row the main view hands over, and
    every row of a render, whose empty pixel is already (0, 0, 0, 0) - is
    packed in one C call instead of pixel by pixel (#v2.8.0): the pane at
    1x on a big drawing is most of a million pixels per repaint. (An alpha-0
    pixel keeps its RGB that way rather than being zeroed; it is exactly as
    invisible.)"""
    h = len(grid)
    w = len(grid[0]) if h else 0
    raw = bytearray()
    for row in grid:
        raw.append(0)  # filter: none
        if None not in row:
            packed = bytes(chain.from_iterable(row))
            if len(packed) == 4 * len(row):
                raw += packed
                continue
        for px in row:
            if not px or px[3] == 0:
                raw += b"\x00\x00\x00\x00"
            else:
                raw += bytes(px[:4])

    def chunk(tag, data):
        body = struct.pack(">I", len(data)) + tag + data
        return body + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 1)) + chunk(b"IEND", b""))


def photo(grid, scale=1, master=None):
    """A `tk.PhotoImage` of `grid` at `scale` pixels per cell. The caller
    must keep a reference — Tk drops the image the moment Python does."""
    img = tk.PhotoImage(data=png_bytes(grid), master=master)
    if scale > 1:
        img = img.zoom(scale, scale)
    return img


def fit_scale(grid, max_px, cap):
    """The biggest whole scale <= `cap` at which `grid` fits in `max_px`."""
    h = len(grid)
    w = len(grid[0]) if h else 1
    return max(1, min(cap, max_px // max(1, w), max_px // max(1, h)))


def over(px, rgba):
    """One pixel laid on the opaque colour `rgba`: itself if solid, the
    colour if empty, and a mix in between for a partly covered one."""
    if not px or px[3] == 0:
        return rgba
    a = px[3]
    if a == 255:
        return px
    k = a / 255
    return (round(px[0] * k + rgba[0] * (1 - k)), round(px[1] * k + rgba[1] * (1 - k)),
            round(px[2] * k + rgba[2] * (1 - k)), 255)


def on_colour(grid, rgba):
    """`grid` laid on the flat colour `rgba`: an image with no transparency,
    for a picture that always sits on that one colour anyway. Tk builds a
    mask for any photo with see-through pixels, and for scattered pixel art
    that mask is the slowest thing on screen (#v2.8.0). A half-covered pixel
    - what `reduce` makes of an edge - is mixed with the colour, not dropped."""
    return [[over(px, rgba) for px in row] for row in grid]


def reduce(grid, n):
    """`grid` n times smaller, each pixel the AVERAGE of the n x n cells it
    stands for - a box filter (#v2.8.0, third test pass).

    Up to then a small picture of a big drawing kept every n-th cell and
    threw the rest away, so a line one cell thin was in the preview or not
    depending on where it fell ("bazı kısımlar aktarılmamış"). Averaged,
    every cell counts: a thin line shows as the faint line it is at that
    size. The average is premultiplied, so an edge block half covered comes
    out half as opaque rather than darkened by the empty cells beside it. A
    block cut short by the right or bottom edge averages the cells it has.

    Pillow does it in C when it is there - it is in every build; from source
    it is optional - and a pure-Python loop gives the same picture when not."""
    if n <= 1:
        return grid
    if not grid or not grid[0]:
        return grid
    img = to_image(grid)
    if img is None:  # pragma: no cover - Pillow ships with every build
        return _reduce_by_hand(grid, n)
    return image_to_grid(reduce_image(img, n))


# ---- the same, on Pillow images (#v2.8.0) ------------------------------------
#
# A drawing thousands of cells wide is millions of Python tuples, and turning
# them into pixels is the slow part of every picture of it - so the window
# does it ONCE per change (`ArtKitApp._rendered_image`) and cuts, averages
# and lays out the result here, in C.

def to_image(grid):
    """`grid` as a Pillow RGBA image, or None when Pillow is not there."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    h = len(grid)
    w = len(grid[0]) if h else 0
    data = bytearray()
    for row in grid:
        if None in row:
            row = [px or CLEAR for px in row]
        data += bytes(chain.from_iterable(row))
    return Image.frombytes("RGBA", (w, h), bytes(data))


def blank_image(w, h):
    """An empty w x h picture - a Pillow image, or None without Pillow."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    return Image.new("RGBA", (w, h), CLEAR)


def reduce_image(img, n):
    """`reduce` on a Pillow image: the premultiplied n x n box average."""
    return img if n <= 1 else img.convert("RGBa").reduce(n).convert("RGBA")


def on_image(img, rgba):
    """`on_colour` on a Pillow image: laid on one opaque colour."""
    from PIL import Image
    return Image.alpha_composite(Image.new("RGBA", img.size, tuple(rgba)), img)


def image_to_grid(img):
    """A Pillow RGBA image back into rows of (r, g, b, a) tuples."""
    w, h = img.size
    flat = img.tobytes()
    return [[tuple(flat[i:i + 4]) for i in range(y * w * 4, (y + 1) * w * 4, 4)]
            for y in range(h)]


def image_photo(img, scale=1, master=None):
    """A Pillow image straight into a Tk photo, through Pillow's own (C) PNG
    encoder rather than `png_bytes`."""
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    shown = tk.PhotoImage(data=buf.getvalue(), master=master)
    return shown.zoom(scale, scale) if scale > 1 else shown


def _reduce_by_hand(grid, n):
    """`reduce` without Pillow: the same premultiplied box average."""
    h, w = len(grid), len(grid[0])
    out = []
    for r0 in range(0, h, n):
        block_rows = grid[r0:r0 + n]
        line = []
        for c0 in range(0, w, n):
            sr = sg = sb = sa = count = 0
            for row in block_rows:
                for px in row[c0:c0 + n]:
                    count += 1
                    if px and px[3]:
                        a = px[3]
                        sr += px[0] * a
                        sg += px[1] * a
                        sb += px[2] * a
                        sa += a
            if sa:
                line.append((round(sr / sa), round(sg / sa), round(sb / sa), round(sa / count)))
            else:
                line.append(CLEAR)
        out.append(line)
    return out


def shrink(grid, max_px):
    """`grid` made to fit `max_px` on its longer side by `reduce`, the
    averaging one. Returns `(grid, n)`, n being 1 when it already fit.

    For the thumbnails and previews of drawings bigger than their box (#v2.8.0):
    until the 64-cell cap went, `fit_scale`'s floor of 1 was always small
    enough, and a 300-wide drawing would have pushed a 300 px thumbnail into a
    64 px library row."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    n = max(1, -(-max(w, h) // max(1, max_px)))
    return (grid, 1) if n == 1 else (reduce(grid, n), n)
