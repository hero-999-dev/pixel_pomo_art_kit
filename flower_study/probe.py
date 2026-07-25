# One-off: overlay a labeled 50px grid on each per-shape sheet's bottom-left
# quadrant so the blueprint box can be read off and hardcoded (bpfix style).
from PIL import Image, ImageDraw
import pathlib

# The game checkout is found RELATIVE to this file (both live under one
# "Pixel Pomo" folder), so moving or renaming that folder can't break it.
_APP = pathlib.Path(__file__).resolve().parents[2] / "App"

G = str(_APP / "feedback & guides" / "Guides" / "Sprite Guides" / "Daisy")
sheets = {
    'd01': rf'{G}\c9934cca-d7eb-4d7f-957c-85d7758b8a3c.png',
    'd02': rf'{G}\f473d1c8-de44-44f9-beb8-211054d1b78c.png',
    'd04': rf'{G}\image.png',
}
for k, p in sheets.items():
    im = Image.open(p).convert('RGB')
    w, h = im.size
    oy = int(h * 0.35)
    crop = im.crop((0, oy, int(w * 0.48), h))
    dr = ImageDraw.Draw(crop)
    for x in range(0, crop.width, 50):
        dr.line([(x, 0), (x, crop.height)], fill=(255, 0, 0), width=1)
        if x % 100 == 0:
            dr.text((x + 2, 2), str(x), fill=(255, 90, 90))
    for y in range(0, crop.height, 50):
        dr.line([(0, y), (crop.width, y)], fill=(255, 0, 0), width=1)
        if y % 100 == 0:
            dr.text((2, y + 2), str(y + oy), fill=(255, 90, 90))
    crop.save(rf'C:\Users\claude\flower_study\probe_{k}.png')
    print(k, 'sheet', w, 'x', h, '-> probe', crop.size)
