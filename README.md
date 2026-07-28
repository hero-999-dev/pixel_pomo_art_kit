# Pixel Pomo Art Kit

A desktop pixel-art editor (Windows and macOS) for drawing and editing the
sprites that grow in Pixel Pomo's garden — flowers and the surrounding forest.
It is not a general-purpose pixel editor:
the document format, the palette, and the render path are all borrowed
directly from the game's own sprite generator (`gen_objects.py`), so a flower
drawn or edited here comes back out **byte-for-byte identical** to the PNG the
game actually ships — because the live preview and every export all run the
game's own compositing code, not a reimplementation of it.

## Running it

**Just want to draw?** Grab the build for your machine from the latest
[Release](../../releases/latest) — no Python needed either way, and both carry
their own copy of the sprite generator, so they work with no game checkout at
all. Each keeps its `library/` and `exports/` folders next to itself.

| | file | notes |
|---|---|---|
| **Windows** | `PixelPomoArtKit-windows.zip` → `PixelPomoArtKit.exe` | unsigned, so SmartScreen says "Windows protected your PC": **More info → Run anyway**. `library/` and `exports/` sit next to the .exe. |
| **macOS** | `PixelPomoArtKit-macos.zip` → `PixelPomoArtKit.app` | **Apple Silicon only** — see below. Each zip carries its own step-by-step guide (`READ-ME-FIRST.txt` / `READ-ME-FIRST-MAC.txt`). |

Both are built by CI from the same commit, so the two platforms never drift
apart.

### macOS, step by step

**This build only runs on Apple Silicon (M1/M2/M3/M4).** It will not open on an
Intel Mac.  → *About This Mac*: "Chip: Apple M…" is fine, "Processor: Intel…"
is not — ask for an Intel build and it can be added to the same release.

1. **Unzip** `PixelPomoArtKit-macos.zip`.

2. **Drag `PixelPomoArtKit.app` into your Applications folder.** Don't skip
   this. macOS runs unsigned apps launched from `Downloads` out of a randomised
   read-only copy (*app translocation*), and the app misbehaves from there.

3. **First launch only** — the app is unsigned, so macOS blocks it. Try **A**,
   and if the menu item isn't there use **B**:

   - **A — right-click** the app → **Open** → **Open** again in the dialog.
     Works on macOS 14 and earlier. *Double-clicking will not offer this
     choice*; you have to right-click the first time.
   - **B — macOS 15 (Sequoia) and later** removed that shortcut. Double-click
     once and dismiss the warning, then  → **System Settings** → **Privacy &
     Security** → scroll down to **Security** → *"PixelPomoArtKit.app was
     blocked…"* → **Open Anyway** → confirm.
   - **C — last resort**, in Terminal:
     ```
     xattr -dr com.apple.quarantine /Applications/PixelPomoArtKit.app
     ```

   After this, it opens by double-click like anything else.

4. **Your drawings live in `~/Documents/PixelPomoArtKit/`** — `library/` for the
   drawings, `exports/` for exported sprites.

   Deliberately *not* beside the app, unlike Windows. `sys.executable` inside a
   `.app` points at `Contents/MacOS/`, so "next to the executable" would hide
   every drawing inside the bundle — and dragging a new version over the old app
   would delete all of them without warning. Documents is visible, stable, and
   survives replacing the app.

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
  It is found **relative to this folder** — the game is expected at `..\App`,
  i.e. both checkouts sitting side by side under one `Pixel Pomo` folder — so
  moving or renaming that folder does not break it. Point the
  `PIXEL_POMO_TOOLS` environment variable at a `tools` folder to override that
  for a layout that isn't this one.

On first run the app creates a `library/` folder next to `art_kit/` and seeds
it with everything the game ships, read live from `gen_objects.py` — not copied
in: the **24 flowers** (12 species, 2 hand-authored models each) and the whole
**forest** — 20 trees, 10 bushes, 5 rocks (#v34.8).

Forest props are raw pixel art: no letter palette, no automatic rim, so what you
paint is exactly what the garden draws. A tree's canvas size *is* its size in the
garden — 16px per tile, so a 2/3/4-tile tree is a 32/48/64-cell grid — and
exporting one at the wrong size is refused rather than written at a pixel density
that would not match the rest of the scene. Every drawing
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
| **Export engine sprite…** | The actual file(s) the game loads: `flower_<species>_<model>.png` (or `tree_07.png` for a forest prop) at the engine's real x16 scale, through the same upscale/write code the shipped assets were made with. Exporting a drawing's model 0 also writes `flower_<species>.png`, the shop thumbnail. Refuses a drawing that isn't exactly 16 cells wide, or has no species set. The save dialog opens on a repo-local `exports/` folder — never the game's asset tree, which is read-only to this app — behind a confirmation that names exactly what it will overwrite. | **Hand this back to the developer.** Drop the output into the game's `assets/objects/` and the artwork ships. |
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
