import tempfile
import unittest
from pathlib import Path
from unittest import mock


from art_kit import engine_io
from art_kit.model import Drawing
import pathlib

# Everything the app seeds: two models per flower, plus the forest props the
# engine loads (#v34.8). Derived, so adding a species or a tree moves it
# automatically instead of leaving a stale literal behind.
SEEDED = engine_io.seeded_count()


# The game checkout is found RELATIVE to this file (both live under one
# "Pixel Pomo" folder), so moving or renaming that folder can't break it.
_APP = pathlib.Path(__file__).resolve().parents[2] / "App"


class ImportBridgeTest(unittest.TestCase):
    def test_gen_objects_module_loads_with_the_pieces_we_rely_on(self):
        g = engine_io.gen_objects()
        for name in ("blank", "hexrgb", "upscale", "write_png", "outline",
                     "_rose_compose", "flower_variant", "rose_variant",
                     "_FLOWER_BLOOMS", "_FLOWER_PALS", "_flower_pal"):
            self.assertTrue(hasattr(g, name), f"gen_objects has no {name}")

    def test_the_module_is_cached_not_reimported(self):
        self.assertIs(engine_io.gen_objects(), engine_io.gen_objects())

    def test_filenotfound_when_gen_objects_missing(self):
        # Save original state
        original_dir = engine_io.GEN_OBJECTS_DIR
        try:
            # Create a temporary empty directory
            with tempfile.TemporaryDirectory() as tmpdir:
                # Clear cache and point to nonexistent gen_objects.py
                engine_io.gen_objects.cache_clear()
                engine_io.GEN_OBJECTS_DIR = Path(tmpdir)

                # Assert that FileNotFoundError is raised with path in message
                with self.assertRaises(FileNotFoundError) as ctx:
                    engine_io.gen_objects()
                self.assertIn(str(engine_io.GEN_OBJECTS_DIR), str(ctx.exception))
        finally:
            # Restore original state and cache
            engine_io.GEN_OBJECTS_DIR = original_dir
            engine_io.gen_objects.cache_clear()


class ImportFlowersTest(unittest.TestCase):
    def test_twelve_species_two_models_each(self):
        drawings = engine_io.import_all()
        self.assertEqual(len(drawings), SEEDED)
        self.assertEqual(len(engine_io.SPECIES), 12)
        self.assertIn("gul", engine_io.SPECIES)
        self.assertIn("lale", engine_io.SPECIES)

    def test_a_letter_flower_keeps_its_letters_and_size(self):
        d = engine_io.import_flower("lale", 0)
        self.assertIsInstance(d, Drawing)
        self.assertEqual(d.kind, "letters")
        self.assertEqual(d.width, 16)
        self.assertTrue(d.is_letters())
        self.assertIn("m", {c for row in d.cells for c in row})

    def test_the_letters_match_the_engines_own_grid(self):
        g = engine_io.gen_objects()
        rows = g._FLOWER_BLOOMS["lale"][0]
        d = engine_io.import_flower("lale", 0)
        self.assertEqual(d.height, len(rows))
        for r, line in enumerate(rows):
            for c in range(16):
                expected = line[c] if c < len(line) and line[c] != "." else None
                self.assertEqual(d.get(c, r), expected, f"cell {c},{r}")

    def test_the_palette_comes_from_the_engine(self):
        g = engine_io.gen_objects()
        d, m, l, centre, rim = g._FLOWER_PALS["lale"]
        pal = engine_io.import_flower("lale", 0).palette
        self.assertEqual((pal.d, pal.m, pal.l, pal.centre, pal.rim), (d, m, l, centre, rim))

    def test_the_cactuses_use_their_own_green_plant_rim(self):
        g = engine_io.gen_objects()
        # _PLANT_OL["kaktusf"] and the _ROSE_GRN_OL fallback are the same string
        # today, so asserting the value proves nothing about which one was read.
        # Swap the engine's entry for the length of the test and the lookup has
        # to show itself.
        with mock.patch.dict(g._PLANT_OL, {"kaktusf": "ABCDEF"}):
            self.assertEqual(engine_io.import_flower("kaktusf", 0).palette.plant_rim, "ABCDEF")
        self.assertEqual(engine_io.import_flower("kaktusf", 0).palette.plant_rim,
                         g._PLANT_OL["kaktusf"])

    def test_the_roses_rgba_tones_become_hex_in_channel_order(self):
        pal = engine_io.import_flower("gul", 0).palette
        # Literals, not a re-run of hexof(): an r/b swap has to fail here.
        self.assertEqual((pal.d, pal.m, pal.l), ("8E1B2E", "CC2A3D", "F26571"))
        self.assertEqual(pal.rim, engine_io.gen_objects()._ROSE_RED_OL)

    def test_the_rose_imports_as_raw_pixels(self):
        d = engine_io.import_flower("gul", 0)
        self.assertEqual(d.kind, "pixels")
        self.assertFalse(d.is_letters())
        self.assertEqual(d.width, 16)
        opaque = [c for row in d.cells for c in row if c is not None]
        self.assertTrue(opaque, "the rose should not import blank")
        self.assertTrue(all(isinstance(c, tuple) and len(c) == 4 for c in opaque))


class RenderTest(unittest.TestCase):
    def test_a_letter_flower_renders_exactly_like_the_engine(self):
        g = engine_io.gen_objects()
        for species in ("lale", "papatya", "kasimpati", "kaktusf"):
            for model in (0, 1):
                with self.subTest(species=species, model=model):
                    mine = engine_io.render(engine_io.import_flower(species, model))
                    self.assertEqual(mine, g.flower_variant(species, model))

    def test_the_rose_renders_exactly_like_the_engine(self):
        g = engine_io.gen_objects()
        for model in (0, 1):
            mine = engine_io.render(engine_io.import_flower("gul", model))
            self.assertEqual(mine, g.rose_variant(model))

    def test_a_letter_grid_with_raw_colours_in_it_renders_both(self):
        # The colour picker drops raw RGBA onto a letter drawing; both paths
        # have to survive the same render.
        from art_kit.model import Palette
        pal = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C", rim="2E0810")
        d = Drawing.blank(16, 4, pal)
        d.paint(2, 1, "m")
        d.paint(8, 1, (10, 20, 30, 255))
        grid = engine_io.render(d)
        self.assertEqual(grid[1][2], pal.colors()["m"])
        self.assertEqual(grid[1][8], (10, 20, 30, 255))

    def test_an_empty_drawing_renders_fully_transparent(self):
        from art_kit.model import Drawing, Palette
        pal = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C", rim="2E0810")
        grid = engine_io.render(Drawing.blank(16, 4, pal))
        self.assertTrue(all(px == (0, 0, 0, 0) for row in grid for px in row))


def _pixels(path):
    """A PNG's decoded RGBA pixels.

    Compared instead of the raw file bytes (#v2.1.0). The claim these tests make
    is "what the kit writes IS the shipped sprite", and that is about pixels —
    but a PNG's bytes also carry zlib's output, which is not portable. The macOS
    runner's zlib compresses the same pixels differently from Windows', so a
    byte comparison failed on CI for two sprites whose images were identical.
    A test that fails on the operating system rather than on the artwork is
    testing the wrong thing.
    """
    from PIL import Image
    with Image.open(path) as im:
        return im.convert("RGBA").tobytes(), im.size


class ExportTest(unittest.TestCase):
    ASSETS = Path(str(_APP / "flutter" / "assets" / "objects"))

    def test_an_untouched_flower_exports_pixel_for_pixel_as_shipped(self):
        for species, model in (("lale", 0), ("papatya", 1), ("gul", 0)):
            with self.subTest(species=species, model=model):
                shipped = _pixels(self.ASSETS / f"flower_{species}_{model}.png")
                with tempfile.TemporaryDirectory() as tmp:
                    written = engine_io.export_engine_sprite(
                        engine_io.import_flower(species, model), Path(tmp))
                    mine = _pixels(Path(tmp) / f"flower_{species}_{model}.png")
                self.assertEqual(mine, shipped)
                self.assertTrue(written)

    def test_model_zero_also_writes_the_shop_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine_io.export_engine_sprite(engine_io.import_flower("lale", 0), Path(tmp))
            thumb = _pixels(Path(tmp) / "flower_lale.png")
            shipped = _pixels(self.ASSETS / "flower_lale.png")
        self.assertEqual(thumb, shipped)

    def test_model_one_does_not_overwrite_the_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine_io.export_engine_sprite(engine_io.import_flower("lale", 1), Path(tmp))
            self.assertFalse((Path(tmp) / "flower_lale.png").exists())

    def test_engine_export_refuses_a_grid_that_is_not_16_wide(self):
        from art_kit.model import Drawing
        d = engine_io.import_flower("lale", 0)
        narrow = Drawing.blank(12, 4, d.palette, species="lale")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(engine_io.ExportRefused):
                engine_io.export_engine_sprite(narrow, Path(tmp))

    def test_png_export_writes_a_readable_file_at_the_asked_scale(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.png"
            engine_io.export_png(d, out, scale=8)
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.size, (16 * 8, d.height * 8))
                self.assertEqual(im.mode, "RGBA")

    def test_jpg_export_flattens_onto_the_given_background(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.jpg"
            engine_io.export_jpg(d, out, scale=4, background=(255, 0, 0))
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.mode, "RGB")
                # JPEG is lossy, so the flat background comes back near, not at,
                # the colour asked for. Pinning the exact value would make a
                # Pillow upgrade look like a regression.
                for got, want in zip(im.getpixel((0, 0)), (255, 0, 0)):
                    self.assertAlmostEqual(got, want, delta=3)

    def test_png_export_keeps_empty_cells_transparent_by_default(self):
        """The default has to stay what every earlier version wrote: a sprite
        with a background baked in would be a silent regression for the game."""
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.png"
            engine_io.export_png(d, out, scale=2)
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.mode, "RGBA")
                self.assertEqual(im.getpixel((0, 0))[3], 0)

    def test_png_export_flattens_empty_cells_onto_the_chosen_background(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.png"
            engine_io.export_png(d, out, scale=2, background="FFFFFF")
            from PIL import Image
            with Image.open(out) as im:
                # PNG is lossless, so the corner is EXACTLY white and opaque,
                # and no pixel anywhere is left see-through.
                self.assertEqual(im.getpixel((0, 0)), (255, 255, 255, 255))
                px = im.load()
                self.assertTrue(all(px[x, y][3] == 255
                                    for y in range(im.height) for x in range(im.width)))

    def test_png_background_blends_a_half_transparent_pixel(self):
        """Source-over, not a threshold: a half-transparent red over white is
        pink. 128/255 is a hair over half, so white contributes 127."""
        big = [[(255, 0, 0, 128)]]
        self.assertEqual(engine_io.flatten_onto(big, "#FFFFFF"), [[(255, 127, 127, 255)]])

    def test_png_background_is_flattened_under_the_grid_lines(self):
        """The grid keeps the colour it was asked for; it is drawn last."""
        d = Drawing.blank(2, 2, engine_io.import_flower("lale", 0).palette, species="lale")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.png"
            engine_io.export_png(d, out, scale=4, grid="FF0000", background="FFFFFF")
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.getpixel((0, 0)), (255, 0, 0, 255))     # a grid line
                self.assertEqual(im.getpixel((2, 2)), (255, 255, 255, 255))  # inside a cell

    def test_png_background_refuses_something_that_is_not_a_colour(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(engine_io.ExportRefused):
                engine_io.export_png(d, Path(tmp) / "x.png", background="white")

    def test_svg_export_lays_the_background_down_first(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.svg"
            engine_io.export_svg(d, out, cell=4, background="#123456")
            text = out.read_text(encoding="utf-8")
            body = text.splitlines()
            self.assertIn('fill="#123456"', body[1])  # the rect right after <svg>
            engine_io.export_svg(d, out, cell=4)
            self.assertNotIn('fill="#123456"', out.read_text(encoding="utf-8"))

    def test_jpg_export_takes_a_hex_background_and_the_grid_lines(self):
        """#v2.8.0: JPG is offered with a grid and a chosen background too."""
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.jpg"
            engine_io.export_jpg(d, out, scale=4, background="0000FF", grid="FF0000")
            from PIL import Image
            with Image.open(out) as im:
                self.assertEqual(im.mode, "RGB")
                for got, want in zip(im.getpixel((0, 0)), (255, 0, 0)):
                    self.assertAlmostEqual(got, want, delta=4)   # a grid line
                for got, want in zip(im.getpixel((2, 2)), (0, 0, 255)):
                    self.assertAlmostEqual(got, want, delta=4)   # the background

    def test_jpg_still_defaults_to_white_when_no_background_is_given(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.jpg"
            engine_io.export_jpg(d, out, scale=4, background=None)
            from PIL import Image
            with Image.open(out) as im:
                for got in im.getpixel((0, 0)):
                    self.assertAlmostEqual(got, 255, delta=3)

    def test_composed_is_what_png_export_writes(self):
        """The preview calls `composed`; if the two ever diverge the artist is
        shown one thing and handed another."""
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.png"
            engine_io.export_png(d, out, scale=3, grid="FF0000", background="FFFFFF")
            from PIL import Image
            with Image.open(out) as im:
                px = im.load()
                cells = engine_io.composed(d, 3, "FF0000", "FFFFFF")
                self.assertEqual(im.size, (len(cells[0]), len(cells)))
                for y, row in enumerate(cells):
                    for x, want in enumerate(row):
                        self.assertEqual(px[x, y], want, f"at {x},{y}")

    def test_grid_literal_round_trips_through_the_engines_own_format(self):
        g = engine_io.gen_objects()
        text = engine_io.export_grid_literal(engine_io.import_flower("lale", 0))
        rows = [line.strip().strip(",").strip('"') for line in text.splitlines() if '"' in line]
        self.assertEqual(rows, list(g._FLOWER_BLOOMS["lale"][0]))

    def test_grid_literal_is_refused_for_a_raw_pixel_drawing(self):
        with self.assertRaises(engine_io.ExportRefused):
            engine_io.export_grid_literal(engine_io.import_flower("gul", 0))

    def test_palette_literal_is_the_engines_own_pals_line(self):
        g = engine_io.gen_objects()
        d, m, l, centre, rim = g._FLOWER_PALS["lale"]
        line = engine_io.export_palette_literal(engine_io.import_flower("lale", 0))
        self.assertEqual(line, f"    'lale': ('{d}', '{m}', '{l}', '{centre}', '{rim}'),")
        with self.assertRaises(engine_io.ExportRefused):
            engine_io.export_palette_literal(Drawing.blank(16, 4,
                engine_io.import_flower("lale", 0).palette))

    def test_the_confirm_names_are_exactly_the_files_export_writes(self):
        # engine_sprite_names feeds the overwrite-confirmation dialog; if it ever
        # named different files than export_engine_sprite writes, the dialog would
        # under-report what it clobbers. Lock them together.
        for model, count in ((0, 2), (1, 1)):
            with self.subTest(model=model):
                d = engine_io.import_flower("lale", model)
                names = engine_io.engine_sprite_names(d)
                self.assertEqual(len(names), count)
                with tempfile.TemporaryDirectory() as tmp:
                    written = engine_io.export_engine_sprite(d, Path(tmp))
                self.assertEqual(sorted(p.name for p in written), sorted(names))

    def test_engine_export_refuses_a_drawing_with_no_species(self):
        # A fresh drawing has species="" until the artist picks one.
        d = engine_io.import_flower("lale", 0)
        unnamed = Drawing.blank(16, 4, d.palette)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(engine_io.ExportRefused):
                engine_io.export_engine_sprite(unnamed, Path(tmp))

    def test_export_refuses_a_scale_below_one(self):
        d = engine_io.import_flower("lale", 0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(engine_io.ExportRefused):
                engine_io.export_png(d, Path(tmp) / "x.png", scale=0)
            self.assertFalse((Path(tmp) / "x.png").exists())


class ArtistExportsTest(unittest.TestCase):
    """#v2.6.0: the artist's sprite export takes any size and any name, and
    PNGs can carry a grid."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_export_sprite_writes_any_size_at_x16(self):
        d = Drawing.blank(32, 20, engine_io._forest_palette(), name="My Tree!")
        d.paint(0, 0, (1, 2, 3, 255))
        path = engine_io.export_sprite(d, Path(self.tmp.name) / "anything.png")
        from PIL import Image
        img = Image.open(path)
        self.assertEqual(img.size, (32 * 16, 20 * 16))
        self.assertEqual(img.getpixel((5, 5)), (1, 2, 3, 255))
        # the strict developer export still refuses what the engine cannot load
        with self.assertRaises(engine_io.ExportRefused):
            engine_io.export_engine_sprite(
                Drawing.blank(32, 20, engine_io._forest_palette(), species="lale"), self.tmp.name)

    def test_suggested_names(self):
        self.assertEqual(engine_io.suggested_sprite_name(engine_io.import_flower("lale", 1)),
                         "flower_lale_1.png")
        self.assertEqual(engine_io.suggested_sprite_name(engine_io.import_forest_prop("tree", 6)),
                         "tree_06.png")
        mine = Drawing.blank(8, 8, engine_io._forest_palette(), name="Sun Flower 2!")
        self.assertEqual(engine_io.suggested_sprite_name(mine), "sun_flower_2.png")
        self.assertEqual(engine_io.suggested_sprite_name(
            Drawing.blank(8, 8, engine_io._forest_palette(), name="!!!")), "sprite.png")

    def test_export_png_with_grid_draws_closed_lines_on_every_boundary(self):
        d = Drawing.blank(3, 2, engine_io._forest_palette())
        d.paint(1, 0, (200, 0, 0, 255))
        path = engine_io.export_png(d, Path(self.tmp.name) / "g.png", scale=8, grid="#10FF20")
        from PIL import Image
        img = Image.open(path)
        line = (0x10, 0xFF, 0x20, 255)
        self.assertEqual(img.size, (24, 16))
        for x in (0, 8, 16, 23):
            self.assertEqual(img.getpixel((x, 5)), line, f"vertical line at x={x}")
        for y in (0, 8, 15):
            self.assertEqual(img.getpixel((12, y)), line, f"horizontal line at y={y}")
        self.assertEqual(img.getpixel((12, 4)), (200, 0, 0, 255), "the cell itself keeps its colour")
        self.assertEqual(img.getpixel((4, 4)), (0, 0, 0, 0), "empty stays transparent")
        plain = engine_io.export_png(d, Path(self.tmp.name) / "p.png", scale=8)
        self.assertEqual(Image.open(plain).getpixel((0, 5)), (0, 0, 0, 0), "no grid unless asked")

    def test_default_labels(self):
        self.assertEqual(engine_io.default_label("lale"), "flower")
        self.assertEqual(engine_io.default_label("gul"), "flower")
        self.assertEqual(engine_io.default_label("tree"), "tree")
        self.assertEqual(engine_io.default_label("rock"), "rock")
        self.assertEqual(engine_io.default_label(""), "")
        self.assertEqual(engine_io.default_label("whatever"), "")
        self.assertEqual(engine_io.default_label("bug"), "bugs")
        self.assertTrue(all(d.label for d in engine_io.import_all()), "everything seeded is labelled")


class ForestPropsAreEditable(unittest.TestCase):
    """#v34.8 — the artist asked to draw the forest, not just the flowers."""

    def test_the_library_offers_every_prop_the_engine_loads(self):
        # Identified by species+model, not by the label. The label is what the
        # ARTIST reads and is English now (#v2.2.0); the engine's identity for a
        # prop is the pair that produces its filename, and that has not moved.
        got = {(d.species, d.model)
               for d in engine_io.import_all() if engine_io.is_forest(d.species)}
        expected = {(kind, i) for kind, n in engine_io.FOREST for i in range(n)}
        self.assertEqual(got, expected)

    def test_every_prop_and_flower_has_an_english_label(self):
        # The artists do not read Turkish, and the ids are Turkish because the
        # engine loads `flower_gul_0.png`. A species added to SPECIES or FOREST
        # without a DISPLAY_NAMES entry would silently fall back to its id and
        # put "kasimpati" back in front of them.
        for species in engine_io.SPECIES + engine_io.FOREST_KINDS:
            with self.subTest(species=species):
                self.assertIn(species, engine_io.DISPLAY_NAMES,
                              f"{species} has no English label")
                label = engine_io.DISPLAY_NAMES[species]
                self.assertNotEqual(label, species)
                self.assertTrue(label[0].isupper(), f"{label} is not title-case")
        for d in engine_io.import_all():
            with self.subTest(drawing=d.name):
                self.assertFalse(any(ch in d.name for ch in "ğüşıöçĞÜŞİÖÇ"),
                                 f"{d.name} still reads as Turkish")

    def test_a_tree_opens_at_the_size_it_occupies_in_the_garden(self):
        # A tree's canvas IS its size: the engine reads the tile count from its
        # own table and the sprite is 16px per tile, so a 4-tile tree has to be
        # a 64-cell grid or it renders at the wrong pixel density.
        gen = engine_io.gen_objects()
        for i in range(len(gen.TREE_TILES)):
            with self.subTest(tree=i):
                d = engine_io.import_forest_prop("tree", i)
                want = gen.TREE_TILES[i] * gen.TREE_PX_PER_TILE
                self.assertEqual((d.width, d.height), (want, want))

    def test_bushes_and_rocks_are_one_tile(self):
        for kind in ("bush", "rock"):
            d = engine_io.import_forest_prop(kind, 0)
            self.assertEqual((d.width, d.height), (16, 16))

    def test_a_prop_exports_under_its_own_engine_filename(self):
        # NOT flower_tree_00_0.png — the engine loads forest props by their own
        # name, and the `flower_` prefix on a tree was the #v17 "only shadows"
        # bug (it looked up a file that does not exist and drew nothing).
        d = engine_io.import_forest_prop("tree", 7)
        self.assertEqual(engine_io.engine_sprite_names(d), ["tree_07.png"])
        self.assertEqual(engine_io.engine_sprite_names(engine_io.import_forest_prop("rock", 2)),
                         ["rock_02.png"])

    def test_an_untouched_prop_exports_pixel_for_pixel_as_shipped(self):
        # The whole point of the kit: what it writes IS the shipped sprite.
        # Pixels, not file bytes — see _pixels for why (#v2.1.0).
        shipped = engine_io.APP_DIR / "flutter" / "assets" / "objects"
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("tree_00", "tree_03", "tree_12", "bush_04", "rock_01"):
                with self.subTest(prop=name):
                    kind, idx = name.split("_")
                    d = engine_io.import_forest_prop(kind, int(idx))
                    out = engine_io.export_engine_sprite(d, tmp)[0]
                    self.assertEqual(_pixels(out), _pixels(shipped / f"{name}.png"))

    def test_an_off_size_tree_is_refused_rather_than_written_wrong(self):
        d = engine_io.import_forest_prop("tree", 0)          # a 2-tile tree, 32 cells
        d.resize(48, 48)
        with self.assertRaises(engine_io.ExportRefused):
            engine_io.export_engine_sprite(d, tempfile.gettempdir())

    def test_a_prop_is_raw_pixels_so_the_engine_adds_no_rim(self):
        # Flowers are letter grids the engine outlines; forest props are drawn
        # exactly as painted. Rendering one must not change it.
        d = engine_io.import_forest_prop("bush", 1)
        rendered = engine_io.render(d)
        original = engine_io.gen_objects()._bush_variant(2)
        self.assertEqual(rendered, original)


class BugsAndSvgTest(unittest.TestCase):
    def test_every_critter_imports_as_an_8x8_bugs_labelled_drawing(self):
        bugs = [d for d in engine_io.import_all() if d.species == engine_io.BUG]
        self.assertEqual(len(bugs), len(engine_io.BUG_IDS))
        for i, d in enumerate(bugs):
            self.assertEqual((d.width, d.height), (8, 8))
            self.assertEqual(d.label, "bugs")
            self.assertEqual(engine_io.engine_sprite_names(d), [f"{engine_io.BUG_IDS[i]}.png"])

    def test_svg_export_is_vector_rects_not_a_bitmap(self):
        d = Drawing.blank(4, 2, engine_io._forest_palette())
        d.paint(0, 0, (200, 10, 10, 255))
        d.paint(1, 0, (200, 10, 10, 255))
        with tempfile.TemporaryDirectory() as tmp:
            path = engine_io.export_svg(d, Path(tmp) / "a.svg", cell=10)
            text = path.read_text(encoding="utf-8")
        self.assertIn('shape-rendering="crispEdges"', text)
        self.assertIn("<rect", text)
        self.assertNotIn("<image", text)
        self.assertIn('width="20"', text)  # two neighbouring cells of one colour merge



class RenderShortcutTest(unittest.TestCase):
    """#v2.8.0: a drawing with no palette letter skips the generator's walk.
    Its answer has to be the generator's own, cell for cell - the export
    tests of the shipped forest go through it, and so does this."""

    @staticmethod
    def _generator(d):
        """`render`'s generator path, whatever the cells."""
        g = engine_io.gen_objects()
        colors = d.palette.colors()
        bloom, plant, raw = (g.blank(d.width, d.height) for _ in range(3))
        for r, row in enumerate(d.cells):
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                if isinstance(cell, tuple):
                    raw[r][c] = cell
                elif cell in engine_io.BLOOM_LETTERS:
                    bloom[r][c] = colors[cell]
                elif cell in engine_io.PLANT_LETTERS:
                    plant[r][c] = colors[cell]
        bloom = g.outline(bloom, d.palette.rim)
        plant = g.outline(plant, d.palette.plant_rim)
        return g._rose_compose([plant, bloom, raw])

    def test_it_is_the_generators_answer_for_every_seeded_drawing(self):
        drawings = engine_io.import_all()
        self.assertTrue(any(engine_io.has_letters(d) for d in drawings))
        self.assertTrue(any(not engine_io.has_letters(d) for d in drawings))
        for d in drawings:
            self.assertEqual(engine_io.render(d), self._generator(d), d.name)

    def test_and_for_a_big_scattered_one(self):
        import random
        rnd = random.Random(7)
        d = Drawing.blank(300, 200, engine_io._forest_palette())
        for _ in range(5000):
            d.paint(rnd.randrange(300), rnd.randrange(200), (rnd.randrange(256), 9, 9, 255))
        self.assertFalse(engine_io.has_letters(d))
        self.assertEqual(engine_io.render(d), self._generator(d))
        d.paint(0, 0, "m")                      # one letter: the generator's path again
        self.assertTrue(engine_io.has_letters(d))
        self.assertEqual(engine_io.render(d), self._generator(d))


class DrawingPatchTest(unittest.TestCase):
    """#v2.8.0: the game's #v36.1 ships anthurium, pilea and sundew as the PNGs
    Ola Górecka drew. The kit brings all five in, signed, and gives each one
    back pixel for pixel."""

    def test_the_five_come_in_signed_by_their_artist(self):
        patch = [d for d in engine_io.import_all() if d.species in engine_io.PATCH_FLOWERS]
        self.assertEqual(sorted((d.species, d.model) for d in patch),
                         [("anthurium", 0), ("pilea", 0), ("pilea", 1), ("sundew", 0), ("sundew", 1)])
        for d in patch:
            self.assertEqual((d.artist, d.label, d.width, d.height),
                             ("Ola Górecka", "flower", 16, 16))
        self.assertEqual([d.name for d in patch],
                         ["Anthurium", "Pilea 1", "Pilea 2", "Sundew 1", "Sundew 2"])

    def test_each_goes_back_out_as_the_sprite_the_game_ships(self):
        from PIL import Image
        for species, n in engine_io.PATCH_FLOWERS.items():
            for model in range(n):
                d = engine_io.import_seed(species, model)
                shipped = Image.open(engine_io.patch_sprite(species, model)).convert("RGBA")
                px = shipped.load()
                want = [px[x, y] if px[x, y][3] else (0, 0, 0, 0)
                        for y in range(shipped.height) for x in range(shipped.width)]
                big = engine_io._scaled(d, 16)
                got = [tuple(p) if p[3] else (0, 0, 0, 0) for row in big for p in row]
                self.assertEqual(got, want, f"{species} {model}")

    def test_the_single_form_has_no_model_number(self):
        anthurium = engine_io.import_seed("anthurium", 0)
        self.assertEqual(engine_io.engine_sprite_names(anthurium), ["flower_anthurium.png"])
        self.assertEqual(engine_io.suggested_sprite_name(anthurium), "flower_anthurium.png")
        pilea = engine_io.import_seed("pilea", 0)
        self.assertEqual(engine_io.engine_sprite_names(pilea),
                         ["flower_pilea_0.png", "flower_pilea.png"])
