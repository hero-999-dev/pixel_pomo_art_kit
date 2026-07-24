import unittest

from art_kit.model import Drawing, Palette

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
