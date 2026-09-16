# Testing — Pixel Pomo Art Kit

## Running the suite

```
python -m unittest discover -s tests -v
```

**145 tests, all passing.** Verified 2026-09-16 on `main`, Windows 11, Python
3.14.4, Tk 8.6, Pillow 12.2.0, `PIXEL_POMO_TOOLS` unset (i.e. against the
sibling game checkout the kit resolves relatively,
`..\App\flutter\tools\gen_objects.py`). About 70 s wall clock, almost all of
it the 37 smoke tests each building the whole window. Nothing in the suite
touches the network: the updater is tested against a fake opener.

Everything is plain `unittest` — no third-party test framework, no fixtures
beyond `tempfile.TemporaryDirectory`, no mocked filesystem. The release
workflow runs the suite on Windows, Apple Silicon and Intel macOS before it
builds anything.

## What each file covers

| File | Covers | Tests |
|---|---|---|
| `tests/test_model.py` | `Palette` (the nine letters resolving to RGBA). `Drawing` (blank/paint/erase/bounds, `copy()` not sharing rows, and that painting a raw colour flips a drawing from `"letters"` to `"pixels"`). `History` (a whole drag is one undo step, undo/redo restore the exact prior grid, a no-op stroke isn't recorded, redo's branch is dropped by a new stroke after an undo, undo/redo are no-ops at either end, the 200-entry cap). Also that `Drawing.kind` is derived from the cells; that `flood()` fills exactly the connected region and no-ops on its own value; that `resize()` pads right/below and crops right/below without touching the art; and that `History.repaint()` puts a palette change on every snapshot. | 18 |
| `tests/test_engine_io.py` | The forest props (#v34.8): every tree/bush/rock the engine loads is in the library, a tree opens at the canvas size its tile count implies, props export under their own filename with no `flower_` prefix, an untouched prop is byte-identical to the shipped PNG, an off-size tree is refused, and rendering one returns it unchanged. Importing the 24 shipped flowers live from `gen_objects.py`. Rendering equals the engine's own `flower_variant`/`rose_variant` output. Every export function and every `ExportRefused` guard; `engine_sprite_names` names exactly the files `export_engine_sprite` writes; `export_palette_literal` reproduces the engine's `_FLOWER_PALS` line. Every species and forest kind has an English display name (#v2.2.0). PNG import: profile → sRGB, alpha snapping, nearest-neighbour downscale, the x16-only scale guess. | 34 |
| `tests/test_store.py` | The JSON codec round-tripping a letters, a raw-pixel and a mixed drawing. Every malformed-file `CorruptDrawing` path. Atomic save. `Library`: seeding, reopening, duplicate/remove/rename, a corrupt file is skipped rather than failing the load, value-equal drawings are not confused on removal, the session's first save leaves a `.json.bak`. | 21 |
| `tests/test_symmetry.py` | The symmetry bar (#v2.4.0), pure geometry: a vertical bar covers `length` rows centred on the click (odd and even lengths), a horizontal one covers columns; each reports its angle (90/180); a vertical bar mirrors left↔right only within its reach and never for a cell on the bar, a horizontal one top↔bottom; length is clamped and a bad orientation refused; `moved_to` keeps the shape; `expand()` leaves cells alone with no bar, appends each twin after its original without duplicates, and paints cells beyond the bar alone. STICK (#v2.5.0): a horizontal stick runs to the right from the click, a vertical one downward, length 1 is an ordinary click, length is clamped and a bad orientation refused, `expand_stick()` grows every cell without duplicates. | 13 |
| `tests/test_settings.py` | The preferences file (#v2.4.0): a missing file gives the six classic favourites, `draw`, and a vertical 5-long bar in mode `off`, and writes nothing until something changes; add/remove favourites round-trip through the file, case- and `#`-insensitively, without duplicates; a bad hex is refused; tool and symmetry persist (mode kept when not given, stored when given); an old file without a mode still reads; a corrupt file falls back to defaults instead of raising; a hand-edited bad favourite drops that entry only, and a wrong-typed field keeps its default. | 7 |
| `tests/test_paths.py` | Where the data lives (#v2.5.0): from source, the repo root; a frozen Windows build uses `%LOCALAPPDATA%\PixelPomoArtKit`, never the .exe's folder, and names that folder as the legacy place to migrate from; a frozen Mac uses Documents and has no legacy folder. `migrate_legacy()` copies drawings and `settings.json` from an old beside-the-exe folder and leaves it untouched, skips non-drawings, never overwrites a file already in the data folder, copies nothing on a second run, and copes with a missing legacy folder or with being handed the data folder itself. | 6 |
| `tests/test_updater.py` | Updates (#v2.5.0), all against a fake HTTP opener: `version.parse` handles `v` prefixes, two-digit components and `-rc` suffixes (leading digits only), and `VERSION` is a real triplet; `Release.is_newer` for newer/same/older tags; `check()` hits the releases API with a `PixelPomoArtKit` User-Agent and parses tag, page, notes and asset URLs; a non-JSON body raises rather than guesses; `download()` writes the file, reports progress up to the total, and leaves no `.part` behind; `backup_library()` zips every drawing and returns None for an empty library; `stage_windows()` unpacks the .exe from the zip beside the running one without touching it and writes a hand-off script naming this pid, the `.old.exe` it keeps, the two moves and the relaunch; a zip with no .exe is refused. | 9 |
| `tests/test_app_smoke.py` | The tkinter window wired up end-to-end against a real (hidden) `Tk()` root, with the library AND the settings file in a temp dir. From before: opens with every seeded drawing listed; a drag paints as one undoable stroke; the eraser; switching drawings keeps edits; zoom clamps; a picked colour turns a letters drawing into pixels; `set_ink` rejects what `render()` would drop; the panes are wired; the shade square sets a real ink; a frozen Mac build keeps drawings out of the bundle and a frozen Windows build writes beside the exe; the export dialog does not default into the game's assets; a fast drag fills the Bresenham line; right-click eyedrops and ignores empties; unknown tools are refused; the fill floods as one undo; a new drawing is 32x32 by default; an undo is written to disk. **New in #v2.4.0:** `save()` writes and reports success; the ink entry is an `Entry` showing the bare `#rrggbb` (no `ink:` prefix) and `set_ink_hex` accepts `RRGGBB`/`#rrggbb` and refuses anything else without changing the ink; a letter ink shows its palette colour; `+` adds the ink to favourites and `remove_favourite` takes it out of both settings and the grid; the ready and favourite grids and the hue strip are all `PICKER_W` wide; `set_tool` persists and a second app on the same settings opens with that tool; `new_drawing(cols, rows)` honours its size and `size_presets()` gives Flower 16 x the engine's bloom height, Bush 16x16, and trees at 32/48/64; `resize()` is one undo and the size label follows; with SYMMETRY on the first click places the bar and paints nothing, later strokes mirror within the bar's reach only, the mirror undoes with its stroke, and off means no mirror; orientation/length rebuild the bar and persist; a stroke updates one library row (the row widgets are the same objects) and the art is a single canvas image item; the help overlay toggles; `close()` writes a stroke that was still in progress and destroys the window once; the icon grid is a complete 16x16 sprite whose letters all have colours and that renders to a PhotoImage. **New in #v2.5.0:** a frozen Windows build writes to the user profile, not beside the .exe (the v2.4.0 test asserted the opposite); STICK paints `length` cells from the click as one undo and persists its mode; pressing on the bar drags it (with the grab offset kept) without painting or recording a stroke, and PLACE BAR re-arms click-to-place; `m` cycles OFF → MIRROR → STICK and a bad mode is refused; `import_png` puts a PNG into the library saved, with a row, name from the file and species `""`; a newer `Release` turns the UPDATE button into `UPDATE ● vX`, a current one leaves it alone, and a failed silent check changes nothing. | 37 |
| **Total** | | **145** |

## Not covered

- **How the window actually looks.** The smoke tests drive `ArtKitApp`
  through its grid-coordinate methods and assert on model state and widget
  wiring — never on pixel output or layout. The screenshots taken while
  building #v2.4.0 (main window, help overlay, symmetry bar, a 48-cell tree,
  the size dialog) were checked by eye on Windows and are not part of the
  suite. A misaligned pane or an unreadable label would not fail a test.
- **macOS, live.** This kit is developed on Windows. The suite runs on the
  macOS CI runners before every release, and the #v2.4.0 changes were written
  against known Aqua behaviour (native buttons ignore `bg`, right-click is
  `Button-2`, Cmd+Q bypasses `WM_DELETE_WINDOW`, Documents needs permission),
  but nobody has clicked through the Mac build as part of this release. The
  Documents-refused fallback in `__main__.data_dir()` in particular cannot be
  provoked from Windows and is untested beyond its own logic.
- **Interactive widget behaviour.** Double-click-to-select in the ink entry,
  right-click on a favourite opening a menu, the Spinbox arrows, hover colours
  on buttons, the ghost bar following the cursor — all exercised by hand, none
  by the suite, which calls the methods those events lead to instead.
- **`test_app_smoke.py` skips itself when there is no display.**
  `_tk_or_skip()` turns the `TclError` from `tkinter.Tk()` into
  `unittest.SkipTest`, so a headless machine reports its 32 tests as skipped,
  not failed. Here a real display was available, so they all ran.
- **Byte-exact export is sampled, not exhaustive.** The shipped-PNG comparison
  runs against three flowers and one forest prop; every drawing goes through
  the same `render()`/`export_engine_sprite()` code, so this is strong
  evidence for all of them, not individual proof of each one.
- **The Windows self-update, end to end.** The suite proves the pieces
  (download, backup, staging, the script's text). The actual hand-off —
  cmd waiting for the process to exit, swapping the .exe, relaunching — was
  run by hand against the built v2.5.0 .exe in a temp folder (it swapped,
  kept `.old.exe`, deleted its script and relaunched; see log.md for the
  `DETACHED_PROCESS` pipe hang that the first attempt found). It is not in
  the suite: it needs a frozen .exe and kills the process it runs in. Nor is
  the macOS branch (open the release page) beyond `webbrowser.open` being the
  standard library.
- **Talking to GitHub for real.** Every updater test uses a fake opener. A
  changed API shape or a rate-limited response would surface as the "could
  not reach GitHub" dialog, not as a test failure.
- **Performance is measured, not asserted.** The 64x64 stroke timings in
  `log.md` (#v2.4.0) came from a one-off script; no test fails if rendering
  gets slow again. The structural test — one image item, rows built once —
  guards the specific regression that caused the freeze, not the number.
