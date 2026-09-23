"""Who made it: on the picture, inside the file, and in a record (#v2.8.0).

"exportlarda artist bookmarkı ayarı istiyorum ... eserlerin çalınmasını
istemem". Of the layers proposed, the artist chose three:

1. **The name inside the file.** Every image export carries its title, its
   artist and a copyright line in the places each format keeps them: PNG
   text chunks plus XMP; JPEG EXIF (Artist, Copyright, and the XPAuthor
   Windows' Properties window reads) plus XMP and a comment; SVG `<title>`,
   `<desc>` and Dublin Core metadata. Invisible, standard, and read by
   Explorer, Photoshop and every serious viewer.
2. **The name on the picture**, when asked for: "© 2026 MIR" in the kit's
   own pixel letters, small in a corner, faint all over (a proof to share), or
   both at once. It is drawn in the file's own pixels, so a screenshot keeps
   it too.
3. **A record of every export**, `export-log.jsonl` beside the library: when,
   which file and its SHA-256, which drawing, whose, how it was marked. Each
   line carries the digest of the one before it, so an edit in the middle of
   the record breaks the chain from there on.

None of it can stop a copy - a picture on a screen can always be drawn
again - and none of it pretends to. It makes the name travel with the file,
makes taking it off a deliberate act (which is the act the law punishes), and
leaves the artist the proof that the work was theirs, and when.

Every image export also says what made it - "Made with Pixel Pomo Art Kit",
as the file's Software / Program name and in its comment - whether or not the
artist's own name goes in (sixth test pass: "şu uygulamadan yapıldı diye
propertylere ekleyelim").

The engine sprite export stays clean on purpose: it is an input to the game's
build, compared pixel for pixel with what the generator makes.
"""
import hashlib
import json
import struct
import unicodedata
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from art_kit.version import VERSION

NONE, CORNER, WATERMARK = "none", "corner", "watermark"
BOTH = "corner+watermark"   # the two are independent: either, neither or both
MODES = (NONE, CORNER, WATERMARK, BOTH)

LOG_NAME = "export-log.jsonl"
SOFTWARE = f"Pixel Pomo Art Kit {VERSION}"
MADE_WITH = "Made with Pixel Pomo Art Kit"


def parts(signature):
    """The set of marks a signature asks for: {"corner"}, {"watermark"}, both
    or neither."""
    return {p for p in str(signature or "").split("+") if p in (CORNER, WATERMARK)}


def signature_of(corner, watermark):
    """The one string that names a choice of marks - how it is kept."""
    return {(False, False): NONE, (True, False): CORNER,
            (False, True): WATERMARK, (True, True): BOTH}[(bool(corner), bool(watermark))]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class Mark:
    """What one export says about where it came from."""
    title: str = ""
    artist: str = ""
    signature: str = NONE   # the name ON the picture: NONE, CORNER, WATERMARK or BOTH
    metadata: bool = True   # the name INSIDE the file
    when: datetime = field(default_factory=lambda: datetime.now().astimezone())
    export_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    drawing_id: str = ""    # the SHA-256 of the drawing's own file, when known
    signed: bool = False    # set by the exporter: did a signature actually fit?

    @property
    def year(self):
        return self.when.year

    def notice(self):
        """"© 2026 Mir", or "" with no artist to name."""
        return f"© {self.year} {self.artist}" if self.artist else ""

    def rights(self):
        return f"{self.notice()}. All rights reserved." if self.artist else ""

    def signs(self):
        """Is a signature asked for, with a name the pixel letters can draw?"""
        return bool(parts(self.signature)) and bool(pixel_name(self.artist))


# ---- plain letters ------------------------------------------------------------
_FOLD = str.maketrans({"ı": "i", "İ": "I", "ł": "l", "Ł": "L",
                       "ß": "ss", "ẞ": "SS", "æ": "ae", "Æ": "AE",
                       "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
                       "œ": "oe", "Œ": "OE", "þ": "th", "Þ": "TH"})


def fold(text):
    """`text` in plain ASCII - Ş to S, ı to i, ł to l - for the places that
    hold nothing else: the pixel letters and EXIF's ASCII fields. The full
    name still goes wherever Unicode can: XMP, PNG iTXt, XPAuthor, SVG."""
    text = unicodedata.normalize("NFKD", str(text).translate(_FOLD))
    kept = "".join(c for c in text if not unicodedata.combining(c))
    return kept.encode("ascii", "ignore").decode("ascii")


def pixel_name(artist):
    """The artist's name as the pixel letters can draw it: capitals, one
    space between words, and nothing the font has no letter for."""
    words = fold(artist).upper().split()
    return " ".join("".join(c for c in w if c in _GLYPHS) for w in words).strip()


# ---- the pixel letters ----------------------------------------------------------
# Five rows, each letter as narrow as it can be and still read: only M, N
# and W need more than three columns. The © is seven rows - a ring round a
# c does not fit in five - so a line is seven, the letters in its middle five.
LINE = 7
_GLYPHS = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"), "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"), "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"), "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"), "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"), "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"), "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#"),
    "N": ("#..#", "##.#", "#.##", "#..#", "#..#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."), "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "##.", ".##"), "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."), "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"), "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"), "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    "0": ("###", "#.#", "#.#", "#.#", "###"), "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"), "3": ("##.", "..#", ".#.", "..#", "##."),
    "4": ("#.#", "#.#", "###", "..#", "..#"), "5": ("###", "#..", "##.", "..#", "##."),
    "6": (".##", "#..", "###", "#.#", "###"), "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"), "9": ("###", "#.#", "###", "..#", "##."),
    ".": (".", ".", ".", ".", "#"), "-": ("...", "...", "###", "...", "..."),
    "'": ("#", "#", ".", ".", "."), "&": (".#.", "#.#", ".#.", "#.#", ".##"),
}
_COPYRIGHT = ("..###..", ".#...#.", "#..##.#", "#.#...#", "#..##.#", ".#...#.", "..###..")
_SPACE = 2  # columns, on top of the one every letter is followed by


def text_bits(text):
    """(width, lit): the pixels of `text` on a LINE-row grid, as a set of
    (x, y). Anything the font has no letter for is left out."""
    lit, x = set(), 0
    for ch in text:
        if ch == " ":
            x += _SPACE
            continue
        if ch == "©":
            rows = _COPYRIGHT
        elif ch in _GLYPHS:
            rows = ("",) + _GLYPHS[ch]   # the five rows sit in the middle of seven
        else:
            continue
        for y, row in enumerate(rows):
            lit.update((x + dx, y) for dx, c in enumerate(row) if c == "#")
        x += max(len(r) for r in rows) + 1
    return max(0, x - 1), lit


# ---- the signature on the picture ------------------------------------------------
# Light letters in a dark rim: readable on white, on black, on the art, and
# on nothing at all. The watermark is the same, faint.
CORNER_INK, CORNER_RIM = (255, 255, 255, 235), (24, 24, 24, 190)
WATERMARK_INK, WATERMARK_RIM = (255, 255, 255, 84), (0, 0, 0, 52)


def _forms(mark):
    """The signature, longest first: with the year, without it, the first
    name only, the initials - whichever is the first to fit the picture."""
    name = pixel_name(mark.artist)
    if not name:
        return []
    words = name.split()
    forms = [f"© {mark.year} {name}", f"© {name}", f"© {words[0]}",
             "© " + "".join(w[0] for w in words)]
    return list(dict.fromkeys(forms))


def stamp(width, height, mark):
    """The signature for a `width` x `height` picture, as rectangles
    (x, y, w, h, rgba) to lay over it - [] for none, or none that fits.

    Sized to the picture, not to the drawing's cells: about a twentieth of
    the shorter side for the corner, a little more for the watermark, in
    whole pixels per letter pixel so the letters stay as crisp as the art.
    The long form ("© 2026 MIR") if it fits, else a shorter one (`_forms`).
    Both marks at once lay the watermark first and the corner over it, so
    the corner reads clearly on top of the faint copies."""
    if mark is None or not mark.signs() or width < 1 or height < 1:
        return []
    wanted, forms, out = parts(mark.signature), _forms(mark), []
    if WATERMARK in wanted:
        out += _watermark(width, height, forms)
    if CORNER in wanted:
        out += _corner(width, height, forms)
    return out


def _corner(width, height, forms):
    side = min(width, height)
    for text in forms:
        tw, lit = text_bits(text)
        f = max(1, round(side * 0.05 / LINE))
        while f > 1 and (tw + 2) * f > width * 0.45:
            f -= 1
        w, h = (tw + 2) * f, (LINE + 2) * f   # the rim is one letter pixel all round
        if w > width * 0.6 or h > height * 0.25:
            continue
        margin = max(1, round(side * 0.03))
        return _rects(lit, width - margin - w + f, height - margin - h + f, f,
                      CORNER_INK, CORNER_RIM, width, height)
    return []


def _watermark(width, height, forms):
    side = min(width, height)
    for text in forms:
        tw, lit = text_bits(text)
        f = max(1, round(side * 0.07 / LINE))
        while f > 1 and (tw + 2) * f > width * 0.8:
            f -= 1
        w, h = (tw + 2) * f, (LINE + 2) * f
        if w > width or h > height:
            continue
        # Rows of copies a copy's width apart, every other row shifted half
        # way, so no band of the picture is free of the name - and centred,
        # so the pattern sits evenly rather than hugging the top-left corner.
        step_x, step_y = w * 2, h * 3
        y = ((height - h) % step_y) // 2
        while y > 0:
            y -= step_y
        out, odd = [], False
        while y < height:
            x = ((width - w) % step_x) // 2 - step_x + (w if odd else 0)
            while x < width:
                out += _rects(lit, x + f, y + f, f, WATERMARK_INK, WATERMARK_RIM, width, height)
                x += step_x
            y += step_y
            odd = not odd
        return out
    return []


def _rects(lit, x0, y0, f, ink, rim, width, height):
    """`lit` (letter pixels) at `f` px each with its top-left at (x0, y0):
    the rim first, then the letters, as runs along each row, cut to the
    picture. The rim is the ring AROUND the letters, not under them, so a
    half-transparent letter is not darkened by a rim beneath it."""
    around = {(x + dx, y + dy) for x, y in lit for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - lit
    out = []
    for colour, pixels in ((rim, around), (ink, lit)):
        rows = {}
        for x, y in pixels:
            rows.setdefault(y, []).append(x)
        for y, xs in sorted(rows.items()):
            xs.sort()
            start = prev = xs[0]
            for x in xs[1:] + [None]:
                if x is not None and x == prev + 1:
                    prev = x
                    continue
                cut = _clip(x0 + start * f, y0 + y * f, (prev - start + 1) * f, f, width, height)
                if cut is not None:
                    out.append(cut + (colour,))
                if x is not None:
                    start = prev = x
    return out


def _clip(x, y, w, h, width, height):
    x1, y1 = min(width, x + w), min(height, y + h)
    x, y = max(0, x), max(0, y)
    if x1 <= x or y1 <= y:
        return None
    return (x, y, x1 - x, y1 - y)


def over(src, dst):
    """The pixel `src` laid over `dst`, both straight RGBA (None is empty)."""
    sr, sg, sb, sa = src
    dr, dg, db, da = dst if dst else (0, 0, 0, 0)
    if sa >= 255:
        return (sr, sg, sb, 255)
    k = da * (255 - sa) / 255
    a = sa + k
    if a <= 0:
        return (0, 0, 0, 0)
    return (round((sr * sa + dr * k) / a), round((sg * sa + dg * k) / a),
            round((sb * sa + db * k) / a), round(a))


def apply(grid, rects):
    """`grid` (rows of RGBA) with `rects` laid over it. A row is copied
    before it is touched: an upscale may hand the same row object back for
    every pixel row of a cell."""
    if not rects:
        return grid
    out, copied = list(grid), set()
    for x, y, w, h, rgba in rects:
        for yy in range(y, y + h):
            if yy not in copied:
                out[yy] = list(out[yy])
                copied.add(yy)
            row = out[yy]
            for xx in range(x, x + w):
                row[xx] = over(rgba, row[xx])
    return out


def svg_signature(rects):
    """The same rectangles as SVG, in one group of their own."""
    if not rects:
        return ""
    parts = ['<g id="signature">']
    for x, y, w, h, (r, g, b, a) in rects:
        opacity = "" if a >= 255 else f' fill-opacity="{a / 255:.3f}"'
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                     f'fill="#{r:02x}{g:02x}{b:02x}"{opacity}/>')
    parts.append("</g>")
    return "".join(parts)


# ---- the name inside the file -----------------------------------------------------
def description(mark):
    """"Begonia 1 by Mir - Made with Pixel Pomo Art Kit", as much as is known."""
    who = f"{mark.title} by {mark.artist}" if mark.artist else mark.title
    return " - ".join(p for p in (who.strip(), MADE_WITH) if p)


def text_fields(mark):
    """(keyword, text) pairs, in PNG's own vocabulary of keywords.

    What made the file is always there (Software, and "Made with ..." as the
    comment); the title, the artist and the copyright line only while the
    artist keeps their name in the file (`mark.metadata`)."""
    fields = []
    if mark.metadata:
        fields += [("Title", mark.title)]
        if mark.artist:
            fields += [("Author", mark.artist), ("Copyright", mark.rights())]
        fields += [("Description", description(mark)),
                   ("Creation Time", format_datetime(mark.when))]
    fields += [("Software", SOFTWARE), ("Comment", MADE_WITH)]
    return [(k, v) for k, v in fields if v]


def xmp(mark):
    """The XMP packet: Dublin Core title, creator and rights, marked as
    copyrighted, with the export's own id - the one the export log has."""
    e = escape
    lines = [
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>',
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">',
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
        '  <rdf:Description rdf:about=""',
        '    xmlns:dc="http://purl.org/dc/elements/1.1/"',
        '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"',
        '    xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/"',
        '    xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"',
        '    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">',
        f'   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{e(mark.title)}</rdf:li>'
        f'</rdf:Alt></dc:title>',
        f'   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{e(description(mark))}'
        f'</rdf:li></rdf:Alt></dc:description>',
    ]
    if mark.artist:
        lines += [
            f'   <dc:creator><rdf:Seq><rdf:li>{e(mark.artist)}</rdf:li></rdf:Seq></dc:creator>',
            f'   <dc:rights><rdf:Alt><rdf:li xml:lang="x-default">{e(mark.rights())}</rdf:li>'
            f'</rdf:Alt></dc:rights>',
            '   <xmpRights:Marked>True</xmpRights:Marked>',
            f'   <photoshop:Credit>{e(mark.artist)}</photoshop:Credit>',
        ]
    lines += [
        f'   <xmp:CreatorTool>{e(SOFTWARE)}</xmp:CreatorTool>',
        f'   <xmp:CreateDate>{mark.when.isoformat(timespec="seconds")}</xmp:CreateDate>',
        f'   <xmpMM:InstanceID>xmp.iid:{mark.export_id}</xmpMM:InstanceID>',
    ]
    if mark.drawing_id:
        lines.append(f'   <xmpMM:DocumentID>xmp.did:{mark.drawing_id}</xmpMM:DocumentID>')
    lines += ['  </rdf:Description>', ' </rdf:RDF>', '</x:xmpmeta>', '<?xpacket end="w"?>']
    return "\n".join(lines)


def _png_chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png_text(key, value):
    """tEXt when the text is Latin-1, which is all tEXt may hold; iTXt
    (UTF-8, no compression, no language) for a name that is not."""
    try:
        return _png_chunk(b"tEXt", key.encode("latin-1") + b"\0" + value.encode("latin-1"))
    except UnicodeEncodeError:
        return _png_itxt(key, value)


def _png_itxt(key, value):
    # keyword, 0, compression flag 0, method 0, language "" 0, translated "" 0, text
    return _png_chunk(b"iTXt", key.encode("latin-1") + b"\0\0\0\0\0" + value.encode("utf-8"))


def png_with_metadata(data, mark):
    """PNG bytes with the text chunks - and, with the artist's name in the
    file, the XMP packet - just after IHDR, where readers look first. The
    pixels are not touched."""
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    end = 8 + 12 + struct.unpack(">I", data[8:12])[0]   # length, type, data, crc
    extra = b"".join(_png_text(k, v) for k, v in text_fields(mark))
    if mark.metadata:
        extra += _png_itxt("XML:com.adobe.xmp", xmp(mark))
    return data[:end] + extra + data[end:]


def _xp(text):
    """Windows' own EXIF text (XPAuthor and friends): UTF-16, NUL-ended."""
    return text.encode("utf-16-le") + b"\0\0"


def exif_bytes(mark):
    """EXIF for a JPEG: the ASCII fields every camera tool reads, folded to
    plain letters because that is all they hold, and Windows' UTF-16 ones
    with the name exactly as written. Software - Explorer's "Program name" -
    and the comment are always there; the rest only with the name in the
    file."""
    from PIL import Image
    exif = Image.Exif()
    exif[0x0131] = fold(SOFTWARE)                                   # Software
    if mark.metadata:
        exif[0x0132] = mark.when.strftime("%Y:%m:%d %H:%M:%S")      # DateTime
        if mark.title:
            exif[0x9C9B] = _xp(mark.title)                          # XPTitle
        exif[0x010E] = fold(description(mark))                      # ImageDescription
        if mark.artist:
            exif[0x013B] = fold(mark.artist)                        # Artist
            exif[0x8298] = fold(f"Copyright {mark.year} {mark.artist}. All rights reserved.")
            exif[0x9C9D] = _xp(mark.artist)                         # XPAuthor
    comment = f"{mark.rights()} {MADE_WITH}." if mark.metadata and mark.artist else f"{MADE_WITH}."
    exif[0x9C9C] = _xp(comment)                                     # XPComment
    return exif.tobytes()


def _segment(marker, payload):
    return bytes((0xFF, marker)) + (len(payload) + 2).to_bytes(2, "big") + payload


def jpeg_with_metadata(data, mark):
    """JPEG bytes with a comment - and, with the artist's name in the file,
    XMP (APP1) - after the JFIF and EXIF headers, where readers expect them.
    The picture data is not touched."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    pos = 2
    while pos + 4 <= len(data) and data[pos] == 0xFF and data[pos + 1] in (0xE0, 0xE1):
        pos += 2 + int.from_bytes(data[pos + 2:pos + 4], "big")
    extra = b""
    if mark.metadata:
        packet = b"http://ns.adobe.com/xap/1.0/\x00" + xmp(mark).encode("utf-8")
        extra += _segment(0xE1, packet)
        comment = f"{description(mark)}. {mark.rights()}".strip()
    else:
        comment = MADE_WITH
    extra += _segment(0xFE, comment.encode("utf-8"))
    return data[:pos] + extra + data[pos:]


def svg_metadata(mark):
    """What made it, as a comment, and - with the artist's name in the file -
    `<title>`, `<desc>` and Dublin Core, to open an SVG with."""
    e = escape
    out = [f"<!-- {MADE_WITH} {VERSION} -->"]
    if not mark.metadata:
        return "\n".join(out)
    out.append(f"<title>{e(mark.title)}</title>")
    out.append(f"<desc>{e(' '.join(p for p in (description(mark) + '.', mark.rights()) if p))}</desc>")
    out += ['<metadata>',
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:cc="http://creativecommons.org/ns#">',
            '<cc:Work rdf:about="">',
            f'<dc:title>{e(mark.title)}</dc:title>']
    if mark.artist:
        out += [f'<dc:creator><cc:Agent><dc:title>{e(mark.artist)}</dc:title></cc:Agent></dc:creator>',
                f'<dc:rights><cc:Agent><dc:title>{e(mark.rights())}</dc:title></cc:Agent></dc:rights>']
    out += [f'<dc:date>{mark.when.isoformat(timespec="seconds")}</dc:date>',
            f'<dc:identifier>{mark.export_id}</dc:identifier>',
            f'<dc:source>{e(SOFTWARE)}</dc:source>',
            '</cc:Work>', '</rdf:RDF>', '</metadata>']
    return "\n".join(out)


# ---- the record ----------------------------------------------------------------------
def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(log_path, file_path, kind, drawing=None, mark=None):
    """Write one export down at the end of the log, and return the entry.

    `prev` is the SHA-256 of the line before, so the record is a chain: a
    line edited or taken out afterwards shows as the first link that no
    longer matches (`verify`). One JSON object a line, UTF-8, appended - a
    log from an older kit is read by a newer one, and a crash mid-write can
    cost at most the line being written."""
    path = Path(file_path)
    data = path.read_bytes()
    when = mark.when if mark is not None else datetime.now().astimezone()
    entry = {"time": when.isoformat(timespec="seconds"), "kind": kind, "file": str(path),
             "bytes": len(data), "sha256": digest(data)}
    if drawing is not None:
        entry.update({"drawing": drawing.name, "cells": [drawing.width, drawing.height],
                      "artist": drawing.artist or None})
        if mark is not None and mark.drawing_id:
            entry["drawing_sha256"] = mark.drawing_id
    entry.update({"signature": (mark.signature if mark is not None and mark.signed
                                and mark.signature in MODES else NONE),
                  "metadata": bool(mark is not None and mark.metadata),
                  "export_id": mark.export_id if mark is not None else uuid.uuid4().hex,
                  "kit": VERSION, "prev": _last_line_digest(log_path)})
    line = json.dumps(entry, ensure_ascii=False)
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    return entry


def _last_line_digest(log_path):
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            tail = f.read()
    except OSError:
        return ""
    lines = [line.rstrip(b"\r") for line in tail.split(b"\n") if line.strip()]
    return digest(lines[-1]) if lines else ""


def verify(log_path):
    """(entries, broken): how many lines the log has, and the 1-based number
    of the first whose `prev` does not match the line before it (0 if the
    chain is whole)."""
    lines = [line.rstrip(b"\r") for line in Path(log_path).read_bytes().split(b"\n")
             if line.strip()]
    before = ""
    for n, line in enumerate(lines, 1):
        try:
            prev = json.loads(line).get("prev", "")
        except ValueError:
            return len(lines), n
        if prev != before:
            return len(lines), n
        before = digest(line)
    return len(lines), 0
