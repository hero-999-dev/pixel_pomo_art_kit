"""The bridge to Pixel Pomo's sprite generator.

Everything the art kit knows about the engine's file format comes from
`gen_objects.py` itself — imported, never copied. A reimplementation would be a
second source of truth that drifts the first time either side is touched, and
the whole point of this app is that its output IS the shipped sprite.
"""
import functools
import importlib.util
import os
import sys
from pathlib import Path

from art_kit.model import Drawing, Palette, BLOOM_LETTERS, PLANT_LETTERS

# Overridable so a checkout somewhere else can still run the app.
GEN_OBJECTS_DIR = Path(
    os.environ.get("PIXEL_POMO_TOOLS", r"C:\Users\claude\pixel_pomo\flutter\tools")
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
            f"environment variable at pixel_pomo\\flutter\\tools."
        )
    spec = importlib.util.spec_from_file_location("gen_objects", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Catalogue order — the rose first, the way the shop lists them.
SPECIES = ["gul", "papatya", "lale", "kaktus", "kaktusf", "kaktusd",
           "kasimpati", "menekse", "nilufer", "orkide", "begonya", "kamelya"]


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
                       palette=palette, kind="pixels")
    rows = g._FLOWER_BLOOMS[species][model]
    cells = []
    for line in rows:
        row = []
        for c in range(16):
            ch = line[c] if c < len(line) else "."
            row.append(ch if ch != "." else None)
        cells.append(row)
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette, kind="letters")


def import_all():
    return [import_flower(s, v) for s in SPECIES for v in (0, 1)]


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


def export_engine_sprite(drawing, out_dir):
    """Write the sprite(s) the garden loads: ×16, RGBA, engine naming."""
    if drawing.width != 16:
        raise ExportRefused(
            f"engine sprites are 16 cells wide, this drawing is {drawing.width}")
    if not drawing.species:
        raise ExportRefused("give the drawing a species before exporting it")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    big = _scaled(drawing, 16)
    written = [out_dir / f"flower_{drawing.species}_{drawing.model}.png"]
    if drawing.model == 0:
        # model 0 doubles as the shop thumbnail, exactly as gen_objects does it
        written.append(out_dir / f"flower_{drawing.species}.png")
    for path in written:
        gen_objects().write_png(str(path), big)
    return written


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
