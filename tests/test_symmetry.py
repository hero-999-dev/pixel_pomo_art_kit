import unittest

from art_kit import symmetry
from art_kit.symmetry import Bar, HORIZONTAL, VERTICAL, expand


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

    def test_a_vertical_bar_mirrors_left_to_right_within_its_reach(self):
        bar = Bar(VERTICAL, 5, col=7, row=4)
        self.assertEqual(bar.mirror(4, 3), (10, 3))
        self.assertEqual(bar.mirror(10, 6), (4, 6))
        self.assertIsNone(bar.mirror(4, 1), "row 1 is above the bar's reach")
        self.assertIsNone(bar.mirror(4, 7), "row 7 is below the bar's reach")
        self.assertIsNone(bar.mirror(7, 4), "a cell ON the bar has no twin")

    def test_a_horizontal_bar_mirrors_top_to_bottom(self):
        bar = Bar(HORIZONTAL, 3, col=5, row=8)
        self.assertEqual(bar.mirror(5, 6), (5, 10))
        self.assertEqual(bar.mirror(4, 9), (4, 7))
        self.assertIsNone(bar.mirror(3, 6), "column 3 is outside a 3-long bar at 5")
        self.assertIsNone(bar.mirror(5, 8))

    def test_length_is_clamped_and_orientation_checked(self):
        self.assertEqual(Bar(VERTICAL, 0, 0, 0).length, symmetry.MIN_LENGTH)
        self.assertEqual(Bar(VERTICAL, 999, 0, 0).length, symmetry.MAX_LENGTH)
        with self.assertRaises(ValueError):
            Bar("diagonal", 5, 0, 0)

    def test_moved_to_keeps_shape_and_changes_place(self):
        moved = Bar(HORIZONTAL, 6, 1, 1).moved_to(9, 9)
        self.assertEqual((moved.orientation, moved.length, moved.col, moved.row),
                         (HORIZONTAL, 6, 9, 9))


class ExpandTest(unittest.TestCase):
    def test_no_bar_returns_the_cells_unchanged(self):
        self.assertEqual(expand(None, [(1, 1), (2, 2)]), [(1, 1), (2, 2)])

    def test_twins_follow_their_originals_and_are_not_duplicated(self):
        bar = Bar(VERTICAL, 5, col=7, row=4)
        cells = [(6, 4), (7, 4), (8, 4)]  # (8,4) is (6,4)'s twin already
        self.assertEqual(expand(bar, cells), [(6, 4), (8, 4), (7, 4)])

    def test_cells_beyond_the_bar_are_painted_alone(self):
        bar = Bar(VERTICAL, 1, col=7, row=4)  # one cell long: only row 4 mirrors
        self.assertEqual(expand(bar, [(3, 4), (3, 5)]), [(3, 4), (11, 4), (3, 5)])


if __name__ == "__main__":
    unittest.main()
