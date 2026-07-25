# Preview all 16 candidates on the real in-game grass tile, bottom-anchored like
# the garden billboard renderer.
import os
from PIL import Image
import pathlib

# The game checkout is found RELATIVE to this file (both live under one
# "Pixel Pomo" folder), so moving or renaming that folder can't break it.
_APP = pathlib.Path(__file__).resolve().parents[3] / "App"

OUT = os.path.dirname(os.path.abspath(__file__))  # outputs sit beside the script
GRASS = str(_APP / "flutter" / "assets" / "objects" / "grass.png")

names = [f"{m}_{k}_{i}" for m in ("m1", "m2") for k in ("flower", "plain") for i in range(4)]
tile = Image.open(GRASS).convert("RGB").resize((128, 128), Image.NEAREST)
strip = Image.new("RGB", (128 * 8, 128 * 2))
for n, name in enumerate(names):
    r, c = divmod(n, 8)
    cell = tile.copy()
    sp = Image.open(f"{OUT}\\{name}.png").convert("RGBA")
    w = 96
    h = round(sp.height * w / sp.width)
    sp = sp.resize((w, h), Image.NEAREST)
    cell.paste(sp, ((128 - w) // 2, 128 - h - 6), sp)
    strip.paste(cell, (c * 128, r * 128))
strip.save(f"{OUT}\\gardenstrip.png")
print("ok")
