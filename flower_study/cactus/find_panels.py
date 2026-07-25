# ponytail: histogram-based tan-rectangle finder — the art panels are the only
# large sand-colored rectangles on the near-black sheets.
from PIL import Image
import pathlib

# The game checkout is found RELATIVE to this file (both live under one
# "Pixel Pomo" folder), so moving or renaming that folder can't break it.
_APP = pathlib.Path(__file__).resolve().parents[3] / "App"

GUIDES = str(_APP / "feedback & guides" / "Guides" / "Sprite Guides" / "Cactus")
SHEETS = {
    "flower": "b222f4da-80d1-4ed3-a0e4-ea105220737d.png",   # big renders WITH flower
    "plain":  "658210e0-299a-47ed-aedc-f3f636235640.png",   # renders NO flower
}


def tan(p):
    r, g, b = p[:3]
    return 165 < r < 250 and 120 < g < 215 and 70 < b < 175 and r > g > b


def bands(hist, thresh, minlen):
    out, start = [], None
    for i, v in enumerate(hist + [0]):
        if v >= thresh and start is None:
            start = i
        elif v < thresh and start is not None:
            if i - start >= minlen:
                out.append((start, i))
            start = None
    return out


for name, fn in SHEETS.items():
    im = Image.open(f"{GUIDES}\\{fn}").convert("RGB")
    w, h = im.size
    px = im.load()
    mask = [[tan(px[x, y]) for x in range(w)] for y in range(h)]
    colh = [sum(mask[y][x] for y in range(h)) for x in range(w)]
    cols = bands(colh, 80, 100)
    print(name, "cols:", cols)
    for (x0, x1) in cols:
        rowh = [sum(mask[y][x] for x in range(x0, x1)) for y in range(h)]
        rows = bands(rowh, (x1 - x0) * 6 // 10, 80)
        print("   rows in", (x0, x1), "->", rows)
