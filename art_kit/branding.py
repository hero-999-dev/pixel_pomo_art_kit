"""The kit's icon: Pixel Pomo's tomato with a brush beside it (#v2.4.0, item 6).

Defined as a letter grid here, the way the game's own sprites are, so the
window icon is built at run time with no image file to bundle, and the
.ico / .icns the installers carry are generated from the same grid by
`python -m art_kit.branding` (needs Pillow) into `assets/`.
"""
from pathlib import Path

from art_kit.raster import photo

# 16x16. The tomato is the app icon's, cell for cell; the brush stands to
# its right, tip dipped in the matcha accent.
ICON = [
    "................",
    "....GG......HH..",
    "..GGGGGG....HH..",
    ".RRRRRRRR...HH..",
    "RRLLRRRRRR..HH..",
    "RRLLRRRRRR..HH..",
    "RRRRRRRRRR..HH..",
    "RRRRRRRRRR..HH..",
    "RRRRRRRRRR.FFFF.",
    "RRRRRRRRRR.FFFF.",
    "RRRRRRRRRR.BBBB.",
    ".DDDDDDDD..BBBB.",
    "...........BBBB.",
    "...........AAAA.",
    "............AA..",
    "................",
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
    file). A failure is cosmetic and swallowed."""
    try:
        images = [photo(icon_grid(), scale=s, master=root) for s in (1, 2, 4)]
        root._icon_images = images  # keep them alive for the window's lifetime
        root.iconphoto(True, *images)
    except Exception:
        pass


def write_icon_files(out_dir):
    """`icon.png`, `icon.ico`, `icon.icns` into `out_dir`. Needs Pillow.

    The Windows and Mac files are rendered from the same grid at the sizes each
    platform expects; the Mac one sits on the matcha window tile because a
    transparent 16-cell sprite floats oddly in the Dock beside rounded tiles."""
    from PIL import Image
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def render(grid, size):
        img = Image.new("RGBA", (16, 16))
        img.putdata([px if px else (0, 0, 0, 0) for row in grid for px in row])
        return img.resize((size, size), Image.NEAREST)

    plain = icon_grid()
    render(plain, 512).save(out_dir / "icon.png")
    render(plain, 256).save(
        out_dir / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # macOS: the sprite on a rounded matcha tile, inset the way Apple's own
    # icons are.
    tile = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(tile).rounded_rectangle(
        (0, 0, 1023, 1023), radius=200, fill=(0x1A, 0x24, 0x20, 255))
    sprite = render(plain, 768)
    tile.alpha_composite(sprite, (128, 128))
    tile.save(out_dir / "icon.icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128),
                                             (256, 256), (512, 512), (1024, 1024)])
    return [out_dir / n for n in ("icon.png", "icon.ico", "icon.icns")]


if __name__ == "__main__":
    for p in write_icon_files(Path(__file__).resolve().parent.parent / "assets"):
        print(p)
