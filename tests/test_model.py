import unittest

from art_kit.model import Drawing, History, Palette

PAL = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C",
              rim="2E0810", plant_rim="1E5A24")


class PaletteTest(unittest.TestCase):
    def test_nine_letters_resolve_to_rgba(self):
        colors = PAL.colors()
        self.assertEqual(set(colors), set("dmlCxSGko"))
        self.assertEqual(colors["m"], (0xD9, 0x36, 0x45, 255))
        self.assertEqual(colors["x"], (0x2E, 0x08, 0x10, 255))  # bloom seam = rim
        self.assertEqual(colors["o"], (0x1E, 0x5A, 0x24, 255))  # plant seam


class DrawingTest(unittest.TestCase):
    def test_blank_is_empty_at_the_requested_size(self):
        d = Drawing.blank(16, 14, PAL)
        self.assertEqual((d.width, d.height), (16, 14))
        self.assertIsNone(d.get(0, 0))
        self.assertTrue(d.is_letters())

    def test_paint_and_erase_one_cell(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(1, 2, "m")
        self.assertEqual(d.get(1, 2), "m")
        d.erase(1, 2)
        self.assertIsNone(d.get(1, 2))

    def test_painting_a_raw_colour_makes_it_a_pixel_drawing(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(0, 0, (10, 20, 30, 255))
        self.assertFalse(d.is_letters())

    def test_kind_is_derived_and_tracks_the_cells_both_ways(self):
        d = Drawing.blank(4, 3, PAL)
        self.assertEqual(d.kind, "letters")
        d.paint(0, 0, "m")
        self.assertEqual(d.kind, "letters")       # a letter is still letters
        d.paint(1, 0, (1, 2, 3, 255))
        self.assertEqual(d.kind, "pixels")        # a raw colour flips it
        d.erase(1, 0)
        self.assertEqual(d.kind, "letters")       # and removing it flips back

    def test_out_of_bounds_paint_is_ignored_not_an_error(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(9, 9, "m")
        d.paint(-1, 0, "m")
        self.assertTrue(d.is_letters())

    def test_flood_fills_the_connected_region_only(self):
        d = Drawing.blank(6, 3, PAL)
        for r in range(3):
            d.paint(3, r, "k")  # a wall down column 3
        d.flood(0, 0, "m")
        self.assertEqual(d.get(2, 2), "m", "left of the wall fills")
        self.assertEqual(d.get(3, 1), "k", "the wall itself is untouched")
        self.assertIsNone(d.get(4, 0), "right of the wall is another region")

    def test_flood_on_the_same_value_is_a_no_op(self):
        d = Drawing.blank(4, 3, PAL)
        d.flood(0, 0, None)  # would recurse forever if not guarded
        self.assertIsNone(d.get(0, 0))

    def test_resize_pads_and_crops_right_and_below(self):
        d = Drawing.blank(4, 3, PAL)
        d.paint(1, 1, "m")
        d.resize(6, 5)
        self.assertEqual((d.width, d.height), (6, 5))
        self.assertIsNone(d.get(5, 4))
        self.assertEqual(d.get(1, 1), "m", "existing cells survive a pad")
        d.resize(2, 2)
        self.assertEqual((d.width, d.height), (2, 2))
        self.assertEqual(d.get(1, 1), "m", "cropping stops before the art")

    def test_count_and_empty_count(self):
        d = Drawing.blank(4, 3, PAL)
        self.assertEqual(d.count(), 0)
        self.assertEqual(d.empty_count(), 12)
        d.paint(0, 0, "m")
        d.paint(1, 1, "l")
        self.assertEqual(d.count(), 2)
        self.assertEqual(d.empty_count(), 10)

    def test_fill_region_paints_the_rectangle(self):
        d = Drawing.blank(6, 4, PAL)
        d.fill_region(1, 1, 3, 2, "m")
        painted = {(c, r) for r in range(4) for c in range(6) if d.get(c, r) == "m"}
        self.assertEqual(painted, {(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2)})
        d = Drawing.blank(4, 3, PAL)
        clone = d.copy()
        clone.paint(0, 0, "d")
        self.assertIsNone(d.get(0, 0), "editing the copy must not touch the original")


class LabelAndBlocksTest(unittest.TestCase):
    """#v2.6.0: the label field, the pixel counters, and the block helpers
    behind select / copy / paste."""

    def test_label_defaults_empty_and_survives_copy(self):
        d = Drawing.blank(4, 4, PAL)
        self.assertEqual(d.label, "")
        d.label = "wip"
        self.assertEqual(d.copy().label, "wip")
        self.assertEqual(Drawing.blank(2, 2, PAL, label="tree").label, "tree")

    def test_the_left_and_top_edges_record_how_far_the_art_moved(self):
        """#v2.8.0: `shift` is how the window keeps the art still when an
        undo takes back columns a left-edge drag added. Only the left and the
        top move the art; it rides along in the undo snapshots; it is never
        written to the file and never makes two drawings unequal."""
        from art_kit import store
        d = Drawing.blank(4, 4, PAL)
        self.assertEqual(d.shift, (0, 0))
        d.resize_edge("left", 2)
        d.resize_edge("top", -1)
        d.resize_edge("right", 3)
        d.resize_edge("bottom", 1)
        self.assertEqual(d.shift, (2, -1))
        self.assertEqual(d.copy().shift, (2, -1))
        self.assertNotIn("shift", store.to_dict(d))
        self.assertEqual(d, Drawing(name=d.name, species=d.species, model=d.model,
                                    cells=[list(r) for r in d.cells], palette=PAL))

    def test_counts_total_row_and_column(self):
        d = Drawing.blank(4, 3, PAL)
        for c in range(3):
            d.paint(c, 1, "m")
        d.paint(0, 2, "m")
        self.assertEqual(d.count(), 4)
        self.assertEqual(d.row_count(1), 3)
        self.assertEqual(d.row_count(0), 0)
        self.assertEqual(d.col_count(0), 2)
        self.assertEqual(d.row_count(99), 0)
        self.assertEqual(d.col_count(-1), 0)

    def test_region_copies_a_rectangle_in_either_corner_order(self):
        d = Drawing.blank(5, 5, PAL)
        d.paint(1, 1, "m")
        d.paint(2, 2, "l")
        cells, w, h = d.region(2, 2, 1, 1)
        self.assertEqual((w, h), (2, 2))
        self.assertEqual(cells, [["m", None], [None, "l"]])
        cells[0][0] = "d"
        self.assertEqual(d.get(1, 1), "m", "a copy, not a view")

    def test_stamp_skips_empty_cells_and_clips_at_the_edge(self):
        d = Drawing.blank(4, 4, PAL)
        d.paint(3, 3, "d")
        d.stamp([["m", None], [None, "l"]], 2, 2)
        self.assertEqual(d.get(2, 2), "m")
        self.assertEqual(d.get(3, 3), "l")
        d.stamp([["m", None]], 3, 3)
        self.assertEqual(d.get(3, 3), "m")
        d.stamp([[None, "l"]], 3, 0)  # (4, 0) is off the grid: dropped, no error
        self.assertIsNone(d.get(3, 0))
        d.stamp([[None]], 0, 0, skip_empty=False)
        self.assertIsNone(d.get(0, 0))

    def test_clear_region(self):
        d = Drawing.blank(4, 4, PAL)
        for c in range(4):
            d.paint(c, 0, "m")
        d.clear_region(2, 0, 1, 0)
        self.assertEqual([d.get(c, 0) for c in range(4)], ["m", None, None, "m"])


class SwapColourTest(unittest.TestCase):
    """SWAP (#v2.9.0): every cell of one colour, however it is stored."""

    def test_a_letter_and_a_raw_colour_that_look_alike_both_match(self):
        d = Drawing.blank(4, 2, PAL)
        d.paint(0, 0, "m")
        d.paint(3, 1, PAL.colors()["m"])
        d.paint(1, 0, "d")
        self.assertEqual(d.cells_coloured(PAL.colors()["m"]), [(0, 0), (3, 1)])

    def test_swap_changes_them_all_and_counts_them(self):
        d = Drawing.blank(4, 2, PAL)
        for c in range(4):
            d.paint(c, 0, "l")
        self.assertEqual(d.swap_colour(PAL.colors()["l"], "d"), 4)
        self.assertEqual(d.cells[0], ["d"] * 4)
        self.assertEqual(d.cells[1], [None] * 4, "empty cells are never a colour")

    def test_a_region_keeps_it_inside(self):
        d = Drawing.blank(4, 4, PAL)
        for c in range(4):
            d.paint(c, c, "l")
        self.assertEqual(d.swap_colour(PAL.colors()["l"], "d", (0, 0, 1, 1)), 2)
        self.assertEqual(d.get(2, 2), "l")
        self.assertEqual(d.cells_coloured(PAL.colors()["d"], (-5, -5, 99, 99)), [(0, 0), (1, 1)],
                         "a region past the edges is clipped")

    def test_colour_of(self):
        d = Drawing.blank(1, 1, PAL)
        self.assertIsNone(d.colour_of(None))
        self.assertEqual(d.colour_of("m"), PAL.colors()["m"])
        self.assertEqual(d.colour_of([1, 2, 3, 255]), (1, 2, 3, 255))


class HistoryTest(unittest.TestCase):
    def test_a_big_drawing_keeps_a_shorter_undo_memory_rather_than_all_of_it(self):
        """#v2.8.0: with no size cap, two hundred snapshots of a big drawing
        would fill the machine. Past CELL_BUDGET the oldest steps go - never
        the newest."""
        h = History(Drawing.blank(100, 100, PAL))               # 10 000 cells a snapshot
        h.CELL_BUDGET = 50_000
        for i in range(12):
            h.begin_stroke()
            h.current.paint(i, 0, "m")
            h.end_stroke()
        self.assertEqual(len(h._undo), 5, "five snapshots fill 50 000 cells")
        h.undo()
        self.assertIsNone(h.current.get(11, 0), "the newest stroke is still undoable")
        self.assertEqual(h.current.get(10, 0), "m")

    def setUp(self):
        self.h = History(Drawing.blank(4, 3, PAL))

    def _stroke(self, *cells):
        self.h.begin_stroke()
        for col, row, val in cells:
            self.h.current.paint(col, row, val)
        self.h.end_stroke()

    def test_undo_restores_the_grid_before_the_stroke(self):
        self._stroke((0, 0, "d"), (1, 0, "d"))
        self.assertEqual(self.h.current.get(1, 0), "d")
        self.h.undo()
        self.assertIsNone(self.h.current.get(0, 0))
        self.assertIsNone(self.h.current.get(1, 0))

    def test_a_drag_is_one_undo_not_one_per_pixel(self):
        self._stroke((0, 0, "d"), (1, 0, "d"), (2, 0, "d"))
        self.h.undo()
        self.assertFalse(self.h.can_undo())

    def test_redo_puts_it_back_then_stops(self):
        self._stroke((0, 0, "d"))
        self.h.undo()
        self.h.redo()
        self.assertEqual(self.h.current.get(0, 0), "d")
        self.assertFalse(self.h.can_redo())

    def test_undo_at_the_start_and_redo_at_the_end_do_nothing(self):
        self.assertFalse(self.h.can_undo())
        self.h.undo()  # must not raise
        self.h.redo()  # must not raise
        self.assertEqual(self.h.current.get(0, 0), None)

    def test_a_new_stroke_after_an_undo_drops_the_redo_branch(self):
        self._stroke((0, 0, "d"))
        self.h.undo()
        self._stroke((1, 1, "m"))
        self.assertFalse(self.h.can_redo())
        self.assertEqual(self.h.current.get(1, 1), "m")

    def test_a_stroke_that_changed_nothing_is_not_recorded(self):
        self.h.begin_stroke()
        self.h.end_stroke()
        self.assertFalse(self.h.can_undo())

    def test_repaint_survives_an_undo(self):
        self._stroke((0, 0, "d"))
        pal2 = Palette(d="111111", m="222222", l="333333", centre="444444", rim="555555")
        self.h.repaint(pal2)
        self.h.undo()
        self.assertIs(self.h.current.palette, pal2,
                      "undo restores cells, never an old palette")

    def test_the_undo_stack_stops_at_its_limit(self):
        h = History(Drawing.blank(5, 3, PAL), limit=3)
        for col in range(5):
            h.begin_stroke()
            h.current.paint(col, 0, "d")
            h.end_stroke()
        undone = 0
        while h.can_undo():
            h.undo()
            undone += 1
        self.assertEqual(undone, 3)
