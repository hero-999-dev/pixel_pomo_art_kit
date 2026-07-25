# Change Log — Pixel Pomo Art Kit

What was built, round by round. Newest first.

---

## v1 — initial build (2026-07-25)

**Date:** 2026-07-25

**Prompt:** _[original Turkish prompt to be filled in by the user]_ — in
English: a Windows desktop pixel editor an art student can draw Pixel Pomo
flowers in, whose exported sprite is byte-identical to what the game ships.

**Changes:** the app was built incrementally — the data model first, then the
bridge to the game's sprite generator, then on-disk storage, then the window
— each layer landing with its own tests before the next was built on top of
it.

- `art_kit/model.py`: `Palette` (nine hex slots resolving to RGBA), `Drawing`
  (a grid of palette letters and/or raw RGBA cells — painting a raw colour
  onto a letters drawing turns it into a pixels drawing), `History`
  (stroke-grouped undo/redo over whole-grid snapshots, capped at 200
  entries).
- `art_kit/engine_io.py`: imports Pixel Pomo's own `gen_objects.py` live,
  never reimplemented, to load the 24 shipped flower models (12 species x 2
  hand-authored models each — 11 species as letter grids, the rose `gul` as
  raw composited pixels). Renders a drawing through the engine's real
  compositing so the preview can never disagree with an export, and exports
  PNG, JPG, the actual engine sprite (`flower_<species>_<model>.png`, plus
  the shop thumbnail when exporting model 0), and a grid-literal paste for
  `_FLOWER_BLOOMS`. Anything that can't be produced honestly raises
  `ExportRefused` instead of writing a wrong file.
- `art_kit/store.py`: one human-readable JSON file per drawing, atomic saves
  (write-temp-then-rename, so an interrupted save can't truncate existing
  work), strict validation on load, and a `Library` that seeds itself from
  the engine on first run and skips — rather than crashes on — a corrupt
  file.
- `art_kit/app.py` + `art_kit/__main__.py`: the tkinter window — a library
  pane, a canvas pane with click-to-place painting and zoom, and a tools
  pane with the palette, a free colour picker, draw/erase, and undo/redo.
  Runs with `python -m art_kit`.
- `README.md`, `prompt.md`, `TESTING.md`, and this file, written last, once
  the app was feature-complete, so they describe what actually shipped
  rather than what was planned.

**Tests:** 66, all passing — `python -m unittest discover -s tests -v`.
