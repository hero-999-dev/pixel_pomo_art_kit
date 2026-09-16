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
import struct
import tkinter as tk
import zlib


def png_bytes(grid):
    """An RGBA grid as PNG bytes. Same layout `gen_objects.write_png` uses,
    kept here so a preview never needs a temp file. Empty cells (None or
    alpha 0) come out fully transparent."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    raw = bytearray()
    for row in grid:
        raw.append(0)  # filter: none
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
