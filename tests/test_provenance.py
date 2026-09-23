"""The artist's mark on exports (#v2.8.0, sixth test pass): the name on the
picture, the name inside the file, and the record of every export."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from art_kit import engine_io, provenance
from art_kit.model import Drawing, Palette

WHEN = datetime(2026, 9, 23, 10, 15, 3, tzinfo=timezone(timedelta(hours=2)))


def _mark(**kw):
    kw.setdefault("title", "Begonia 1")
    kw.setdefault("artist", "Mir")
    kw.setdefault("when", WHEN)
    return provenance.Mark(**kw)


def _drawing(w=16, h=16, artist="Mir"):
    d = Drawing.blank(w, h, Palette(d="2E2E2E", m="6E6E6E", l="B0B0B0", centre="F2C94C",
                                    rim="1A1A1A"), artist=artist)
    for c in range(w):
        d.paint(c, h // 2, (200, 40, 40, 255))
    d.name = "Begonia 1"
    return d


class PixelLettersTest(unittest.TestCase):
    def test_every_letter_and_digit_has_a_glyph_in_the_line(self):
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789©":
            width, lit = provenance.text_bits(ch)
            self.assertTrue(lit, ch)
            self.assertTrue(all(0 <= x < width and 0 <= y < provenance.LINE for x, y in lit), ch)

    def test_letters_sit_in_the_middle_five_rows_and_the_copyright_sign_fills_seven(self):
        _w, lit = provenance.text_bits("H")
        self.assertEqual({y for _x, y in lit}, {1, 2, 3, 4, 5})
        _w, lit = provenance.text_bits("©")
        self.assertEqual({y for _x, y in lit}, set(range(7)))

    def test_names_are_folded_to_letters_the_font_has(self):
        self.assertEqual(provenance.fold("Şükrü Ilıcalı"), "Sukru Ilicali")
        self.assertEqual(provenance.fold("Łukasz Gößner"), "Lukasz Gossner")
        self.assertEqual(provenance.pixel_name("  mir   the 2nd! "), "MIR THE 2ND")
        self.assertEqual(provenance.pixel_name("山田"), "", "nothing the font can draw")


class SignatureTest(unittest.TestCase):
    def test_nothing_is_drawn_without_an_artist_or_a_choice(self):
        self.assertEqual(provenance.stamp(256, 256, _mark(signature=provenance.NONE)), [])
        self.assertEqual(provenance.stamp(256, 256, _mark(artist="", signature="corner")), [])
        self.assertEqual(provenance.stamp(256, 256, None), [])

    def test_the_corner_signature_is_small_legible_and_in_the_bottom_right(self):
        rects = provenance.stamp(256, 256, _mark(signature=provenance.CORNER))
        self.assertTrue(rects)
        x0 = min(x for x, _y, _w, _h, _c in rects)
        y0 = min(y for _x, y, _w, _h, _c in rects)
        x1 = max(x + w for x, _y, w, _h, _c in rects)
        y1 = max(y + h for _x, y, _w, h, _c in rects)
        self.assertGreater(x0, 128, "right half")
        self.assertGreater(y0, 200, "bottom")
        self.assertLessEqual((x1, y1), (256, 256))
        self.assertLessEqual(x1 - x0, 256 * 0.45, "a corner, not a banner")
        colours = {c for *_xywh, c in rects}
        self.assertEqual(colours, {provenance.CORNER_INK, provenance.CORNER_RIM})

    def test_the_watermark_crosses_the_whole_picture(self):
        rects = provenance.stamp(2560, 960, _mark(signature=provenance.WATERMARK))
        rows = {y * 3 // 960 for _x, y, _w, _h, _c in rects}
        cols = {x * 3 // 2560 for x, _y, _w, _h, _c in rects}
        self.assertEqual((rows, cols), ({0, 1, 2}, {0, 1, 2}), "top to bottom, side to side")
        self.assertTrue(all(0 <= x and x + w <= 2560 and 0 <= y and y + h <= 960
                            for x, y, w, h, _c in rects), "cut to the picture")

    def test_the_corner_and_the_watermark_together(self):
        """"ikisini de yapma olsun": both marks, the corner laid last, on top."""
        self.assertEqual(provenance.parts(provenance.BOTH), {"corner", "watermark"})
        self.assertEqual(provenance.signature_of(True, True), provenance.BOTH)
        self.assertEqual(provenance.signature_of(False, True), provenance.WATERMARK)
        self.assertEqual(provenance.signature_of(False, False), provenance.NONE)
        corner = provenance.stamp(512, 512, _mark(signature=provenance.CORNER))
        mark = _mark(signature=provenance.WATERMARK)
        faint = provenance.stamp(512, 512, mark)
        both = provenance.stamp(512, 512, _mark(signature=provenance.BOTH))
        self.assertEqual(both, faint + corner, "the watermark first, the corner over it")

    def test_a_picture_too_small_for_letters_is_left_alone(self):
        self.assertEqual(provenance.stamp(8, 8, _mark(signature=provenance.CORNER)), [])

    def test_a_long_name_falls_back_to_the_short_form(self):
        mark = _mark(artist="Bartholomew Montgomery-Smith", signature=provenance.CORNER)
        rects = provenance.stamp(128, 128, mark)
        self.assertTrue(rects)
        width = max(x + w for x, _y, w, _h, _c in rects) - min(x for x, *_r in rects)
        long_w, _lit = provenance.text_bits("© 2026 BARTHOLOMEW MONTGOMERY-SMITH")
        self.assertLess(width, long_w, "a shorter form, to make room")

    def test_apply_touches_only_the_stamped_pixels_even_on_shared_rows(self):
        row = [(10, 20, 30, 255)] * 64
        grid = [row] * 64                  # one row object, as an upscale can hand back
        rects = [(60, 60, 2, 2, (255, 255, 255, 255))]
        out = provenance.apply(grid, rects)
        self.assertEqual(out[60][60], (255, 255, 255, 255))
        self.assertEqual(out[0][60], (10, 20, 30, 255), "the shared row was copied first")
        self.assertEqual(grid[60][60], (10, 20, 30, 255), "and the input left as it was")

    def test_over_blends_straight_alpha(self):
        self.assertEqual(provenance.over((255, 0, 0, 255), (0, 0, 255, 255)), (255, 0, 0, 255))
        self.assertEqual(provenance.over((255, 0, 0, 128), None), (255, 0, 0, 128))
        r, g, b, a = provenance.over((255, 255, 255, 128), (0, 0, 0, 255))
        self.assertEqual(a, 255)
        self.assertTrue(126 <= r <= 130 and r == g == b)


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_a_png_carries_the_name_and_keeps_its_pixels(self):
        from PIL import Image
        d = _drawing()
        plain = engine_io.export_png(d, self.dir / "plain.png")
        marked = engine_io.export_png(d, self.dir / "marked.png", mark=_mark())
        with Image.open(plain) as a, Image.open(marked) as b:
            self.assertEqual(a.convert("RGBA").tobytes(), b.convert("RGBA").tobytes(),
                             "no signature asked: the same picture")
            self.assertEqual(a.text, {}, "no mark: no text, as before")
            text = dict(b.text)
        self.assertEqual(text["Title"], "Begonia 1")
        self.assertEqual(text["Author"], "Mir")
        self.assertEqual(text["Copyright"], "© 2026 Mir. All rights reserved.")
        self.assertTrue(text["Software"].startswith("Pixel Pomo Art Kit"))
        xmp = text["XML:com.adobe.xmp"]
        self.assertIn("<rdf:li>Mir</rdf:li>", xmp)
        self.assertIn("<xmpRights:Marked>True</xmpRights:Marked>", xmp)

    def test_a_name_latin_1_cannot_hold_goes_in_as_utf8(self):
        from PIL import Image
        path = engine_io.export_png(_drawing(), self.dir / "l.png", mark=_mark(artist="Łucja"))
        with Image.open(path) as img:
            self.assertEqual(img.text["Author"], "Łucja")

    def test_with_the_name_off_only_what_made_it_is_written(self):
        """"şu uygulamadan yapıldı diye propertylere ekleyelim": the app is
        named whatever the artist chose about their own name."""
        from PIL import Image
        path = engine_io.export_png(_drawing(), self.dir / "o.png", mark=_mark(metadata=False))
        with Image.open(path) as img:
            self.assertEqual(dict(img.text), {"Software": provenance.SOFTWARE,
                                              "Comment": provenance.MADE_WITH})

    def test_every_format_says_what_made_it(self):
        from PIL import Image
        png = engine_io.export_png(_drawing(), self.dir / "m.png", mark=_mark())
        with Image.open(png) as img:
            self.assertEqual(img.text["Comment"], provenance.MADE_WITH)
            self.assertIn(provenance.MADE_WITH, img.text["Description"])
        jpg = engine_io.export_jpg(_drawing(), self.dir / "m.jpg", mark=_mark(metadata=False))
        with Image.open(jpg) as img:
            exif = img.getexif()
        self.assertTrue(exif[0x0131].startswith("Pixel Pomo Art Kit"), "Explorer's Program name")
        self.assertIn(provenance.MADE_WITH,
                      bytes(exif[0x9C9C]).decode("utf-16-le"), "Explorer's Comments")
        self.assertNotIn(0x013B, exif, "no artist asked in: none written")
        svg = engine_io.export_svg(_drawing(), self.dir / "m.svg", mark=_mark(metadata=False))
        text = svg.read_text(encoding="utf-8")
        self.assertIn(f"<!-- {provenance.MADE_WITH}", text)
        self.assertNotIn("<metadata>", text)

    def test_a_jpeg_carries_exif_xmp_and_a_comment(self):
        from PIL import Image
        path = engine_io.export_jpg(_drawing(), self.dir / "m.jpg", mark=_mark(artist="Mır"))
        with Image.open(path) as img:
            exif = img.getexif()
            comment = img.info.get("comment", b"")
        self.assertEqual(exif[0x013B], "Mir", "ASCII fields folded, not '?'")
        self.assertIn("Copyright 2026", exif[0x8298])
        self.assertEqual(bytes(exif[0x9C9D]).decode("utf-16-le").rstrip("\0"), "Mır",
                         "Windows' own field keeps the name as written")
        data = path.read_bytes()
        self.assertIn(b"http://ns.adobe.com/xap/1.0/\x00", data)
        self.assertIn("Mır".encode("utf-8"), data)
        self.assertIn(b"Begonia 1", comment)

    def test_an_svg_opens_with_its_title_and_ends_with_its_signature(self):
        path = engine_io.export_svg(_drawing(), self.dir / "m.svg",
                                    mark=_mark(signature=provenance.CORNER))
        text = path.read_text(encoding="utf-8")
        self.assertIn("<title>Begonia 1</title>", text)
        self.assertIn("<dc:creator><cc:Agent><dc:title>Mir</dc:title>", text)
        self.assertLess(text.index('<g id="signature">'), text.index("</svg>"))
        import xml.dom.minidom
        xml.dom.minidom.parseString(text)          # still well-formed XML

    def test_the_signature_is_in_the_file_s_own_pixels(self):
        from PIL import Image
        d = _drawing()
        mark = _mark(signature=provenance.CORNER)
        path = engine_io.export_png(d, self.dir / "s.png", mark=mark)
        self.assertTrue(mark.signed)
        with Image.open(path) as opened:
            img = opened.convert("RGBA")
        self.assertEqual(img.getpixel((5, 5))[3], 0, "the empty top-left stays empty")
        corner = img.crop((128, 200, 256, 256)).tobytes()
        ink = bytes(provenance.CORNER_INK[:3])
        self.assertTrue(any(corner[i:i + 3] == ink for i in range(0, len(corner), 4)),
                        "the letters' own colour, in the corner")


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.log = self.dir / provenance.LOG_NAME

    def test_every_export_is_a_line_chained_to_the_one_before(self):
        d = _drawing()
        first = engine_io.export_png(d, self.dir / "a.png", mark=_mark())
        second = engine_io.export_png(d, self.dir / "b.png")
        e1 = provenance.record(self.log, first, "png", d, _mark(drawing_id="ab" * 32))
        e2 = provenance.record(self.log, second, "engine", d)
        self.assertEqual(e1["prev"], "", "the first has nothing before it")
        lines = self.log.read_bytes().split(b"\n")
        self.assertEqual(e2["prev"], provenance.digest(lines[0]))
        self.assertEqual(e1["sha256"], provenance.digest(first.read_bytes()))
        self.assertEqual((e1["artist"], e1["cells"], e1["drawing_sha256"]), ("Mir", [16, 16], "ab" * 32))
        self.assertEqual(provenance.verify(self.log), (2, 0))

    def test_an_edit_in_the_middle_breaks_the_chain_where_it_was_made(self):
        d = _drawing()
        path = engine_io.export_png(d, self.dir / "a.png")
        for _ in range(3):
            provenance.record(self.log, path, "png", d)
        lines = self.log.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["artist"] = "Somebody Else"
        lines[0] = json.dumps(entry, ensure_ascii=False)
        self.log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertEqual(provenance.verify(self.log), (3, 2))


if __name__ == "__main__":
    unittest.main()
