# ponytail: hand-calibrated crop boxes, verified by eyeball on saved previews.
from PIL import Image

G = r"C:\Users\claude\pixel_pomo\feedback & guides\Guides\Sprite Guides\Cactus"
OUT = r"C:\Users\claude\cactus_study"

JOBS = {
    # Method A sources: rendered pixel art panels (4 shapes each)
    "art_flower": ("b222f4da-80d1-4ed3-a0e4-ea105220737d.png",
                   [(31, 140, 327, 408), (381, 140, 677, 408),
                    (731, 140, 1027, 408), (1081, 140, 1377, 408)]),
    "art_plain": ("658210e0-299a-47ed-aedc-f3f636235640.png",
                  [(36, 113, 190, 268), (386, 113, 540, 268),
                   (736, 113, 890, 268), (1086, 113, 1240, 268)]),
    # Method B sources: pixel blueprint grids (generous boxes, tighten after view)
    "bp_flower": ("035b4d32-7cbd-4027-bb3b-ff86f18a6f22.png",
                  [(28, 445, 330, 670), (378, 445, 680, 670),
                   (728, 445, 1030, 670), (1078, 445, 1380, 670)]),
    "bp_plain": ("658210e0-299a-47ed-aedc-f3f636235640.png",
                 [(28, 390, 330, 615), (378, 390, 680, 615),
                  (728, 390, 1030, 615), (1078, 390, 1380, 615)]),
}

for name, (fn, boxes) in JOBS.items():
    im = Image.open(f"{G}\\{fn}").convert("RGB")
    for i, box in enumerate(boxes):
        c = im.crop(box)
        c = c.resize((c.width * 2, c.height * 2), Image.NEAREST)
        c.save(f"{OUT}\\calib_{name}_{i}.png")
print("saved")
