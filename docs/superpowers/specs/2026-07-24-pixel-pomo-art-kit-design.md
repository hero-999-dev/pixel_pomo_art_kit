# Pixel Pomo Art Kit — design

**Date:** 2026-07-24
**Status:** approved (design), pending implementation plan

## Why this exists

The user is bringing an art student in to draw 2D pixel flowers for Pixel Pomo's
garden. Today a sprite only becomes real by hand-editing a Python literal inside
`pixel_pomo\flutter\tools\gen_objects.py` and re-running it — a workflow that
assumes you know the repo. The art student needs a window they can draw in whose
output is, without translation or interpretation, exactly what the engine ships.

That last clause is the whole design. An editor that produces "a PNG the engine
can probably load" is a different, much weaker product than one that produces the
file byte-for-byte.

## Shape

A Windows desktop app, `Pixel Pomo Art Kit`, living in its own repository at
`C:\Users\claude\drawing kit\`. The existing `flower_study\` workspace moves in
beside it — same subject, same folder.

- **Left:** the drawing list, one row per model with a thumbnail, grouped by
  species. `+` at the bottom starts a new drawing. Each row carries a `⋮` menu:
  Duplicate · Export PNG · Export JPG · Export engine sprite · Rename · Delete.
- **Centre:** the canvas. Click or drag to place a pixel, mouse wheel or `+`/`−`
  to zoom, grid lines on, a checkerboard behind transparent cells. Beside it the
  live **engine preview** — the sprite as the garden will draw it — and the
  **8×8 squint test**, which the project's own pixel-art rule already requires
  before any sprite is accepted.
- **Right:** DRAW / ERASE · UNDO / REDO · the species palette slots · a free
  colour picker with the app's ready colours underneath.

## The document is a character grid, not a bitmap

The engine's flowers are stored as a 16-wide grid of palette letters plus five
hex colours — `_FLOWER_BLOOMS[fid][v]` and `_FLOWER_PALS[fid]` in
`gen_objects.py`. Letters split into two materials: `d`/`m`/`l` petal tones, `C`
centre and `x` bloom seam make the **bloom**; `S` stem, `G` leaf, `k` leaf vein
and `o` plant seam make the **plant**. Each is outlined in its own dark rim and
the two are composited, so the materials read apart instead of sharing one black
silhouette.

The art kit adopts that as its document format rather than inventing one. This
is what makes the rest of the design fall out:

- **Loading** reads the real grids. No copy of the data exists to drift.
- **The preview** calls the real `outline()` and `_rose_compose()`. What the
  artist sees is the shipped sprite, rims and compositing included — not an
  approximation that gets a surprise when it reaches the game.
- **Engine export** calls the real `upscale()` and `write_png()`. The output is
  the same bytes CI publishes.

A cell holds *either* a palette letter or a raw RGBA colour, so the free colour
picker is not a separate mode with a separate file format. A drawing whose cells
are all letters can additionally be exported as a grid literal ready to paste
into `_FLOWER_BLOOMS`; one containing raw colours exports as PNG only, and the
menu says so rather than failing at the end.

## What gets loaded

Twelve flowers, two hand-authored models each — **24 drawings**. Not 36: the
third shipped file per flower, `flower_<id>.png`, is a copy of model 0 used as
the shop thumbnail, not a separate drawing.

Eleven of the twelve are already character grids and load directly, as 22
letter-grid drawings.

The rose (`gul`) is stored differently — a bloom grid and a stem grid composed
with a row offset — and **cannot be flattened into one letter grid**. This was
checked against the real data rather than assumed: the stem's first row lands on
the bloom's last row and collides at two cells (`v0` row 11, `v1` row 9, columns
7–8, `d` under `S`), and one cell holds one letter, so a flattened grid renders a
visibly different sprite. Verified by rendering both and comparing.

So the rose loads as a **raw-pixel drawing** instead: the composed RGBA grid
`rose_variant(v)` produces, before upscaling. It is fully editable and exports
byte-identically, because the export is that same grid upscaled and written —
there is no second interpretation step to disagree with. What it cannot do is
export a `_FLOWER_BLOOMS` grid literal, which is correct: the rose has never
lived in `_FLOWER_BLOOMS`.

Both paths were proven byte-exact against the shipped assets before this design
was finalised: `flower_lale_0.png` and `flower_papatya_1.png` via letters,
`flower_gul_0.png` via raw pixels.

## Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `art_kit/model.py` | The grid, the palette, the undo stack, the library of drawings. Pure data — no tkinter, no file I/O. | stdlib |
| `art_kit/store.py` | Reading and writing drawings as JSON on disk. | `model` |
| `art_kit/engine_io.py` | The bridge to `gen_objects.py`: import the shipped flowers, render a grid to RGBA, write PNG / JPG / engine sprite / grid literal. | `model`, `gen_objects`, PIL (JPG only) |
| `art_kit/app.py` | The tkinter window: three panes, menus, key bindings. | all of the above |

The split matters for testing more than for tidiness: everything worth asserting
lives in the first three, none of which need a display.

## Storage

One JSON file per drawing under `library\`, holding the grid rows, the palette,
and a little metadata (name, species, model index, size). Readable, diffable,
and recoverable with a text editor if the app ever writes something wrong. No
database, no binary format, no migration story to maintain.

## Exports

- **PNG** — RGBA, nearest-neighbour, at a chosen scale (1×, 8×, 16×).
- **JPG** — the same, flattened onto white, via PIL. JPEG has no alpha; the app
  says which colour it flattened onto rather than silently picking one.
- **Engine sprite** — `flower_<id>_<v>.png` at ×16 through the real helpers,
  written either into `pixel_pomo\flutter\assets\objects\` behind a confirmation
  or into a folder the user picks. Overwriting a shipped sprite is the point of
  the feature, but it is still an overwrite, so it asks first.
- **Grid literal** — a `.txt` of the Python rows, ready to paste into
  `_FLOWER_BLOOMS`, offered only when every cell is a letter.

## Testing

`unittest`, standard library, no framework. The suite that matters:

- **The bridge is exact.** Load `lale` model 0, change nothing, export the engine
  sprite, compare the bytes to the shipped `flower_lale_0.png`. If the import,
  the render and the writer all agree with `gen_objects.py`, this passes and
  nothing else needs to argue the point. Repeated for `papatya` model 1 and for
  the rose, which travels the raw-pixel path instead of the letter path.
- **The grid model** — paint, erase, undo past the start, redo past the end,
  duplicate, resize, and that undo restores the exact prior grid rather than a
  shallow copy that shares rows.
- **The codec** — JSON round-trip, including a drawing that mixes letters and raw
  colours, and a file with a missing or malformed field decoding to something
  usable instead of crashing the app on launch.
- **Export guards** — grid-literal export refused on a drawing with raw colours;
  engine export refused on a grid that is not 16 wide.

Not covered by tests, by nature: how the window looks and feels. That is checked
by running it.

## Documentation

`README.md`, `prompt.md`, `log.md`, `TESTING.md` in the repository root,
following the conventions Pixel Pomo already uses — `log.md` and `prompt.md`
prepend newest-first, `TESTING.md` records what each round covered and, just as
importantly, what it did not.

## Deliberately not in scope

- Packaging to a standalone `.exe`. The app runs with `python -m art_kit`; if the
  art student turns out not to have Python, PyInstaller is a later, separate job.
- Layers, selection, fill, shape tools, eyedropper. The brief is place a pixel,
  erase a pixel, undo. Adding a tool because pixel editors usually have one is
  how this grows into something nobody asked for.
- Editing anything but flowers. Trees, fences, critters and roads are generated
  by different code paths in `gen_objects.py`; the loader could reach them later
  if the need appears.
