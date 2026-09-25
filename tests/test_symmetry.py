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


class ReverseTest(unittest.TestCase):
    """REVERSE (#v2.9.0), in STICK's place: the selection turned over and
    copied beside itself."""

    BLOCK = [["a", "b", None],
             ["c", None, "d"]]

    def test_across_x_the_rows_swap(self):
        self.assertEqual(symmetry.turned(self.BLOCK, symmetry.AXIS_X),
                         [["c", None, "d"], ["a", "b", None]])

    def test_across_y_the_columns_swap(self):
        self.assertEqual(symmetry.turned(self.BLOCK, symmetry.AXIS_Y),
                         [[None, "b", "a"], ["d", None, "c"]])

    def test_across_both_it_is_turned_half_round(self):
        self.assertEqual(symmetry.turned(self.BLOCK, symmetry.AXIS_XY),
                         [["d", None, "c"], [None, "b", "a"]])
        with self.assertRaises(ValueError):
            symmetry.turned(self.BLOCK, "z")

    def test_turning_leaves_the_block_it_was_given_alone(self):
        block = [list(row) for row in self.BLOCK]
        symmetry.turned(block, symmetry.AXIS_XY)
        self.assertEqual(block, self.BLOCK)

    def test_distance_0_is_right_beside_the_selection(self):
        sel = (2, 3, 4, 4)                    # 3 wide, 2 tall
        self.assertEqual(symmetry.reverse_corner(sel, "right", 0, 0), (5, 3))
        self.assertEqual(symmetry.reverse_corner(sel, "left", 0, 0), (-1, 3))
        self.assertEqual(symmetry.reverse_corner(sel, "up", 0, 0), (2, 1))
        self.assertEqual(symmetry.reverse_corner(sel, "down", 0, 0), (2, 5))

    def test_a_distance_leaves_that_many_empty_cells_between(self):
        """"mesafeye 1 seçildi, direkt seçimin yanından değil 1 mesafe uzağından"."""
        self.assertEqual(symmetry.reverse_corner((2, 3, 4, 4), "right", 1, 1), (6, 3))

    def test_a_diagonal_moves_both_ways_by_the_same_distance(self):
        """"sol altı seçtim, 15 yazdım: 15 x ve 15 y sol çaprazda"."""
        self.assertEqual(symmetry.reverse_corner((20, 20, 21, 21), "down_left", 15, 15), (3, 37))

    def test_x_and_y_apart(self):
        """"sağ 5 yukarı 2"."""
        self.assertEqual(symmetry.reverse_corner((10, 10, 11, 11), "up_right", 5, 2), (17, 6))

    def test_a_straight_arrow_ignores_the_other_distance(self):
        self.assertEqual(symmetry.reverse_corner((10, 10, 11, 11), "right", 5, 9), (17, 10))

    def test_distances_are_clamped_and_directions_checked(self):
        self.assertEqual(symmetry.reverse_corner((0, 0, 0, 0), "right", -4, 0), (1, 0))
        self.assertEqual(symmetry.reverse_corner((0, 0, 0, 0), "right", 10 ** 6, 0),
                         (1 + symmetry.MAX_GAP, 0))
        with self.assertRaises(ValueError):
            symmetry.reverse_corner((0, 0, 0, 0), "sideways", 0, 0)

    def test_reverse_copy_stamps_the_turned_block_and_leaves_the_original(self):
        d = Drawing.blank(10, 4, PAL)
        d.paint(0, 0, "d")
        d.paint(1, 0, "m")
        d.paint(4, 0, "l")                    # under the copy, where the block is empty
        col, row, w, h, dropped = symmetry.reverse_copy(d, (0, 0, 2, 0), symmetry.AXIS_Y, "right", 1, 1)
        self.assertEqual((col, row, w, h, dropped), (4, 0, 3, 1, 0))
        self.assertEqual([d.get(c, 0) for c in range(7)], ["d", "m", None, None, "l", "m", "d"],
                         "turned over, one cell away; an empty cell of the block wipes nothing")

    def test_what_falls_off_the_drawing_is_counted(self):
        d = Drawing.blank(4, 4, PAL)
        d.paint(0, 0, "d")
        d.paint(1, 0, "m")
        *_, dropped = symmetry.reverse_copy(d, (0, 0, 1, 0), symmetry.AXIS_Y, "left", 0, 0)
        self.assertEqual(dropped, 2)
        *_, dropped = symmetry.reverse_copy(d, (0, 0, 1, 0), symmetry.AXIS_Y, "right", 1, 0)
        self.assertEqual(dropped, 1, "column 4 is past the edge of a 4-wide drawing")
        self.assertEqual(d.get(3, 0), "m")


if __name__ == "__main__":
    unittest.main()
