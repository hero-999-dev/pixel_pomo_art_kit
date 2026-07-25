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

    def test_copy_does_not_share_rows(self):
        d = Drawing.blank(4, 3, PAL)
        clone = d.copy()
        clone.paint(0, 0, "d")
        self.assertIsNone(d.get(0, 0), "editing the copy must not touch the original")


class HistoryTest(unittest.TestCase):
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
