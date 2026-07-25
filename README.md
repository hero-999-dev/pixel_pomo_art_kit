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
  Duplicate, Export PNG…, Export JPG…, Export engine sprite…, Rename…,
  Species…, Size…, Delete. Clicking a row opens it in the canvas.
  `+ NEW DRAWING` at the bottom starts a blank 32x32 drawing — room for the
  trees and pets that are coming, not just 16-wide flowers; `Size…` changes
  its width/height (engine flowers need width 16), and `Species…` names a
  brand-new flower so it can export as an engine sprite.
- **Canvas.** The grid fills the middle: selecting a drawing auto-zooms it
  to fit the pane. Click or drag to paint with the current tool and ink —
  fast drags are interpolated, so a quick stroke is a continuous line, not a
  trail of dots, and **what you paint is exactly what appears**: one click,
  one square. **Right-click is an eyedropper**: the cell under the cursor
  becomes the ink. The mouse wheel (or `+`/`-`) zooms from 4x to 48x, with
  scrollbars so the edge pixels stay reachable at any zoom; empty cells show
  a checkerboard; grid lines appear once each cell is 8px or larger. Beside
  it sit two live previews, both rendered through the same engine code as
  every export: one at 1x actual size, and one at a fixed "squint test"
  scale — the same distance check the project already requires before a
  sprite is accepted, so you don't have to eyeball it yourself.
- **Tools.** DRAW / ERASE / FILL (flood fill from the pressed cell, one undo
  step), UNDO / REDO, an **ink swatch** showing exactly what the next click
  will paint, thirty ready-made colours, and below them the **full colour
  panel**, embedded the way a phone app does it — a hue strip over a
  shade square, click or drag to pick any colour. No popups, no extra
  windows, no palette jargon.

Keyboard: `Ctrl+Z` undo, `Ctrl+Y` / `Ctrl+Shift+Z` redo, `e` / `b` / `f`
erase/draw/fill, `+` / `-` zoom. Right-click on the canvas picks up the
colour under the cursor. The title bar always names the drawing you are
editing.

## Exports, and which one to hand back to the developer

| Export | What it produces | Use it for |
|---|---|---|
| **Export PNG…** | An RGBA PNG at 16x (the export dialog just asks where to save it; `export_png`/`export_jpg` underneath both take a `scale` argument if you're driving them from a script instead of the window). | Sharing a look, a reference — anything that isn't shipping straight into the game. |
| **Export JPG…** | The same render flattened onto white (JPEG has no alpha channel, so transparency has to become some solid colour — the underlying `export_jpg` takes the background as an explicit argument, the window just always calls it with the white default today). | Quick previews outside the game; never for shipping, since the transparency is gone. |
| **Export engine sprite…** | The actual file(s) the game loads: `flower_<species>_<model>.png` at the engine's real x16 scale, through the same upscale/write code the shipped assets were made with. Exporting a drawing's model 0 also writes `flower_<species>.png`, the shop thumbnail. Refuses a drawing that isn't exactly 16 cells wide, or has no species set. The save dialog opens on a repo-local `exports/` folder — never the game's asset tree, which is read-only to this app — behind a confirmation that names exactly what it will overwrite. | **Hand this back to the developer.** Drop the output into the game's `assets/objects/` and the artwork ships. |
## Sending a drawing back (for the artist)

Two easy ways, pick either:

- **The lossless one (best):** send the drawing's `.json` file from the
  `library\` folder next to the app — it is the drawing itself, nothing lost.
- **The visual one:** `⋮ → Export PNG…` and send that.

If the drawing is a 16-wide flower with its species set, `⋮ → Export engine
sprite…` also works and produces the exact files the game loads. Everything
else — palettes, letter grids, engine source entries — is the developer's
problem, on purpose: **you draw with real colours, one click one square, and
send it; the developer converts it for the engine behind the scenes.**

## Developer notes: letters and palettes (not the artist's job)

The engine stores each flower as a letter grid (`_FLOWER_BLOOMS`) plus five
tones (`_FLOWER_PALS`). The 24 imported flowers arrive in that form and
render with the engine's automatic rims — which is also why they must keep
looking exactly as shipped. Anything the artist paints is a raw colour on
top; raw cells render as-is, with no rim magic (the rose already ships
exactly this way, byte-identically).

Converting a finished raw drawing into engine source, when wanted, happens
in code, not in the artist's window: `engine_io.export_grid_literal()` and
`engine_io.export_palette_literal()` produce the two paste-ready lines for a
letter drawing, and `store.load()` gives you the raw cells to map onto
letters first. Engine sprites are always 16 cells wide — `Export engine
sprite…` checks that before writing anything.

## Tests

81 tests, all passing:

```
python -m unittest discover -s tests -v
```

See `TESTING.md` for what each test file covers and what is deliberately not
covered.
