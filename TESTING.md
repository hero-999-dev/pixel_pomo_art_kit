# Testing — Pixel Pomo Art Kit

## Running the suite

```
python -m unittest discover -s tests -v
```

**80 tests, all passing.** Verified 2026-07-25 on `main`, Python 3.14.4,
Pillow 12.2.0, `PIXEL_POMO_TOOLS` unset (i.e.
against the default `C:\Users\claude\pixel_pomo\flutter\tools\gen_objects.py`
checkout).

Everything is plain `unittest` — no third-party test framework, no fixtures
beyond `tempfile.TemporaryDirectory`, no mocked filesystem.

## What each file covers

| File | Covers | Tests |
|---|---|---|
| `tests/test_model.py` | `Palette` (the nine letters resolving to RGBA). `Drawing` (blank/paint/erase/bounds, `copy()` not sharing rows, and that painting a raw colour flips a drawing from `"letters"` to `"pixels"`). `History` (a whole drag is one undo step, undo/redo restore the exact prior grid, a no-op stroke isn't recorded, redo's branch is dropped by a new stroke after an undo, undo/redo are no-ops at either end, the 200-entry cap). Also that `Drawing.kind` is derived from the cells — a raw colour flips it to `"pixels"`, erasing back to all-letters flips it to `"letters"`; that `flood()` fills exactly the connected region (walls untouched, other regions untouched) and no-ops on its own value; that `resize_rows()` pads below / crops below without touching the art; and that `History.repaint()` puts a palette edit on every snapshot so an undo can't revert the colours. | 18 |
| `tests/test_engine_io.py` | Importing the 24 shipped flowers live from `gen_objects.py` (letter grids for eleven species, raw composited pixels for the rose). Rendering a drawing and asserting the result equals the engine's own `flower_variant`/`rose_variant` output directly. Every export function — `export_png`, `export_jpg`, `export_engine_sprite` (including three flowers' output compared byte-for-byte against the PNGs actually shipped in `pixel_pomo\flutter\assets\objects`), `export_grid_literal` — and every `ExportRefused` guard (no species set, not 16 cells wide, scale below 1, raw colours in a grid-literal export), plus that `engine_sprite_names` (which the overwrite-confirmation dialog shows) names exactly the files `export_engine_sprite` writes, and that `export_palette_literal` reproduces the engine's own `_FLOWER_PALS` line (and refuses a drawing with no species). | 26 |
| `tests/test_store.py` | The JSON codec round-tripping a letters drawing, a raw-pixel drawing, and a mixed one. Every malformed-file `CorruptDrawing` path: missing field, ragged rows, cells not a list of rows, a malformed row, an out-of-alphabet letter, a wrong-length colour tuple, an unknown `kind`. Atomic save (a second save leaves no stray `.tmp` file behind). `Library`: seeding writes/skips-on-repeat, reopening finds what was saved, duplicate/remove/rename, a corrupt file is skipped rather than failing the whole load, two value-equal drawings don't get confused with each other on removal, and a session's first save of an existing file leaves a `.json.bak` of the session's starting point that later saves don't clobber. | 21 |
| `tests/test_app_smoke.py` | The tkinter window wired up end-to-end against a real (hidden) `Tk()` root: opens with all 24 seeded drawings listed; a click-drag paints a run of cells as one undoable stroke; the eraser clears a cell; switching to another drawing and back preserves the edit; zoom clamps to `[MIN_ZOOM, MAX_ZOOM]`; painting with a picked colour turns a letters drawing into a pixels one; `set_ink` rejects a value `render()` would silently drop (a non-alphabet letter, a wrong-length tuple); the three panes are wired up (canvas and both previews are real `Canvas` widgets); the export dialog's default folder is not inside the game's read-only asset tree; an undo is written through to the drawing's file on disk, not just held in memory; a fast drag paints the whole Bresenham line between sparse motion events, not dots; right-click eyedrops the cell under the cursor into the ink (and ignores empty cells); `set_tool` rejects unknown tools; MIRROR X paints and erases both halves; the fill tool floods from the pressed cell and undoes as one stroke. | 15 |
| **Total** | | **80** |

## Not covered

- **How the window actually looks.** The smoke tests drive `ArtKitApp`
  through its grid-coordinate methods (`on_canvas_press`, `.zoom`, …) and
  assert on model state (`history.current`, `zoom_level`) — never on pixel
  output, widget geometry, colours, or layout. There is no way to capture a
  screenshot in this build environment, so a purely visual regression (a
  misaligned pane, a swapped colour, an unreadable label) would not be caught
  by the suite. The only way to check the window's actual appearance is to
  run `python -m art_kit` and look at it.
- **Whether tkinter behaves identically on another Windows machine.** This
  suite runs against one Tk/Tcl build, on one machine, at one DPI setting.
  Font metrics, default widget sizing, and high-DPI scaling can all differ on
  a different install; none of that is exercised here.
- **`test_app_smoke.py` skips itself when there is no display.**
  `_tk_or_skip()` catches the `tkinter.TclError` that `tkinter.Tk()` raises
  with no display available and turns it into `unittest.SkipTest` — on a
  headless machine (CI, a remote shell with no Windows session) all 15 of its
  tests report as **skipped**, not failed, and `discover` still exits 0. In
  this environment a real display was available (1024x768), so all 15 ran for
  real rather than skipping — that's a property of the machine the suite
  happened to run on here, not a guarantee for every environment.
- **Byte-exact export is sampled, not exhaustive.** The shipped-PNG
  comparison runs against three flowers (`lale` model 0, `papatya` model 1,
  `gul` model 0 — one plain letter grid, one letter grid with more colour
  variety, and the rose's raw-pixel path), and the render-equals-engine check
  runs against a wider but still partial sample of species. Every flower goes
  through the same `render()`/`export_engine_sprite()` code, so this is
  strong evidence for all 24 shipped models, not individual proof of each one.
