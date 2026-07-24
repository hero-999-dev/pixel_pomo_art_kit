import tempfile
import unittest
from pathlib import Path

from art_kit import engine_io


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
