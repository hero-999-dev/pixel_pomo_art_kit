# Change Log — Pixel Pomo Art Kit

What was built, round by round. Newest first.

---

## v2 — upgrade pass by a stronger model (2026-07-25)

**Date:** 2026-07-25

**Prompt (Turkish):** "simdi ilk promptumu biliyorsun suraya ekleyeyim, suan
dha üst bir modelle yapiyorum, bunu daha öncesinde opus, sonnet, haiku karisimi
kullandim, senden istedigim prompta bak, yapilan uygulamaya bak gerekirse,
kendin nasil yapardin, düsün , yükseltmeleri yap, yada yeniden yap, incele ve
hatalari gider, test et, son halini githube pushla"

In English: v1 was built by a mix of Opus/Sonnet/Haiku subagents; re-examine
the original prompt and the app with a stronger model, decide whether to
upgrade or rebuild, fix what's wrong, test, and push the final state.

**Verdict on the architecture:** kept. Importing the game's own
`gen_objects.py` and running preview + export through its real compositing is
the one decision everything else hangs off — it is what makes the exported
sprite byte-identical to the shipped asset, and a rewrite would re-risk the
already-proven byte-equality, atomic saves, and undo/identity reconciliation
for no user-visible gain.

**What the review found and fixed** — all in the window layer; the model,
bridge, and store came through the re-read clean:

- **Fast drags left dotted lines.** tkinter delivers motion events sparsely,
  and the canvas painted only the reported cells. Strokes now interpolate
  with integer Bresenham between consecutive events, so a quick flick is a
  continuous line. (This is the one an artist would have hit in the first
  minute.)
- **Edge cells were unreachable at high zoom.** 16 cells x 48px is wider than
  the canvas pane; there were no scrollbars. The canvas now scrolls both
  ways, and pointer events go through `canvasx`/`canvasy` so painting stays
  accurate while scrolled.
- **No eyedropper.** On a letter drawing the eye cannot reliably tell `d`
  from `m` from `l`, so continuing in the same tone meant guessing.
  Right-click now picks the cell under the cursor as the ink; empty cells
  are ignored (a misclick should not quietly become "paint nothing").
- **Nothing showed what the next click would paint.** The tools pane now has
  an ink swatch (colour + name), and the active palette letter shows as
  pressed.
- **The library list jumped to the top on every stroke** (it is rebuilt to
  refresh thumbnails, which reset the scroll). The scroll position is now
  restored across rebuilds.
- Smaller: `set_tool` rejects unknown tools at the boundary (matching
  `set_ink`); a successful engine-sprite export now reports the files it
  wrote instead of finishing silently; the title bar names the drawing being
  edited.

**Tests:** 72, all passing — three new: the Bresenham line is filled exactly,
right-click eyedropping picks letters and ignores empties, unknown tools are
refused.

---

## v1 — initial build (2026-07-25)

**Date:** 2026-07-25

**Prompt (Turkish):** "simdi yeni bir dictionary yapalim, drawing kit diye,
flower studyleri icine koyalim. ve istedigim sey su, ben cizimleri yapmasi icin
bir sanat ögrencisiyle konusuyorum motora uygun 2d pixel cizmesi icin söyle bir
planim var, bir uygulama olsun solda cicekler yaptigimiz, ve sol altta + olacak
ve yeni cizim ekleyecegiz, onun disinda orta alanda piksel kareleri teker
koyacagimiz cizim alani, yakinlastirma, uzaklastirma olacak, sag taraftan renk
sececegiz,uygulamadaki gibi ve ortada mouse tiklamasiyla yerlestirecegiz, ayrica
sagda cizim ve silgi modu olacak, solda ayrica cizimin üstünde üc nokta olacak
basinca cogalt ve export olacak png, jpg falan exportu olacak,ve motora özel
sprite exportu da olsun, simdi bu uygulamayi yaparken ciceklrin tüm modellerini
bu uygulamaya ekle, bu uygulama icin, prompt, readme, log, test md olacak, bu
uygulamanin adi pixel pomo art kit olacak,windows icin olacak, bu uygulama, ve
sagda cizimde undo ve redo tusu olacak, md dosyalari icin benzer processleri
uygula,"

In English: a new `drawing kit` folder with the flower studies inside; a
Windows desktop pixel editor for an art student to draw engine-ready 2D pixel
flowers — flowers listed on the left with a `+` at the bottom-left to add a new
one, a centre canvas that places pixel squares one click at a time with
zoom in/out, colour picked on the right (as in the app) and placed by mouse
click, draw and erase modes on the right, a three-dot menu above each drawing on
the left for duplicate and export (PNG, JPG, and an engine-specific sprite
export), all flower models loaded into the app, undo/redo on the right, its own
prompt/readme/log/test md files following the same process, named **Pixel Pomo
Art Kit**.

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
- Packaged as a standalone Windows `.exe` with PyInstaller (`run_art_kit.py`
  is the frozen entry point), bundling a copy of `gen_objects.py` so the exe
  runs on a machine with no game checkout, and writing `library/`/`exports/`
  beside the exe rather than inside its temporary unpack dir. Shipped as a
  zip on the GitHub Release.

**Tests:** 69, all passing — `python -m unittest discover -s tests -v`.
