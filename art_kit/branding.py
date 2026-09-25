"""The kit's icon: Pixel Pomo's tomato with a brush beside it (#v2.4.0, item 6).

Defined as a letter grid here, the way the game's own sprites are, so the
window icon is built at run time with no image file to bundle, and the
.ico / .icns the installers carry are generated from the same grid by
`python -m art_kit.branding` (needs Pillow) into `assets/`.

The grid itself is drawn in the kit - the app's own icon is a Pixel Pomo
drawing, exported and pasted in here, which is the point.
"""
import sys
from pathlib import Path

from art_kit.raster import photo

# 32x32, drawn in the kit itself and exported from it (#v2.8.0, was 16x16).
# The tomato is the app icon's, cell for cell; the brush stands to its right,
# tip dipped in the matcha accent. Twice the grid, so the tomato carries its
# highlight and its underside at a size the taskbar can actually show - at 16
# they were one pixel each and the icon read as a red blob.
#
# The letters are the same eight the 16x16 used, so COLOURS below is unchanged.
ICON = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    ".........GGGG............HHHH...",
    ".........GGGG............HHHH...",
    ".....GGGGGGGGGGGG........HHHH...",
    ".....GGGGGGGGGGGG........HHHH...",
    "...RRRRRRRRRRRRRRRRR.....HHHH...",
    "...RRRRRRRRRRRRRRRRR.....HHHH...",
    ".RRRRLLLLRRRRRRRRRRRR....HHHH...",
    ".RRRRLLLLRRRRRRRRRRRR....HHHH...",
    ".RRRRLLLLRRRRRRRRRRRR....HHHH...",
    ".RRRRLLLLRRRRRRRRRRRR....HHHH...",
    ".RRRRRRRRRRRRRRRRRRRR..FFFFFFFF.",
    ".RRRRRRRRRRRRRRRRRRRR..FFFFFFFF.",
    ".RRRRRRRRRRRRRRRRRRRR..FFFFFFFF.",
    ".RRRRRRRRRRRRRRRRRRRR..FFFFFFFF.",
    ".RRRRRRRRRRRRRRRRRRRR..BBBBBBBB.",
    ".RRRRRRRRRRRRRRRRRRRR..BBBBBBBB.",
    ".RRRRRRRRRRRRRRRRRRRR..BBBBBBBB.",
    ".RRRRRRRRRRRRRRRRRRRR..BBBBBBBB.",
    ".RRRRRRRRRRRRRRRRRRRR..AAAAAAAA.",
    ".RRRRRRRRRRRRRRRRRRRR..AAAAAAAA.",
    "...DDDDDDDDDDDDDDDDD.....AAAA...",
    "...DDDDDDDDDDDDDDDDD.....AAAA...",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]

COLOURS = {
    "G": "3DE38A",  # leaf
    "R": "E53945",  # tomato
    "L": "FF6B6B",  # highlight
    "D": "9B1B23",  # underside
    "H": "8B5A2B",  # brush handle
    "F": "CDD6F4",  # ferrule
    "B": "F2E2B8",  # bristles
    "A": "A6E3A1",  # paint on the tip - the matcha accent
}


def icon_grid(background=None):
    """The icon as an RGBA grid. `background` (hex) fills the empty cells,
    for platforms whose icons want a solid tile."""
    bg = _rgba(background) if background else None
    grid = []
    for line in ICON:
        row = []
        for ch in line:
            row.append(_rgba(COLOURS[ch]) if ch in COLOURS else bg)
        grid.append(row)
    return grid


def _rgba(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def apply_window_icon(root):
    """Set the title-bar / dock icon. `iconphoto` takes a PhotoImage on every
    platform (Windows also accepts .ico via iconbitmap, but this needs no
    file). A failure is cosmetic and swallowed.

    On a Mac this image IS the Dock icon, in place of the bundle's .icns, and
    the Dock draws it at up to 256 px on a Retina screen. It was the bare
    sprite at 128 px at most, stretched and blurred there ("the icon does
    look a bit blurry in my dock", #v2.9.0). A Mac gets the .icns picture
    instead - the sprite on its matcha tile - at 1024 px, scaled by whole
    pixels, so it is sharp and matches the icon in Finder."""
    try:
        if sys.platform == "darwin":
            from art_kit import raster
            images = [raster.image_photo(mac_tile(1024), master=root)]
        else:
            images = [photo(icon_grid(), scale=s, master=root) for s in (1, 2, 4)]
        root._icon_images = images  # keep them alive for the window's lifetime
        root.iconphoto(True, *images)
    except Exception:
        pass


def _render(grid, size):
    """The grid as a `size`-pixel square image, every cell a block of pixels
    (NEAREST): scaled, never smoothed."""
    from PIL import Image
    # From the grid's own dimensions: ICON was 16x16 and is 32x32 now, and a
    # literal here would have silently cropped it to the top-left corner.
    h, w = len(grid), len(grid[0])
    img = Image.new("RGBA", (w, h))
    img.putdata([px if px else (0, 0, 0, 0) for row in grid for px in row])
    return img.resize((size, size), Image.NEAREST)


def mac_tile(size):
    """The macOS icon at `size` px: the sprite on a rounded matcha tile,
    inset the way Apple's own icons are.

    Drawn afresh at each size rather than shrunk from the 1024 one: Pillow's
    .icns writer shrinks with a smoothing filter, which is what made the small
    sizes soft. The sprite is laid on at the largest whole number of pixels a
    cell that fits three quarters of the tile, so every cell stays a crisp
    block; 16 px and 32 px icons cannot hold a 32-cell sprite whole, and those
    two alone are shrunk."""
    from PIL import Image, ImageDraw
    grid = icon_grid()
    cells = len(grid[0])
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=round(size * 200 / 1024), fill=(0x1A, 0x24, 0x20, 255))
    per_cell = (size * 3 // 4) // cells
    if per_cell >= 1:
        sprite = _render(grid, per_cell * cells)
    else:
        sprite = _render(grid, cells * 4).resize((size * 3 // 4,) * 2, Image.LANCZOS)
    off = (size - sprite.width) // 2
    tile.alpha_composite(sprite, (off, off))
    return tile


def write_icon_files(out_dir):
    """`icon.png`, `icon.ico`, `icon.icns` into `out_dir`. Needs Pillow.

    The Windows and Mac files are rendered from the same grid at the sizes each
    platform expects; the Mac one sits on the matcha window tile because a
    transparent 16-cell sprite floats oddly in the Dock beside rounded tiles."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    render = _render
    plain = icon_grid()
    render(plain, 512).save(out_dir / "icon.png")
    render(plain, 256).save(
        out_dir / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # macOS: every size the .icns holds drawn on its own (`mac_tile`), handed
    # to Pillow so it has nothing to shrink (#v2.9.0: "a bit blurry").
    sizes = (16, 32, 64, 128, 256, 512)
    mac_tile(1024).save(out_dir / "icon.icns", append_images=[mac_tile(n) for n in sizes])
    return [out_dir / n for n in ("icon.png", "icon.ico", "icon.icns")]


if __name__ == "__main__":
    for p in write_icon_files(Path(__file__).resolve().parent.parent / "assets"):
        print(p)
