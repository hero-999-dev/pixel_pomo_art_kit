import unittest

from art_kit import symmetry
from art_kit.model import Drawing, Palette
from art_kit.symmetry import Bar, HORIZONTAL, VERTICAL, expand


PAL = Palette(d="9C1B2E", m="D93645", l="F2737C", centre="F2C94C",
              rim="2E0810", plant_rim="1E5A24")


class BarTest(unittest.TestCase):
    def test_a_vertical_bar_covers_length_rows_centred_on_the_click(self):
        bar = Bar(VERTICAL, 5, col=7, row=4)
        self.assertEqual(bar.span(), (2, 6))
        self.assertEqual(bar.cells(), [(7, r) for r in range(2, 7)])
        self.assertEqual(bar.angle, 90)

    def test_a_horizontal_bar_covers_length_columns(self):
        bar = Bar(HORIZONTAL, 4, col=7, row=4)
        # even length: the extra cell falls to the right/below of centre
        self.assertEqual(bar.span(), (6, 9))
        self.assertEqual(bar.cells(), [(c, 4) for c in range(6, 10)])
        self.assertEqual(bar.angle, 180)

    def test_a_vertical_bar_mirrors_across_the_line_between_cells(self):
        bar = Bar(VERTICAL, 5, col=7, row=4)
        # the line is the left edge of column 7: 6 <-> 7, 5 <-> 8, 4 <-> 9
        self.assertEqual(bar.mirror(4, 3), (9, 3))
        self.assertEqual(bar.mirror(9, 6), (4, 6))
        self.assertEqual(bar.mirror(6, 4), (7, 4), "neighbours across the line swap")
        self.assertIsNone(bar.mirror(4, 1), "row 1 is above the bar's reach")
        self.assertIsNone(bar.mirror(4, 7), "row 7 is below the bar's reach")

    def test_a_horizontal_bar_mirrors_top_to_bottom_across_the_line(self):
        bar = Bar(HORIZONTAL, 3, col=5, row=8)
        self.assertEqual(bar.mirror(5, 6), (5, 9))  # 2*8-1-6 = 9
        self.assertEqual(bar.mirror(4, 9), (4, 6))
        self.assertIsNone(bar.mirror(3, 6), "column 3 is outside a 3-long bar at 5")

    def test_touches_either_side_of_the_line(self):
        bar = Bar(VERTICAL, 5, col=7, row=4)
        self.assertTrue(bar.touches(7, 4))
        self.assertTrue(bar.touches(6, 4))
        self.assertFalse(bar.touches(5, 4))
        self.assertFalse(bar.touches(7, 1))

    def test_length_is_clamped_and_orientation_checked(self):
        self.assertEqual(Bar(VERTICAL, 0, 0, 0).length, symmetry.MIN_LENGTH)
        self.assertEqual(Bar(VERTICAL, 999, 0, 0).length, symmetry.MAX_LENGTH)
        with self.assertRaises(ValueError):
            Bar("diagonal", 5, 0, 0)

    def test_moved_to_keeps_shape_and_changes_place(self):
        moved = Bar(HORIZONTAL, 6, 1, 1).moved_to(9, 9)
        self.assertEqual((moved.orientation, moved.length, moved.col, moved.row),
                         (HORIZONTAL, 6, 9, 9))


class StickTest(unittest.TestCase):
    def test_a_horizontal_stick_runs_to_the_right_from_the_click(self):
        self.assertEqual(symmetry.stick(HORIZONTAL, 5, 3, 8),
                         [(3, 8), (4, 8), (5, 8), (6, 8), (7, 8)])

    def test_a_vertical_stick_runs_downward(self):
        self.assertEqual(symmetry.stick(VERTICAL, 3, 3, 8), [(3, 8), (3, 9), (3, 10)])

    def test_length_one_is_an_ordinary_click_and_length_is_clamped(self):
        self.assertEqual(symmetry.stick(HORIZONTAL, 1, 2, 2), [(2, 2)])
        self.assertEqual(len(symmetry.stick(HORIZONTAL, 0, 2, 2)), symmetry.MIN_LENGTH)
        self.assertEqual(len(symmetry.stick(HORIZONTAL, 500, 2, 2)), symmetry.MAX_LENGTH)
        with self.assertRaises(ValueError):
            symmetry.stick("sideways", 3, 0, 0)

    def test_expand_stick_grows_every_cell_without_duplicates(self):
        out = symmetry.expand_stick(HORIZONTAL, 3, [(0, 0), (1, 0)])
        self.assertEqual(out, [(0, 0), (1, 0), (2, 0), (3, 0)])


class ExpandTest(unittest.TestCase):
    def test_no_bar_returns_the_cells_unchanged(self):
        self.assertEqual(expand(None, [(1, 1), (2, 2)]), [(1, 1), (2, 2)])

    def test_twins_follow_their_originals_and_are_not_duplicated(self):
        bar = Bar(VERTICAL, 5, col=7, row=4)
        cells = [(6, 4), (7, 4)]  # neighbours across the line
        self.assertEqual(expand(bar, cells), [(6, 4), (7, 4)])

    def test_cells_beyond_the_bar_are_painted_alone(self):
        bar = Bar(VERTICAL, 1, col=7, row=4)  # one cell long: only row 4 mirrors
        self.assertEqual(expand(bar, [(3, 4), (3, 5)]), [(3, 4), (10, 4), (3, 5)])


class StampAcrossTest(unittest.TestCase):
    def test_a_vertical_stick_copies_the_length_rows_to_the_other_side(self):
        d = Drawing.blank(8, 6, PAL)
        d.paint(1, 2, "m")
        d.paint(2, 3, "l")
        bar = Bar(VERTICAL, 3, col=4, row=2)  # span rows 1..3, line between 3 and 4
        written = symmetry.stamp_across(d, bar)
        self.assertEqual(d.get(6, 2), "m")  # 2*4-1-1 = 6
        self.assertEqual(d.get(5, 3), "l")  # 2*4-1-2 = 5
        self.assertIsNone(d.get(6, 5), "row 5 is outside the 3-long span")
        self.assertIn((6, 2), written)


if __name__ == "__main__":
    unittest.main()
