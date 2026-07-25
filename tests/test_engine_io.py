import tempfile
import unittest
from pathlib import Path
from unittest import mock

from art_kit import engine_io
from art_kit.model import Drawing


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
        self.assertEqual(len(drawings), 24)
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


class ExportTest(unittest.TestCase):
    ASSETS = Path(r"C:\Users\claude\pixel_pomo\flutter\assets\objects")

    def test_an_untouched_flower_exports_byte_for_byte_as_shipped(self):
        for species, model in (("lale", 0), ("papatya", 1), ("gul", 0)):
            with self.subTest(species=species, model=model):
                shipped = (self.ASSETS / f"flower_{species}_{model}.png").read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    written = engine_io.export_engine_sprite(
                        engine_io.import_flower(species, model), Path(tmp))
                    mine = (Path(tmp) / f"flower_{species}_{model}.png").read_bytes()
                self.assertEqual(mine, shipped)
                self.assertTrue(written)

    def test_model_zero_also_writes_the_shop_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine_io.export_engine_sprite(engine_io.import_flower("lale", 0), Path(tmp))
            thumb = (Path(tmp) / "flower_lale.png").read_bytes()
            shipped = (self.ASSETS / "flower_lale.png").read_bytes()
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

    def test_grid_literal_round_trips_through_the_engines_own_format(self):
        g = engine_io.gen_objects()
        text = engine_io.export_grid_literal(engine_io.import_flower("lale", 0))
        rows = [line.strip().strip(",").strip('"') for line in text.splitlines() if '"' in line]
        self.assertEqual(rows, list(g._FLOWER_BLOOMS["lale"][0]))

    def test_grid_literal_is_refused_for_a_raw_pixel_drawing(self):
        with self.assertRaises(engine_io.ExportRefused):
            engine_io.export_grid_literal(engine_io.import_flower("gul", 0))

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
