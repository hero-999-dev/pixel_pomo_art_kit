"""The bridge to Pixel Pomo's sprite generator.

Everything the art kit knows about the engine's file format comes from
`gen_objects.py` itself — imported, never copied. A reimplementation would be a
second source of truth that drifts the first time either side is touched, and
the whole point of this app is that its output IS the shipped sprite.
"""
import functools
import io
import importlib.util
import os
import sys
from pathlib import Path

from art_kit import provenance
from art_kit.model import Drawing, Palette, BLOOM_LETTERS, PLANT_LETTERS

# Both checkouts live side by side under one "Pixel Pomo" folder, so the game
# is found RELATIVE to this file (art_kit/ -> ArtKit/ -> Pixel Pomo/ -> App/).
# That survives the whole folder being moved or renamed, which the old absolute
# default did not. PIXEL_POMO_TOOLS still wins, for a layout that isn't this one.
APP_DIR = Path(__file__).resolve().parents[2] / "App"
GEN_OBJECTS_DIR = Path(
    os.environ.get("PIXEL_POMO_TOOLS", str(APP_DIR / "flutter" / "tools"))
)
# The game's shipped sprites, beside its tools: flutter/tools -> flutter/assets.
OBJECTS_DIR = GEN_OBJECTS_DIR.parent / "assets" / "objects"


@functools.lru_cache(maxsize=1)
def gen_objects():
    """The `gen_objects` module, imported from the Pixel Pomo checkout."""
    path = GEN_OBJECTS_DIR / "gen_objects.py"
    if not path.exists() and getattr(sys, "frozen", False):
        # Packaged as a standalone .exe on a machine with no game checkout:
        # fall back to the copy PyInstaller bundled at the archive root.
        path = Path(sys._MEIPASS) / "gen_objects.py"
    if not path.exists():
        raise FileNotFoundError(
            f"gen_objects.py not found at {path}. Point the PIXEL_POMO_TOOLS "
            f"environment variable at the game's flutter\\tools folder."
        )
    spec = importlib.util.spec_from_file_location("gen_objects", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Catalogue order — the rose first, the way the shop lists them.
SPECIES = ["gul", "papatya", "lale", "kaktus", "kaktusf", "kaktusd",
           "kasimpati", "menekse", "nilufer", "orkide", "begonya", "kamelya"]

# What the ARTIST sees. The ids above are Turkish because the engine loads
# `flower_gul_0.png` and saved gardens reference them by that name — renaming
# them would break every shipped sprite and every save. The artists do not read
# Turkish, so the library list, the window title and the species picker show
# these instead (#v2.2.0).
#
# Copied from the game's own catalogue (`Flowers.all` in logic.dart), not
# invented here, so the kit and the shop call the same flower the same thing.
# `kaktus` is the pre-#v26 cactus, kept because its art still generates; the
# game maps it to `kaktusd` for saves.
DISPLAY_NAMES = {
    "gul": "Rose",
    "papatya": "Daisy",
    "lale": "Tulip",
    "kaktus": "Cactus (old)",
    "kaktusf": "Flower Cactus",
    "kaktusd": "Desert Cactus",
    "kasimpati": "Chrysanthemum",
    "menekse": "Violet",
    "nilufer": "Water Lily",
    "orkide": "Orchid",
    "begonya": "Begonia",
    "kamelya": "Camellia",
    "anthurium": "Anthurium",
    "pilea": "Pilea",
    "sundew": "Sundew",
    "tree": "Tree",
    "bush": "Bush",
    "rock": "Rock",
}

# Drawing Patch 1 (the game's #v36.1): three houseplants Ola Górecka drew as 16x16
# pixel art. The rest of the catalogue is generator output; these the game
# ships as the very PNGs she drew - flutter/assets/objects, at x16 - so that
# is where the kit reads them from (#v2.8.0). `(species, how many models)`;
# anthurium has one form, and its one sprite carries no model number.
PATCH_FLOWERS = {"anthurium": 1, "pilea": 2, "sundew": 2}
PATCH_ARTIST = "Ola Górecka"   # was "Mir" until the ninth test pass of #v2.8.0

# The garden's critters (#v2.7.0, item 13): the engine's CRITTERS table, in
# its order, as `bug` models 0..6. Each is an 8x8 raw-pixel sprite; the game
# spins it into a facing atlas (`make_atlas`) when it writes `<id>.png`, which
# is why the kit exports the single base frame under that id and leaves the
# atlas to the developer.
BUG_IDS = ["bee", "butterfly", "ladybug", "ladybug_yellow", "butterfly_monarch",
           "butterfly_blue", "bee_bumble"]
BUG_NAMES = {
    "bee": "Bee", "butterfly": "Butterfly", "ladybug": "Ladybug",
    "ladybug_yellow": "Yellow Ladybug", "butterfly_monarch": "Monarch Butterfly",
    "butterfly_blue": "Blue Butterfly", "bee_bumble": "Bumblebee",
}
BUG = "bug"


def display_name(species, model):
    """The label the artist sees for one drawing — never a filename."""
    if species == BUG:
        return BUG_NAMES.get(BUG_IDS[model % len(BUG_IDS)], f"Bug {model + 1}")
    base = DISPLAY_NAMES.get(species, species)
    if is_forest(species):
        return f"{base} {model + 1:02d}"
    if PATCH_FLOWERS.get(species) == 1:
        return base  # the only form there is: "Anthurium", not "Anthurium 1"
    return f"{base} {model + 1}"

# The forest that surrounds the garden (#v34.8). Not flowers: these are raw
# pixel art with no letter palette and no rim pass — the engine draws them
# exactly as painted — so they ride the same path the rose already uses for
# raw cells. `(kind, how many the engine loads)`.
FOREST = [("tree", 20), ("bush", 10), ("rock", 5)]
FOREST_KINDS = [kind for kind, _ in FOREST]


def is_forest(species):
    """A forest prop rather than a flower — different naming, no palette."""
    return species in FOREST_KINDS


def default_label(species):
    """The label a seeded drawing starts with (#v2.6.0): 'flower' for every
    shipped species, the kind itself for a forest prop, 'bugs' for a critter,
    nothing otherwise."""
    if species in FOREST_KINDS:
        return species
    if species in SPECIES or species in PATCH_FLOWERS:
        return "flower"
    if species == BUG:
        return "bugs"
    return ""


# Every kind the kit seeds, with the (species, model) pairs each one means.
# `Library.seed_missing_kinds` walks this so a kind added in a later version
# (the bugs, #v2.7.0) lands in a library that was seeded before it existed.
def seed_kinds():
    kinds = {"flower": [(s, v) for s in SPECIES for v in (0, 1)]
             + [(s, v) for s, n in PATCH_FLOWERS.items() for v in range(n)
                if patch_sprite(s, v) is not None]}
    for kind, n in FOREST:
        kinds[kind] = [(kind, i) for i in range(n)]
    kinds["bugs"] = [(BUG, i) for i in range(len(BUG_IDS))]
    return kinds


def seeded_count():
    """How many drawings `import_all` / a fresh library contains."""
    return sum(len(pairs) for pairs in seed_kinds().values())


def import_seed(species, model):
    """One shipped drawing of any kind."""
    if species == BUG:
        return import_bug(model)
    if is_forest(species):
        return import_forest_prop(species, model)
    if species in PATCH_FLOWERS:
        return import_patch_flower(species, model)
    return import_flower(species, model)


def patch_sprite(species, model):
    """Where the game keeps one Drawing Patch sprite, or None when it cannot
    be read here - no game checkout and no bundled copy, or no Pillow to read
    a PNG with. None keeps it out of the seeding instead of failing a start."""
    name = (f"flower_{species}.png" if PATCH_FLOWERS[species] == 1
            else f"flower_{species}_{model}.png")
    for folder in (OBJECTS_DIR,
                   Path(getattr(sys, "_MEIPASS", "")) / "objects" if getattr(sys, "frozen", False)
                   else None):
        if folder is not None and (folder / name).is_file():
            try:
                import PIL  # noqa: F401  - import_png reads it with Pillow
            except ImportError:
                return None
            return folder / name
    return None


def import_patch_flower(species, model):
    """One Drawing Patch model as an editable drawing: her x16 PNG brought
    back to its 16x16 cells - losslessly, the sprites being hard-edged 16 px
    blocks - named, labelled a flower, and signed by its artist."""
    drawing, _notes = import_png(patch_sprite(species, model))
    drawing.name = display_name(species, model)
    drawing.species, drawing.model = species, model
    drawing.label = default_label(species)
    drawing.artist = PATCH_ARTIST
    return drawing


def import_bug(index):
    g = gen_objects()
    maker = g.CRITTERS[BUG_IDS[index]]
    grid = maker()
    cells = [[px if px[3] else None for px in row] for row in grid]
    return Drawing(name=display_name(BUG, index), species=BUG, model=index, cells=cells,
                   palette=_forest_palette(), label=default_label(BUG))


def _palette_for(species):
    g = gen_objects()
    if species == "gul":
        # The rose predates _FLOWER_PALS and keeps its tones in _ROSE_PAL as
        # RGBA. Rebuild the hex form so the editor can show real swatches.
        def hexof(letter):
            r, gg, b, _ = g._ROSE_PAL[letter]
            return f"{r:02X}{gg:02X}{b:02X}"
        # _ROSE_PAL has no centre — a rose has no eye to colour. F2C94C is the
        # centre gold the other species share, here only so the swatch shows
        # something real. It is not engine data for the rose; don't chase it.
        return Palette(d=hexof("d"), m=hexof("m"), l=hexof("l"),
                       centre="F2C94C", rim=g._ROSE_RED_OL,
                       plant_rim=g._ROSE_GRN_OL)
    d, m, l, centre, rim = g._FLOWER_PALS[species]
    return Palette(d=d, m=m, l=l, centre=centre, rim=rim,
                   plant_rim=g._PLANT_OL.get(species, g._ROSE_GRN_OL))


def import_flower(species, model):
    """One shipped model as an editable drawing."""
    g = gen_objects()
    palette = _palette_for(species)
    name = display_name(species, model)
    if species == "gul":
        grid = g.rose_variant(model)  # already outlined and composited
        cells = [[px if px[3] else None for px in row] for row in grid]
        return Drawing(name=name, species=species, model=model, cells=cells,
                       palette=palette, label=default_label(species))
    rows = g._FLOWER_BLOOMS[species][model]
    cells = []
    for line in rows:
        row = []
        for c in range(16):
            ch = line[c] if c < len(line) else "."
            row.append(ch if ch != "." else None)
        cells.append(row)
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette, label=default_label(species))


def import_forest_prop(kind, index):
    """One shipped forest prop as an editable drawing (#v34.8).

    Raw pixels, like the rose: the generator composes these directly rather
    than from letters, and the engine adds no rim, so what is painted here is
    exactly what the garden draws. Trees are 32/48/64 cells square depending on
    how many tiles they occupy; bushes and rocks are 16.
    """
    g = gen_objects()
    maker = {"tree": g._tree_variant, "bush": g._bush_variant, "rock": g._rock_variant}[kind]
    grid = maker(index + 1)  # the generators are 1-based
    cells = [[px if px[3] else None for px in row] for row in grid]
    return Drawing(name=display_name(kind, index), species=kind, model=index, cells=cells,
                   palette=_forest_palette(), label=default_label(kind))


def forest_canvas(kind, index):
    """The cell size a forest prop must be, read from the generator rather than
    hardcoded — a tree's canvas IS its size in the garden (16px per tile)."""
    g = gen_objects()
    if kind != "tree":
        return 16
    return g.TREE_TILES[index % len(g.TREE_TILES)] * g.TREE_PX_PER_TILE


def _forest_palette():
    """Forest props carry no letter palette — the swatches would be a lie. This
    is a neutral stand-in so the editor has something to show; painting uses
    picked colours, which is what these are made of."""
    return Palette(d="23602C", m="327A3B", l="4E9B4A", centre="4A3421", rim="17401F",
                   plant_rim="17401F")


def import_all():
    flowers = [import_flower(s, v) for s in SPECIES for v in (0, 1)]
    patch = [import_patch_flower(s, v) for s, n in PATCH_FLOWERS.items() for v in range(n)
             if patch_sprite(s, v) is not None]
    forest = [import_forest_prop(k, i) for k, n in FOREST for i in range(n)]
    bugs = [import_bug(i) for i in range(len(BUG_IDS))]
    return flowers + patch + forest + bugs


# The generator's empty pixel (`gen_objects.blank`): what a rendered grid holds
# wherever nothing is drawn.
CLEAR = (0, 0, 0, 0)


def has_letters(drawing):
    """Does any cell hold a palette letter? Asked of the DISTINCT cell values -
    the union of the rows is built in C - so a 512-wide drawing answers in
    milliseconds rather than a Python loop over a quarter of a million cells."""
    return any(isinstance(v, str) for v in set().union(*drawing.cells))


def render(drawing):
    """The drawing as the garden will draw it: rims added, layers composited.

    This is `flower_variant()`'s body with the grid coming from the editor
    instead of `_FLOWER_BLOOMS`, so the preview cannot disagree with the export.

    A drawing with no palette letter in it - every forest prop, every import,
    everything painted in real colours - takes a shortcut (#v2.8.0). Rims only
    ever grow around LETTER cells, so for such a drawing the generator's two
    letter layers are empty grids that outline into nothing, and the
    composite is the raw layer as it stands: each painted cell as it is, each
    empty one fully transparent. That is computed here directly, in one pass
    instead of five over the whole grid - the difference between a 512-wide
    drawing repainting in a blink and in seconds, once the 64-cell cap went.
    The byte-for-byte export tests of the shipped forest run through it.
    """
    if not has_letters(drawing):
        return [[cell if cell is not None and cell[3] != 0 else CLEAR for cell in row]
                for row in drawing.cells]
    g = gen_objects()
    w, h = drawing.width, drawing.height
    colors = drawing.palette.colors()
    bloom = g.blank(w, h)
    plant = g.blank(w, h)
    raw = g.blank(w, h)
    for r in range(h):
        for c in range(w):
            cell = drawing.cells[r][c]
            if cell is None:
                continue
            if isinstance(cell, tuple):
                raw[r][c] = cell
            elif cell in BLOOM_LETTERS:
                bloom[r][c] = colors[cell]
            elif cell in PLANT_LETTERS:
                plant[r][c] = colors[cell]
    bloom = g.outline(bloom, drawing.palette.rim)
    plant = g.outline(plant, drawing.palette.plant_rim)
    return g._rose_compose([plant, bloom, raw])


class ExportRefused(Exception):
    """Raised instead of writing a file the engine could not use."""


def _scaled(drawing, scale):
    if scale < 1:
        raise ExportRefused(f"scale must be at least 1, got {scale}")
    return gen_objects().upscale(render(drawing), scale)


def rgb_of(hexcol):
    """'#a6e3a1' / 'A6E3A1' -> (166, 227, 161). One parser, so the exporters
    and the background dialog can never disagree about a colour."""
    h = str(hexcol).lstrip("#")
    if len(h) != 6:
        raise ExportRefused(f"not a six-digit hex colour: {hexcol!r}")
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        raise ExportRefused(f"not a six-digit hex colour: {hexcol!r}") from None


def flatten_onto(big, hexcol):
    """`big` (an RGBA grid) composited over an opaque `hexcol` (#v2.8.0).

    Straight source-over, so a half-transparent pixel blends rather than
    snapping to either side — which is what makes a soft edge still look soft
    on a white export. Every pixel comes out opaque; nothing in the grid is
    see-through afterwards, which is the whole point of choosing a
    background."""
    br, bg_, bb = rgb_of(hexcol)
    out = []
    for row in big:
        new_row = []
        for px in row:
            r, g, b, a = px if px else (0, 0, 0, 0)
            if a >= 255:
                new_row.append((r, g, b, 255))
            elif a <= 0:
                new_row.append((br, bg_, bb, 255))
            else:
                f = a / 255.0
                new_row.append((round(r * f + br * (1 - f)),
                                round(g * f + bg_ * (1 - f)),
                                round(b * f + bb * (1 - f)), 255))
        out.append(new_row)
    return out


def as_rgb(value, default=(255, 255, 255)):
    """An RGB triple from a hex string, an (r, g, b) tuple, or None.

    JPEG's background arrived as a tuple long before the artist could choose
    one, and the dialog speaks hex; rather than make one of them convert at
    every call site, both are accepted here."""
    if value is None:
        return default
    if isinstance(value, (tuple, list)):
        if len(value) < 3:
            raise ExportRefused(f"not an r,g,b colour: {value!r}")
        return tuple(int(n) for n in value[:3])
    return rgb_of(value)


def composed(drawing, scale=16, grid=None, background=None, mark=None):
    """The exact RGBA grid an image export writes, at `scale` px per cell.

    The one place the decisions are made in the right order: upscale,
    flatten onto the background, draw the grid lines ON TOP so they keep
    the colour they were asked for, and last of all the artist's signature,
    over everything (`mark`, a `provenance.Mark`; #v2.8.0). `export_png` is
    this plus a write, and the background dialog previews this at a smaller
    scale (#v2.8.0) - so what the artist is shown cannot drift from what
    lands on disk."""
    big = _scaled(drawing, scale)
    if background is not None:
        big = flatten_onto(big, background)
    if grid is not None:
        big = with_grid_lines(big, scale, grid)
    if mark is not None:
        rects = provenance.stamp(len(big[0]), len(big), mark)
        mark.signed = bool(rects)
        big = provenance.apply(big, rects)
    return big


def export_png(drawing, path, scale=16, grid=None, background=None, mark=None):
    """An RGBA PNG at `scale` px per cell. `grid` (a hex colour) draws a
    one-pixel line along every cell boundary, the outer edge included — the
    "export with grid" the artists asked for (#v2.6.0), for sharing a
    work-in-progress where the cells have to be countable.

    `background` is None for the transparent PNG this has always written, or
    a hex colour the empty cells are flattened onto (#v2.8.0) — for the
    artist who wants a white sheet rather than a checkerboard when the file
    lands in a chat window. Flattened BEFORE the grid lines go on, so the
    lines stay the colour they were asked for.

    `mark` (#v2.8.0) signs the picture if it asks to, and writes what made
    it - and, if the artist keeps their name in the file, the title, the
    artist and the copyright line - into its text chunks and XMP."""
    gen_objects().write_png(str(path), composed(drawing, scale, grid, background, mark))
    if mark is not None:
        written = Path(path)
        written.write_bytes(provenance.png_with_metadata(written.read_bytes(), mark))
    return Path(path)


def with_grid_lines(big, scale, hexcol):
    """`big` (an upscaled RGBA grid) with `hexcol` lines on the cell
    boundaries. Lines sit on the first pixel row/column of each cell and on
    the very last pixel of the image, so the outer border is closed on all
    four sides — the on-canvas grid used to lose its right and bottom edge
    for exactly this off-by-one (#v2.6.0)."""
    h = hexcol.lstrip("#")
    line = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    height, width = len(big), len(big[0])
    out = [list(row) for row in big]
    xs = set(range(0, width, scale)) | {width - 1}
    ys = set(range(0, height, scale)) | {height - 1}
    for y in range(height):
        row = out[y]
        if y in ys:
            out[y] = [line] * width
            continue
        for x in xs:
            row[x] = line
    return out


def export_sprite(drawing, path, scale=16):
    """The engine-scale sprite of ANY drawing, at a path the artist chose
    (#v2.6.0). `export_engine_sprite` below stays the strict developer path
    — engine names, engine sizes, refusals — this one is the artist's: x16,
    RGBA, whatever size the drawing is, whatever the file is called. The
    developer resizes or renames if the garden needs it."""
    if scale < 1:
        raise ExportRefused(f"scale must be at least 1, got {scale}")
    gen_objects().write_png(str(path), _scaled(drawing, scale))
    return Path(path)


def suggested_sprite_name(drawing, ext="png"):
    """A default filename for `export_sprite`: the engine's own name when the
    drawing is a shipped species/prop/bug, else a slug of the artist's name."""
    if drawing.species and (is_forest(drawing.species) or drawing.species in SPECIES
                            or drawing.species in PATCH_FLOWERS or drawing.species == BUG):
        return engine_sprite_names(drawing)[0].rsplit(".", 1)[0] + f".{ext}"
    import re
    slug = re.sub(r"[^a-z0-9_-]+", "_", (drawing.name or "sprite").lower()).strip("_")
    return f"{slug or 'sprite'}.{ext}"


def export_svg(drawing, path, cell=16, grid=None, background=None, mark=None):
    """The drawing as SVG: one `<rect>` per painted cell, `cell` units each,
    with `shape-rendering="crispEdges"` (#v2.7.0, item 4). Vector, so it
    stays sharp at any zoom in Illustrator, a browser, a chat preview.
    `grid` (hex) adds one-unit lines on every cell boundary, border closed.

    `background` is None for the transparent SVG (the default, unchanged) or
    a hex colour laid down as one full-size rect underneath everything
    (#v2.8.0). A rect rather than flattened pixels: the art stays editable
    and a half-transparent cell still blends against it in any renderer.

    `mark` (#v2.8.0): the title, the artist and the copyright line as
    `<title>`, `<desc>` and Dublin Core metadata, and the signature, if one is
    asked for, as a last group of rects over everything else."""
    rendered = render(drawing)
    h, w = len(rendered), len(rendered[0])
    W, H = w * cell, h * cell
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" shape-rendering="crispEdges">']
    if mark is not None:
        out.append(provenance.svg_metadata(mark))
    if background is not None:
        br, bg_, bb = rgb_of(background)
        out.append(f'<rect x="0" y="0" width="{W}" height="{H}" '
                   f'fill="#{br:02x}{bg_:02x}{bb:02x}"/>')
    for r, row in enumerate(rendered):
        c = 0
        while c < w:
            px = row[c]
            if not px or px[3] == 0:
                c += 1
                continue
            # run-length: neighbouring cells of one colour become one rect
            end = c
            while end + 1 < w and row[end + 1] == px:
                end += 1
            fill = f"#{px[0]:02x}{px[1]:02x}{px[2]:02x}"
            opacity = "" if px[3] == 255 else f' fill-opacity="{px[3] / 255:.3f}"'
            out.append(f'<rect x="{c * cell}" y="{r * cell}" width="{(end - c + 1) * cell}" '
                       f'height="{cell}" fill="{fill}"{opacity}/>')
            c = end + 1
    if grid is not None:
        g = "#" + grid.lstrip("#")
        lines = []
        for x in range(0, W + 1, cell):
            xx = min(x, W - 1)
            lines.append(f'<rect x="{xx}" y="0" width="1" height="{H}"/>')
        for y in range(0, H + 1, cell):
            yy = min(y, H - 1)
            lines.append(f'<rect x="0" y="{yy}" width="{W}" height="1"/>')
        out.append(f'<g fill="{g}">' + "".join(lines) + "</g>")
    if mark is not None:
        rects = provenance.stamp(W, H, mark)
        mark.signed = bool(rects)
        if rects:
            out.append(provenance.svg_signature(rects))
    out.append("</svg>")
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return Path(path)


def export_jpg(drawing, path, scale=16, background=(255, 255, 255), grid=None, mark=None):
    """JPEG has no alpha, so transparency is flattened onto `background`.

    The caller is told which colour that was rather than the app quietly
    picking one and the artist finding a white halo later. `background` may be
    a hex string or an (r, g, b) tuple, and None means white - there is no
    transparent JPEG to fall back on (#v2.8.0). `grid` (hex) draws the cell
    lines, so "export with grid" is offered for this format too.

    `mark` (#v2.8.0): the signature, if asked for, and the name in EXIF
    (Artist, Copyright, Windows' XPAuthor), XMP and a JPEG comment.
    """
    from PIL import Image
    rgb = as_rgb(background)
    # Composed against the SAME background the flatten below uses, so a
    # half-transparent pixel blends once, not twice.
    cells = composed(drawing, scale, grid, "%02X%02X%02X" % rgb, mark)
    h, w = len(cells), len(cells[0])
    rgba = Image.new("RGBA", (w, h))
    rgba.putdata([px for row in cells for px in row])
    flat = Image.new("RGB", (w, h), rgb)
    flat.paste(rgba, mask=rgba.split()[3])
    named = mark is not None
    buf = io.BytesIO()
    extra = {"exif": provenance.exif_bytes(mark)} if named else {}
    flat.save(buf, "JPEG", quality=95, subsampling=0, **extra)
    data = buf.getvalue()
    if named:
        data = provenance.jpeg_with_metadata(data, mark)
    Path(path).write_bytes(data)
    return Path(path)


def engine_sprite_names(drawing):
    """Basenames export_engine_sprite will write: the model's own sprite, plus
    the bare thumbnail the shop uses when it's model 0. One definition so the
    confirmation dialog and the writer can never name different files."""
    if drawing.species == BUG:
        return [f"{BUG_IDS[drawing.model % len(BUG_IDS)]}.png"]
    if is_forest(drawing.species):
        # tree_07.png — the engine loads forest props by their own filename,
        # with no `flower_` prefix and no bare thumbnail (#v17's "only shadows"
        # bug was exactly that prefix being applied to a tree).
        return [f"{drawing.species}_{drawing.model:02d}.png"]
    if PATCH_FLOWERS.get(drawing.species) == 1:
        return [f"flower_{drawing.species}.png"]  # a single form: no model number
    names = [f"flower_{drawing.species}_{drawing.model}.png"]
    if drawing.model == 0:
        names.append(f"flower_{drawing.species}.png")
    return names


def export_engine_sprite(drawing, out_dir):
    """Write the sprite(s) the garden loads: ×16, RGBA, engine naming."""
    if not drawing.species:
        raise ExportRefused("give the drawing a species before exporting it")
    if drawing.species == BUG:
        if (drawing.width, drawing.height) != (8, 8):
            raise ExportRefused(
                f"a bug is an 8x8 frame, this drawing is {drawing.width}x{drawing.height}")
    elif is_forest(drawing.species):
        # A tree's canvas size IS its size in the garden: the engine reads the
        # tile count from its own table and the sprite is generated at 16px per
        # tile, so an off-size grid would render at the wrong pixel density.
        want = forest_canvas(drawing.species, drawing.model)
        if drawing.width != want or drawing.height != want:
            raise ExportRefused(
                f"{drawing.species}_{drawing.model:02d} must be {want}x{want} cells, "
                f"this drawing is {drawing.width}x{drawing.height}")
    elif drawing.width != 16:
        raise ExportRefused(
            f"engine sprites are 16 cells wide, this drawing is {drawing.width}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    big = _scaled(drawing, 16)
    written = [out_dir / name for name in engine_sprite_names(drawing)]
    for path in written:
        gen_objects().write_png(str(path), big)
    return written


def export_palette_literal(drawing):
    """The palette as a `_FLOWER_PALS` line, ready to paste.

    The grid literal alone is half a flower — the engine defines one as rows
    PLUS the five tones. This is the other half of the hand-back."""
    if not drawing.species:
        raise ExportRefused("give the drawing a species before exporting it")
    p = drawing.palette
    return (f"    '{drawing.species}': "
            f"('{p.d}', '{p.m}', '{p.l}', '{p.centre}', '{p.rim}'),")


def export_grid_literal(drawing):
    """The rows as Python source, ready to paste into _FLOWER_BLOOMS."""
    if not drawing.is_letters():
        raise ExportRefused(
            "this drawing has raw colours in it, so it has no letter grid — "
            "export it as a PNG instead")
    lines = [f"[  # {drawing.species} model {drawing.model}"]
    for row in drawing.cells:
        lines.append('    "' + "".join(c if c else "." for c in row) + '",')
    lines.append("],")
    return "\n".join(lines)


# ---- bringing outside art in (#v34.10) --------------------------------------

class ImportRefused(Exception):
    """Raised instead of importing a file that would come out wrong."""


#: Alpha at or above this counts as an opaque pixel; below it becomes empty.
#: The engine composites hard-edged sprites — a half-transparent pixel has no
#: meaning there — so anti-aliased edges have to be decided one way or another
#: at import rather than shipped as fringe.
ALPHA_CUTOFF = 128


def import_png(path, cells=None, alpha_cutoff=ALPHA_CUTOFF):
    """An outside PNG as an editable drawing, plus a note on what was changed.

    Lets an artist work in Procreate, Aseprite, Photoshop — anything — and
    bring the result in without it quietly going wrong in the engine. Three
    things get fixed here, because each is invisible until it ships:

    * **Colour profile.** Procreate paints in Display P3 by default. The same
      "green" carries different RGB numbers in a P3 file than in an sRGB one,
      so the art drifts against every colour already in the game. Any embedded
      profile is converted to sRGB.
    * **Anti-aliasing.** Normal brushes feather their edges. The engine draws
      hard pixels, so a feathered edge becomes a fringe of half-ghosts. Alpha
      is snapped to fully on or fully off at [alpha_cutoff].
    * **Scale.** Art exported at 16x (or any whole multiple) is brought back
      down by nearest-neighbour, which is lossless for pixel art — resampling
      it smoothly would blur it into mush.

    [cells] forces the grid size; by default the PNG's own size is used, or the
    largest whole-number downscale of it that still divides evenly.

    Returns `(drawing, notes)` — `notes` is a list of plain sentences naming
    every change, so the artist is told rather than surprised.
    """
    try:
        from PIL import Image, ImageCms
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportRefused(
            "importing a PNG needs Pillow (pip install Pillow)") from exc

    path = Path(path)
    notes = []
    img = Image.open(path)

    # 1) colour profile -> sRGB
    icc = img.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            name = ImageCms.getProfileDescription(src).strip()
            img = ImageCms.profileToProfile(
                img.convert("RGBA"), src, ImageCms.createProfile("sRGB"),
                outputMode="RGBA")
            if "srgb" not in name.lower():
                notes.append(f"converted {name} to sRGB")
        except Exception:  # a broken profile is not worth failing the import
            notes.append("left an unreadable colour profile alone")
    img = img.convert("RGBA")

    w, h = img.size
    if w == 0 or h == 0:
        raise ImportRefused("that image is empty")

    # 2) scale down to the grid
    target = cells or _guess_cells(w, h)
    if target != (w, h):
        if w % target[0] or h % target[1]:
            raise ImportRefused(
                f"{w}x{h} does not divide evenly into {target[0]}x{target[1]} cells — "
                f"resize it in your drawing app first, or pick a size that fits")
        img = img.resize(target, Image.NEAREST)
        notes.append(f"scaled {w}x{h} down to {target[0]}x{target[1]} (nearest, lossless)")

    # 3) flatten anti-aliasing
    cols, rows = target
    px = img.load()
    cells_out = []
    softened = 0
    for r in range(rows):
        row = []
        for c in range(cols):
            red, green, blue, alpha = px[c, r]
            if alpha and alpha < 255:
                softened += 1
            row.append((red, green, blue, 255) if alpha >= alpha_cutoff else None)
        cells_out.append(row)
    if softened:
        notes.append(f"squared off {softened} part-transparent pixel(s) from anti-aliasing")

    if not any(cell for row in cells_out for cell in row):
        raise ImportRefused(
            "everything in that image was too faint to keep — it may be anti-aliased "
            "to near-nothing, or saved with no opaque pixels")

    return Drawing(name=path.stem, species="", model=0, cells=cells_out,
                   palette=_forest_palette(), label="import"), notes


#: Grid sizes the engine actually uses: flowers/bushes/rocks are 16, trees are
#: 2/3/4 tiles at 16px each.
KNOWN_CELLS = (16, 32, 48, 64)


def _guess_cells(w, h):
    """The grid an exported PNG most likely came from.

    ONLY x16 is treated as an export scale, because that is the only one the
    engine uses: a 1024x1024 file is a 64-cell tree. Guessing at x2/x4/x8 as
    well looked clever and was destructive — a 32x32 drawing (a real 2-tile
    tree size) got "recognised" as a 16-cell drawing exported at x2 and thrown
    away half its resolution. Anything else is taken at face value.
    """
    if w % 16 == 0 and h % 16 == 0:
        cw, ch = w // 16, h // 16
        if cw in KNOWN_CELLS and ch in KNOWN_CELLS:
            return (cw, ch)
    return (w, h)
