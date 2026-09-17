import json
import tempfile
import unittest
from pathlib import Path

from art_kit.settings import DEFAULT_FAVOURITES, Settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "settings.json"

    def test_a_missing_file_gives_the_six_classic_favourites(self):
        s = Settings(self.path)
        self.assertEqual(s.favourites, DEFAULT_FAVOURITES)
        self.assertEqual(len(s.favourites), 6)
        self.assertEqual(s.tool, "draw")
        self.assertEqual(s.symmetry, {"orientation": "vertical", "length": 5, "mode": "off"})
        self.assertFalse(self.path.exists(), "nothing is written until something changes")

    def test_favourites_round_trip_through_the_file(self):
        s = Settings(self.path)
        self.assertTrue(s.add_favourite("#a6e3a1"))
        self.assertFalse(s.add_favourite("A6E3A1"), "same colour, different spelling: no duplicate")
        self.assertTrue(s.remove_favourite("ff0000"))
        self.assertFalse(s.remove_favourite("ff0000"))
        again = Settings(self.path)
        self.assertEqual(again.favourites, DEFAULT_FAVOURITES[1:] + ["A6E3A1"])

    def test_a_bad_hex_is_refused(self):
        s = Settings(self.path)
        self.assertFalse(s.add_favourite("not a colour"))
        self.assertFalse(s.add_favourite("#fff"))
        self.assertEqual(s.favourites, DEFAULT_FAVOURITES)

    def test_tool_and_symmetry_persist(self):
        s = Settings(self.path)
        s.tool = "fill"
        s.set_symmetry("horizontal", 9)
        again = Settings(self.path)
        self.assertEqual(again.tool, "fill")
        self.assertEqual(again.symmetry, {"orientation": "horizontal", "length": 9, "mode": "off"},
                         "mode is kept when not given")
        again.set_symmetry("vertical", 3, "stick")
        self.assertEqual(Settings(self.path).symmetry["mode"], "stick")

    def test_an_old_settings_file_without_a_mode_still_reads(self):
        self.path.write_text(json.dumps({"symmetry": {"orientation": "horizontal", "length": 7}}),
                             encoding="utf-8")
        self.assertEqual(Settings(self.path).symmetry,
                         {"orientation": "horizontal", "length": 7, "mode": "off"})

    def test_a_corrupt_file_falls_back_to_defaults_instead_of_raising(self):
        self.path.write_text("{ this is not json", encoding="utf-8")
        s = Settings(self.path)
        self.assertEqual(s.favourites, DEFAULT_FAVOURITES)

    def test_a_hand_edited_bad_favourite_drops_that_entry_only(self):
        self.path.write_text(json.dumps({"favourites": ["112233", 42, "zzzzzz", "#AABBCC"],
                                         "tool": 7}), encoding="utf-8")
        s = Settings(self.path)
        self.assertEqual(s.favourites, ["112233", "AABBCC"])
        self.assertEqual(s.tool, "draw", "a wrong-typed field keeps its default")


class SettingsV26Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "settings.json"

    def test_grid_colours_default_validate_and_reset(self):
        s = Settings(self.path)
        self.assertEqual(s.grid, {"c1": "232F28", "c2": "2A3A30"})
        s.set_grid(c1="#402020")
        self.assertEqual(Settings(self.path).grid, {"c1": "402020", "c2": "2A3A30"})
        s.set_grid(c2="not a colour")
        self.assertEqual(s.grid["c2"], "2A3A30", "a bad code changes nothing")
        s.reset_grid()
        self.assertEqual(s.grid["c1"], "232F28")

    def test_show_grid_and_eraser_persist(self):
        s = Settings(self.path)
        self.assertTrue(s.show_grid)
        self.assertEqual(s.eraser, {"w": 1, "h": 1})
        s.show_grid = False
        s.set_eraser(3, 200)
        again = Settings(self.path)
        self.assertFalse(again.show_grid)
        self.assertEqual(again.eraser, {"w": 3, "h": 64}, "clamped to the biggest drawing")


if __name__ == "__main__":
    unittest.main()
