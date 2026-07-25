# Pixel Pomo Art Kit

A Windows desktop pixel-art editor for drawing and editing the flower sprites
that grow in Pixel Pomo's garden. It is not a general-purpose pixel editor:
the document format, the palette, and the render path are all borrowed
directly from the game's own sprite generator (`gen_objects.py`), so a flower
drawn or edited here comes back out **byte-for-byte identical** to the PNG the
game actually ships — because the live preview and every export all run the
game's own compositing code, not a reimplementation of it.

## Running it

**Just want to draw?** Download `PixelPomoArtKit-windows.zip` from the latest
[Release](../../releases/latest), unzip it, and run `PixelPomoArtKit.exe` — no
Python needed, and it carries its own copy of the sprite generator so it works
on any Windows machine. (The exe is unsigned, so Windows SmartScreen may say
"Windows protected your PC" the first time: *More info -> Run anyway*.) It keeps
`library/` and `exports/` folders next to the exe.

To run from source instead, from the repository root:

```
python -m art_kit
```

Requirements:
- Python 3 with `tkinter` (part of the standard Windows installer).
- [Pillow](https://pypi.org/project/Pillow/) (`pip install Pillow`) — needed
  for `Export JPG…` and by a couple of tests that inspect PNG/JPG output.
  Plain PNG and engine-sprite export don't need it: the generator writes PNG
  bytes itself, standard library only.
- A checkout of the Pixel Pomo game containing `flutter/tools/gen_objects.py`.
  The default location is `C:\Users\claude\pixel_pomo\flutter\tools`; point
  the `PIXEL_POMO_TOOLS` environment variable at a different `tools` folder
  to use another checkout.

On first run the app creates a `library/` folder next to `art_kit/` and seeds
it with the 24 flowers the game already ships (12 species, 2 hand-authored
models each), read live from `gen_objects.py` — not copied in. Every drawing
is one JSON file in `library/`: plain, readable text, safe to open, diff, or
hand-edit if the app ever writes something wrong. The first time a session
touches a drawing, the file it started from is kept as `<name>.json.bak` —
undo history dies with the window, but "how it looked when I opened the app
today" survives next to it.

## The window

Three panes, left to right:

- **Library.** A scrollable list, one row per drawing: a small thumbnail
  (rendered the same way the canvas is), the drawing's name, and a `⋮` menu —
  Duplicate, Export PNG…, Export JPG…, Export engine sprite…, Copy grid
  literal, Copy palette literal, Rename…, Species…, Rows…, Delete. Clicking a
  row opens it in the canvas. `+ NEW DRAWING` at the bottom starts a blank
  16-wide drawing, carrying over the species and palette of whatever is
  currently selected; `Rows…` grows or crops it (width is the engine's fixed
  16), and `Species…` names a brand-new flower so it can export as an engine
  sprite.
- **Canvas.** Click or drag to paint with the current tool and ink colour —
  fast drags are interpolated, so a quick stroke is a continuous line, not a
  trail of dots. **Right-click is an eyedropper**: the cell under the cursor
  becomes the ink, which is how you continue in the same tone when the eye
  can't tell `d` from `m` from `l`. The mouse wheel (or `+`/`-`) zooms from
  4x to 48x, with scrollbars so the edge pixels stay reachable at any zoom;
  empty cells show a checkerboard; grid lines appear once each cell is 8px
  or larger. Beside it sit two live previews, both rendered through the same
  engine code as every export: one at 1x actual size, and one at a fixed
  "squint test" scale — the same distance check the project already requires
  before a sprite is accepted, so you don't have to eyeball it yourself.
- **Tools.** DRAW / ERASE / FILL (flood fill from the pressed cell, one undo
  step), a **MIRROR X** toggle that paints both halves at once — flowers are
  mostly symmetric, so half the clicks — UNDO / REDO, an **ink swatch**
  showing exactly what the next click will paint, the nine palette-letter
  slots (dark, mid, light, centre, bloom seam, stem, leaf, vein, plant seam —
  coloured from the open drawing's own palette, the active one held down;
  **right-click a slot to change that colour** for the whole drawing, which
  is how a new species gets its own tones), a row of ten ready-made colours
  from Pixel Pomo's own theme palette, and a `PICK COLOUR…` button for
  anything outside the palette.

Keyboard: `Ctrl+Z` undo, `Ctrl+Y` / `Ctrl+Shift+Z` redo, `e` / `b` / `f`
erase/draw/fill, `x` mirror, `+` / `-` zoom. Right-click on the canvas picks
up the colour under the cursor. The title bar always names the drawing you
are editing.

## Exports, and which one to hand back to the developer

| Export | What it produces | Use it for |
|---|---|---|
| **Export PNG…** | An RGBA PNG at 16x (the export dialog just asks where to save it; `export_png`/`export_jpg` underneath both take a `scale` argument if you're driving them from a script instead of the window). | Sharing a look, a reference — anything that isn't shipping straight into the game. |
| **Export JPG…** | The same render flattened onto white (JPEG has no alpha channel, so transparency has to become some solid colour — the underlying `export_jpg` takes the background as an explicit argument, the window just always calls it with the white default today). | Quick previews outside the game; never for shipping, since the transparency is gone. |
| **Export engine sprite…** | The actual file(s) the game loads: `flower_<species>_<model>.png` at the engine's real x16 scale, through the same upscale/write code the shipped assets were made with. Exporting a drawing's model 0 also writes `flower_<species>.png`, the shop thumbnail. Refuses a drawing that isn't exactly 16 cells wide, or has no species set. The save dialog opens on a repo-local `exports/` folder — never the game's asset tree, which is read-only to this app — behind a confirmation that names exactly what it will overwrite. | **Hand this back to the developer.** Drop the output into the game's `assets/objects/` and the artwork ships. |
| **Copy grid literal** | The drawing's rows as Python source text, on the clipboard, ready to paste into `_FLOWER_BLOOMS` in `gen_objects.py`. Refuses a drawing that has any raw-colour cell in it — see below. | **Also hand this to the developer**, whenever the drawing is (or should stay) a letter-grid flower, so the engine's own source of truth matches what shipped. |
| **Copy palette literal** | The drawing's five tones as a `_FLOWER_PALS` line, on the clipboard. Refuses a drawing with no species. | **The other half of the grid literal** — a letter grid means nothing to the engine without its palette line. |

## Handing a NEW flower to the developer

The round trip for a species the game has never seen:

1. `+ NEW DRAWING`, then `⋮ → Species…` to give it its engine id (lowercase,
   e.g. `gonca`), and `⋮ → Rows…` if it needs more or fewer than 16 rows.
2. Right-click the palette slots to set the new flower's own dark / mid /
   light / centre / rim tones. Stay in palette letters while you draw.
3. Check the 1x and squint previews — that is exactly how the garden will
   draw it.
4. Hand back three things from the `⋮` menu: **Export engine sprite…** (the
   PNGs), **Copy grid literal** (the `_FLOWER_BLOOMS` entry), and **Copy
   palette literal** (the `_FLOWER_PALS` line). The developer pastes the two
   literals into `gen_objects.py` and drops the PNGs into `assets/objects/` —
   at that point the game can regenerate the identical sprite from source.

## The one rule to know before you draw

**Engine sprites are always 16 cells wide.** That's a hard requirement of
`Export engine sprite…`, checked before anything is written.

**A drawing stays "bakeable" back into the game's source only as long as
every cell is a palette letter.** The nine tool-pane slots paint letters; the
`PICK COLOUR…` picker paints a raw RGBA colour instead. The moment one cell
holds a raw colour, the drawing becomes a **pixel** drawing, and
**Copy grid literal** refuses it outright — there is no letter left to write
down for that cell. `Export PNG`, `Export JPG`, and `Export engine sprite`
don't care either way and keep working on a pixel drawing exactly as they do
on a letter one — that is, in fact, exactly how the rose (`gul`) already
ships: it was never a letter grid to begin with, only composited raw pixels,
and it still exports byte-identically. So: stay in letters for as long as you
want the option to hand back a grid literal too; reach for the free colour
picker only once you've accepted this drawing will ship as a PNG/sprite and
nothing else.

## Tests

80 tests, all passing:

```
python -m unittest discover -s tests -v
```

See `TESTING.md` for what each test file covers and what is deliberately not
covered.
