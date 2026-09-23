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


class ArtistColourTest(unittest.TestCase):
    """#v2.8.0: "her artist için random farklı bir renk atansın"."""

    def test_each_artist_gets_a_colour_of_their_own_and_keeps_it(self):
        import colorsys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            s = Settings(path)
            colours = {name: s.artist_colour(name) for name in ("Mir", "Mia", "Ola")}
            self.assertEqual(len(set(colours.values())), 3)
            hues = [colorsys.rgb_to_hsv(*(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)))[0]
                    for c in colours.values()]
            for i, a in enumerate(hues):
                for b in hues[i + 1:]:
                    self.assertGreater(min(abs(a - b), 1 - abs(a - b)), 1 / 12,
                                       "far apart on the wheel, so a shared initial still differs")
            self.assertEqual(Settings(path).artist_colour("Mia"), colours["Mia"], "kept")


class ExportMarkTest(unittest.TestCase):
    """#v2.8.0, sixth test pass: the artist's mark on exports is remembered."""

    def test_the_signature_and_the_name_in_the_file_persist_and_validate(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            s = Settings(path)
            self.assertEqual((s.export_signature, s.export_metadata), ("none", True))
            s.export_signature = "watermark"
            s.export_metadata = False
            s.export_signature = "graffiti"                    # not a mode: ignored
            again = Settings(path)
            self.assertEqual((again.export_signature, again.export_metadata), ("watermark", False))
            again.data["export_signature"] = "nonsense"        # a hand-edited file
            self.assertEqual(again.export_signature, "none")
            again.export_signature = "corner+watermark"       # both marks at once
            self.assertTrue(again.export_log, "the record is kept unless the artist says no")
            again.export_log = False
            last = Settings(path)
            self.assertEqual((last.export_signature, last.export_log), ("corner+watermark", False))


class ArtistRenameTest(unittest.TestCase):
    """#v2.8.0, ninth test pass: an artist renamed keeps their colour; one
    taken off every drawing gives it back."""

    def test_the_colour_follows_a_rename_and_goes_with_a_removal(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(Path(tmp) / "settings.json")
            mir = s.artist_colour("Mir")
            s.rename_artist("Mir", "Ola Górecka")
            self.assertEqual(Settings(Path(tmp) / "settings.json").artist_colour("Ola Górecka"), mir)
            self.assertNotIn("Mir", s.data["artist_colours"])
            other = s.artist_colour("Hero")
            s.rename_artist("Hero", "Ola Górecka")               # onto a name that has one
            self.assertEqual(s.artist_colour("Ola Górecka"), mir, "the existing one is kept")
            self.assertNotEqual(other, mir)
            s.forget_artist("Ola Górecka")
            self.assertNotIn("Ola Górecka", s.data["artist_colours"])
