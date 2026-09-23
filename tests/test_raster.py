import unittest

from art_kit import raster


class ShrinkTest(unittest.TestCase):
    """#v2.8.0: thumbnails and previews of drawings bigger than their box."""

    def test_a_grid_that_fits_comes_back_untouched(self):
        grid = [[(1, 1, 1, 255)] * 64 for _ in range(40)]
        small, n = raster.shrink(grid, 64)
        self.assertIs(small, grid)
        self.assertEqual(n, 1)

    def test_a_bigger_one_is_averaged_down_to_fit(self):
        grid = [[(c % 200, r, 0, 255) for c in range(300)] for r in range(150)]
        small, n = raster.shrink(grid, 64)
        self.assertEqual(n, 5)                                  # 300 / 64, rounded up
        self.assertEqual((len(small[0]), len(small)), (60, 30))
        # the block of columns 10..14 and rows 5..9 averages to 12, 7
        self.assertEqual(small[1][2], (12, 7, 0, 255))
        self.assertLessEqual(max(len(small[0]), len(small)), 64)


class ReduceTest(unittest.TestCase):
    """#v2.8.0, third test pass: "bazı kısımlar aktarılmamış". Keeping every
    n-th cell dropped a line one cell thin whenever it fell between two
    samples; averaged, every cell counts."""

    def setUp(self):
        import random
        rnd = random.Random(5)
        self.grid = [[None] * 600 for _ in range(600)]
        for r in range(600):
            self.grid[r][37] = (255, 0, 0, 255)               # a line one cell thin
        for _ in range(3000):
            self.grid[rnd.randrange(600)][rnd.randrange(600)] = (
                rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255)

    def test_a_one_cell_line_survives_a_tenth_of_the_size(self):
        small = raster.reduce(self.grid, 10)
        self.assertEqual((len(small[0]), len(small)), (60, 60))
        self.assertTrue(all(row[3][3] > 0 for row in small), "the line is in every row")
        self.assertTrue(all(row[3][0] > row[3][1] for row in small), "and it is red")
        nearest = [row[::10] for row in self.grid[::10]]
        self.assertFalse(any(row[3] for row in nearest), "the old sampling lost it")

    def test_a_half_covered_block_is_half_as_opaque_not_darker(self):
        grid = [[(200, 100, 0, 255), None], [(200, 100, 0, 255), None]]
        self.assertEqual(raster._reduce_by_hand(grid, 2), [[(200, 100, 0, 128)]])
        # Pillow's premultiplied 8-bit arithmetic may land one step off
        [[px]] = raster.reduce(grid, 2)
        for got, want in zip(px, (200, 100, 0, 128)):
            self.assertLessEqual(abs(got - want), 1)

    def test_a_block_cut_short_by_the_edge_averages_what_it_has(self):
        grid = [[(10, 20, 30, 255)] * 7 for _ in range(5)]
        small = raster.reduce(grid, 3)
        self.assertEqual((len(small[0]), len(small)), (3, 2))
        self.assertEqual(small[-1][-1], (10, 20, 30, 255))

    def test_with_or_without_pillow_the_picture_is_the_same(self):
        """Pillow averages in 8 bits, premultiplied, so a nearly transparent
        pixel's colour differs - by nothing anyone sees once it is laid on
        the background, which is how every one of them is shown."""
        bg = (26, 36, 32, 255)
        a = raster.on_colour(raster.reduce(self.grid, 10), bg)
        b = raster.on_colour(raster._reduce_by_hand(self.grid, 10), bg)
        worst = max(abs(x - y) for ra, rb in zip(a, b) for pa, pb in zip(ra, rb)
                    for x, y in zip(pa, pb))
        self.assertLessEqual(worst, 2)

    def test_laying_on_a_colour_mixes_a_partly_covered_pixel(self):
        bg = (0, 0, 0, 255)
        self.assertEqual(raster.over((200, 100, 50, 255), bg), (200, 100, 50, 255))
        self.assertEqual(raster.over((200, 100, 50, 0), bg), bg)
        self.assertEqual(raster.over(None, bg), bg)
        self.assertEqual(raster.over((200, 100, 50, 51), bg), (40, 20, 10, 255))


class PngBytesTest(unittest.TestCase):
    """#v2.8.0: rows without a None are packed in one call. The PNG must be
    the one the pixel-by-pixel build always wrote."""

    @staticmethod
    def _one_pixel_at_a_time(grid):
        import struct
        import zlib
        raw = bytearray()
        for row in grid:
            raw.append(0)
            for px in row:
                raw += b"\x00\x00\x00\x00" if not px or px[3] == 0 else bytes(px[:4])

        def chunk(tag, data):
            body = struct.pack(">I", len(data)) + tag + data
            return body + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", len(grid[0]), len(grid), 8, 6, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 1)) + chunk(b"IEND", b""))

    def test_the_bytes_are_the_same_either_way(self):
        clear, red, teal = (0, 0, 0, 0), (200, 30, 40, 255), (20, 180, 170, 255)
        for grid in ([[red, clear, teal], [clear, clear, red]],     # a render: packed
                     [[None, red, None], [teal, None, clear]],      # the icon: by pixel
                     [[red] * 900 for _ in range(3)]):              # a wide opaque tile
            self.assertEqual(raster.png_bytes(grid), self._one_pixel_at_a_time(grid))
