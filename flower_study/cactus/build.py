# Cactus study: 16 candidate sprites from the user's guide sheets, two methods.
#   M1 "traced"    — rose method: sample the rendered art, hue-classify, band tones (1D k-means)
#   M2 "blueprint" — dot method: transcribe the sheet's numbered PIXEL BLUEPRINT cells
# Output: m{1,2}_{flower,plain}_{0..3}.png (x16), ascii_*.txt, contact_sheet.png
import os
import sys

sys.path.insert(0, r"C:\Users\claude\pixel_pomo\flutter\tools")
from gen_objects import blank, hexrgb, upscale, write_png, outline, _rose_compose  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

G = r"C:\Users\claude\pixel_pomo\feedback & guides\Guides\Sprite Guides\Cactus"
OUT = r"C:\Users\claude\cactus_study"
SHEET_FLOWER = f"{G}\\035b4d32-7cbd-4027-bb3b-ff86f18a6f22.png"   # all 4 flowered (art + blueprint)
SHEET_PLAIN = f"{G}\\658210e0-299a-47ed-aedc-f3f636235640.png"    # all 4 plain (art + blueprint)

# app-family palette (same greens as every flower; pinks = existing kaktus)
GRN_OL, PNK_OL = '1E5A24', '5A1030'
PAL = {
    'k': hexrgb('2C6E2A') + (255,), 'S': hexrgb('3E8E36') + (255,), 'G': hexrgb('5FBF4A') + (255,),
    'd': hexrgb('E0457B') + (255,), 'm': hexrgb('F06A92') + (255,), 'l': hexrgb('F9A8C2') + (255,),
    'C': hexrgb('F2C94C') + (255,),
    'o': hexrgb(GRN_OL) + (255,),   # interior seam between plant parts
}

PITCH = 350  # sheet column pitch

# crop boxes, col 0 only — others shift by PITCH*i (calibrated by eyeball)
ART_FLOWER0 = (36, 127, 190, 282)   # 035b4d32 PIXEL ART panel
ART_PLAIN0 = (32, 111, 194, 270)    # 658210e0 PIXEL ART panel
BP_FLOWER0 = (28, 445, 330, 670)    # 035b4d32 blueprint incl. axis labels
BP_PLAIN0 = (28, 390, 330, 615)     # 658210e0 blueprint incl. axis labels


def boxes(b0):
    return [(b0[0] + PITCH * i, b0[1], b0[2] + PITCH * i, b0[3]) for i in range(4)]


# ---- pixel classifier -------------------------------------------------------

def rawclass(p):
    """-> ('P'|'Y'|'A'|'g', luminance) or None (drop: bg/outline/line/rock/shadow)."""
    r, g, b = p[:3]
    mx = max(r, g, b)
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    if mx < 45:
        return None                                   # black bg / outline
    if abs(r - g) < 18 and abs(g - b) < 18:
        return None                                   # gray: gridline / rock / white
    if r > 130 and r - g > 55 and b > 60:
        return ('P', lum)                             # pink petals (incl. warm blends)
    if r > 170 and g > 150 and b < 115 and g - b > 105 and r - g < 55:
        return ('Y', lum)                             # gold (flower centre / speckle)
    if r > 145 and 100 < g < 190 and b < 125 and r > g > b:
        return ('A', lum)                             # sand
    if g > b + 18 and g >= r - 12:
        return ('g', lum)                             # green
    return None


def kmeans3(vals):
    """1D 3-means -> sorted cluster centers + assign fn (dark/mid/light banding)."""
    sv = sorted(vals)
    n = len(sv)
    cents = [sv[max(0, n // 5)], sv[n // 2], sv[min(n - 1, 4 * n // 5)]]
    for _ in range(8):
        groups = [[] for _ in range(3)]
        for v in vals:
            groups[min(range(3), key=lambda i: abs(v - cents[i]))].append(v)
        cents = [sum(g) / len(g) if g else cents[i] for i, g in enumerate(groups)]
    cents.sort()

    def assign(v):
        return min(range(3), key=lambda i: abs(v - cents[i]))
    return cents, assign


def to_chars(cells):
    """cells: 16x16 of rawclass results -> 16x16 char grid ('.' empty).
    Greens band to k/S/G; pinks to d/m/l (flat->m); gold/sand resolve by context."""
    H = len(cells)
    gv = [c[1] for row in cells for c in row if c and c[0] == 'g']
    pv = [c[1] for row in cells for c in row if c and c[0] == 'P']
    _, gband = kmeans3(gv) if len(gv) > 2 else (None, lambda v: 1)
    pflat = not pv or (max(pv) - min(pv) < 25)
    _, pband = kmeans3(pv) if not pflat else (None, lambda v: 1)
    chars = [['.'] * 16 for _ in range(H)]
    for r in range(H):
        for c in range(16):
            cl = cells[r][c]
            if not cl:
                continue
            t, v = cl
            if t == 'g':
                chars[r][c] = 'kSG'[gband(v)]
            elif t == 'P':
                chars[r][c] = 'dml'[pband(v)]
    for r in range(H):          # seam cells: keep as boundary only BETWEEN parts
        for c in range(16):
            cl = cells[r][c]
            if not cl or cl[0] != 'X':
                continue
            lr = c > 0 and c < 15 and cells[r][c - 1] and cells[r][c + 1] \
                and cells[r][c - 1][0] == 'g' and cells[r][c + 1][0] == 'g'
            ud = r > 0 and r < H - 1 and cells[r - 1][c] and cells[r + 1][c] \
                and cells[r - 1][c][0] == 'g' and cells[r + 1][c][0] == 'g'
            if lr or ud:
                chars[r][c] = 'o'                     # interior seam -> plant rim
            elif cl[1] and cl[1][0] == 'g':
                chars[r][c] = 'kSG'[gband(cl[1][1])]  # silhouette edge: keep green
    for r in range(H):          # gold + sand need neighbours, second pass
        for c in range(16):
            cl = cells[r][c]
            if not cl or cl[0] not in 'YA':
                continue
            nb8 = [cells[rr][cc] for rr in range(r - 1, r + 2) for cc in range(c - 1, c + 2)
                   if (rr, cc) != (r, c) and 0 <= rr < H and 0 <= cc < 16]
            npink = sum(1 for n in nb8 if n and n[0] in 'PY')
            if npink >= 3:
                chars[r][c] = 'C'                     # bloom centre
            elif sum(1 for n in nb8 if n and n[0] == 'g') >= 5:
                chars[r][c] = 'G'                     # speckle on the body
    return despeckle(chars)


def despeckle(chars):
    """Kill 0/1-neighbour orphans, fill near-enclosed holes — the automated version
    of the rose's hand-clean step."""
    H = len(chars)

    def nb(r, c):
        return [chars[rr][cc] for rr in range(r - 1, r + 2) for cc in range(c - 1, c + 2)
                if (rr, cc) != (r, c) and 0 <= rr < H and 0 <= cc < 16]
    for r in range(H):
        for c in range(16):
            ch = chars[r][c]
            filled = [n for n in nb(r, c) if n != '.']
            if ch != '.' and len(filled) <= 1 and ch not in 'dmlCo':
                chars[r][c] = '.'                     # lone green orphan
            elif ch == '.' and len(filled) >= 7:
                chars[r][c] = max(set(filled), key=filled.count)   # enclosed hole
    return chars


# ---- the two methods --------------------------------------------------------

def sample9(px, x, y, r):
    """Majority rawclass over a 3x3 point cloud — dodges blueprint number glyphs,
    render AA, and sub-cell misalignment. Cells that are half seam-black keep a
    'dark' flag so interior part-boundaries survive (('X', flag) sentinel)."""
    pts = [px[int(x + dx * r), int(y + dy * r)] for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    votes = [rawclass(p) for p in pts]
    nblack = sum(1 for p in pts if max(p[:3]) < 45)
    best, n = None, 0
    for v in votes:
        if v is None:
            continue
        k = sum(1 for w in votes if w and w[0] == v[0])
        if k > n:
            best, n = v, k
    if best is None or n < 4:
        return ('X', None) if nblack >= 5 else None   # solidly dark cell
    return best if nblack < 3 else ('X', best)        # green-ish but seam-heavy


def method1(sheet, box):
    """Trace the rendered art: the panel IS the 16x16 canvas."""
    im = Image.open(sheet).convert('RGB').crop(box)
    px = im.load()
    cw, ch = im.width / 16, im.height / 16
    cells = [[sample9(px, (c + 0.5) * cw, (r + 0.5) * ch, min(cw, ch) * 0.30)
              for c in range(16)] for r in range(16)]
    return to_chars(cells)


def colorprofile(im, vertical):
    """Per-column (or row) count of saturated pixels — peaks at colored blueprint
    cells, valleys at the dark gaps between them."""
    px = im.load()
    n = im.width if vertical else im.height
    m = im.height if vertical else im.width
    prof = []
    for i in range(n):
        cnt = 0
        for j in range(0, m, 2):
            p = px[(i, j) if vertical else (j, i)]
            if max(p) - min(p) > 55 and max(p) > 80:
                cnt += 1
        prof.append(cnt)
    return prof


def fitgrid(prof, n_px):
    """Find (pitch, phase) putting cell centers on profile peaks and borders in
    valleys. Returns 16 center coords."""
    best, bx = None, None
    lo, hi = (n_px - 42) / 16, (n_px - 6) / 16
    p = lo
    while p <= hi:
        for phase in range(6, 46):
            if phase + 16 * p > n_px - 1:
                continue
            s = 0.0
            for i in range(16):
                s += prof[int(phase + (i + 0.5) * p)]
                s -= prof[int(phase + i * p)]
            s -= prof[int(phase + 16 * p)]
            if best is None or s > best:
                best, bx = s, (p, phase)
        p += 0.1
    pitch, phase = bx
    centers = []
    rad = max(2, int(pitch * 0.25))
    for i in range(16):          # snap each center to the local color peak
        x0 = int(phase + (i + 0.5) * pitch)
        cand = max(range(max(0, x0 - rad), min(len(prof), x0 + rad + 1)),
                   key=lambda j: prof[j])
        centers.append(cand if prof[cand] > 4 else x0)
    return centers, pitch


def method2(sheet, box):
    """Transcribe the numbered blueprint: one sample per fitted grid cell."""
    im = Image.open(sheet).convert('RGB').crop(box)
    cx, pw = fitgrid(colorprofile(im, True), im.width)
    cy, ph = fitgrid(colorprofile(im, False), im.height)
    px = im.load()
    cells = [[sample9(px, cx[c], cy[r], min(pw, ph) * 0.26) for c in range(16)]
             for r in range(16)]
    print(f"    grid pitch {pw:.1f}x{ph:.1f} from ({cx[0]:.0f},{cy[0]:.0f})")
    return to_chars(cells)


# ---- compose + emit ---------------------------------------------------------

def compose(chars):
    """Char grid -> sprite: bloom and plant outlined separately (rose pipeline),
    1 spare row top+bottom for the rim, then trim empty rows."""
    rows = [''.join(r) for r in chars]
    rows = ['.' * 16] + rows + ['.' * 16]
    h = len(rows)
    bloom, plant = blank(16, h), blank(16, h)
    for r, line in enumerate(rows):
        for c in range(16):
            ch = line[c]
            if ch in 'dmlC':
                bloom[r][c] = PAL[ch]
            elif ch in 'kSGo':
                plant[r][c] = PAL[ch]
    grid = _rose_compose([outline(plant, GRN_OL), outline(bloom, PNK_OL)])
    while grid and all(p[3] == 0 for p in grid[0]):
        grid.pop(0)
    while grid and all(p[3] == 0 for p in grid[-1]):
        grid.pop()
    return grid


# Hand-clean step (same as the rose workflow): the pipeline output for these six
# was melty/misread — re-authored from the guide's blueprints + renders. Cluster =
# 3 stems, varied heights, flowers at stem tops (+ one mid-stem, per blueprint 04);
# 1px gaps auto-fill with rim via outline() and read as seams.
# m2_plain_0 + m1_plain_2 are the user's PLAIN picks, re-authored crisper on request
# ("kaktüs hatlarının belirlenmesi lazım"): k edge columns, k ridge dashes like the
# in-app kaktüs, seamed arm/pad junctions.
FIXUPS = {
    'm2_plain_0': [   # tall columnar pick — defined ribs + L/R arms (dots removed)
        '.......SG.......',
        '......kSGG......',
        '......kSGG......',
        '......kSGG......',
        '......kSGG......',
        '..SG..kSGG......',
        '.kSG..kSGG..SG..',
        '.kSG..kSGG..SGk.',
        '.kSGGkkSGG..SGk.',
        '..kSGkkSGGkGSk..',
        '......kSGGkGk...',
        '......kSGG......',
        '......kSGG......',
        '......kSGG......',
        '......kkSG......',
    ],
    'm1_plain_2': [   # plain prickly = de-flowered m1_flower_2 (user-picked shape)
        '...........kG...',
        '...........GGSS.',
        '..GSSG....SGSSS.',
        '..kSGG....SGSSk.',
        '..GSSS..GGkkkk..',
        '..SSSSkGGGSk....',
        '...kSkSGGGGS....',
        '....GkGSGGSS....',
        '.....kSSSSSS....',
        '.....kGSkSSS....',
        '.....kSkSSkk....',
        '......kkkkkk....',
        '......kkkkkk....',
    ],
    'm1_flower_3': [
        '......mCm.......',
        '......dmd.......',
        '......SGGG......',
        '..mCm.SGGG......',
        '..dmd.SGGG.mCm..',
        '.SSGGkSGGG.dmd..',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.kSSGkSGGGkkSSG.',
        '..kkS.kSGG.kkS..',
    ],
    'm1_plain_3': [
        '.......SG.......',
        '......SGGG......',
        '......SGGG......',
        '..SG..SGGG......',
        '.SSGGkSGGG..SG..',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.SSGGkSGGGkSSGG.',
        '.kSSGkSGGGkkSSG.',
        '..kkS.kSGG.kkS..',
    ],
    'm2_flower_0': [
        '.....mlm........',
        '....mlCm........',
        '.....dmd........',
        '.....kSSG.......',
        '.....kSSG.......',
        '.....kSSG.......',
        '.....kSSG.......',
        '.kS..kSSG.......',
        '.kS..kSSG..Sk...',
        '.kSSSkSSG..Sk...',
        '.....kSSG.SSk...',
        '.....kSSG.......',
        '.....kSSG.......',
        '.....kkSG.......',
    ],
    'm2_flower_2': [
        '.......mm.......',
        '..mm..mCm.......',
        '.mCm..SGGGk.....',
        '.SGGk.SGGGk.....',
        '..SGk.kSGk......',
        '...SSGGSSSk.....',
        '..SSGGGGSSSk....',
        '..SSGGGGSSSk....',
        '..kSSGGSSSkk....',
        '...kSSSSSkk.....',
        '.....kkkk.......',
    ],
    'm2_flower_3': [
        '......mCm.......',
        '......dmd.......',
        '......SGG.......',
        '..mCm.SGG.......',
        '..dmd.SGG..mCm..',
        '..SGGkSGG..dmd..',
        '..SGGkSGGkSGG...',
        '..SGGkSGGkmCm...',
        '..SGGkSGGkdmd...',
        '..SGGkSGGkSGG...',
        '..kSGkSGGkkSG...',
        '...kS.kSG.kS....',
    ],
    'm2_plain_3': [
        '......SG........',
        '......SGG.......',
        '......SGG.......',
        '..SG..SGG.......',
        '..SGGkSGG..SG...',
        '..SGGkSGGkSGG...',
        '..SGGkSGGkSGG...',
        '..SGGkSGGkSGG...',
        '..SGGkSGGkSGG...',
        '..SGGkSGGkSGG...',
        '..kSGkSGGkkSG...',
        '...kS.kSG.kS....',
    ],
}
for _k, _g in FIXUPS.items():
    assert all(len(r) == 16 for r in _g), f"bad row width in {_k}"


def main():
    jobs = [
        ('m1_flower', method1, SHEET_FLOWER, boxes(ART_FLOWER0)),
        ('m1_plain', method1, SHEET_PLAIN, boxes(ART_PLAIN0)),
        ('m2_flower', method2, SHEET_FLOWER, boxes(BP_FLOWER0)),
        ('m2_plain', method2, SHEET_PLAIN, boxes(BP_PLAIN0)),
    ]
    sprites = {}
    for name, fn, sheet, bxs in jobs:
        for i, box in enumerate(bxs):
            print(f"{name}_{i}")
            chars = fn(sheet, box)
            if f"{name}_{i}" in FIXUPS:
                chars = [list(r) for r in FIXUPS[f"{name}_{i}"]]
            with open(f"{OUT}\\ascii_{name}_{i}.txt", 'w') as f:
                f.write('\n'.join(''.join(r) for r in chars))
            grid = compose(chars)
            sprites[f"{name}_{i}"] = grid
            write_png(f"{OUT}\\{name}_{i}.png", upscale(grid, 16))

    # contact sheet: rows = sets, cols = 4 shapes
    order = ['m1_flower', 'm1_plain', 'm2_flower', 'm2_plain']
    labels = {'m1_flower': 'M1 TRACED + FLOWER', 'm1_plain': 'M1 TRACED PLAIN',
              'm2_flower': 'M2 BLUEPRINT + FLOWER', 'm2_plain': 'M2 BLUEPRINT PLAIN'}
    S, gap, lab = 8, 12, 22
    cellw, cellh = 16 * S + gap, 18 * S + gap + lab
    sheet = Image.new('RGB', (cellw * 4 + gap + 170, cellh * 4 + gap), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(14)
    except TypeError:
        font = ImageFont.load_default()
    for row, key in enumerate(order):
        dr.text((8, gap + row * cellh + 60), labels[key].replace(' ', '\n'),
                fill=(230, 230, 230), font=font)
        for col in range(4):
            grid = sprites[f"{key}_{col}"]
            img = Image.new('RGBA', (16, len(grid)), (0, 0, 0, 0))
            for r, line in enumerate(grid):
                for c, p in enumerate(line):
                    img.putpixel((c, r), p)
            img = img.resize((16 * S, len(grid) * S), Image.NEAREST)
            x = 170 + gap + col * cellw
            y = gap + row * cellh + lab + (16 - len(grid)) * S // 2
            sheet.paste(img, (x, y + max(0, (18 - len(grid)) * S // 2)), img)
            dr.text((x, gap + row * cellh + 2), f"SHAPE {col + 1:02d}",
                    fill=(150, 150, 160), font=font)
    sheet.save(f"{OUT}\\contact_sheet.png")
    print("done:", len(sprites), "sprites")


if __name__ == '__main__':
    main()
