# Flower study (v27): daisy / tulip / chrysanthemum / violet candidates from the
# user's guide sheets, two methods — same workflow as cactus_study:
#   M1 "traced"    — sample the rendered art panel, classify, band tones
#   M2 "blueprint" — transcribe the sheet's numbered PIXEL BLUEPRINT cells
# Output per species dir: ascii_m{1,2}_{0..3}.txt, m{1,2}_{0..3}.png (x16),
# contact_sheet.png, gardenstrip.png, calib_*.png (crop sanity checks).
import os
import sys
import pathlib

# The game checkout is found RELATIVE to this file (both live under one
# "Pixel Pomo" folder), so moving or renaming that folder can't break it.
_APP = pathlib.Path(__file__).resolve().parents[2] / "App"


sys.path.insert(0, str(_APP / "flutter" / "tools"))
from gen_objects import blank, hexrgb, upscale, write_png, outline, _rose_compose  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402


GUIDES = str(_APP / "feedback & guides" / "Guides" / "Sprite Guides")
OUT = os.path.dirname(os.path.abspath(__file__))  # this dir - outputs sit beside the script
GRASS = str(_APP / "flutter" / "assets" / "objects" / "grass.png")
GRN_OL = '1E5A24'

# app-family palettes (= gen_objects._FLOWER_PALS so candidates preview exactly
# as they'd ship): d/m/l petals, C centre, OL bloom rim.
SPECIES = {
    'daisy': dict(
        app='papatya', petal='white', centre='gold',
        pal=('CFD4DA', 'FFFFFF', 'FFDE73', 'F2C94C', '181A1F'),  # near-black rim; l = heart highlight (#v28.4)
        A=f"{GUIDES}\\Daisy\\95c4f326-0bfe-42c3-ab42-b1476dab74fb.png",
        B=f"{GUIDES}\\Daisy\\5452e4c1-262f-47ab-87e9-f3c4bb9eaddd.png",
    ),
    'tulip': dict(
        app='lale', petal='red', centre=None,
        pal=('9C1B2E', 'D93645', 'F2737C', 'F2C94C', '2E0810'),
        A=f"{GUIDES}\\Tulip\\ac23f5f5-1748-443a-900c-5e9c3adcce9a.png",
        B=f"{GUIDES}\\Tulip\\65b53ab3-ddaf-44c4-ab43-7296c1b31d1c.png",
        # col 4's sparse bud left the auto x-refine short — box from siblings' pitch
        bpfix={3: (1072, 400, 1351, 637)},
    ),
    'chrysanthemum': dict(
        app='kasimpati', petal='gold', centre=None,
        pal=('C9710B', 'F2A03A', 'F8C66A', 'E0860B', '5A3206'),
        A=f"{GUIDES}\\Chrysanteum\\47d78df8-0206-4f02-9e3b-06a22a5e07fb.png",
        B=f"{GUIDES}\\Chrysanteum\\f18feccb-1ce1-4b51-8432-17ff72d432e8.png",
        bpfix={1: (381, 438, 667, 654), 2: (730, 438, 1016, 654), 3: (1079, 438, 1364, 654)},
    ),
    'violet': dict(
        app='menekse', petal='purple', centre='gold',
        pal=('5B2A9E', '8E4FE0', 'B98CF0', 'F2C94C', '24104A'),
        A=f"{GUIDES}\\Violet\\b85f9703-3db2-40e7-a01a-63265cd718db.png",
        B=f"{GUIDES}\\Violet\\7d74e868-eea0-432f-9239-6674ba848420.png",
        # dark-purple cells sit under the brightness refine → sibling-pitch boxes
        bpfix={0: (35, 438, 316, 651), 1: (385, 438, 666, 651),
               2: (735, 438, 1016, 651), 3: (1085, 438, 1366, 651)},
    ),
}
# Per-shape sheets (second daisy round, #v27.1): the user added single-shape
# guide sheets (art panel + pixel blueprint + coordinate list on ONE sheet) —
# more authoritative than the 4-panel composites. shape idx -> sheet path;
# shapes not listed keep the composite A/B crops. 02 uses f473d1c8 (matches
# the 4-variant overview render); no per-shape 03 sheet exists.
PER_SHAPE = {
    # shape idx -> (sheet, blueprint box). The bp boxes are probe-measured and
    # HARDCODED (probe.py overlays a labeled grid): the sheets' text anti-
    # aliasing defeats gray/paint auto-detection, and image.png's grid render
    # even has a glitch 17th row slot (its extra empty '16' row falls off the
    # end of a 16-slot box — all content rows are <= 13).
    'daisy': {
        0: (f"{GUIDES}\\Daisy\\c9934cca-d7eb-4d7f-957c-85d7758b8a3c.png",  # DAISY 01 classic
            (44, 570, 504, 1086)),
        1: (f"{GUIDES}\\Daisy\\f473d1c8-de44-44f9-beb8-211054d1b78c.png",  # DAISY 02 wide
            (44, 570, 504, 1086)),
        3: (f"{GUIDES}\\Daisy\\image.png",                                 # DAISY 04 bushy
            (57, 707, 528, 1291)),
    },
}

# fix a typo-prone path programmatically: use whatever file actually exists
for sp in SPECIES.values():
    for k in ('A', 'B'):
        if not os.path.exists(sp[k]):
            d = os.path.dirname(sp[k])
            base = os.path.basename(sp[k])[:8]
            for f in os.listdir(d):
                if f.startswith(base):
                    sp[k] = os.path.join(d, f)
                    break
            assert os.path.exists(sp[k]), sp[k]


# ---- pixel classes ----------------------------------------------------------

def is_gold(r, g, b):
    return r > 165 and g > 130 and b < 130 and g - b > 70 and r - g < 80


def mk_rawclass(petal, centre):
    """-> fn(pixel) -> ('petal'|'green'|'centre', lum) | ('X', dark) | None."""
    def f(p):
        r, g, b = p[:3]
        mx = max(r, g, b)
        lum = 0.3 * r + 0.59 * g + 0.11 * b
        if mx < 45:
            return None                                    # bg / outline
        if centre == 'gold' and is_gold(r, g, b):
            return ('centre', lum)
        if petal == 'white':
            if mx > 185 and mx - min(r, g, b) < 50:
                return ('petal', lum)
        elif petal == 'red':
            if r > 125 and r - g > 50 and r - b > 40:
                return ('petal', lum)
        elif petal == 'gold':
            if is_gold(r, g, b) or (r > 200 and g > 175 and b < 165 and g - b > 40):
                return ('petal', lum)                      # incl. pale light-yellow
        elif petal == 'purple':
            if b > g + 25 and b > 110 and r > 55 and r < b + 30:
                return ('petal', lum)
        if abs(r - g) < 18 and abs(g - b) < 18:
            return None                                    # gray: gridline / text
        if 150 < r < 250 and 100 < g < 210 and b < 130 and r > g > b:
            return None                                    # sand / soil: not ours
        if g > b + 18 and g >= r - 12 and g > 60:
            return ('green', lum)
        return None
    return f


def kmeans3(vals):
    sv = sorted(vals)
    n = len(sv)
    cents = [sv[max(0, n // 5)], sv[n // 2], sv[min(n - 1, 4 * n // 5)]]
    for _ in range(8):
        groups = [[] for _ in range(3)]
        for v in vals:
            groups[min(range(3), key=lambda i: abs(v - cents[i]))].append(v)
        cents = [sum(g) / len(g) if g else cents[i] for i, g in enumerate(groups)]
    cents.sort()
    return cents, lambda v: min(range(3), key=lambda i: abs(v - cents[i]))


def to_chars(cells):
    """16xH rawclass results -> char grid. Petals band d/m/l, greens k/S/G,
    centre 'C'; solid-dark cells between greens become interior seams 'o'."""
    H = len(cells)
    gv = [c[1] for row in cells for c in row if c and c[0] == 'green']
    pv = [c[1] for row in cells for c in row if c and c[0] == 'petal']
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
            if t == 'green':
                chars[r][c] = 'kSG'[gband(v)]
            elif t == 'petal':
                chars[r][c] = 'dml'[pband(v)]
            elif t == 'centre':
                chars[r][c] = 'C'
    for r in range(H):
        for c in range(16):
            cl = cells[r][c]
            if not cl or cl[0] != 'X':
                continue
            lr = 0 < c < 15 and cells[r][c - 1] and cells[r][c + 1] \
                and cells[r][c - 1][0] == 'green' and cells[r][c + 1][0] == 'green'
            ud = 0 < r < H - 1 and cells[r - 1][c] and cells[r + 1][c] \
                and cells[r - 1][c][0] == 'green' and cells[r + 1][c][0] == 'green'
            plr = 0 < c < 15 and cells[r][c - 1] and cells[r][c + 1] \
                and cells[r][c - 1][0] in ('petal', 'centre') and cells[r][c + 1][0] in ('petal', 'centre')
            pud = 0 < r < H - 1 and cells[r - 1][c] and cells[r + 1][c] \
                and cells[r - 1][c][0] in ('petal', 'centre') and cells[r + 1][c][0] in ('petal', 'centre')
            if lr or ud:
                chars[r][c] = 'o'
            elif plr or pud:
                chars[r][c] = 'x'  # bloom-interior seam (bushy daisy separates its blooms with outline cells)
            elif cl[1] and cl[1][0] == 'green':
                chars[r][c] = 'kSG'[gband(cl[1][1])]
    return despeckle(chars)


def despeckle(chars):
    H = len(chars)

    def nb(r, c):
        return [chars[rr][cc] for rr in range(r - 1, r + 2) for cc in range(c - 1, c + 2)
                if (rr, cc) != (r, c) and 0 <= rr < H and 0 <= cc < 16]
    for r in range(H):
        for c in range(16):
            ch = chars[r][c]
            filled = [n for n in nb(r, c) if n != '.']
            if ch != '.' and len(filled) <= 1 and ch not in 'dmlCox':
                chars[r][c] = '.'
            elif ch == '.' and len(filled) >= 7:
                chars[r][c] = max(set(filled), key=filled.count)
    return chars


# ---- panel + blueprint auto-detection ---------------------------------------

def is_panel_green(p):
    r, g, b = p[:3]
    return g > 95 and g > r + 20 and g > b + 45 and r < 200


def is_panel_tan(p):
    r, g, b = p[:3]
    return 165 < r < 250 and 120 < g < 215 and 70 < b < 175 and r > g > b


def bands(hist, thresh, minlen):
    out, start = [], None
    for i, v in enumerate(list(hist) + [0]):
        if v >= thresh and start is None:
            start = i
        elif v < thresh and start is not None:
            if i - start >= minlen:
                out.append((start, i))
            start = None
    return out


def find_art_panels(path, raw, n=4):
    """n big grass rectangles → boxes, left-to-right. The panel mask counts the
    sprite's own petal/centre colors too — a big white daisy bloom would
    otherwise split its green panel into two bands. n=1 (per-shape sheet):
    the WIDEST green band is the DRAWN PIXEL ART panel (the in-game preview
    panel beside it is narrower)."""
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    top = int(h * 0.45)  # panels live in the top row; skips the garden strip

    def pred(p):
        if is_panel_green(p):
            return True
        cl = raw(p)
        return cl is not None and cl[0] in ('petal', 'centre')

    mask = [[pred(px[x, y]) for x in range(w)] for y in range(top)]
    colh = [sum(mask[y][x] for y in range(top)) for x in range(w)]
    cols = bands(colh, 80, 90)
    if n == 1:
        assert cols, f"{path}: no art band"
        cols = [max(cols, key=lambda c: c[1] - c[0])]
    # keep the 4 most similar-width bands (drops the full-width garden strip)
    if len(cols) > 4:
        med = sorted(x1 - x0 for x0, x1 in cols)[len(cols) // 2]
        cols = [c for c in cols if abs((c[1] - c[0]) - med) < med * 0.35][:4]
    if len(cols) == 3:  # one panel's colors slipped the predicate → infer from pitch
        pitch = min(b[0] - a[0] for a, b in zip(cols, cols[1:]))
        wid = sorted(c[1] - c[0] for c in cols)[1]
        xs = [cols[0][0] + k * pitch for k in range(4)]
        have = [any(abs(c[0] - x) < pitch // 3 for c in cols) for x in xs]
        cols = sorted(cols + [(xs[k], xs[k] + wid) for k in range(4) if not have[k]])
    assert len(cols) == n, f"{path}: art col bands = {cols}"
    boxes = []
    for (x0, x1) in cols:
        rowh = [sum(mask[y][x] for x in range(x0, x1)) for y in range(top)]
        rows = bands(rowh, (x1 - x0) * 45 // 100, 70)
        assert rows, f"no row band in col {(x0, x1)} of {path}"
        y0, y1 = rows[0]  # topmost = the art panel (titles/notes are too sparse)
        boxes.append((x0, y0, x1, y1))
    return boxes


def is_grid_gray(p):
    r, g, b = p[:3]
    return abs(r - g) < 14 and abs(g - b) < 14 and 26 < max(r, g, b) < 140


def movingmax(hist, w=25):
    """Envelope: gridlines are thin periodic peaks — a moving max bridges the
    dark gaps between them so the whole grid reads as one band."""
    n = len(hist)
    return [max(hist[max(0, i - w):min(n, i + w + 1)]) for i in range(n)]


def find_blueprints(path, n=4):
    """n blueprint grids = the big columns of gridline-gray pixels; refine
    the row extent inside each column, then the x extent inside those rows.
    n=1 (per-shape sheet): the widest gray band is the one PIXEL BLUEPRINT."""
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    W = 14  # envelope window ≳ half the cell pitch: bridges the 15-30px line gaps
    mask = [[is_grid_gray(px[x, y]) for x in range(w)] for y in range(h)]
    # refine passes count "gridline OR painted cell" — colored/white cells
    # replace the gridlines they cover, which used to cut the box mid-grid
    cell = [[mask[y][x] or max(px[x, y]) > 150 for x in range(w)] for y in range(h)]
    colh = movingmax([sum(mask[y][x] for y in range(h)) for x in range(w)], W)
    cols = bands(colh, max(70, h // 14), 150)
    if len(cols) > n:
        cols = sorted(cols, key=lambda c: c[1] - c[0], reverse=True)[:n]
        cols.sort()
    assert len(cols) == n, f"{path}: grid col bands = {cols}"
    boxes = []
    for (x0, x1) in cols:
        rowh = movingmax([sum(cell[y][x] for x in range(x0, x1)) for y in range(h)], W)
        rows = bands(rowh, (x1 - x0) // 3, 120)
        assert rows, f"no grid rows in {(x0, x1)} of {path}"
        y0, y1 = max(rows, key=lambda r: r[1] - r[0])
        colh2 = movingmax([sum(cell[y][x] for y in range(y0, y1)) for x in range(x0, x1)], W)
        cbs = bands(colh2, (y1 - y0) // 3, 120)
        assert cbs, f"no grid cols in {(x0, x1)} of {path}"
        cx0, cx1 = max(cbs, key=lambda c: c[1] - c[0])
        boxes.append((x0 + cx0 + W - 6, y0 + W - 6, x0 + cx1 - W + 6, y1 - W + 6))
    return boxes


def _runs(vals, maxgap):
    groups, s, p = [], None, None
    for v in vals:
        if s is None:
            s = p = v
        elif v - p <= maxgap:
            p = v
        else:
            groups.append((s, p))
            s = p = v
    if s is not None:
        groups.append((s, p))
    return groups


def find_art_panel_single(path, raw):
    """Per-shape sheet: ONE 'DRAWN PIXEL ART' panel = the widest green column
    band; its y extent = the longest run of mostly-NON-DARK rows (the flower's
    dark leaf mass and fat outline fail the green predicate and used to cut
    the panel short — anything brighter than the near-black sheet bg counts)."""
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    top = int(h * 0.45)

    def pred(p):
        if is_panel_green(p):
            return True
        cl = raw(p)
        return cl is not None and cl[0] in ('petal', 'centre')

    mask = [[pred(px[x, y]) for x in range(w)] for y in range(top)]
    colh = [sum(mask[y][x] for y in range(top)) for x in range(w)]
    cols = bands(colh, 80, 90)
    assert cols, f"{path}: no art band"
    x0, x1 = max(cols, key=lambda c: c[1] - c[0])
    ys = [y for y in range(top)
          if sum(max(px[x, y][:3]) > 60 for x in range(x0, x1, 2)) * 2 > (x1 - x0) * 0.72]
    assert ys, f"{path}: no art rows"
    # maxgap must bridge the sprite's full-width BLACK OUTLINE bands (up to ~2
    # cells ≈ 90px) that read as dark rows mid-panel; the title text above and
    # the sheet bg below never qualify, so the run still stops at the panel.
    y0, y1 = max(_runs(ys, 90), key=lambda g: g[1] - g[0])
    return (x0, y0, x1, y1 + 1)


def find_blueprint_single(path):
    """Per-shape sheet: ONE pixel-blueprint grid. Coarse x band from gridline-
    gray columns, then SNAP to the outermost long gridlines (rows/cols where
    ≥35% of the band is gridline-gray, clustered with gaps up to ~1.5 cells) —
    excludes the white coordinate-list text and the axis labels, and keeps the
    grid's empty bottom rows that the envelope detector used to drop."""
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    W = 14
    mask = [[is_grid_gray(px[x, y]) for x in range(w)] for y in range(h)]

    def painted(p):
        r, g, b = p[:3]
        sat = max(p[:3]) - min(p[:3])
        return (sat > 55 and max(p[:3]) > 80) or (max(p[:3]) > 195 and sat < 45) \
            or (g > r + 12 and g > b + 12 and g > 55)  # incl. dark leaf cells

    colh = movingmax([sum(mask[y][x] for y in range(h)) for x in range(w)], W)
    cols = bands(colh, max(70, h // 14), 150)
    assert cols, f"{path}: no grid band"
    x0, x1 = max(cols, key=lambda c: c[1] - c[0])

    # A line qualifies when it's mostly gridline-gray (empty grid regions), OR
    # heavily painted while still showing SOME gray (a gridline buried under
    # painted cells). Title/coordinate text is painted but has ~zero gray.
    def qrow(y):
        n = (x1 - x0 + 1) // 2
        g = sum(mask[y][x] for x in range(x0, x1, 2))
        p = sum(painted(px[x, y]) for x in range(x0, x1, 2))
        return g > n * 0.30 or (p > n * 0.45 and g > n * 0.04)

    ys = [y for y in range(h) if qrow(y)]
    assert ys, f"{path}: no gridline rows"
    y0, y1 = max(_runs(ys, 55), key=lambda g: g[1] - g[0])

    def qcol(x):
        n = (y1 - y0 + 1) // 2
        g = sum(mask[y][x] for y in range(y0, y1, 2))
        p = sum(painted(px[x, y]) for y in range(y0, y1, 2))
        return g > n * 0.30 or (p > n * 0.45 and g > n * 0.04)

    xs = [x for x in range(max(0, x0 - 40), min(w, x1 + 40)) if qcol(x)]
    assert xs, f"{path}: no gridline cols"
    gx0, gx1 = max(_runs(xs, 55), key=lambda g: g[1] - g[0])
    pw, ph = (gx1 - gx0) / 16, (y1 - y0) / 16
    assert 12 < pw < 60 and abs(pw - ph) < 5, f"{path}: grid pitch {pw:.1f}x{ph:.1f}"
    return (gx0, y0, gx1 + 1, y1 + 1)


# ---- the two methods --------------------------------------------------------

def mk_sample9(rawclass, ring_only=False):
    """ring_only (blueprints): skip the centre point — every blueprint cell has
    a white DIGIT glyph dead-centre, which used to outvote the cell colour
    ('1' outline cells sampled as white petals → stray nubs, merged blooms)."""
    offs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if not (ring_only and dx == 0 and dy == 0)]
    thr_black = 5 if not ring_only else 5
    def sample9(px, x, y, r):
        pts = [px[int(x + dx * r), int(y + dy * r)] for dx, dy in offs]
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
            return ('X', None) if nblack >= thr_black else None
        return best if nblack < 3 else ('X', best)
    return sample9


def method1(sheet, box, sample9):
    """Unlike the cactus sheets (sand bg), these panels sit on GRASS — estimate
    the grass luminance from the panel's outer ring and drop green pixels at or
    above it, keeping only the darker plant greens."""
    im = Image.open(sheet).convert('RGB').crop(box)
    px = im.load()
    cw, ch = im.width / 16, im.height / 16
    # grass colour from the panel's outer ring — per-CHANNEL median, and drop
    # green pixels by colour DISTANCE, not luminance: the sheets' light leaf
    # green is BRIGHTER than grass, so the old lum cut ate whole leaves.
    ring = []
    for c in range(16):
        for r in (0, 15):
            ring.append(px[int((c + 0.5) * cw), int((r + 0.5) * ch)])
            ring.append(px[int((r + 0.5) * cw), int((c + 0.5) * ch)])
    ring = [p for p in ring if p[1] > p[0] and p[1] > p[2] and p[1] > 60]
    if ring:
        gmed = tuple(sorted(p[i] for p in ring)[len(ring) // 2] for i in range(3))
    else:
        gmed = (-999, -999, -999)

    def s9(pxl, x, y, rad):
        cl = sample9(pxl, x, y, rad)
        if cl and cl[0] == 'green':
            p0 = pxl[int(x), int(y)]
            if sum((a - b) ** 2 for a, b in zip(p0[:3], gmed)) < 42 ** 2:
                return None
        return cl

    cells = [[s9(px, (c + 0.5) * cw, (r + 0.5) * ch, min(cw, ch) * 0.30)
              for c in range(16)] for r in range(16)]
    return to_chars(cells)


def colorprofile(im, vertical):
    """Count of blueprint-cell pixels per column/row: saturated OR near-white
    (daisy petals) — gridline grays and bg stay out."""
    px = im.load()
    n = im.width if vertical else im.height
    m = im.height if vertical else im.width
    prof = []
    for i in range(n):
        cnt = 0
        for j in range(0, m, 2):
            p = px[(i, j) if vertical else (j, i)]
            sat = max(p) - min(p)
            if (sat > 55 and max(p) > 80) or (max(p) > 195 and sat < 45):
                cnt += 1
        prof.append(cnt)
    return prof


def fitgrid(prof, n_px):
    """(pitch, phase) for a TIGHT box: grid spans nearly the whole crop."""
    best, bx = None, None
    lo, hi = (n_px - 10) / 16, n_px / 16
    p = lo
    while p <= hi:
        for phase in range(0, 10):
            if phase + 16 * p > n_px:
                continue
            s = 0.0
            for i in range(16):
                s += prof[min(n_px - 1, int(phase + (i + 0.5) * p))]
                s -= prof[min(n_px - 1, int(phase + i * p))]
            s -= prof[min(n_px - 1, int(phase + 16 * p))]
            if best is None or s > best:
                best, bx = s, (p, phase)
        p += 0.1
    pitch, phase = bx
    centers = []
    rad = max(2, int(pitch * 0.25))
    for i in range(16):
        x0 = int(phase + (i + 0.5) * pitch)
        cand = max(range(max(0, x0 - rad), min(len(prof), x0 + rad + 1)),
                   key=lambda j: prof[j])
        centers.append(cand if prof[cand] > 4 else x0)
    return centers, pitch


def method2(sheet, box, sample9, radf=0.26):
    im = Image.open(sheet).convert('RGB').crop(box)
    cx, pw = fitgrid(colorprofile(im, True), im.width)
    cy, ph = fitgrid(colorprofile(im, False), im.height)
    px = im.load()
    cells = [[sample9(px, cx[c], cy[r], min(pw, ph) * radf) for c in range(16)]
             for r in range(16)]
    print(f"    grid pitch {pw:.1f}x{ph:.1f} from ({cx[0]:.0f},{cy[0]:.0f})")
    return to_chars(cells)


# ---- compose + emit ---------------------------------------------------------

def compose(chars, pal_hex):
    d, m, l, cen, ol = pal_hex
    PAL = {
        'd': hexrgb(d) + (255,), 'm': hexrgb(m) + (255,), 'l': hexrgb(l) + (255,),
        'C': hexrgb(cen) + (255,), 'x': hexrgb(ol) + (255,),
        'k': hexrgb('2C6E2A') + (255,), 'S': hexrgb('3E8E36') + (255,),
        'G': hexrgb('5FBF4A') + (255,), 'o': hexrgb(GRN_OL) + (255,),
    }
    rows = [''.join(r) for r in chars]
    rows = ['.' * 16] + rows + ['.' * 16]
    h = len(rows)
    bloom, plant = blank(16, h), blank(16, h)
    for r, line in enumerate(rows):
        for c in range(16):
            ch = line[c]
            if ch in 'dmlCx':
                bloom[r][c] = PAL[ch]
            elif ch in 'kSGo':
                plant[r][c] = PAL[ch]
    grid = _rose_compose([outline(plant, GRN_OL), outline(bloom, ol)])
    while grid and all(p[3] == 0 for p in grid[0]):
        grid.pop(0)
    while grid and all(p[3] == 0 for p in grid[-1]):
        grid.pop()
    return grid


# Hand-clean step (rose workflow): re-authored grids replace melty pipeline
# output — pipeline ascii as scaffold, guide blueprints/renders as reference.
# These 8 are the integration picks (2 per species).
FIXUPS = {
    # DAISY round 3 (#v27.1 feedback: "pure pipeline output" was the wrong call —
    # rose/cactus finals were always HAND-authored over the trace scaffold; the
    # sampler mangles thin white petals, and the sheets' soft render bleeds
    # across cells). These 8 grids are hand-drawn BY EYE from the per-shape
    # blueprints/art: m2_* = blueprint-exact (smooth ring silhhouettes, the
    # sheets' cell layout), m1_* = render-feel (separated petal lobes like the
    # drawn art panels). Symmetric, 1px rims, deliberate d-shadows, 3-4 colors.
    'daisy_m1_0': [   # classic, render-feel — distinct petal lobes, fat gold eye
        '......mm........',
        '..mm.mmmm.mm....',
        '..mmmmmmmmmm....',
        '...mmmCCCmmm....',
        '...mmCCCCCmm....',
        '...mmmCCCmmm....',
        '..mmmmmmmmmm....',
        '..mm.mddm.mm....',
        '......mm........',
        '.......S........',
        '.......S........',
        '....G..S..G.....',
        '...GGkkSkkGG....',
        '....GGGSGGG.....',
        '.......S........',
    ],
    'daisy_m2_0': [   # classic — FINAL (#v28.8): uniform 2/4/4/2 dark-gold
        # heart, all seams aligned; tapered corners, rounded mound.
        '......dmmd......',
        '....m.mmmm.m....',
        '...mmmdmmdmmm...',
        '...dmmdCCdmmd...',
        '..mmmmCCCCmmmm..',
        '..dmmmCCCCmmmd..',
        '...mmmdCCdmmm...',
        '...mmmdmmdmmm...',
        '....d.mmmm.d....',
        '......mmmm......',
        '..GG..GGGG..GG..',
        '..GGGGkkkkGGGG..',
        '....GGkkkkGG....',
        '......GGGG......',
    ],
    'daisy_m1_1': [   # wide, render-feel — spread petal tips, low profile
        '....mm.mm.mm....',
        '..mmmmmmmmmmm...',
        '.mmmdCCCCdmmmm..',
        '.mmmCCCCCCmmmm..',
        '..mmmCCCCmmmm...',
        '...mm.mmm.mm....',
        '.......S........',
        '..GGGGkSkGGGG...',
        '.GGSGGGSGGGSGG..',
        '....kGGSGGk.....',
    ],
    'daisy_m2_1': [   # wide, blueprint-exact — flat oval, 4-6-6 gold core, widest leaves
        '.....mmmmmm.....',
        '...mmmCCCCmmm...',
        '..mmmCCCCCCmmm..',
        '..mmmCCCCCCmmm..',
        '...mmdmmmmdmm...',
        '.......S........',
        '.GGGGGkSkGGGGG..',
        '..GGSGGSGGSGG...',
        '...kkGGSGGkk....',
    ],
    'daisy_m1_2': [   # tall, render-feel — notched little head, long stem
        '......m.m.......',
        '.....mmmmm......',
        '.....mCCCm......',
        '.....mmmmm......',
        '......m.m.......',
        '.......S........',
        '.......S........',
        '.......S........',
        '.......S........',
        '.....G.S.G......',
        '....GGkSkGG.....',
        '.....kGSGk......',
        '.......S........',
    ],
    'daisy_m2_2': [   # tall, blueprint-exact — round mini bloom, elegant stem
        '......mmm.......',
        '.....mCCCm......',
        '.....mCCCm......',
        '......mmm.......',
        '.......S........',
        '.......S........',
        '.......S........',
        '.......S........',
        '.......S........',
        '....G..S..G.....',
        '...GGkSkGG......',
        '.....GGSGG......',
        '.......S........',
    ],
    'daisy_m1_3': [   # bushy, render-feel — three notched heads over the mound
        '......m.m.......',
        '.....mmmmm......',
        '.....mCCCm..m...',
        '.....mmmmm.mmm..',
        '..m...mm...mCm..',
        '.mmm...S...mmm..',
        '.mCm...S....m...',
        '.mmm...S........',
        '..m....S........',
        '..GGGkGSGkGGG...',
        '.GGSGGkSkGGSGG..',
        '..GGkSGSGSkGG...',
        '...kGGkSkGGk....',
        '.....kkkkk......',
    ],
    'daisy_m2_3': [   # bushy (#v28.9) — side blooms mirror about the STEM
        # column c7 (not the grid midline), everything centers on the stem.
        '......mmm.......',
        '.....mmCmm......',
        '.....mmCmm......',
        '......mmm.......',
        '..mmm..S..mmm...',
        '.mmCmm.S.mmCmm..',
        '.mmCmm.S.mmCmm..',
        '..mmm..S..mmm...',
        '.......S........',
        '..GGGkGSGkGGG...',
        '.GGSGGkSkGGSGG..',
        '..GGkSGSGSkGG...',
        '...kGGkSkGGk....',
        '.....kkkkk......',
    ],
    'tulip_m2_0': [   # classic closed tulip — smooth cup, blade leaves
        '.......ll.......',
        '......lmml......',
        '.....dmmmmd.....',
        '.....dmmmmd.....',
        '.....dmlmld.....',
        '......dmmd......',
        '.......S........',
        '.......S........',
        '.....G.S.G......',
        '....GGkSkGG.....',
        '.....GGSGG......',
        '......kSk.......',
        '.......S........',
    ],
    'tulip_m2_2': [   # open tulip — flared crown with three tips
        '.....l..l..l....',
        '.....mllmllm....',
        '....dmmmmmmd....',
        '....dmmmmmmd....',
        '.....dmmmmd.....',
        '......dmmd......',
        '.......S........',
        '.......S........',
        '....GkkSkkG.....',
        '.....GGSGG......',
        '......kSk.......',
        '.......S........',
    ],
    'chrysanthemum_m2_0': [   # pom-pom mum — dense round bloom, curl speckles
        '......mmm.......',
        '....mlmlmlm.....',
        '....lmdmlml.....',
        '...mlmldmlmm....',
        '...mmdmlmdlm....',
        '....lmldmlm.....',
        '.....mdmdm......',
        '......mmm.......',
        '.......S........',
        '.......S........',
        '....GGkSkGG.....',
        '.....GGSGG......',
        '.......S........',
    ],
    'chrysanthemum_m2_1': [   # spider mum — thin radiating petals
        '....d..m..d.....',
        '....md.m.dm.....',
        '.....mmmmm......',
        '...mmldmdlmm....',
        '.....mmmmm......',
        '....md.m.dm.....',
        '....d..m..d.....',
        '.......S........',
        '.......S........',
        '....GGkSkGG.....',
        '.....GGSGG......',
        '.......S........',
    ],
    'violet_m2_0': [   # classic violet — five-petal bloom, gold eye, leaf mound
        '.....mm.mm......',
        '....lmmlmml.....',
        '....lmmCmml.....',
        '.....mmlmm......',
        '......mmm.......',
        '.......S........',
        '.......S........',
        '....GkkSkkG.....',
        '...GGSGGSGGG....',
        '....kGGSGGk.....',
        '.....kkkkk......',
    ],
    'violet_m2_1': [   # upright violets — two blooms + side bud over the mound
        '......mm........',
        '.....lmml.......',
        '.....mlCm.ll....',
        '......mm..mm....',
        '.......S..d.....',
        '.......S.S......',
        '..ll...S.S......',
        '..lmd..SS.......',
        '...d...S........',
        '...S...S........',
        '..GGSkGSGkGG....',
        '...GGkSGGkG.....',
        '....kkkkk.......',
    ],
}
for _k, _g in FIXUPS.items():
    assert all(len(r) == 16 for r in _g), f"bad row width in {_k}"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    font = ImageFont.load_default()
    tile = Image.open(GRASS).convert('RGB').resize((128, 128), Image.NEAREST)
    for name, sp in SPECIES.items():
        if only and name != only:
            continue
        print(f"== {name}")
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        raw = mk_rawclass(sp['petal'], sp['centre'])
        s9 = mk_sample9(raw)
        s9r = mk_sample9(raw, ring_only=True)  # blueprints: dodge the digit glyphs
        art = find_art_panels(sp['A'], raw)
        bps = find_blueprints(sp['B'])
        srcA = {i: sp['A'] for i in range(4)}
        srcB = {i: sp['B'] for i in range(4)}
        for i, (sheet, bpbox) in PER_SHAPE.get(name, {}).items():
            srcA[i], srcB[i] = sheet, sheet
            art[i] = find_art_panel_single(sheet, raw)
            bps[i] = bpbox
        sprites = {}
        for i, box in enumerate(art):
            Image.open(srcA[i]).convert('RGB').crop(box).save(f"{d}\\calib_art_{i}.png")
            print(f"  m1_{i} art box {box}")
            chars = FIXUPS.get(f"{name}_m1_{i}") or method1(srcA[i], box, s9)
            chars = [list(r) for r in chars]
            sprites[f"m1_{i}"] = chars
        for i, box in enumerate(bps):
            box = sp.get('bpfix', {}).get(i, box)
            Image.open(srcB[i]).convert('RGB').crop(box).save(f"{d}\\calib_bp_{i}.png")
            print(f"  m2_{i} bp box {box}")
            # ring-only sampling ONLY for the per-shape sheets (big ~30px cells,
            # digit dead-centre); the composite grids' cells are too small for
            # the ring — their digits are unavoidable either way.
            pershape = i in PER_SHAPE.get(name, {})
            chars = FIXUPS.get(f"{name}_m2_{i}") or \
                method2(srcB[i], box, s9r if pershape else s9, 0.28 if pershape else 0.26)
            chars = [list(r) for r in chars]
            sprites[f"m2_{i}"] = chars

        grids = {}
        for key, chars in sprites.items():
            with open(f"{d}\\ascii_{key}.txt", 'w') as f:
                f.write('\n'.join(''.join(r) for r in chars))
            grid = compose(chars, sp['pal'])
            grids[key] = grid
            write_png(f"{d}\\{key}.png", upscale(grid, 16))

        # contact sheet (2 rows: m1 / m2) + gardenstrip on real grass
        S, gap, lab = 8, 12, 20
        cellw, cellh = 16 * S + gap, 18 * S + gap + lab
        sheet = Image.new('RGB', (cellw * 4 + gap + 130, cellh * 2 + gap), (24, 24, 28))
        dr = ImageDraw.Draw(sheet)
        for row, mkey in enumerate(('m1', 'm2')):
            dr.text((8, gap + row * cellh + 60),
                    'M1 TRACED' if mkey == 'm1' else 'M2 BLUEPRINT', fill=(230, 230, 230), font=font)
            for coln in range(4):
                grid = grids[f"{mkey}_{coln}"]
                img = Image.new('RGBA', (16, len(grid)), (0, 0, 0, 0))
                for r, line in enumerate(grid):
                    for c, p in enumerate(line):
                        img.putpixel((c, r), p)
                img = img.resize((16 * S, len(grid) * S), Image.NEAREST)
                x = 130 + gap + coln * cellw
                y = gap + row * cellh + lab + max(0, (16 - len(grid))) * S // 2
                sheet.paste(img, (x, y), img)
                dr.text((x, gap + row * cellh + 2), f"SHAPE {coln + 1:02d}", fill=(150, 150, 160), font=font)
        sheet.save(f"{d}\\contact_sheet.png")

        strip = Image.new('RGB', (128 * 4, 128 * 2))
        for nidx, key in enumerate([f"{m}_{i}" for m in ('m1', 'm2') for i in range(4)]):
            r, c = divmod(nidx, 4)
            cell = tile.copy()
            spim = Image.open(f"{d}\\{key}.png").convert('RGBA')
            w = 96
            hh = round(spim.height * w / spim.width)
            spim = spim.resize((w, hh), Image.NEAREST)
            cell.paste(spim, ((128 - w) // 2, 128 - hh - 6), spim)
            strip.paste(cell, (c * 128, r * 128))
        strip.save(f"{d}\\gardenstrip.png")
        print(f"  -> {d}")


if __name__ == '__main__':
    main()
