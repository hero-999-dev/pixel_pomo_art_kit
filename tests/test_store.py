import json
import tempfile
import unittest
from pathlib import Path


from art_kit import engine_io, store
from art_kit.model import Drawing, Palette

# Everything the app seeds: two models per flower, plus the forest props the
# engine loads (#v34.8). Derived, so adding a species or a tree moves it
# automatically instead of leaving a stale literal behind.
SEEDED = engine_io.seeded_count()


PAL = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C", rim="2E0810")


class CodecTest(unittest.TestCase):
    def test_a_pixel_drawing_is_written_a_row_a_line(self):
        """#v2.8.0: `indent=1` put every number on a line of its own - 37 MB
        for a 2000-cell square. A row a line; a letter drawing unchanged."""
        d = Drawing.blank(3, 2, PAL, artist="Mir")
        d.paint(0, 0, (1, 2, 3, 255))
        text = store.dumps(store.to_dict(d))
        self.assertIn('"cells": [\n  [[1,2,3,255],null,null],\n  [null,null,null]\n ]', text)
        back = store.from_dict(json.loads(text))
        self.assertEqual((back.cells, back.artist), (d.cells, "Mir"))
        letters = engine_io.import_flower("lale", 0)
        self.assertEqual(store.dumps(store.to_dict(letters)),
                         json.dumps(store.to_dict(letters), indent=1), "byte for byte as before")

    def test_a_file_from_before_artists_has_none(self):
        data = store.to_dict(Drawing.blank(2, 2, PAL))
        del data["artist"]
        self.assertEqual(store.from_dict(data).artist, "")

    def test_leaving_the_colours_as_tuples_writes_the_same_file(self):
        """#v2.8.0: `to_dict` no longer turns every colour into a list first -
        `json.dumps` writes a tuple as an array anyway - and the saved text
        must not change by a byte for it."""
        d = Drawing.blank(3, 2, PAL)
        d.paint(0, 0, (1, 2, 3, 255))
        d.paint(2, 1, "m")
        data = store.to_dict(d)
        listed = dict(data, cells=[[list(c) if isinstance(c, tuple) else c for c in row]
                                   for row in d.cells])
        self.assertEqual(json.dumps(data, indent=1), json.dumps(listed, indent=1))
        self.assertEqual(store.from_dict(data).cells, d.cells)
        self.assertEqual(store.from_dict(json.loads(json.dumps(data))).cells, d.cells)

    def test_a_letter_drawing_round_trips(self):
        original = engine_io.import_flower("lale", 0)
        clone = store.from_dict(store.to_dict(original))
        self.assertEqual(clone.cells, original.cells)
        self.assertEqual(clone.palette, original.palette)
        self.assertEqual((clone.species, clone.model, clone.kind),
                         ("lale", 0, "letters"))

    def test_a_letter_drawing_is_stored_as_readable_rows(self):
        data = store.to_dict(engine_io.import_flower("lale", 0))
        self.assertIsInstance(data["cells"][0], str)
        self.assertEqual(len(data["cells"][0]), 16)

    def test_a_raw_pixel_drawing_round_trips(self):
        original = engine_io.import_flower("gul", 0)
        clone = store.from_dict(store.to_dict(original))
        self.assertEqual(clone.cells, original.cells)
        self.assertEqual(clone.kind, "pixels")

    def test_a_mixed_drawing_round_trips(self):
        d = engine_io.import_flower("lale", 0)
        d.paint(0, 0, (1, 2, 3, 255))
        clone = store.from_dict(store.to_dict(d))
        self.assertEqual(clone.get(0, 0), (1, 2, 3, 255))
        self.assertEqual(clone.get(7, 1), d.get(7, 1))

    def test_missing_fields_raise_something_the_app_can_report(self):
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict({"name": "x"})

    def test_a_ragged_grid_is_refused_rather_than_half_loaded(self):
        data = store.to_dict(engine_io.import_flower("lale", 0))
        data["cells"][2] = "dm"
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)

    def test_cells_that_are_not_a_list_of_rows_is_refused(self):
        # A bare string is iterable-of-characters, so a naive row loop can
        # "succeed" on it silently instead of rejecting the wrong shape.
        data = store.to_dict(engine_io.import_flower("lale", 0))
        data["cells"] = "not a grid"
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)

    def test_a_malformed_cell_raises_corrupt_drawing_not_a_bare_exception(self):
        # A row that is neither a string nor a list (e.g. a stray number from
        # a hand-edit) must not leak a raw TypeError past the trust boundary,
        # or one bad file takes down the whole library load with it.
        data = store.to_dict(engine_io.import_flower("lale", 0))
        data["cells"][2] = 12345
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)

    def test_a_letter_outside_the_alphabet_is_refused(self):
        # The format is hand-editable; a typo'd letter would otherwise load and
        # then silently vanish at render time instead of being caught here.
        data = store.to_dict(engine_io.import_flower("lale", 0))
        data["cells"][2] = data["cells"][2][:-1] + "Z"
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)

    def test_a_colour_cell_of_the_wrong_length_is_refused(self):
        d = engine_io.import_flower("lale", 0)
        d.paint(0, 0, (1, 2, 3, 255))
        data = store.to_dict(d)
        data["cells"][0][1] = [1, 2, 3]  # three channels, not four
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)

    def test_an_unknown_kind_is_refused(self):
        data = store.to_dict(engine_io.import_flower("lale", 0))
        data["kind"] = "sculpture"
        with self.assertRaises(store.CorruptDrawing):
            store.from_dict(data)


class LabelCodecTest(unittest.TestCase):
    def test_label_round_trips(self):
        d = Drawing.blank(16, 2, PAL, name="x", species="lale", label="wip")
        again = store.from_dict(store.to_dict(d))
        self.assertEqual(again.label, "wip")

    def test_a_file_without_a_label_or_with_a_bad_one_reads_as_unlabelled(self):
        data = store.to_dict(Drawing.blank(16, 2, PAL, name="x", species="lale"))
        del data["label"]
        self.assertEqual(store.from_dict(data).label, "")
        data["label"] = 42
        self.assertEqual(store.from_dict(data).label, "")
        data["label"] = "  tree "
        self.assertEqual(store.from_dict(data).label, "tree")


class SaveLoadTest(unittest.TestCase):
    def test_save_overwrites_atomically_leaving_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"
            store.save(engine_io.import_flower("lale", 0), path)
            store.save(engine_io.import_flower("lale", 1), path)
            self.assertEqual(store.load(path).model, 1)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["d.json"])


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = store.Library(Path(self.tmp.name))

    def test_seeding_writes_every_shipped_drawing(self):
        self.lib.seed_from_engine()
        self.assertEqual(len(self.lib.drawings), SEEDED)
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.json"))), SEEDED)

    def test_seeding_twice_does_not_duplicate(self):
        self.lib.seed_from_engine()
        self.lib.seed_from_engine()
        self.assertEqual(len(self.lib.drawings), SEEDED)

    def test_reopening_the_library_finds_what_was_saved(self):
        self.lib.seed_from_engine()
        again = store.Library(Path(self.tmp.name))
        again.load_all()
        self.assertEqual(len(again.drawings), SEEDED)

    def test_duplicate_makes_an_independent_copy_with_a_new_name(self):
        d = self.lib.add(Drawing.blank(16, 4, PAL, name="rose sketch", species="lale"))
        copy = self.lib.duplicate(d)
        self.assertNotEqual(copy.name, d.name)
        copy.paint(0, 0, "m")
        self.assertIsNone(d.get(0, 0))
        self.assertEqual(len(self.lib.drawings), 2)

    def test_remove_deletes_the_file_too(self):
        d = self.lib.add(Drawing.blank(16, 4, PAL, name="gone", species="lale"))
        self.lib.remove(d)
        self.assertEqual(self.lib.drawings, [])
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])

    def test_two_drawings_with_the_same_name_get_separate_files(self):
        self.lib.add(Drawing.blank(16, 4, PAL, name="same", species="lale"))
        self.lib.add(Drawing.blank(16, 4, PAL, name="same", species="lale"))
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.json"))), 2)

    def test_removing_one_of_two_value_equal_drawings_keeps_the_other_usable(self):
        # Two fresh blanks compare == ; remove must go by identity or it splices
        # out the wrong one, orphans the survivor from _paths, and the next
        # save() on it crashes.
        a = self.lib.add(Drawing.blank(16, 4, PAL, name="same", species="lale"))
        b = self.lib.add(Drawing.blank(16, 4, PAL, name="same", species="lale"))
        self.lib.remove(b)
        self.assertIs(self.lib.drawings[0], a)
        self.assertEqual(len(self.lib.drawings), 1)
        self.lib.save(a)  # must not raise KeyError
        self.assertEqual(len(list(Path(self.tmp.name).glob("*.json"))), 1)

    def test_first_save_of_a_session_leaves_a_bak_of_what_the_session_started_with(self):
        d = self.lib.add(Drawing.blank(16, 4, PAL, name="art", species="lale"))
        # A later session opens the library and edits.
        again = store.Library(Path(self.tmp.name))
        again.load_all()
        loaded = again.drawings[0]
        # the file as it was on disk (load_all may fill a default label in
        # memory for a pre-#v2.6.0 file; the .bak is the DISK starting point)
        original = json.loads(again._paths[id(loaded)].read_text(encoding="utf-8"))
        loaded.paint(0, 0, "m")
        again.save(loaded)
        loaded.paint(1, 0, "m")
        again.save(loaded)  # second save must not clobber the backup
        baks = list(Path(self.tmp.name).glob("*.json.bak"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(json.loads(baks[0].read_text(encoding="utf-8")), original,
                         "the .bak is the session's starting point, not a later state")

    def test_loading_an_old_unlabelled_library_gives_seeded_kinds_their_label(self):
        # #v2.6.0: a library written before labels existed
        self.lib.add(Drawing.blank(16, 4, PAL, name="old flower", species="lale"))
        self.lib.add(Drawing.blank(32, 32, PAL, name="old tree", species="tree"))
        self.lib.add(Drawing.blank(8, 8, PAL, name="mine", species=""))
        again = store.Library(Path(self.tmp.name))
        again.load_all()
        by_name = {d.name: d.label for d in again.drawings}
        self.assertEqual(by_name, {"old flower": "flower", "old tree": "tree", "mine": ""})
        self.assertEqual(again.labels(), ["flower", "tree"])

    def test_a_corrupt_file_is_skipped_not_fatal(self):
        self.lib.seed_from_engine()
        (Path(self.tmp.name) / "broken.json").write_text("{ not json", encoding="utf-8")
        again = store.Library(Path(self.tmp.name))
        skipped = again.load_all()
        self.assertEqual(len(again.drawings), SEEDED)
        self.assertEqual(len(skipped), 1)

    def test_seed_missing_kinds_adds_bugs_to_an_older_library(self):
        self.lib.add(Drawing.blank(16, 4, PAL, name="only a flower", species="lale"))
        added = self.lib.seed_missing_kinds()
        kinds = {(d.species, d.model) for d in self.lib.drawings}
        for species, model in engine_io.seed_kinds()["bugs"]:
            self.assertIn((species, model), kinds)
        self.assertTrue(any(d.label == "bugs" for d in added))
        again = self.lib.seed_missing_kinds()
        self.assertEqual(again, [], "a second pass adds nothing")


class DrawingPatchSeedingTest(unittest.TestCase):
    def test_a_library_seeded_before_the_patch_gets_it_on_the_next_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = store.Library(Path(tmp) / "library")
            lib.seed_from_engine()
            for d in [d for d in lib.drawings if d.species in engine_io.PATCH_FLOWERS]:
                lib.remove(d)                                   # as a v2.7.0 library has it
            added = lib.seed_missing_kinds()
            self.assertEqual(sorted((d.species, d.model) for d in added),
                             [("anthurium", 0), ("pilea", 0), ("pilea", 1), ("sundew", 0), ("sundew", 1)])
            self.assertTrue(all(d.artist == engine_io.PATCH_ARTIST for d in added))
            self.assertEqual(lib.seed_missing_kinds(), [], "and only once")
            self.assertEqual(lib.artists(), [engine_io.PATCH_ARTIST])


class BundledDesignsTest(unittest.TestCase):
    """#v2.9.0: HeroDev999's and LadyOfDynamite's designs ship with the kit -
    not the Copy Siberian study, which is nobody's signed work."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = store.Library(Path(self.tmp.name) / "library")

    def test_the_bundle_is_the_two_artists_designs(self):
        keys = [k for k, _d in store.bundled_designs()]
        self.assertEqual(sorted(keys), ["HeroDev999/Space Eyes 13x13", "HeroDev999/Space Eyes 208x208",
                                        "LadyOfDynamite/Border", "LadyOfDynamite/Ghostie"])
        self.assertFalse([k for k in keys if "siberian" in k.lower()])

    def test_they_are_added_once_and_saved(self):
        offered = self.lib.seed_designs([])
        self.assertEqual(len(offered), 4)
        self.assertEqual({d.artist for d in self.lib.drawings}, {"HeroDev999", "LadyOfDynamite"})
        again = store.Library(self.lib.root)
        again.load_all()
        self.assertEqual(len(again.drawings), 4, "written to disk")
        self.assertEqual(again.seed_designs(offered), [], "offered before: not again")
        self.assertEqual(len(again.drawings), 4)

    def test_a_deleted_design_stays_deleted(self):
        offered = self.lib.seed_designs([])
        self.lib.remove(self.lib.drawings[0])
        self.lib.seed_designs(offered)
        self.assertEqual(len(self.lib.drawings), 3)

    def test_a_library_that_already_has_one_gets_no_twin(self):
        _key, border = [kd for kd in store.bundled_designs() if kd[0] == "LadyOfDynamite/Border"][0]
        self.lib.add(border)
        self.lib.seed_designs([])
        self.assertEqual([d.name for d in self.lib.drawings].count("Border"), 1)
        self.assertEqual(len(self.lib.drawings), 4)
