# Change Log — Pixel Pomo Art Kit

What was built, round by round. Newest first.

---

## v2.8.0 (in progress) — ninth test pass: a ruled guide, drawn arrows, names renamed and taken off, white and black grounds
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> guide kisminda her bölüm cizgi ile ayrilsin aralardaki mesafe korunsun ve basliklar sola dogru entegre olsun,ALL
> yanindaki ücgen asagi dogru okay ama yana dogru degil normal halde birde guide kapatirken ki x kösede pikselli
> duruyor büyüt ve saga endeksle scroll down ,upin hizasina, onun disinda alttaki sag sol oku pikselli duruyor,
> empty  ve pixelsin in basina total pikseli de yazalim , mirmiri Ola Górecka  olarak degistireli, Heroyu
> HeroDev999 yapalim,artistlerin adini degistime ve silme opsiyonu gelsin ,ayni sekilde labellarda da , label ve
> artist ekle bölümünde üc nokta olsun oradan labellar cikarilsin , LadyOfDynamite ismi yeni artist olarak
> eklensin, grid kisminda colour 1 ve 2 üc nokta hizasina cekilsin ayni sekilde alttaki renk menüsü de
> kenarlardan kisaltilsin esit olsun bos olan yere iki tane hazir stil gelsin Üste White , Alta Black, hazir grid
> ayari direk,iki renk direk siyah veya direk beyaz olsun , test art kite ekledim sanatcilara

- **The guide, ruled.** A hairline between one row and the next, the rows' own
  spacing kept round it; each heading flush left over an accent line; the
  sub-rows no longer indented by two spaces. The ▾ ALL row still described the
  sixth pass's filter - it describes the one checklist now.
- **Drawn, not typed: the arrows and the ×.** `theme.icon` draws a triangle or
  an X at four times its size and averages it down, so the slanted edges are
  smooth: the ALL arrow (the font's ▶ could come out as an emoji, bigger than
  the ▼ beside it), the colour strip's pager (a canvas polygon has no
  antialiasing on Windows), and the guide's close button - bigger, its right
  edge on the scrollbar's.
- **Total pixels** first under the canvas: `total · empty · pixels`; the
  cursor readout's "empty" is translated too.
- **Artists and labels, renamed or taken off everywhere**: a ⋮ beside every
  name in the label and the artist dialogs - Rename… (every drawing that
  carries it, the ticks and, for an artist, the colour following) and Delete
  (asked first; the drawings stay, the label or artist comes off them, an
  artist's colour is given back). The Drawing Patch 1 flowers are signed
  **Ola Górecka** now (was Mir); the artist had already renamed Mir and Hero
  (HeroDev999) and added LadyOfDynamite in the test kit.
- **The grid's ready grounds**: WHITE over BLACK between DEFAULT and the
  fields, each making both tones white or both black - a plain ground to judge
  the art on - with the cell lines darkened on a light ground rather than
  lightened into it. Each colour's name sits right beside its …, and the two
  fields are the same width.
- **One width down the tools pane.** Rows stretched into the room a hidden
  scrollbar leaves and ran 14 px past the colour grids and the colour panel,
  which cannot stretch. Every row is INNER_W now, centred with even margins
  while the bar is hidden, the block at the bottom lined up under it.

364 tests, all passing (was 356).

---

## v2.8.0 (in progress) — eighth test pass: dialogs in place, symmetry per drawing, LOOK, GUIDE
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> grid colour1 ve 2 de üc noktaya basinca sol üstten bir menü anlik gözüküp kayiyor,birde symmetry bazen mirror ve
> stick acik kaliyor farkli bir ekrana gecince yani semaya böyle alanin disinda kalmis sekilde görebiliyoruz, onun
> olmasinin önüne gecelim, onun disinda birde help kisminda en altta copyright önlemlerinin nasil calistiginin
> neyin ne oldugunu anlatan bir kisim ekleyelim, Helpin adi Guide olsun, birde squint görüntüsü var arkadaki
> tasarim tamamen yok oluyor bu ,  sagina check Look ekleyelim orada cizim kapali olsun sadece bakma icin olsun
> orasi, oraya tiklayinca iste oradan sekilin nasil calistigina bakmis olacagiz nasil göründügüne

- **No window in the corner first.** `theme.dark_title_bar` runs
  `update_idletasks`, which mapped every new dialog where Windows puts a new
  window - the top-left of the screen - before `run` moved it to its place:
  the grid colour picker (…), and the export, label, artist and size dialogs
  the same way. `theme.unseen` maps a dialog see-through (alpha 0) until it is
  placed, and `theme.reveal` shows it there; alpha rather than withdraw, since
  the dark title needs the window mapped - and an override-redirect menu, once
  measured while withdrawn, is never shown again by Tk. Menus go the same way.
- **Symmetry belongs to the drawing.** The mode and the line were the kit's, so
  they followed the artist into the next drawing, the line off its edge when
  that one was smaller. Each drawing now keeps its own (`_sym_frames`, like
  LOCK's frames): it comes back with its line, a drawing never given one opens
  OFF, and a line the drawing shrank away from - a resize, an undo - is taken
  off, the mode waiting for a click to place it again (`_keep_bar_inside`).
- **LOOK**, beside squint: the canvas shows the drawing as it looks - the empty
  cells in the canvas's own colour instead of the checkerboard, no cell lines,
  no symmetry line, no eraser outline - and nothing is drawn, erased, resized,
  cut, pasted or undone while it is ticked; a press says why, as LOCK's refusals
  do. Zoom, pan and the eyedropper still work.
- **GUIDE** (was HELP), in the four languages: GUIDE / REHBER / POMOC / HILFE on
  the button (the box is pinned to the English word, and PRZEWODNIK or
  ANLEITUNG would not fit it at any size), guide / rehber / przewodnik /
  Anleitung in its title. It ends with **how the work is protected** - what the
  corner and the watermark are, the name in the file, "made with", the export
  log and the fingerprint it keeps, why engine sprites stay clean, C2PA later -
  in the language chosen, where the rows above it are still English.

356 tests, all passing (was 352).

---

## v2.8.0 (in progress) — seventh test pass: one checklist, both marks, every corner translated, an eraser that keeps up
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> simdi copyright yaparken ikisini de yapma olsun, onun disinda snapshot sadece test modunda olsun, test
> özelliginde olsun, 160x60 actim orada snapshotu görebilirsin, ve all sectim hepsi tikli sonrasinda no artisti
> sectim kapanmak yerine diger sanatcilari siliyor, birde mesela hero sectim tikladim yukarda all tiki gitmis ama
> diger herseyin tiki gözüküyor bu sacma, ben hangiseyin tikini sectiysem onlar gözüksün, hero secebilirim ve hero
> sadece 2 tane otheri vardir sonrasinda yukaridan othera basarim ve bir tane daha tüm otherlar ve digerleri
> gözülür , bu arada every export is also written down in export-log.jsonl dedigin kisimda tikli olsun, yani
> kullaniciya kalsin tercih, birde su uygulamadan yapildi diye propertylere ekleyelim, ekleyebiliyorsak yada meta
> dataya ekleyelim, symmetry, squint, colour, ready colours, favourite colours, ink, kaydetin yanindaki durum
> raporlari, yenicizime basincaki kisimlar, soldaki üc noktali menü ve uzantilari  farkli dillerde calismiyor,
> birde 5 numarada önerdigin sertifika isini ilerde yapilacaklar kismina ekle, piksel pomo projesinin overview
> kismina ve pixel pomo art kiti de güncelle orada , eraser calisirken bug var söyle cok fps düsüyor gibi
> optimizasyon sorunu var gecikmeli geliyor , onun disinda altta pikselleri sag sol yapan kisimda sag sol en
> sagda olsun ve biraz daha belirgin olsun bir tik daha büyük , son olarak all kisminda, allun yanindaki ikon
> biraz daha net olsun yana dogru all'a dogru olsun basinca asagi döndürsün yönünü, birde sag üstte durum
> raporunda anlik raporda bazen metinin hepsi görünmüyor metin uzun kaliyor kutuya onu da düzeltelim

The artist's three F12 snapshots (the first ones this kit has sent back) showed
FIT right at 2x - a 160-wide drawing in a 455-px pane, where 3x would be 480 -
the filter's menu mid-state, and the status corner cutting "exported
House3.png" to "rted House3.png".

- **One checklist.** Labels and artists were two filters combined with AND,
  each with its own ALL: an artist picked from ALL left every label ticked above
  a list of one artist's work, and NO ARTIST picked from ALL unticked the other
  artists while every label stayed ticked. Now one set of ticks over both, and
  a drawing is listed if its label OR its artist is ticked - "whatever I tick
  is what shows": Hero lists Hero's two; OTHER after it adds every other OTHER
  ("bir tane daha"). From ALL a click ticks just that row; ticks are always
  exactly what is listed. The arrow is a clearer ▶ at the words, turning ▼
  while the list is open.
- **Both marks.** CORNER and WATERMARK are two switches now, either, neither or
  both (the watermark laid first, the corner on top). The record is a tick too,
  on by default, the artist's to turn off. And every image export says what
  made it: Software "Pixel Pomo Art Kit" (Explorer's Program name), comment
  "Made with Pixel Pomo Art Kit", and an SVG opens with it - whatever the
  artist chose about their own name.
- **F12 is the TEST build's.** Not bound, and not in HELP, in a release.
- **Every corner in four languages.** The tools pane's headings (Ink,
  Favourite colours, Ready colours, Colour, Symmetry, squint) were built once in
  the starting language and never re-texted; the status messages, the new
  drawing and resize dialogs (presets included), the label and artist dialogs,
  rename, delete, import, the favourites menu, the update and save dialogs and
  the startup messages were English outright; the row ⋮ menus were fixed at
  build time. All of it is in the four tables now (173 keys each, placeholders
  checked), and a row menu reads its labels when it opens. The HELP body is
  still English.
- **The eraser.** Each erased cell was a canvas rectangle of its own, and the
  whole 16 × 16 footprint was re-erased and re-drawn at every step, cells long
  empty included: one stroke across the 160 × 60 left 38,562 items on the canvas,
  all redrawn on every move. Now only cells that held something are erased, and
  each lands in the view's own picture (`PhotoImage.put`, in C): 18.8 ms a step
  → 2.6 ms (worst 49 → 8), 2 canvas items instead of 38,562, release 51 → 23 ms.
  Painting goes the same way.
- **The colour pager** sits at the strip's far right as two solid triangles,
  a size up, where it had trailed the last colour as two thin brackets.
- **The status corner** is as wide as its message (a very long one is cut in
  the middle, at 48 characters), where a fixed 14 characters cut off the start.
- The Pixel Pomo overview (Overview/generate.py) has a **Later** list, with
  Content Credentials (C2PA) signing for exports on it, and its Art Kit card,
  mind-map branch and module notes follow the kit as it is now.

352 tests, all passing (was 340).

---

## v2.8.0 (in progress) — sixth test pass: the artist's mark on exports, F12, one artist at a time, a fit that holds, the 2 × 2 board back
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> 1, 2 ve 4'ü ekle, F12 kısayolunu da yap birde arkadaki gridlerin 2x2 2x2 den farkli bir sekle gecmis
> eski versiyonlarla karsilastirinca onu da düzeltelim, birde sadece mir diyorum gözükmüyor ikinci bir
> artist de ekledim sadece onu secsemde olmuyor karisiyorlar birbirlerine , fit halen düzgün degil mesela
> 160x60li untitledte yapiyorum görebilirsin

"1, 2 and 4" are three of the five layers proposed for protecting the artists'
work: the name inside the file, the name on the picture, and a record of every
export (not taken: an invisible LSB mark, and C2PA signing).

- **The artist's mark (`provenance.py`).** The export dialog asks, under the
  background: a signature on the picture — NONE, CORNER ("© 2026 MIR" in the
  kit's own pixel letters, light with a dark rim, about a twentieth of the
  picture's shorter side) or WATERMARK (the same, faint, in staggered rows over
  the whole picture) — and ☑ name and © inside the file. Both remembered, like
  the background. Drawn into the file's own pixels, previewed, stepping down to
  a shorter form when the name does not fit, refused (with the way to fix it)
  when the drawing has no artist. Inside the file: PNG tEXt/iTXt and XMP, JPEG
  EXIF (ASCII fields folded to plain letters, XPAuthor/XPTitle in UTF-16 with
  the name as written) plus XMP and a comment, SVG title/desc/Dublin Core.
  The engine sprite stays clean, on purpose.
- **`export-log.jsonl`.** Every export, engine sprites and JSON included: time,
  file, SHA-256, drawing, size, artist, the drawing file's own SHA-256, how it
  was marked, and the export id its XMP carries. Each line holds the digest of
  the one before; `provenance.verify` finds the first link that no longer
  matches.
- **F12, a snapshot.** The window as it is on screen (a dialog or menu over it
  included), cut from a screen grab at the window's real-pixel bounds from the
  compositor — Tk's own coordinates are scaled on a 125/150 % display and would
  crop the wrong rectangle — plus a JSON of what the view was: zoom, fit zoom,
  pane, camera origin and scroll region, visible cells, the drawing, the
  filters. Into `snapshots/` in the data folder. With no screen to grab the
  JSON is still written and says why.
- **"sadece Mir diyorum gözükmüyor ... karışıyorlar".** Three faults. A label
  still ticked from before (OTHER) and Mir's flowers made "only Mir" an empty
  list: a click that would list nothing only because of the other group now
  clears that group. A click on a second artist ADDED them to the first: the
  artist group is one artist at a time now (a click on the one shown lists
  every artist again). And a row that came back was packed at the END of the
  list, so every filter change shuffled it: rows out of order are put back in
  the library's order.
- **The checkerboard, 2 × 2 again.** Every version drew ten squares a side of
  whatever the drawing was; the viewport renderer (fourth pass) put the board
  into the art tile cut to whole cells, and ten into 16 cells came out 2, 2, 1,
  2, 1… wide — ten into a 160 × 60 banner, as 16 × 6 slabs. Now every square is
  2 × 2 cells on every drawing, doubling while it would be under 4 px on
  screen (1x: 4 cells; 1/n x: exactly 4 px of blocks). The board is in the
  tile only; the 100 checker items under it are gone.
- **FIT that holds.** Simulated on the 160 × 60 in every camera mode, after
  extreme zooms and pans: FIT itself fitted and centred every time. What was
  not right is what happened NEXT — fold the library with ☰ and the art sat
  off-centre in the wider pane; unfold it and a fit made for the wide pane ran
  off the narrow one. A fitted view now follows the pane until the artist
  zooms or pans. Below 1x, the free camera's one-cell rule kept a third of a
  pixel on screen — none, once floored; it keeps a whole pixel now. If FIT is
  still wrong after this, an F12 of it will show exactly how.
- The startup messages (migration, refused folder, unreadable files) use the
  kit's own boxes, like every other popup.
- `build_test.ps1` builds with `--clean`. With nothing changed since the last
  build, PyInstaller judged the .exe up to date and never wrote it, and the
  script reported that as a file held open.

340 tests, all passing (was 312).

---

## v2.8.0 (in progress) — fifth test pass: the eraser's outline, the artist layer, Drawing Patch 1, big drawings that keep up
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> elektron testi tarzi testler yapip canli bakma sansin yok mu ?, birde 1,2,3 düzgün calisiyor eline saglik, birde
> simdi symmetry de stick yerine gerceklestirecegimiz yeni metodu aciklayacagim , ilk olarak silgiye basinca
> kayboluyor silmeye devam ediyor ama kaybolmasini istemiyorum, yada silginin yarisi alanin disina cikinca
> silginin cizgisinin takilmasini engelleyelim birde fit kismi cok büyüklerde calismiyor birde üc noktalara
> artist ekleyelim bu artist labeli olacak, ve exportlarda artist bookmarki ayari istiyorum yapabilecegimiz
> kadar yapalim ki eserlerin calinmasini istemem , bunun icin mümkün metodlari arastirip uygulamaya eklemeden
> önce önerini sun onun disinda diger kisimlari ekleyelim ,artistlerin labeli farkli bir katman olsun üc
> nokta ile normal labellarin arasindaki kisimda olsun artistlerin bas harfi olsun sadece buradaki farklilik
> her artist icin random farkli bir renk atansin, ve en son pixel pomo sürümünde eklenen 5 model de pixel pomo
> art kite eklensin artiste mir yazalim , birde sol üstte artiste göre filtreleme olsun all icinde

- **The eraser's outline stays with it.** It was skipped while erasing, so it vanished
  when erasing began - or, until a repaint, stayed stuck where the stroke started.
  `_draw_ghost` draws it on every step of a stroke and after every repaint. An eraser
  whose footprint still covers the drawing is erasing wherever the pointer is: no edge
  grab (half of it past the edge used to catch on the resize band), and a press with
  the pointer beyond the edge erases the border cells under it.
- **FIT on a very big drawing.** It chose the right zoom, but took seconds - 7.6 s on a
  4096-cell square - turning the same millions of cells into pixels again for each
  picture. `_rendered_image` renders the open drawing once per change (a Pillow image,
  keyed on a content version every change bumps, mid-stroke too); the zoomed-out view
  (`_tile_image`), both corner pictures and the thumbnail crop and average it in C.
  FIT: 0.20 s at 4096², 0.07 s at 2000². A new 4096² drawing: 1.96 s, was 27.9 - a
  blank one skips rendering altogether, `is_letters` asks the distinct values not every
  cell, a letter row is joined in C, and `store.dumps` writes one ROW a line instead of
  one number a line (37 MB for a 2000² square; a letter file is byte for byte as before).
- **The artist, a layer of its own.** `Drawing.artist` (saved; files before it read as
  none). ⋮ → Artist… (the label dialog's other kind). On the row, between the label
  chip and ⋮, the artist's initial in that artist's own colour - random for each new
  artist, as far as possible in hue from the ones already given out, and kept in the
  settings. The ▾ ALL checklist has an ARTISTS group, each row in its artist's colour;
  it combines with the labels (flowers by Mir), and a new drawing or import joins the
  ticked artists the way it joins the ticked labels.
- **Drawing Patch 1.** The game's #v36.1 ships anthurium, pilea and sundew as the PNGs
  Mir drew, not generator output. The kit reads them from flutter/assets/objects (and
  bundles them for a build with no checkout), brings them back to their 16 × 16 cells,
  labels them flowers and signs them Mir. A library from before gets them on its next
  start (`seed_missing_kinds`). Exported, each is the shipped sprite pixel for pixel;
  anthurium, the single form, exports as `flower_anthurium.png` with no model number.
- Not yet, on purpose: the artist mark in exports (a proposal first, as asked), and the
  method replacing STICK (to be described).

312 tests, all passing (was 299).

---

## v2.8.0 (in progress) — fourth test pass: below 1x, corner pictures that keep every cell, a clean fold
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> simdi 1px e aliniyor current ama yandaki squint ve 1/11x cok dogru degiil yani hassas degil aktariken buglar
> oluyor ve bazi kisimlar aktarilmamis birde söyle bir problem var mesela 600 ve 600 yaptik sag altta 1/10x e
> kadar squinte kadar kücülme hakki olsun geriye gidince ana ekranda cünkü ana ekranda 1x oluyor yani sag
> alttaki en kücük kisma kadar kücülme olsun hep, ve üc cizgiye basip paneli kapatip acarken takilmalar bazi
> parcalarin sanki kesiliyormus ve geri birlesiyormus gibi imaji veriyor özellikle üst menüde , birde soldaki
> gene üc cizgiye basinca altindaki scroll down ,up kismi yok olmuyor bunun cözülmesi lazim

- **Corner pictures that keep every cell.** The 1/n x preview, the squint and the
  library thumbnail of a big drawing kept every n-th cell and dropped the rest, so a
  line one cell thin was in them or not by where it fell. `raster.reduce` averages each
  n × n block instead (a box filter - Pillow in C, the same sum by hand without it),
  premultiplied so a half-covered block is half as opaque rather than darkened;
  `raster.over` / `on_colour` mix such a pixel with the background it sits on.
- **Below 1x.** A 600-wide drawing stopped at 1 px a cell while the corner showed it at
  1/10x; the view now goes down to that same 1/n x (`min_zoom`: the longer side over the
  1x box, rounded up) - 1x as before for anything the box holds. `ZOOM_OUT_STOPS`
  1/64 … 1/2 join the ladder, with the drawing's own floor always on it; `fit_zoom`
  gives the largest 1/n that fits a drawing bigger than the pane. The zoom is an exact
  `Fraction` down there (in floating point 3 // 0.1 is 29, and the pointer would paint
  the wrong cell); every coordinate that reaches Tk is turned into a number Tk can read,
  since a Fraction would arrive as the string "7/2". At 1/n the view renders the visible
  cells, averages n × n blocks and lays them on the checker (`_tile(..., n)`); the
  readout says `1/10 px`, and a pan or an autoscroll is at least one pixel.
- **A clean fold.** The ☰ slid the whole canvas pane 200 px and Windows repainted it
  widget by widget - the camera strip visibly cut apart and joined back.
  `theme.held_paint` holds the window's painting (WM_SETREDRAW) while the layout, the
  strip's scrollbar and the drawing settle, then shows the result in one frame. The
  list's scrollbar now leaves the rail with the list, and comes back under the ☰.

299 tests, all passing (was 289). New: the view zooming out to the corner's 1/10x and
no further, with exact pixel-to-cell arithmetic; fit below 1x and nothing fractional
reaching Tk; the zoomed-out view equal to each block's average on the checker; a
one-cell line kept by the 1/10x and squint pictures; the fold taking the scrollbar
with it; `raster.reduce` (a thin line, half coverage, cut-short blocks, Pillow and the
hand-made sum agreeing once laid on the background) and `raster.over`.

---

## v2.8.0 (in progress) — third test pass: a steady LOCK, a label checklist, edges out of the way, no size cap
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> simdi   3. Kilitliyken sol kenardan büyüt, ardından Ctrl+Z yap. bunu yaptim calisiyor, kilitliyken
> yakinlastirma yaparken lock isareti yanip sönüyor, cakisiyor gibi ,soldaki labellarda label isimlerinin
> yaninda tik olsun all olunca hepsi tikli ama onun disinda birkacina tiklayip sadece birkacinin gözükmesinin
> isteyebilirim,24x den itibaren kücülünce kenarlarda cizmek zorlasiyor büyütme kisimi cakisiyor onun daha
> hassaslastirilmasi lazim ic taraftan, birde en fazla 64x64 yapabiliyoruz o limiti tamamen kaldiralim,
> tamamen custom yapalim

- **LOCK, steadily.** The LOCK button no longer blinks on a refused notch - under a
  spinning wheel it read as LOCK and the zoom fighting. The corner still says *camera
  locked*, and holds it: `_set_status` keeps ONE pending fade now, so a message repeated
  faster than it fades stops flickering (and an old fade can no longer dim an error that
  replaced it).
- **The labels are a checklist.** The filter is a set of labels (None is ALL). ▾ ALL
  opens ☑ / ☐ rows (`PopupMenu.add_checkbutton`): under ALL every label is ticked; a click
  from there lists just that label, further clicks tick more on or off, and the list
  stays open while they do. Nothing ticked, or everything, is ALL. The button reads
  `BUSH + TREE · 30`, or `3 LABELS · 44` when the names do not fit. A new drawing takes
  the filtered label when there is exactly one; a new drawing or an import the filter
  would hide adds its label to the ticked ones instead of wiping the filter.
- **Edges out of the way.** The grab band was 10 px either side of an edge - 40% of an
  edge cell at 24 px a cell, all of it at 8. Outside the art it still is 10 px; inside
  it is an eighth of a cell, never more than 3 px (`EDGE_GRAB_INSIDE`), and nothing at
  all below 8 px a cell.
- **No size cap.** New drawing and Size take any width × height. Past 512 × 512 the
  dialog asks first (`BIG_CELLS`); more than 4096 a side is refused as the typo it is
  (`HUGE_SIDE`), since 60000 for 600 would take the window down. The eraser keeps its
  own 64 (`ERASER_MAX`). What makes a big drawing workable rather than frozen:
  - the main view renders only the visible cells plus a one-cell margin (`_tile`) and
    lays them on the checker itself, so the image is opaque - Tk's transparency mask for
    scattered pixel art took over a second on a 256-cell square, opaque it is 2 ms;
  - `engine_io.render` takes a shortcut for a drawing with no palette letter - exactly
    the generator's answer (asserted for every seeded drawing and a random 300 × 200
    one), about twelve times faster;
  - thumbnails and previews shrink to their boxes (`raster.shrink`; the 1x caption then
    says 1/2x, 1/3x…) and sit baked onto their background;
  - one full render per stroke instead of three; the pixel totals counted once per
    change, not on every mouse move; the colour strip counted in C; `png_bytes` packs a
    row without holes in one call; `store.to_dict` leaves colour tuples to `json.dumps`
    (the same file, byte for byte);
  - the undo stack holds at most `History.CELL_BUDGET` (24 million) cells of snapshots,
    so a big drawing keeps a shorter undo memory instead of eating the machine's.
  - Measured (scattered pixel art, 900 × 800 pane, fitted): 256² stroke end 0.11 s,
    repaint 0.06 s; 512² 0.30 s / 0.19 s; 1024² 1.5 s / 0.65 s; a pointer move at most
    0.3 ms at every size.
- HELP and README follow: the checklist, any size, the grab outside the edge.

289 tests, all passing (was 276). New: the checklist (toggle rules, the menu staying
open, ticks re-read in place), the imported drawing's label joining the filter, the edge
band inside and out at five zooms, any size and the eraser's own limit, the Size
dialog's question and refusal, previews and thumbnails of a big drawing, the visible
tile equal to the whole render cut to the view (rims included), the steady status
under a spinning wheel; the render shortcut against the generator, `raster.shrink`,
`png_bytes` either way, the undo cell budget, and the saved file unchanged by the
tuple shortcut.

---

## v2.8.0 (in progress) — second test pass: LOCK holds the whole camera, the kit's own popups
**Date:** 2026-09-23 · not tagged yet

Prompt (verbatim):

> üc cizgi fit in hizasinda degil veya allin, onun disinda lock kismi sabitliyor ama zoom out yapilabiliyor
> olmamasi lazim, yani lock halinde kamera acisi sabit olmasi lazim, icon copy adini icon yaptim, lock
> tamamen düzgün calismis olmasi lazim , mesela isim sec diyorum, cikan menü gri kirmizi klasik menü yada
> renk sec diyorum gridin oradada klasik menü tüm popup menülerinin hepsi görsel stil olarak uygulamaya uygun
> olsun

- **☰ on the ALL / FIT line.** The library's ☰ had no top margin while ALL and the
  camera strip (FIT) had `PAD`; it now gets the same `pady=(PAD, 4)` and the same
  button height (`pady=4`) - all three are 23 px tall, 8 px from the top.
- **LOCK holds the camera - all of it.** Every other mode leaves the zoom free, as before.
  - The wheel, `+`/`-`, FIT, Shift+wheel, Space+drag, the middle button and the
    scrollbars leave the zoom and the view alone (`_camera_frozen()`), and a stroke
    dragged against the pane's edge no longer autoscrolls - it used to repaint the
    whole view on every motion event with nothing able to move.
  - Anything aimed at the camera blinks the LOCK button and says *camera locked* in
    the status corner; FIT is dimmed while locked. A dead wheel with no word of
    explanation reads as a frozen app.
  - Each drawing keeps its own frozen view while LOCK stays on (`_lock_frames`): lock
    A, look at B (fitted, centred, frozen), come back to A exactly as it was left.
    Leaving LOCK forgets them all.
  - Starting up in LOCK freezes the fitted, centred view, not the canvas origin -
    which pinned the art to the pane's top-left corner.
  - A left or top edge drag moves the frozen point with the art: held still, the art
    jumped a cell for every cell added while the grabbed edge stayed put. Undoing or
    redoing that drag keeps the art still too, in every mode - `Drawing.shift`
    (session only, never saved) records how far left/top edge changes pushed the art,
    and `_follow_shift` moves the view by as much. Before, an undone left-edge grow
    jumped the drawing sideways; under LOCK there was no way to pan it back.
  - The one re-frame: a shrink (the Size dialog, a smaller window) that leaves none
    of the drawing inside the frozen view fits and centres it again, still locked.
- **The kit's own popups.** New `art_kit/dialogs.py`:
  - `PopupMenu` for the filter, row ⋮, favourite and language menus: the row about to
    run wears the accent, the arrow keys / Enter / Esc work, it opens upwards instead
    of off the bottom of the screen (and never over the button it drops from), and it
    stays on the monitor it was opened on.
  - `showinfo` / `showwarning` / `showerror` / `askyesno` / `askstring` in MATCHA
    colours with the call shapes of the modules they replace; a coloured strip marks
    a warning or an error, and Delete's question is a warning.
  - The grid's `…` opens `ColourDialog` (the kit's hue strip + shade square) instead of
    the Windows colour chooser. The checkerboard follows it live, CANCEL puts it
    back, OK is one undo step however far the picker travelled.
  - `theme.setup` no longer styles `tk.Menu`: there is none left. New i18n keys
    `ok` / `yes` / `no` / `cam_locked` in all four languages.
  - Native on purpose: the file picker behind IMPORT PNG and the exports - it is
    Explorer's own window (Quick Access, search, OneDrive), and a Tk copy would be a
    worse tool in a nicer colour.
- HELP no longer describes the corner zoom this version replaced; it has the camera
  strip, LOCK and panning instead. README likewise.
- "icon copy" → "icon" was the artist's rename (in the test library's copy - the real
  library still says "icon copy"); nothing to change in code.

Process note: the first half of this round was written by the Lea shadow run, which
does not stay in its sandbox for a project outside the workspace - it edited this
repository directly, and rebuilt `dist\PixelPomoArtKit.exe` from unreleased code. That
work was reviewed, kept and finished in the main session.

276 tests, all passing (was 261). New: LOCK freezing the zoom, swallowing every pan
and saying why, dimming FIT, a frozen view per drawing, starting up in LOCK, re-framing
only a lost drawing, the locked left-edge drag and its undo; the popup's placement and
keyboard, the message boxes' answers, `ColourDialog`, the grid picker's live preview;
`Drawing.shift`; and `test_no_native_menu_or_dialog_is_left`. The row-menu tests read
`PopupMenu.labels()`; the every-mode zoom tests skip LOCK.

---

## v2.7.0 — update relaunch, SVG, languages, stick/mirror lines, bugs, corner zoom
**Date:** 2026-09-18

Fifteen items. Drawings stay JSON in the per-user data folder; an update still
only swaps the program. Engine sprites for the game remain PNG (x16). SVG is
the share format that stays sharp when zoomed.

1. Windows self-update no longer inherits the old kit's `_MEIPASS`/`_PYI_*`
   variables (the "Failed to load Python DLL …\_MEI…\python312.dll" dialog).
2. WITH / WITHOUT GRID sits just above UPDATE / HELP.
3. New-drawing Flower preset is 16×16 (plus a Bug 8×8).
4. Export SVG (vector rects, Illustrator-sharp at any zoom); PNG/JPG remain.
5. Empty-pixel count to the left of `pixels N`.
6. A separator under Eraser, above Grid.
7. Ctrl+C then click a cell to paste — including in another drawing.
8. FILL with a selection paints the rectangle; clicking SELECT again (or Esc,
   or a click outside the drawing) dismisses the stuck box.
9. Colour-strip overflow: `… ‹ ›` pages the rest of the colours.
10. LANGUAGE (EN / TR / PL / DE) left of UPDATE / HELP; "click to resize" gone;
    button boxes keep their size, type shrinks.
11. ☰ above the library scrollbar, aligned with ALL, collapses the list.
12. MIRROR and STICK are bright lines *between* pixels (not a cell overlay).
    MIRROR still live-mirrors a stroke. STICK of length 5 copies those 5
    rows/columns across the line.
13. Pixel Pomo bugs (bee, butterflies, ladybugs) with label `bugs`, seeded
    into existing libraries.
14. Library = JSON. Engine sprite = PNG the game loads. Export JSON to share a
    drawing file; update never replaces drawings.
15. Drag the drawing's bottom-right corner to enlarge on-screen pixels;
    Ctrl+Z undoes that zoom.

---

## v2.6.0 — labels, select/copy/paste, a strip under the canvas, and exports that just write the file
**Date:** 2026-09-17

**Prompt (Turkish/English, abridged, eleven items):** replace Species… with
labels that show on each row and filter from the top-left; show-with/without
grid under Symmetry and, along the bottom of the middle pane, which colours the
drawing is made of; export with grid; engine export refuses sizes and throws an
"overwrite" dialog — let any size through and fix the naming; a pixel counter
bottom-left, per marked row; auto-scroll when dragging to the edge while zoomed
in; a Grid section above the colour code with two grid colours (typed or from a
picker) and a default, and the grid not covering the corners; eraser size in X
and Y; drag to resize the symmetry bar; export filenames editable, sprites
overwriting each other's names; copy and paste a selected part of the motif and
move it, with a button and a key (`s`).

### Labels instead of species (item 1)

`Drawing.label` — free text, saved in the JSON (`from_dict` accepts a missing
or non-string one), copied with the drawing. Seeded drawings are labelled by
kind: every shipped flower `flower`, props `tree` / `bush` / `rock`, imports
`import`; a library from before labels gets the same defaults on load. The
row shows the label as a chip left of `⋮` (click it → `LabelDialog`: labels in
use as buttons, a field for a new one, NO LABEL); `⋮ → Label…` does the same
and **Species… is gone**. Top-left of the library, `▾ ALL · 59` drops a menu of
labels with counts (and *No label* when any); the filter hides rows rather
than rebuilding them; a drawing created or imported under a filter takes that
label, and one that would be hidden drops the filter — nothing the artist just
made can vanish.

### Exports (items 3, 4, 10)

The two screenshots were the strict developer path (`export_engine_sprite`:
engine names, engine sizes, a "this will overwrite" question) in the artist's
hands. `⋮ → Export engine sprite…` is now **one ordinary save dialog**: the
filename is editable right there (default: the engine name for a shipped
species/prop, else a slug of the drawing's name), any size goes through at x16
(`engine_io.export_sprite`), and "replace?" is the OS's own question. The
strict function and its tests stay for the developer.
**Export PNG with grid…** draws one-pixel lines on every cell boundary
*including the last pixel row/column*, so the border closes on all four sides
(`with_grid_lines`).

### The pane and the canvas (items 2, 5, 6, 7, 8, 9)

- **Under the canvas:** `pixels N · row r: k · col c: k` (or `selection
  w×h: n`), then the drawing's colours **left to right**, most-used first,
  each with its code and count — click one to make it the ink — and on the
  right the cell and colour under the cursor.
- **Grid** section above the ink: `colour 1` / `colour 2`, the two
  checkerboard tones, as coloured entries (type a code, Enter) with `…` for
  the system picker and DEFAULT. **The checker now covers every corner**: the
  blocks were `width // 10` wide, which left a strip whenever the size was not
  a multiple of ten; edges are integer partitions of the full size now. The
  cell lines stop one pixel short of the far edge so the last line is visible.
  **WITH GRID / WITHOUT GRID** under Symmetry; the line colour is derived
  from colour 2.
- **Eraser W × H** under UNDO/REDO, centred on the pointer, with a ghost of
  the footprint under the cursor.
- **Auto-scroll:** a drag within 24 px of the visible edge scrolls one cell
  that way (`xscrollincrement` = zoom), so a line continues past the edge
  while zoomed in.
- **Resize the bar by dragging an end:** for a bar of 3+ cells the first and
  last cells are grab handles (cursor becomes the double arrow); the other end
  stays put, the length follows the pointer, dragging past the other end
  flips. The middle still moves it.
- The tools pane **scrolls** (it outgrew 820 px) with the previews / size /
  UPDATE / HELP fixed at the bottom; the help overlay scrolls too.

### SELECT, copy, paste (item 11)

A fourth tool, `s`. Drag a rectangle (dashed, in the work green). **Ctrl+C**
copies the cells, **Ctrl+X** cuts (one undo), **Delete** clears. **Ctrl+V**
puts the clipboard down as a **floating block** at the selection's corner (or
the top-left of the view) — drawn as an image with a dashed accent border,
never yet on the drawing. Press inside it and drag, or nudge with the arrow
keys; **Enter** or a click outside stamps it (one undo, empty cells leave the
art alone) and the placed area stays selected. Pressing inside an existing
selection **lifts** those cells off the drawing (one undo) so a part of the
motif can simply be moved. Esc drops a floating block where it is, then clears
the selection — never destructive. Switching tool or drawing drops a block
first. `Drawing.region / stamp / clear_region / count / row_count /
col_count` are the pure pieces.

**Tests:** 145 → 168. Model +5 (label, counts, region, stamp clipping/skip,
clear); store +3 (label round-trip, missing/bad label, an old library gets
kinds labelled and `labels()`); engine_io +4 (any-size x16 export while the
strict path still refuses, suggested names, grid PNG lines closed on all four
sides and absent when not asked, default labels for everything seeded);
settings +2 (grid colours validate/reset, show_grid + clamped eraser persist);
smoke +9 (labels on chips / filter hides rows / Species gone; a new or
imported drawing under a filter; eraser footprint; select→copy→paste→drag→
nudge→commit as one undo; lift by pressing inside and drop by clicking
outside, each one undo; cut/delete; bar-end drag resizes and flips; grid
lines toggle, colours, checker corner-to-corner; the strip's counts, colours
and cursor readout). Auto-scroll was checked by hand with synthetic events
(scrolls up-left at the top-left edge, down-right at the other).

## v2.5.0 — a symmetry bar that moves, STICK, import, a portable program and updates that keep the drawings
**Date:** 2026-09-16

**Prompt (Turkish, abridged):** the symmetry bar gets stuck and cannot be
moved afterwards; put symmetry under the colour panel and make it richer — a
"bar placed" mode without the line through the middle, and a "stick" version
("there are five purple cells over there, you click in line and five purple
cells appear"); an IMPORT under NEW DRAWING that saves imported sprites into
the program; moving the .exe must never lose anything; an UPDATE next to HELP
— Windows updates itself from GitHub, macOS says a new version is out and opens
the page — and, above all, **an update must never take anyone's drawings.**

### The symmetry bar (`symmetry.py`, the block under Colour)

"Stuck" was real: after placing, the only way to move the bar was a click on
the hint text, which nobody found. Now **pressing on the bar picks it up** —
drag it, release to drop (the cursor turns into the move cross over it); a
**PLACE BAR** button re-arms click-to-place; nothing is painted or recorded
while moving. The line through the middle is gone: the bar is one cell wide,
just its outline is drawn.

Three modes, one row of buttons, `m` cycles them:

- **OFF** — plain painting.
- **MIRROR** — the bar as before.
- **STICK** — every click paints `length` cells in one go, to the right
  (`─ 180°`) or downward (`│ 90°`), starting at the click. A ghost of the run
  follows the cursor so it can be lined up. `symmetry.stick()` /
  `expand_stick()` are pure; a stick of length 1 is an ordinary click.

Orientation, length and mode persist in `settings.json`; an old settings file
without a mode still reads.

### IMPORT PNG… (`app.import_png`)

Under NEW DRAWING. `engine_io.import_png` existed since #v34.10 (profile →
sRGB, alpha snapped, x16 downscale) but had no button. Several files at once;
each becomes a drawing and is **saved into the library immediately**; a
summary names what came in and what was changed, and what was refused and why.

### Where the drawings live (`paths.py`) — the portable program

Up to v2.4.0 the Windows build wrote `library/` **beside the .exe**. Move the
.exe, unzip a new version into a new folder, and the drawings were "gone".
Nothing can be stored *inside* a running .exe — it is read-only while it runs,
and a new version is a different file — so the rule is the opposite: **the
data never lives next to the program.** Frozen Windows builds now use
`%LOCALAPPDATA%\PixelPomoArtKit\` (Mac stays on `~/Documents/PixelPomoArtKit`,
source runs stay at the repo root). The .exe can sit anywhere, be moved,
deleted or replaced; the drawings stay put. The first run of v2.5.0 finds an
old beside-the-exe `library/` and **copies** (never moves) every drawing it
does not already have, then says so in a dialog naming the new folder. The
help overlay shows the folder and has an OPEN FOLDER button.

### UPDATE (`updater.py`, `version.py`)

One `VERSION` string; the release tag is `v` + it, and the spec reads it for
the .app's plist. UPDATE asks `api.github.com/repos/…/releases/latest` (the
repo is public; no token) on a worker thread. A frozen build also checks once,
quietly, 2.5 s after opening: a newer release turns the button into
`UPDATE ● vX.Y.Z`, anything else says nothing.

- **Windows** downloads `PixelPomoArtKit-windows.zip` (progress in the status
  label, to a `.part` file first), **zips the library to
  `<data>/backups/library-before-<tag>-<stamp>.zip`**, unpacks the new .exe
  beside the running one as `.new.exe`, writes a small `.cmd` that waits for
  this process to exit, keeps the old .exe as `PixelPomoArtKit.old.exe`
  (rename it back to revert), moves the new one into place and relaunches —
  then the kit saves and closes. A running .exe cannot overwrite itself, hence
  the hand-off. **Exercised for real** with the built v2.5.0 .exe: staged, hand
  off, exited, swapped, relaunched, data folder intact. The first dry run did
  NOT swap: a `DETACHED_PROCESS` cmd has no console and `tasklist | find`
  blocks on the pipe forever; `CREATE_NO_WINDOW` gives it a hidden console and
  it works.
- **macOS / source** show "vX is available" and open the release page.
  Replacing a `.app` behind Gatekeeper's back is what quarantine exists to
  stop, and the artist already has the two-step recipe.

**Why an update cannot lose drawings, twice over:** the data folder is not
beside the program on either platform, so swapping the program cannot reach
it; and the Windows updater zips the library before touching anything.

### Layout

The pane had to fit a 820px window with the symmetry block added: swatches
went from six a row to eight, the shade square from 120 to 100px, the squint
preview from 8x to 6x.

**Tests:** 120 → 145. New `test_paths.py` (6: LOCALAPPDATA on frozen Windows
and the legacy folder it migrates from, Documents on Mac, migration copies
drawings + settings and leaves the old folder, never overwrites, is
idempotent) and `test_updater.py` (9: version parsing incl. `-rc` suffixes,
`Release.is_newer`, `check()` against a fake opener with the right URL and
User-Agent, a bad payload raises, `download()` reports progress and leaves no
`.part`, `backup_library()` zips every drawing, `stage_windows()` unpacks the
.exe and writes a script naming the pid / `.old.exe` / the moves / the
relaunch, a zip with no .exe is refused); `test_symmetry.py` +4 (stick runs
right/down, length 1 = a click, clamping, `expand_stick` dedupes);
`test_settings.py` +1 (old file without a mode); the smoke suite +5 (STICK
paints a run as one undo and persists, pressing on the bar drags it without
painting or recording a stroke and PLACE BAR re-arms, `m` cycles the three
modes, `import_png` lands in the library saved with a row, a newer release
lights the UPDATE button and a current one / a failed silent check do not).
The old "frozen Windows writes beside the exe" test now asserts the opposite.

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
