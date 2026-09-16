# Change Log — Pixel Pomo Art Kit

What was built, round by round. Newest first.

---

## v2.4.0 — the artists' round: matcha, symmetry, favourites, and no more freezing
**Date:** 2026-09-16

**Prompt (Turkish, abridged):** fifteen numbered items from the artists using
the kit on Windows and macOS — a SAVE button, Ctrl+Z/Y/S/N, previews moved to
the bottom right behind a full-height divider, the colour panel widened to the
swatch grid, favourite colours, an ink code that can be copied or typed over
with a `+` to favourite it, the tomato-and-brush icon everywhere, the app
freezing on every change, the grey-and-white Windows chrome replaced with the
game's matcha theme, ready colours rendering white on macOS and closing without
saving there, a visible selected tool, a new-drawing dialog with the garden's
sizes and a clickable size in the corner, a symmetry bar, and a help panel.

### The bug that mattered most (item 7 — "uygulama takiliyor")

Every stroke rebuilt the **entire library list**: 59 rows destroyed and
recreated, each thumbnail one `create_rectangle` per opaque cell. Twenty of
those rows are trees, up to 64x64 — tens of thousands of canvas items per
click. The main canvas did the same at zoom scale.

Rendering is now image-based (`art_kit/raster.py`): a drawing becomes one
in-memory PNG (standard library, Tk 8.6 decodes PNG with alpha natively) and
one `PhotoImage`, scaled in C with `zoom()`. **One canvas item per drawing.**
The list is built once and only the edited row is refreshed
(`_refresh_row`); selection just recolours two rows. Mid-stroke, only the
cells the event touched are painted as rectangles over the image; the full
render happens once, on release. Measured on a 64x64 tree: 60 drag events in
0.69 s including the Tk update, release (render + save + thumbnail) 75 ms.
The test suite, which builds the whole window 30 times, got faster despite
growing from 91 to 120 tests.

### macOS (items 9, 10)

**Ready colours were white.** They were `tk.Button`s, and the Aqua button is a
native control that ignores `bg`. So was every other button — which also means
the pressed-tool look and the matcha theme would have been invisible on a Mac.
Swatches are now one `SwatchGrid` canvas per palette; every button is a
Label-based `theme.Button` that honours its colours on both platforms and
keeps `command`/`invoke()`.

**Closing without saving.** Saves already happen at the end of every stroke,
so "it didn't save" meant "every save was failing silently". The likeliest
cause on macOS: the frozen build writes to `~/Documents/PixelPomoArtKit`, and
macOS gates Documents behind a privacy prompt — an unsigned app that gets
"Don't Allow" raises `PermissionError` on each save, into a stderr nobody
sees. Three fixes, none of which can be verified from Windows, so all three
ship: `__main__` probes the folder for real and falls back to
`~/Library/Application Support/PixelPomoArtKit` with a warning that names both
paths; every save goes through `_save()`, which shows the error once and puts
**SAVE FAILED** in the status label instead of pretending; and the window's
close button and Cmd+Q (`::tk::mac::Quit`) both run `close()`, which finishes
an open stroke and writes every drawing touched this session. The bundle also
declares `NSDocumentsFolderUsageDescription` so the prompt says why.

Also for Mac: right-click is `Button-2` there (plus Control-click), so the
eyedropper and the favourites menu bind all of them; shortcuts bind `Command`
alongside `Control`; the help text says Cmd where it should.

### What the artist sees (items 1–6, 8, 12–15)

- **Matcha theme** (`art_kit/theme.py`), tones copied from `PixelTheme.matcha`
  in the game. `ttk` scrollbars on `clam` (the classic scrollbar is native and
  uncolourable — the grey bars in the screenshot). Windows title bar painted
  dark through `DwmSetWindowAttribute`, dialogs included.
- **SAVE** above the tools, with a `saved HH:MM:SS` status that every autosave
  updates. **Ctrl/Cmd+S**, **Ctrl/Cmd+N** (new drawing), Ctrl/Cmd+Z/Y as before.
- **The selected tool** is the accent-filled button; the **last tool used** is
  remembered across sessions (`settings.json`, beside `library/`).
- **Divider + bottom-right corner:** a one-pixel line runs the full height
  between canvas and tools; the 1x and squint previews, the drawing's
  `W × H` (click to resize) and **HELP** live in the corner.
- **Ink** is an Entry showing just `#rrggbb`: click to type a new code, Enter
  applies, double-click selects it all to copy, `+` adds it to favourites.
- **Favourite colours** above Ready colours, seeded with six classic colours;
  right-click a swatch → Remove. Both grids and the colour panel are exactly
  `PICKER_W` wide, so their edges line up.
- **New drawing / resize dialog** with the garden's sizes read from the engine
  (Flower 16×15, Bush/Rock 16×16, Tree 32/48/64) or a custom width × height;
  a resize is one undo step.
- **Symmetry bar** (`art_kit/symmetry.py`, pure): SYMMETRY on → the next click
  places a bar, `│ 90°` or `─ 180°`, `length` cells long, centred on the
  click; a ghost follows the cursor while placing. Cells painted within the
  bar's reach are mirrored across it; cells beyond it are painted alone; the
  stroke and its mirror are one undo. Orientation/length persist.
- **Help overlay** over the main window: every button and key, closed with ×,
  Esc or F1.
- **Icon:** the tomato with a brush beside it, a 16×16 letter grid in
  `art_kit/branding.py`. Drawn at run time for the title bar/Dock, and
  rendered by `python -m art_kit.branding` into `assets/icon.{png,ico,icns}`
  for the .exe, the .app and the README. Both zips carry `icon.png`.

**Tests:** 91 → 120. New files `test_symmetry.py` (9) and `test_settings.py`
(6); the smoke suite grew by 14 — save writes and reports, the entry shows the
bare code and accepts a typed one, a letter ink resolves to its palette colour,
`+`/remove favourites, grid widths match the picker, the last tool is
remembered by a second app on the same settings, presets come from the engine,
resize is one undo and the label follows, the bar places on the first click
then mirrors within reach only and undoes with its stroke, orientation/length
persist, a stroke updates one row and the art is one image item, help toggles,
`close()` writes an in-progress stroke, the icon grid is complete.

## v2.3.0 — an Intel Mac build, and Tahoe-correct Gatekeeper steps
**Date:** 2026-07-28

**Two Mac downloads now.** PyInstaller cannot cross-compile between
architectures any more than between operating systems, and `macos-latest` is
Apple Silicon (`macos-26-arm64`) — so every Mac build before this one simply
would not open on an Intel Mac, with no useful error. A second job on
`macos-15-intel` produces the Intel binary; the runner images in the log confirm
the split (`macos-26-arm64` vs `macos-15`), as do the sizes, 14.2 MB against
15.6 MB.

The assets are named for the machine rather than the platform —
`PixelPomoArtKit-macos-apple-silicon.zip` and `PixelPomoArtKit-macos-intel.zip`
— because nothing inside the app can warn someone who picked wrong.

**The Gatekeeper instructions were wrong for the artist actually using them.**
One of them is on **Tahoe (macOS 26)**, and the guide led with the right-click
→ Open trick. Apple removed that in Sequoia (15); on Tahoe it does nothing at
all, so the first thing the artist would try was guaranteed to fail.

Reordered: System Settings → Privacy & Security → Open Anyway is now the
primary route, labelled for macOS 15/26 and newer, with right-click kept below
for Sonoma and older and the `xattr` command as a last resort for any version.
The guide also opens with a "check which Mac you have" step before the download.

## v2.2.0 — everything the artist reads is English
**Date:** 2026-07-28

"Sanatcilar türkce bilmiyor." The kit is handed to artists who do not read
Turkish, and two things still did.

**Flower names.** The library list, the window title and every row showed
`gul_0`, `papatya_1`, `kasimpati_0`. Those ids cannot change: the engine loads
`flower_gul_0.png` and saved gardens reference the species by that name, so
renaming them would break every shipped sprite and every existing garden.

The ids stay; the LABEL is now English. `DISPLAY_NAMES` +
`display_name(species, model)` give "Rose 1", "Daisy 2", "Chrysanthemum 1",
"Tree 01". Copied from the game's own catalogue (`Flowers.all` in logic.dart)
rather than invented, so the kit and the shop call the same flower the same
thing in front of the same person.

Verified first that export filenames come from `species` + `model` and never
from the label — otherwise this rename would have quietly changed what the kit
writes into the game.

**The guides.** `OKUBENI.txt` / `OKUBENI-MAC.txt` were Turkish-first with an
English section underneath, and even the filename was Turkish. Replaced by
`READ-ME-FIRST.txt` and `READ-ME-FIRST-MAC.txt`, English only — a file the
reader cannot read the *name* of is a bad start.

The app's own code had no Turkish in it at all; checked rather than assumed.

**Tests:** 90 → 91. The new one walks every species and forest kind and fails
if one has no English label, has a label equal to its id, or produces a name
carrying Turkish characters — so adding a species without a label puts
"kasimpati" back in front of the artist and the suite says so.

## v2.1.1 — macOS setup guide, and drawings kept out of the app bundle
**Date:** 2026-07-28

**A real bug, found while writing the install guide.** `base_dir()` returned
`Path(sys.executable).parent` whenever frozen — correct on Windows, wrong on
macOS, where `sys.executable` is `PixelPomoArtKit.app/Contents/MacOS/…`. That
put `library/` **inside the .app bundle**: hidden behind Finder's "Show Package
Contents", and wiped without warning the moment a new version was dragged over
the old app. Every drawing the artist had made, gone, on update. Gatekeeper's
app translocation can also run a freshly-downloaded bundle from a randomised
read-only path, so writing beside it is not even reliable.

Frozen macOS builds now use `~/Documents/PixelPomoArtKit/`. Windows is
unchanged. Two tests pin both branches, because the failure is invisible on the
platform this is developed on.

**The build is Apple Silicon only.** The runner image is `macos-26-arm64`, so
the `.app` will not open on an Intel Mac. Stated first in both the README and
the in-zip guide rather than left for the artist to discover.

**`OKUBENI-MAC.txt` ships inside the macOS zip** — the Windows one was no use
there. It covers the Applications-folder step (translocation), and *both*
Gatekeeper paths: right-click → Open for macOS 14 and earlier, and System
Settings → Privacy & Security → Open Anyway for macOS 15+, where Apple removed
the right-click shortcut. Getting that wrong is a dead end, not an annoyance.
Turkish and English, same as the Windows guide.

**Tests:** 88 → 90.

## v2.1.0 — Mac build, and releases come from CI
**Date:** 2026-07-28

Three things had been sitting committed but unreleased since v2.0.0 on 25 July:
**Import PNG**, the drawable forest (20 trees, 10 bushes, 5 rocks), and the
relative path fix. They ship here.

**The Art Kit had no CI.** Every release so far was built by hand on one Windows
machine, which is also why there was never a Mac build: PyInstaller cannot
cross-compile, so a macOS binary can only be produced on a macOS runner. There
is no local workaround.

`.github/workflows/release.yml` now builds on `windows-latest` and
`macos-latest` from the same commit and publishes both zips into one release.
The spec grew a `BUNDLE` step guarded by `sys.platform == 'darwin'`, because on
macOS a bare PyInstaller binary opens a Terminal window beside the app and
Finder will not treat it as an application at all — it needs a `.app`.

**The one awkward part is deliberate and documented.** The spec bundles the
game's `gen_objects.py` into the binary, so the build needs a checkout of the
game repo as a sibling — and that repo is private. GitHub's built-in token
cannot read a second private repo, so the workflow takes a PAT from the secret
`APP_REPO_TOKEN` (fine-grained, read-only Contents on `hero-999-dev/pixel_pomo`).
If that token expires, releases stop; there is no silent-degradation path.

# Change Log — Pixel Pomo Art Kit

What was built, round by round. Newest first.

---

## v4 — the artist's window, redesigned on real feedback (2026-07-25)

**Date:** 2026-07-25

**Prompt (Turkish):** "simdi cizim alani, cok daha büyük olsun kare sayisi,
cünkü ilerde agac, evcil hayvan modelleri eklenecek, tüm orta alani kaplasin
kareler, ready colourse biraz daha renk ekle, pick colour kismina basinca
secmelik bir ekran cikmasin, sag alt taraf full renk secimi olsun, telefon
uygulamasindaki gibi mesela, yeni bir sekme olmasin, bana bu cizimi birde
nasil yollayacak export, bu palletteler ne ise yariyor, cizen kisi bunu nasil
kullanacak, birde anladigim kadariyla cizen kisi bu palette seylerini
kullanmasa daha iyi, sen onu sprite yaparken otomatik halledersin diye
düsünüyorum bunu da workflowa ekle, cizer kisi cizip export eder sonra sen
paletteleri kodlarsin gerekirse, cünkü hic bir manasi yok bu palettenin cizen
kisi icin, ve hep bir noktaya basinca diger noktalar da doluyor, sevmedim,
palette kismini direk cikar cizerin gözünden, arka planda sen motora
aktarirken incelersin, mirror x'i de sevmedim onu da sil gereksiz bir özellik
palette ve mirror x gitsin sag taraf full renk secme paneli olsun yukardan
asagi"

**The insight behind it:** the palette letters were engine plumbing leaking
into the artist's hands — and "pressing one point fills other points too"
was the engine's automatic rim/outline appearing around every painted
letter. Both confusions had the same root, so both got the same fix: the
artist now works in real colours only, where one click is one square and
nothing appears that wasn't painted. Turning a finished drawing into engine
letters + palette is the developer's job, in code, afterwards.

**Changes:**

- **Palette UI removed** from the window: no letter slots, no right-click
  palette editing, no grid/palette-literal menu items. The machinery stays
  in `engine_io` (`export_grid_literal`, `export_palette_literal`) and
  `History.repaint()` for the developer's conversion work — it just no
  longer exists in the artist's view.
- **MIRROR X removed** — didn't earn its place.
- **Full colour panel embedded** bottom-right, phone-app style: a hue strip
  over a saturation/value shade square, click or drag, no popup dialog. The
  `PICK COLOUR…` chooser window is gone.
- **Ready colours: 10 → 30** (game theme tones plus a pixel-art staple
  range), in a six-wide grid.
- **Bigger canvas for what's coming:** new drawings start **32x32** (trees
  and pets won't fit 16), `Rows…` became `Size…` (width and height, one
  undoable stroke), and selecting a drawing now **auto-zooms it to fill the
  centre pane**.
- README rewritten around the split: "Sending a drawing back (for the
  artist)" — send the library `.json` (lossless) or an exported PNG — and
  "Developer notes: letters and palettes (not the artist's job)".
  OKUBENI.txt updated to match, including how to send drawings back.

**Tests:** 81, all passing — mirror's test retired with it; new: a fresh
drawing is 32x32, the colour panel exists (and the palette slots/mirror
button demonstrably don't), a shade-square click sets a real RGBA ink,
`resize()` covers width as well as height.

---

## v3 — the new-species round trip (2026-07-25)

**Date:** 2026-07-25

**Prompt (Turkish):** "hepsini yap" — after v2, the model was asked what it
would suggest; it proposed five things and was told to do all of them. Also
confirmed in the same message: yes, this is a pixel-filling drawing app —
click a grid cell, it fills with the chosen colour/letter, exactly the
engine's coordinate + palette format.

**Changes:**

- **The new-species package** — before this, a flower the game had never
  seen could not actually be finished here: no way to set its species, no
  way to change its palette, no way to hand the developer its palette line.
  Now: `⋮ → Species…` names a drawing (validated to the engine's lowercase
  id form, since it becomes the sprite filename); right-clicking a palette
  slot recolours that entry for the whole drawing (`History.repaint()` puts
  the new palette on every undo snapshot, so undo restores cells but never
  silently reverts colours); `⋮ → Copy palette literal` produces the
  `_FLOWER_PALS` source line to pair with the grid literal; and
  `⋮ → Rows…` grows/crops the grid below (width stays the engine's 16), as
  a single undoable stroke.
- **FILL tool** — flood fill from the pressed cell, one undo step. `f` key.
- **MIRROR X toggle** — paints/erases/fills both halves at once; flowers
  are mostly symmetric, so half the clicks. `x` key. A switch, not a
  fourth tool, because it composes with all three.
- **Session backups** — the first time a session saves over an existing
  file, the file's previous content is kept as `<name>.json.bak`. Undo
  history dies with the window; "how it looked when I opened the app
  today" now survives.
- **README: "Handing a NEW flower to the developer"** — the four-step
  round trip (species, palette, draw in letters, hand back sprite + grid
  literal + palette literal).

**Deliberately not done:** CI (the suite imports the game's `gen_objects.py`
live from a sibling checkout that no runner has) and exe code-signing (a
certificate costs real money to silence a warning one person sees once).

**Tests:** 80, all passing — eight new across all four test files.

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

**Tests:** 72 at this version — three new: the Bresenham line is filled
exactly, right-click eyedropping picks letters and ignores empties, unknown
tools are refused.

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
