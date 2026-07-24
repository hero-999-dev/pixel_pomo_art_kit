import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(engine_io.import_flower("kaktusf", 0).palette.plant_rim, "1E5A24")

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

    def test_an_empty_drawing_renders_fully_transparent(self):
        from art_kit.model import Drawing, Palette
        pal = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C", rim="2E0810")
        grid = engine_io.render(Drawing.blank(16, 4, pal))
        self.assertTrue(all(px == (0, 0, 0, 0) for row in grid for px in row))
