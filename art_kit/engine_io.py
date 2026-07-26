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

from art_kit.model import Drawing, Palette, BLOOM_LETTERS, PLANT_LETTERS

# Both checkouts live side by side under one "Pixel Pomo" folder, so the game
# is found RELATIVE to this file (art_kit/ -> ArtKit/ -> Pixel Pomo/ -> App/).
# That survives the whole folder being moved or renamed, which the old absolute
# default did not. PIXEL_POMO_TOOLS still wins, for a layout that isn't this one.
APP_DIR = Path(__file__).resolve().parents[2] / "App"
GEN_OBJECTS_DIR = Path(
    os.environ.get("PIXEL_POMO_TOOLS", str(APP_DIR / "flutter" / "tools"))
)


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

# The forest that surrounds the garden (#v34.8). Not flowers: these are raw
# pixel art with no letter palette and no rim pass — the engine draws them
# exactly as painted — so they ride the same path the rose already uses for
# raw cells. `(kind, how many the engine loads)`.
FOREST = [("tree", 20), ("bush", 10), ("rock", 5)]
FOREST_KINDS = [kind for kind, _ in FOREST]


def is_forest(species):
    """A forest prop rather than a flower — different naming, no palette."""
    return species in FOREST_KINDS


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
    name = f"{species}_{model}"
    if species == "gul":
        grid = g.rose_variant(model)  # already outlined and composited
        cells = [[px if px[3] else None for px in row] for row in grid]
        return Drawing(name=name, species=species, model=model, cells=cells,
                       palette=palette)
    rows = g._FLOWER_BLOOMS[species][model]
    cells = []
    for line in rows:
        row = []
        for c in range(16):
            ch = line[c] if c < len(line) else "."
            row.append(ch if ch != "." else None)
        cells.append(row)
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette)


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
    return Drawing(name=f"{kind}_{index:02d}", species=kind, model=index, cells=cells,
                   palette=_forest_palette())


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
    forest = [import_forest_prop(k, i) for k, n in FOREST for i in range(n)]
    return flowers + forest


def render(drawing):
    """The drawing as the garden will draw it: rims added, layers composited.

    This is `flower_variant()`'s body with the grid coming from the editor
    instead of `_FLOWER_BLOOMS`, so the preview cannot disagree with the export.
    """
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


def export_png(drawing, path, scale=16):
    gen_objects().write_png(str(path), _scaled(drawing, scale))
    return Path(path)


def export_jpg(drawing, path, scale=16, background=(255, 255, 255)):
    """JPEG has no alpha, so transparency is flattened onto `background`.

    The caller is told which colour that was rather than the app quietly
    picking one and the artist finding a white halo later.
    """
    from PIL import Image
    grid = _scaled(drawing, scale)
    h, w = len(grid), len(grid[0])
    rgba = Image.new("RGBA", (w, h))
    rgba.putdata([px for row in grid for px in row])
    flat = Image.new("RGB", (w, h), background)
    flat.paste(rgba, mask=rgba.split()[3])
    flat.save(str(path), "JPEG", quality=95, subsampling=0)
    return Path(path)


def engine_sprite_names(drawing):
    """Basenames export_engine_sprite will write: the model's own sprite, plus
    the bare thumbnail the shop uses when it's model 0. One definition so the
    confirmation dialog and the writer can never name different files."""
    if is_forest(drawing.species):
        # tree_07.png — the engine loads forest props by their own filename,
        # with no `flower_` prefix and no bare thumbnail (#v17's "only shadows"
        # bug was exactly that prefix being applied to a tree).
        return [f"{drawing.species}_{drawing.model:02d}.png"]
    names = [f"flower_{drawing.species}_{drawing.model}.png"]
    if drawing.model == 0:
        names.append(f"flower_{drawing.species}.png")
    return names


def export_engine_sprite(drawing, out_dir):
    """Write the sprite(s) the garden loads: ×16, RGBA, engine naming."""
    if not drawing.species:
        raise ExportRefused("give the drawing a species before exporting it")
    if is_forest(drawing.species):
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

    return Drawing(name=path.stem, species=None, model=0, cells=cells_out,
                   palette=_forest_palette()), notes


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
