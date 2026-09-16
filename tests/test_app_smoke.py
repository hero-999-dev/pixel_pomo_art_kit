import tempfile
import unittest
from pathlib import Path


from art_kit import app, engine_io, store, symmetry
from art_kit.settings import Settings

# Everything the app seeds: two models per flower, plus the forest props the
# engine loads (#v34.8). Derived, so adding a species or a tree moves it
# automatically instead of leaving a stale literal behind.
SEEDED = len(engine_io.SPECIES) * 2 + sum(n for _, n in engine_io.FOREST)



def _tk_or_skip():
    import tkinter
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:  # no display
        raise unittest.SkipTest(f"no Tk display: {exc}")
    root.withdraw()
    return root


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.root = _tk_or_skip()
        self.addCleanup(self.root.destroy)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = store.Library(Path(self.tmp.name) / "library")
        self.lib.seed_from_engine()
        # Preferences go to the temp dir too - never the developer's own file.
        self.settings = Settings(Path(self.tmp.name) / "settings.json")
        self.ui = app.ArtKitApp(self.root, self.lib, self.settings)

    def test_it_opens_on_the_first_drawing_with_all_twenty_four_listed(self):
        self.assertEqual(len(self.lib.drawings), SEEDED)
        self.assertIsNotNone(self.ui.history.current)

    def test_a_drag_paints_a_run_of_cells_and_undoes_as_one(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_drag(1, 0)
        self.ui.on_canvas_drag(2, 0)
        self.ui.on_canvas_release()
        current = self.ui.history.current
        self.assertEqual([current.get(c, 0) for c in (0, 1, 2)], ["m", "m", "m"])
        self.ui.undo()
        self.assertNotEqual(self.ui.history.current.get(0, 0), "m")

    def test_the_eraser_clears_a_cell(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(3, 3)
        self.ui.on_canvas_release()
        self.ui.set_tool("erase")
        self.ui.on_canvas_press(3, 3)
        self.ui.on_canvas_release()
        self.assertIsNone(self.ui.history.current.get(3, 3))

    def test_switching_drawings_keeps_the_edit_on_the_first_one(self):
        first, second = self.lib.drawings[1], self.lib.drawings[2]
        self.ui.select(first)
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_release()
        self.ui.select(second)
        self.ui.select(first)
        self.assertEqual(self.ui.history.current.get(0, 0), "m")

    def test_zoom_stays_inside_its_limits(self):
        for _ in range(50):
            self.ui.zoom(+1)
        self.assertLessEqual(self.ui.zoom_level, app.MAX_ZOOM)
        for _ in range(100):
            self.ui.zoom(-1)
        self.assertGreaterEqual(self.ui.zoom_level, app.MIN_ZOOM)

    def test_a_raw_colour_ink_turns_a_letter_drawing_into_a_pixel_one(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.set_tool("draw")
        self.ui.set_ink((10, 20, 30, 255))
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_release()
        self.assertFalse(self.ui.history.current.is_letters())

    def test_set_ink_rejects_a_value_render_would_silently_drop(self):
        self.ui.set_ink("m")            # a palette letter is fine
        self.ui.set_ink((1, 2, 3, 255))  # an RGBA tuple is fine
        with self.assertRaises(ValueError):
            self.ui.set_ink("Z")         # not in the alphabet -> would vanish at render
        with self.assertRaises(ValueError):
            self.ui.set_ink((1, 2, 3))   # 3 channels, not 4

    def test_the_three_panes_are_wired_up(self):
        # No display needed, so this guards pane wiring the screenshot can't.
        import tkinter as tk
        self.assertIsInstance(self.ui.canvas, tk.Canvas)
        self.assertIsInstance(self.ui.preview_1x, tk.Canvas)
        self.assertIsInstance(self.ui.preview_squint, tk.Canvas)
        # The embedded colour panel replaced both the palette-letter slots and
        # the popup picker — it must exist, and they must not.
        self.assertIsInstance(self.ui._hue_strip, tk.Canvas)
        self.assertIsInstance(self.ui._sv_square, tk.Canvas)
        self.assertFalse(hasattr(self.ui, "_slot_buttons"))
        self.assertFalse(hasattr(self.ui, "_mirror_button"))

    def test_the_shade_square_click_sets_a_real_colour_ink(self):
        class FakeEvent:
            x, y = app.PICKER_W // 2, app.SV_H // 4
        self.ui._on_sv(FakeEvent)
        self.assertIsInstance(self.ui.ink, tuple)
        self.assertEqual(len(self.ui.ink), 4)
        self.assertEqual(self.ui.ink[3], 255)

    def test_a_frozen_mac_app_keeps_drawings_outside_its_own_bundle(self):
        # #v2.1.0. On macOS `sys.executable` is
        # PixelPomoArtKit.app/Contents/MacOS/PixelPomoArtKit, so the Windows
        # rule ("beside the executable") would put library/ INSIDE the bundle —
        # hidden behind Finder's "Show Package Contents", and wiped the moment
        # a new version is dragged over the old app. Every drawing, gone, with
        # no warning. Pinned because the failure is invisible on Windows, which
        # is where this is developed.
        import sys as _sys
        from unittest import mock
        with mock.patch.object(_sys, "frozen", True, create=True), \
                mock.patch.object(_sys, "platform", "darwin"), \
                mock.patch.object(
                    _sys, "executable",
                    "/Applications/PixelPomoArtKit.app/Contents/MacOS/PixelPomoArtKit"):
            base = app.base_dir()
        self.assertNotIn(".app", str(base),
                         f"drawings would live inside the bundle at {base}")
        self.assertIn("Documents", str(base))

    def test_a_frozen_windows_build_still_writes_beside_the_exe(self):
        # Built with the HOST's path separators, and compared against pathlib
        # rather than a hard-coded folder name. The first version hard-coded
        # r"D:\kit\PixelPomoArtKit.exe" and asserted the parent was "kit" —
        # which passes on Windows and fails on the macOS CI runner, where
        # backslashes are ordinary filename characters, so that whole string is
        # ONE component and `.parent` is the working directory. Same class of
        # mistake as the byte-comparison tests this release also fixed: the
        # assertion was about the host, not about the app.
        import sys as _sys
        from unittest import mock
        exe = str(Path("kit") / "PixelPomoArtKit.exe")
        with mock.patch.object(_sys, "frozen", True, create=True), \
                mock.patch.object(_sys, "platform", "win32"), \
                mock.patch.object(_sys, "executable", exe):
            base = app.base_dir()
        self.assertEqual(base, Path(exe).resolve().parent)

    def test_the_export_dialog_does_not_default_into_the_game_assets(self):
        # The game's asset tree is read-only to this app; defaulting the picker
        # there risks clobbering a shipped sprite. The default must live outside.
        #
        # Assert against the ACTUAL asset directory, resolved the same way the
        # app resolves it. The old check looked for the literal "pixel_pomo" in
        # the path — after the checkout moved to "Pixel Pomo\\App" that string
        # appears nowhere, so the test passed while guarding nothing.
        from art_kit import engine_io
        assets = (engine_io.APP_DIR / "flutter" / "assets" / "objects").resolve()
        default = Path(str(app.ENGINE_SPRITE_DIR)).resolve()
        self.assertNotEqual(default, assets)
        self.assertNotIn(assets, default.parents)
        self.assertNotIn("flutter/assets/objects", str(default).replace("\\", "/"))

    def test_a_fast_drag_fills_the_line_between_sparse_motion_events(self):
        # tkinter reports motion sparsely during a quick drag; the app must
        # interpolate or a stroke comes out dotted.
        self.ui._new_drawing()  # blank 16x16, so the painted set is exact
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_drag(4, 2)  # one event, five cells of travel
        self.ui.on_canvas_release()
        d = self.ui.history.current
        painted = {(c, r) for r in range(d.height) for c in range(d.width)
                   if d.get(c, r) == "m"}
        self.assertEqual(painted, {(0, 0), (1, 1), (2, 1), (3, 2), (4, 2)})

    def test_right_click_picks_the_cell_under_the_cursor_as_ink(self):
        self.ui._new_drawing()
        self.ui.set_tool("draw")
        self.ui.set_ink("G")
        self.ui.on_canvas_press(2, 2)
        self.ui.on_canvas_release()
        self.ui.set_ink("m")
        self.ui.on_canvas_pick(2, 2)
        self.assertEqual(self.ui.ink, "G")
        self.ui.on_canvas_pick(0, 0)  # empty cell: a misclick, not an eraser
        self.assertEqual(self.ui.ink, "G")

    def test_set_tool_rejects_an_unknown_tool(self):
        with self.assertRaises(ValueError):
            self.ui.set_tool("lasso")

    def test_a_new_drawing_is_the_big_grid_for_trees_and_pets(self):
        self.ui._new_drawing()
        d = self.ui.history.current
        self.assertEqual((d.width, d.height), (app.NEW_SIZE, app.NEW_SIZE))

    def test_the_fill_tool_floods_from_the_pressed_cell_as_one_undo(self):
        self.ui._new_drawing()
        self.ui.set_tool("fill")
        self.ui.set_ink("G")
        self.ui.on_canvas_press(5, 5)
        self.ui.on_canvas_release()
        d = self.ui.history.current
        self.assertEqual(d.get(0, 0), "G")
        self.assertEqual(d.get(d.width - 1, d.height - 1), "G")
        self.ui.undo()
        self.assertIsNone(self.ui.history.current.get(0, 0),
                          "a fill is one stroke, one undo")

    # ---- #v2.4.0 ------------------------------------------------------------

    def test_save_writes_the_open_drawing_and_reports_success(self):
        drawing = self.lib.drawings[1]
        self.ui.select(drawing)
        self.ui.set_tool("draw")
        self.ui.set_ink((1, 2, 3, 255))
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_release()
        self.assertTrue(self.ui.save())
        self.assertEqual(store.load(self.lib._paths[id(drawing)]).get(0, 0), (1, 2, 3, 255))

    def test_the_ink_entry_shows_only_the_hex_code_and_accepts_a_typed_one(self):
        import tkinter as tk
        self.assertIsInstance(self.ui._ink_entry, tk.Entry)
        self.ui.set_ink((0x6a, 0x2c, 0x2c, 255))
        self.assertEqual(self.ui._ink_entry.get(), "#6a2c2c")  # no "ink:" prefix
        self.assertTrue(self.ui.set_ink_hex("A6E3A1"))
        self.assertEqual(self.ui.ink, (0xa6, 0xe3, 0xa1, 255))
        self.assertTrue(self.ui.set_ink_hex("#1a2420"))
        self.assertFalse(self.ui.set_ink_hex("green"))
        self.assertEqual(self.ui.ink, (0x1a, 0x24, 0x20, 255), "a bad code changes nothing")

    def test_a_letter_ink_resolves_to_its_palette_colour_in_the_entry(self):
        self.ui.select(self.lib.drawings[2])  # a letter-grid flower
        self.ui.set_ink("m")
        expected = app._hex(self.ui.history.current.palette.colors()["m"])
        self.assertEqual(self.ui._ink_entry.get(), expected)

    def test_plus_adds_the_ink_to_favourites_and_right_click_removes_it(self):
        self.ui.set_ink((0x12, 0x34, 0x56, 255))
        self.ui._add_ink_to_favourites()
        self.assertIn("123456", self.settings.favourites)
        self.assertIn("123456", self.ui._favourites.colours)
        self.ui.remove_favourite("123456")
        self.assertNotIn("123456", self.settings.favourites)
        self.assertNotIn("123456", self.ui._favourites.colours)
        self.assertEqual(len(self.ui._favourites.colours), 6)

    def test_the_swatch_grids_are_as_wide_as_the_colour_panel(self):
        # item 4: the ready/favourite grids and the picker share their edges
        self.assertEqual(int(self.ui._ready.cget("width")), app.PICKER_W)
        self.assertEqual(int(self.ui._favourites.cget("width")), app.PICKER_W)
        self.assertEqual(int(self.ui._hue_strip.cget("width")), app.PICKER_W)
        self.assertEqual(len(self.ui._ready.colours), len(app.READY))

    def test_the_last_tool_used_is_remembered_for_the_next_session(self):
        self.ui.set_tool("fill")
        self.assertEqual(self.settings.tool, "fill")
        again = app.ArtKitApp(self.root, self.lib, Settings(self.settings.path))
        self.assertEqual(again.tool, "fill")

    def test_new_drawing_takes_a_size_and_the_presets_come_from_the_engine(self):
        d = self.ui.new_drawing(16, 15)
        self.assertEqual((d.width, d.height), (16, 15))
        self.assertIn(d, self.lib.drawings)
        presets = {name: (c, r) for name, c, r in app.size_presets()}
        flower_h = len(engine_io.gen_objects()._FLOWER_BLOOMS["lale"][0])
        self.assertEqual(presets["Flower"], (16, flower_h))
        self.assertEqual(presets["Bush"], (16, 16))
        self.assertEqual({v for k, v in presets.items() if k.startswith("Tree")},
                         {(32, 32), (48, 48), (64, 64)})

    def test_resize_is_one_undo_step_and_the_size_label_follows(self):
        self.ui.new_drawing(10, 10)
        self.assertEqual(self.ui._size_label.cget("text"), "10 \u00d7 10")
        self.ui.resize(20, 12)
        self.assertEqual((self.ui.history.current.width, self.ui.history.current.height), (20, 12))
        self.assertEqual(self.ui._size_label.cget("text"), "20 \u00d7 12")
        self.ui.undo()
        self.assertEqual((self.ui.history.current.width, self.ui.history.current.height), (10, 10))

    def test_the_symmetry_bar_places_on_the_first_click_then_mirrors_strokes(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_tool("draw")
        self.ui.set_ink((9, 9, 9, 255))
        self.ui.set_symmetry(True)
        self.assertTrue(self.ui._placing_bar)
        self.ui.on_canvas_press(7, 4)  # places a vertical, 5-long bar; paints nothing
        self.ui.on_canvas_release()
        d = self.ui.history.current
        self.assertIsNone(d.get(7, 4))
        self.assertEqual((self.ui.symmetry_bar.col, self.ui.symmetry_bar.row), (7, 4))
        self.assertFalse(self.ui._placing_bar)
        self.ui.on_canvas_press(4, 3)
        self.ui.on_canvas_drag(4, 9)  # runs past the bar's reach (rows 2..6)
        self.ui.on_canvas_release()
        self.assertEqual(d.get(4, 3), (9, 9, 9, 255))
        self.assertEqual(d.get(10, 3), (9, 9, 9, 255), "mirrored across column 7")
        self.assertEqual(d.get(10, 6), (9, 9, 9, 255))
        self.assertIsNone(d.get(10, 7), "beyond the bar: painted alone")
        self.assertEqual(d.get(4, 9), (9, 9, 9, 255))
        self.ui.undo()
        self.assertIsNone(self.ui.history.current.get(4, 3))
        self.assertIsNone(self.ui.history.current.get(10, 3), "the stroke and its mirror undo together")
        self.ui.set_symmetry(False)
        self.ui.on_canvas_press(5, 4)
        self.ui.on_canvas_release()
        self.assertIsNone(self.ui.history.current.get(9, 4), "off: no mirror")

    def test_symmetry_orientation_and_length_persist_and_rebuild_the_bar(self):
        self.ui.set_symmetry(True)
        self.ui.place_symmetry_bar(8, 8)
        self.ui.set_symmetry_orientation(symmetry.HORIZONTAL)
        self.ui.set_symmetry_length(3)
        self.assertEqual(self.ui.symmetry_bar.orientation, symmetry.HORIZONTAL)
        self.assertEqual(self.ui.symmetry_bar.length, 3)
        self.assertEqual(self.settings.symmetry, {"orientation": "horizontal", "length": 3})

    def test_a_stroke_updates_one_library_row_instead_of_rebuilding_them_all(self):
        # item 7: the freeze was 59 thumbnails x thousands of rectangles, rebuilt per stroke
        rows_before = dict(self.ui._rows)
        self.ui.select(self.lib.drawings[3])
        self.ui.set_tool("draw")
        self.ui.set_ink((5, 5, 5, 255))
        self.ui.on_canvas_press(1, 1)
        self.ui.on_canvas_release()
        self.assertEqual(len(self.ui._rows), SEEDED)
        for key, widgets in self.ui._rows.items():
            self.assertIs(widgets["row"], rows_before[key]["row"], "rows are built once")
        self.assertEqual(len(self.ui.canvas.find_withtag("art")), 1, "the drawing is ONE image item")

    def test_the_help_overlay_toggles(self):
        self.assertIsNone(self.ui._help)
        self.ui.toggle_help()
        self.assertIsNotNone(self.ui._help)
        self.ui.toggle_help()
        self.assertIsNone(self.ui._help)

    def test_close_writes_an_unsaved_edit_then_destroys_the_window(self):
        from unittest import mock
        drawing = self.lib.drawings[1]
        self.ui.select(drawing)
        self.ui.set_tool("draw")
        self.ui.set_ink((7, 7, 7, 255))
        self.ui.on_canvas_press(2, 2)  # a stroke still in progress when the window closes
        with mock.patch.object(self.ui.root, "destroy") as destroy:
            self.ui.close()
        destroy.assert_called_once()
        self.assertEqual(store.load(self.lib._paths[id(drawing)]).get(2, 2), (7, 7, 7, 255))

    def test_the_icon_grid_is_a_complete_16x16_sprite(self):
        from art_kit import branding, raster
        grid = branding.icon_grid()
        self.assertEqual((len(grid), len(grid[0])), (16, 16))
        self.assertTrue(all(len(row) == 16 for row in grid))
        self.assertTrue(set("".join(branding.ICON)) - {"."} <= set(branding.COLOURS))
        img = raster.photo(grid, 2, master=self.root)
        self.assertEqual((img.width(), img.height()), (32, 32))

    def test_the_saved_file_tracks_an_undo_not_just_memory(self):
        # History.undo() swaps .current to a different object; the app reconciles
        # that before library.save(). Without the reconciliation the on-disk file
        # lags the undo (or the save KeyErrors). Assert disk == memory afterwards.
        drawing = self.lib.drawings[1]
        self.ui.select(drawing)
        self.ui.set_tool("draw")
        self.ui.set_ink("m")
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_release()
        self.assertEqual(self.ui.history.current.get(0, 0), "m")  # a real change landed
        self.ui.undo()
        path = self.lib._paths[id(drawing)]
        self.assertEqual(store.load(path).cells, self.ui.history.current.cells)
