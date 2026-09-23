import json
import tempfile
import unittest
from pathlib import Path


import tkinter

from art_kit import app, dialogs, engine_io, i18n, model, provenance, raster, store, symmetry, theme
import tkinter as tk
from art_kit.settings import Settings

# Everything the app seeds: two models per flower, plus the forest props the
# engine loads (#v34.8). Derived, so adding a species or a tree moves it
# automatically instead of leaving a stale literal behind.
SEEDED = engine_io.seeded_count()
# Who the seeded Drawing Patch 1 flowers are signed by.
PATCH = engine_io.PATCH_ARTIST



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
        self.addCleanup(self._cancel_timers)      # runs first: cleanups are LIFO
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = store.Library(Path(self.tmp.name) / "library")
        self.lib.seed_from_engine()
        # Preferences go to the temp dir too - never the developer's own file.
        self.settings = Settings(Path(self.tmp.name) / "settings.json")
        self.ui = app.ArtKitApp(self.root, self.lib, self.settings)

    def _cancel_timers(self):
        """A pending `after` (the 80ms fit every `select` schedules) outlives
        `root.destroy()` in Tcl's event queue, and fires into the next test
        that runs an event loop - a modal dialog's `wait_window` - as
        "invalid command name ...zoom_to_fit". Cancelled here instead."""
        try:
            for timer in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(timer)
        except tkinter.TclError:
            pass

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

    def test_a_frozen_windows_build_writes_to_the_user_profile_not_beside_the_exe(self):
        # #v2.5.0. Up to v2.4.0 this asserted the opposite ("beside the exe").
        # That lost drawings whenever the .exe was moved or a new version was
        # unzipped into a fresh folder. The data folder is now per-user, so
        # the program can go anywhere.
        import os as _os
        import sys as _sys
        from unittest import mock
        exe = str(Path("kit") / "PixelPomoArtKit.exe")
        with mock.patch.object(_sys, "frozen", True, create=True), \
                mock.patch.object(_sys, "platform", "win32"), \
                mock.patch.object(_sys, "executable", exe), \
                mock.patch.dict(_os.environ, {"LOCALAPPDATA": str(Path("home") / "AppData" / "Local")}):
            base = app.base_dir()
        self.assertEqual(base, Path("home") / "AppData" / "Local" / "PixelPomoArtKit")
        self.assertNotEqual(base, Path(exe).resolve().parent)

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
        self.assertEqual(presets["Flower"], (16, 16))
        self.assertEqual(presets["Bug"], (8, 8))
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
        self.assertEqual(d.get(9, 3), (9, 9, 9, 255), "mirrored across the line at column 7")
        self.assertEqual(d.get(9, 6), (9, 9, 9, 255))
        self.assertIsNone(d.get(9, 7), "beyond the bar: painted alone")
        self.assertEqual(d.get(4, 9), (9, 9, 9, 255))
        self.ui.undo()
        self.assertIsNone(self.ui.history.current.get(4, 3))
        self.assertIsNone(self.ui.history.current.get(9, 3), "the stroke and its mirror undo together")
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
        self.assertEqual(self.settings.symmetry,
                         {"orientation": "horizontal", "length": 3, "mode": "mirror"})

    # ---- #v2.5.0 ------------------------------------------------------------

    def test_stick_mode_places_a_line_and_stamps_the_strip(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_tool("draw")
        self.ui.set_ink((0x80, 0, 0xff, 255))
        d = self.ui.history.current
        d.paint(2, 8, (0x80, 0, 0xff, 255))
        self.ui.set_symmetry_mode(symmetry.STICK)
        self.ui.set_symmetry_orientation(symmetry.VERTICAL)
        self.ui.set_symmetry_length(5)
        self.assertTrue(self.ui._placing_bar, "STICK with no line yet waits for a click")
        self.ui.on_canvas_press(8, 8)  # places the line; stamps rows 6..10
        self.ui.on_canvas_release()
        self.assertFalse(self.ui._placing_bar)
        self.assertEqual((self.ui.symmetry_bar.col, self.ui.symmetry_bar.row), (8, 8))
        # 2*8-1-2 = 13
        self.assertEqual(self.ui.history.current.get(13, 8), (0x80, 0, 0xff, 255))
        self.ui.undo()
        self.assertIsNone(self.ui.history.current.get(13, 8), "the stamp is one undo")
        self.assertEqual(self.settings.symmetry["mode"], "stick")

    def test_pressing_on_the_bar_drags_it_instead_of_painting(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_tool("draw")
        self.ui.set_ink((1, 1, 1, 255))
        self.ui.set_symmetry_mode(symmetry.MIRROR)
        self.ui.place_symmetry_bar(7, 7)  # vertical, 5 long: cells (7, 5..9)
        self.ui.on_canvas_press(7, 6)     # grabbed one above centre
        self.ui.on_canvas_drag(10, 6)
        self.ui.on_canvas_drag(10, 9)
        self.ui.on_canvas_release()
        self.assertEqual((self.ui.symmetry_bar.col, self.ui.symmetry_bar.row), (10, 10))
        d = self.ui.history.current
        self.assertTrue(all(c is None for row in d.cells for c in row), "a drag paints nothing")
        kinds = [kind for kind, _v in self.ui.history._undo]
        self.assertNotIn(model.History.CELLS, kinds, "and records no STROKE")
        # PLACE BAR re-arms: the next click puts it somewhere new
        self.ui.arm_symmetry_placement()
        self.assertTrue(self.ui._placing_bar)
        self.ui.on_canvas_press(2, 2)
        self.ui.on_canvas_release()
        self.assertEqual((self.ui.symmetry_bar.col, self.ui.symmetry_bar.row), (2, 2))

    def test_the_m_key_cycles_off_mirror_stick(self):
        self.assertEqual(self.ui.symmetry_mode, symmetry.OFF)
        self.ui.cycle_symmetry_mode()
        self.assertEqual(self.ui.symmetry_mode, symmetry.MIRROR)
        self.ui.cycle_symmetry_mode()
        self.assertEqual(self.ui.symmetry_mode, symmetry.STICK)
        self.ui.cycle_symmetry_mode()
        self.assertEqual(self.ui.symmetry_mode, symmetry.OFF)
        with self.assertRaises(ValueError):
            self.ui.set_symmetry_mode("wobble")

    def test_import_png_lands_in_the_library_saved(self):
        from PIL import Image
        png = Path(self.tmp.name) / "sprout.png"
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for x in range(4):
            img.putpixel((x, 0), (10, 200, 30, 255))
        img.save(png)
        before = len(self.lib.drawings)
        drawing, notes = self.ui.import_png(png)
        self.assertEqual(len(self.lib.drawings), before + 1)
        self.assertEqual(drawing.name, "sprout")
        self.assertEqual(drawing.get(0, 0), (10, 200, 30, 255))
        self.assertEqual(store.load(self.lib._paths[id(drawing)]).get(3, 0), (10, 200, 30, 255))
        self.assertIn(id(drawing), self.ui._rows, "and it has a library row")
        self.assertEqual(drawing.species, "", "species is a string, so the filename slug is sane")

    def test_a_newer_release_lights_the_update_button_a_current_one_does_not(self):
        from art_kit import updater
        newer = updater.Release({"tag_name": "v99.0.0", "html_url": "x", "assets": []})
        current = updater.Release({"tag_name": f"v{app.VERSION}", "html_url": "x", "assets": []})
        self.ui._on_update_result(current, None, silent=True)
        self.assertIsNone(self.ui._update_release)
        self.assertEqual(self.ui._update_button.cget("text"), "UPDATE")
        self.ui._on_update_result(newer, None, silent=True)
        self.assertIs(self.ui._update_release, newer)
        self.assertIn("v99.0.0", self.ui._update_button.cget("text"))
        # a failed silent check says nothing and changes nothing
        self.ui._on_update_result(None, OSError("offline"), silent=True)
        self.assertIs(self.ui._update_release, newer)

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

    def test_the_icon_grid_is_a_complete_square_sprite(self):
        """#v2.8.0: 32x32 now, drawn in the kit and pasted in. Square and
        rectangular, every letter known, and it survives being scaled."""
        from art_kit import branding, raster
        grid = branding.icon_grid()
        side = len(grid)
        self.assertEqual(side, 32)
        self.assertTrue(all(len(row) == side for row in grid), "not ragged")
        self.assertTrue(set("".join(branding.ICON)) - {"."} <= set(branding.COLOURS))
        self.assertTrue(any(px for row in grid for px in row), "and not empty")
        img = raster.photo(grid, 2, master=self.root)
        self.assertEqual((img.width(), img.height()), (side * 2, side * 2))

    # ---- #v2.6.0 ------------------------------------------------------------

    def test_labels_show_on_rows_filter_the_list_and_save(self):
        drawing = self.lib.drawings[0]
        self.assertEqual(drawing.label, "flower")
        self.assertEqual(self.ui._rows[id(drawing)]["chip"].cget("text"), "flower")
        self.ui.set_label(drawing, "  wip ")
        self.assertEqual(drawing.label, "wip")
        self.assertEqual(store.load(self.lib._paths[id(drawing)]).label, "wip")
        self.assertEqual(self.ui._rows[id(drawing)]["chip"].cget("text"), "wip")
        self.ui.set_label_filter("tree")
        visible = self.ui.visible_drawings()
        self.assertEqual(len(visible), 20)
        self.assertTrue(all(d.label == "tree" for d in visible))
        self.assertFalse(self.ui._rows[id(drawing)]["row"].winfo_manager(), "hidden by the filter")
        self.assertTrue(self.ui._rows[id(visible[0])]["row"].winfo_manager())
        self.assertIn("TREE", self.ui._filter_button.cget("text"))
        self.ui.set_label_filter(None)
        self.assertTrue(self.ui._rows[id(drawing)]["row"].winfo_manager())
        self.assertEqual(len(self.ui.visible_drawings()), SEEDED)
        self.assertFalse(hasattr(self.ui, "_set_species"), "Species… left the menu")

    def test_a_new_drawing_under_a_filter_takes_that_label_and_stays_visible(self):
        self.ui.set_label_filter("bush")
        d = self.ui.new_drawing(8, 8)
        self.assertEqual(d.label, "bush")
        self.assertTrue(self.ui._rows[id(d)]["row"].winfo_manager())
        self.ui.set_label_filter("rock")
        e = self.ui.import_png(self._png())[0]
        self.assertEqual(e.label, "import")
        # Its label joins the ticked ones instead of wiping them (#v2.8.0):
        # the rocks the artist chose to look at are still listed too.
        self.assertEqual(self.ui._ticked(self.ui.LABEL), {"rock", "import"})
        self.assertTrue(self.ui._rows[id(e)]["row"].winfo_manager())

    def test_the_label_filter_is_a_checklist(self):
        """#v2.8.0, second test pass: "label isimlerinin yanında tik olsun".
        Under ALL every label is ticked; a click on one from there lists just
        that label, more clicks tick more on or off, and the menu stays open
        while they do. Nothing ticked, or everything, is ALL."""
        counts = {}
        for d in self.lib.drawings:
            counts[d.label] = counts.get(d.label, 0) + 1
        self.ui.toggle_label_filter("tree")
        self.assertEqual(self.ui._ticked(self.ui.LABEL), {"tree"}, "from ALL: just the one clicked")
        self.ui.toggle_label_filter("bush")
        self.assertEqual(len(self.ui.visible_drawings()), counts["tree"] + counts["bush"])
        self.assertIn("BUSH + TREE", self.ui._filter_button.cget("text"))
        self.ui.toggle_label_filter("tree")
        self.assertEqual(self.ui._ticked(self.ui.LABEL), {"bush"})
        self.ui.toggle_label_filter("bush")
        self.assertIsNone(self.ui._filter, "nothing ticked lists everything, not nothing")
        keys = sorted(counts)
        for key in keys:
            self.ui.toggle_label_filter(key)
        self.assertEqual(self.ui._ticked(self.ui.LABEL), set(keys))
        self.assertEqual(len(self.ui.visible_drawings()), SEEDED, "every label ticked lists all")

        self.ui.set_label_filter({"tree"})
        self.ui._post_filter_menu()
        menu = self.ui._filter_menu
        self.addCleanup(menu.unpost)
        texts = [row.cget("text") for row, _command in menu._rows]
        self.assertTrue(texts[0].startswith(dialogs.UNTICKED), "ALL is unticked while filtering")
        tree = next(i for i, text in enumerate(texts) if text.endswith(f"tree  ·  {counts['tree']}"))
        bush = next(i for i, text in enumerate(texts) if text.endswith(f"bush  ·  {counts['bush']}"))
        self.assertTrue(texts[tree].startswith(dialogs.TICKED))
        self.assertTrue(texts[bush].startswith(dialogs.UNTICKED))
        menu._rows[bush][0].invoke()                        # a click on bush
        self.assertIsNotNone(menu._win, "a checklist stays open")
        self.assertEqual(self.ui._ticked(self.ui.LABEL), {"tree", "bush"})
        self.assertTrue(menu._rows[bush][0].cget("text").startswith(dialogs.TICKED), "re-ticked in place")
        menu._rows[0][0].invoke()                           # ALL
        self.assertIsNone(self.ui._filter)
        self.assertTrue(all(row.cget("text").startswith(dialogs.TICKED) for row, _c in menu._rows),
                        "ALL ticks everything")

    def _png(self):
        from PIL import Image
        png = Path(self.tmp.name) / "bit.png"
        img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        img.putpixel((0, 0), (9, 9, 9, 255))
        img.save(png)
        return png

    def test_the_eraser_footprint_is_centred_and_sized(self):
        self.ui.new_drawing(10, 10)
        d = self.ui.history.current
        for r in range(10):
            for c in range(10):
                d.paint(c, r, "m")
        self.ui.set_tool("erase")
        self.ui.set_eraser_size(3, 2)
        self.assertEqual(self.settings.eraser, {"w": 3, "h": 2})
        self.ui.on_canvas_press(5, 5)
        self.ui.on_canvas_release()
        d = self.ui.history.current
        cleared = {(c, r) for r in range(10) for c in range(10) if d.get(c, r) is None}
        self.assertEqual(cleared, {(4, 4), (5, 4), (6, 4), (4, 5), (5, 5), (6, 5)})

    def test_select_copy_paste_and_move(self):
        self.ui.new_drawing(12, 12)
        d = self.ui.history.current
        d.paint(1, 1, "m")
        d.paint(2, 2, "l")
        self.ui.set_tool("select")
        self.ui.on_canvas_press(1, 1)
        self.ui.on_canvas_drag(2, 2)
        self.ui.on_canvas_release()
        self.assertEqual(self.ui.selection, (1, 1, 2, 2))
        self.assertTrue(self.ui.copy_selection())
        self.assertEqual(self.ui.clipboard[1:], (2, 2))
        self.assertTrue(self.ui.paste(6, 6))
        self.assertEqual((self.ui.floating["col"], self.ui.floating["row"]), (6, 6))
        self.assertIsNone(self.ui.history.current.get(6, 6), "floating, not yet on the drawing")
        self.ui.on_canvas_press(6, 6)      # inside the block: drag it
        self.ui.on_canvas_drag(8, 7)
        self.ui.on_canvas_release()
        self.assertEqual((self.ui.floating["col"], self.ui.floating["row"]), (8, 7))
        self.ui.nudge_floating(1, 0)
        self.assertTrue(self.ui.commit_floating())
        d = self.ui.history.current
        self.assertEqual(d.get(9, 7), "m")
        self.assertEqual(d.get(10, 8), "l")
        self.assertEqual(d.get(1, 1), "m", "the original stays")
        self.assertEqual(self.ui.selection, (9, 7, 10, 8), "the placed block stays selected")
        self.ui.undo()
        self.assertIsNone(self.ui.history.current.get(9, 7), "a paste is one undo step")

    def test_pressing_inside_a_selection_lifts_it_and_a_click_outside_drops_it(self):
        self.ui.new_drawing(12, 12)
        d = self.ui.history.current
        d.paint(1, 1, "m")
        self.ui.set_tool("select")
        self.ui.select_region(1, 1, 2, 2)
        self.ui.on_canvas_press(1, 1)  # inside -> lifted
        self.assertIsNotNone(self.ui.floating)
        self.assertIsNone(self.ui.history.current.get(1, 1), "lifted off the drawing")
        self.ui.on_canvas_drag(5, 5)
        self.ui.on_canvas_release()
        self.ui.on_canvas_press(0, 11)   # outside -> dropped where it is, nothing painted at (0, 11)
        self.assertIsNone(self.ui.floating)
        d = self.ui.history.current
        self.assertEqual(d.get(5, 5), "m")
        self.assertIsNone(d.get(0, 11))
        self.ui.undo()
        self.assertEqual(self.ui.history.current.get(1, 1), "m",
                         "a move is ONE undo: lift and drop are one edit")
        self.assertIsNone(self.ui.history.current.get(5, 5))

    def test_cut_and_delete_clear_the_selection_as_strokes(self):
        self.ui.new_drawing(6, 6)
        self.ui.history.current.paint(2, 2, "m")
        self.ui.select_region(2, 2, 3, 3)
        self.assertTrue(self.ui.cut_selection())
        self.assertIsNone(self.ui.history.current.get(2, 2))
        self.assertEqual(self.ui.clipboard[0][0][0], "m")
        self.ui.undo()
        self.assertEqual(self.ui.history.current.get(2, 2), "m")
        self.ui.select_region(2, 2, 2, 2)
        self.assertTrue(self.ui.delete_selection())
        self.assertIsNone(self.ui.history.current.get(2, 2))
        self.ui.clear_selection()
        self.assertFalse(self.ui.copy_selection(), "nothing selected, nothing copied")

    def test_dragging_a_bar_end_resizes_it(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_symmetry_mode(symmetry.MIRROR)
        self.ui.set_symmetry_length(5)
        self.ui.place_symmetry_bar(7, 7)       # vertical, rows 5..9
        self.ui.on_canvas_press(7, 9)          # the last cell
        self.ui.on_canvas_drag(7, 12)
        self.ui.on_canvas_release()
        bar = self.ui.symmetry_bar
        self.assertEqual(bar.span(), (5, 12))
        self.assertEqual(bar.length, 8)
        self.assertEqual(self.settings.symmetry["length"], 8)
        self.assertTrue(all(c is None for row in self.ui.history.current.cells for c in row))
        self.ui.on_canvas_press(7, 5)          # the first cell, dragged past the other end
        self.ui.on_canvas_drag(7, 11)
        self.ui.on_canvas_release()
        self.assertEqual(self.ui.symmetry_bar.span(), (11, 12))

    def test_grid_lines_toggle_and_grid_colours(self):
        self.ui.select(self.lib.drawings[1])
        self.ui.zoom_level = 20
        self.ui.set_show_grid(True)
        self.assertTrue(self.ui.canvas.find_withtag("grid"))
        self.ui.set_show_grid(False)
        self.assertFalse(self.ui.canvas.find_withtag("grid"))
        self.assertFalse(self.settings.show_grid)
        self.ui.set_grid_colours(c1="402020")
        self.assertEqual(self.ui.grid_colours(), ("#402020", "#2a3a30"))
        self.assertEqual(self.ui._grid_entries["c1"].get(), "#402020")
        # The checkerboard is in the empty cells of the art tile itself, in
        # the colours just chosen - no canvas items under it (#v2.8.0).
        self.ui.new_drawing(8, 6)
        self.ui.zoom_level = 20
        c1, c2 = (model.hex_to_rgba(c) for c in self.ui.grid_colours())
        tile = self.ui._tile(self.ui.history.current, (0, 0, 7, 5))
        self.assertEqual(tile[0][:4], [c1, c1, c2, c2])
        self.assertEqual(tile[2][:4], [c2, c2, c1, c1], "two cells down, the other way round")
        self.assertEqual(tile[5][:4], [c1, c1, c2, c2], "and so on to the last row")
        self.ui._draw_main()
        self.assertFalse(self.ui.canvas.find_withtag("checker"))
        self.ui.reset_grid_colours()
        self.assertEqual(self.ui.grid_colours(), ("#232f28", "#2a3a30"))

    def test_the_strip_under_the_canvas_counts_pixels_and_lists_colours(self):
        self.ui.new_drawing(6, 6)
        d = self.ui.history.current
        self.ui.set_tool("draw")
        self.ui.set_ink((255, 0, 0, 255))
        self.ui.on_canvas_press(0, 0)
        self.ui.on_canvas_drag(3, 0)
        self.ui.on_canvas_release()
        self.ui.set_ink((0, 0, 255, 255))
        self.ui.on_canvas_press(0, 1)
        self.ui.on_canvas_release()
        self.assertIn("pixels 5", self.ui._counter_label.cget("text"))
        self.assertIn("empty 31", self.ui._counter_label.cget("text"))
        self.ui._hover_cell = (0, 0)
        self.ui._refresh_counter()
        self.ui._refresh_cursor_label()
        self.assertIn("row 0: 4", self.ui._counter_label.cget("text"))
        self.assertIn("col 0: 2", self.ui._counter_label.cget("text"))
        self.assertIn("#ff0000", self.ui._cursor_label.cget("text"))
        self.assertEqual([h for h, _ in self.ui._colour_strip._items], ["FF0000", "0000FF"])
        self.assertEqual(self.ui._colour_strip._items[0][1], 4)
        self.ui.select_region(0, 0, 5, 0)
        self.assertIn("selection 6\u00d71: 4", self.ui._counter_label.cget("text"))

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

    def test_fill_paints_the_selection_and_select_again_dismisses_it(self):
        self.ui.new_drawing(8, 8)
        self.ui.set_ink((1, 2, 3, 255))
        self.ui.set_tool("select")
        self.ui.select_region(1, 1, 3, 2)
        self.ui.set_tool("fill")
        d = self.ui.history.current
        filled = {(c, r) for r in range(8) for c in range(8) if d.get(c, r) == (1, 2, 3, 255)}
        self.assertEqual(filled, {(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2)})
        self.assertIsNone(self.ui.selection, "FILL with a selection dismisses the box")
        self.assertEqual(self.ui.tool, "fill")
        self.ui.set_tool("select")
        self.ui.select_region(0, 0, 1, 1)
        self.assertIsNotNone(self.ui.selection)
        self.ui.set_tool("select")  # click SELECT again
        self.assertIsNone(self.ui.selection)
        self.assertEqual(self.ui.tool, "select")

    def test_copy_then_click_pastes_and_survives_switching_drawings(self):
        a = self.ui.new_drawing(8, 8)
        a.paint(0, 0, "m")
        a.paint(1, 0, "l")
        self.ui.select_region(0, 0, 1, 0)
        self.assertTrue(self.ui.copy_selection())
        self.assertTrue(self.ui._paste_armed)
        self.assertTrue(self.ui.paste_at(3, 4))
        self.assertEqual(self.ui.history.current.get(3, 4), "m")
        self.assertEqual(self.ui.history.current.get(4, 4), "l")
        b = self.ui.new_drawing(8, 8)
        self.assertTrue(self.ui.paste_at(1, 1))
        self.assertEqual(b.get(1, 1), "m")
        self.assertEqual(b.get(2, 1), "l")

    def test_language_and_library_collapse_persist(self):
        self.ui.set_language("tr")
        self.assertEqual(self.settings.language, "tr")
        self.assertIn("KAYDET", self.ui._save_button.cget("text"))
        self.ui.set_language("en")
        self.ui.set_library_collapsed(True)
        self.assertTrue(self.settings.library_collapsed)
        self.assertEqual(int(self.ui._library_outer.cget("width")), app.LIBRARY_RAIL)
        self.ui.set_library_collapsed(False)
        self.assertEqual(int(self.ui._library_outer.cget("width")), app.LIBRARY_W)

    def test_click_to_resize_hint_is_gone(self):
        texts = []
        for w in self.ui._size_label.master.winfo_children():
            try:
                texts.append(w.cget("text"))
            except Exception:
                pass
        self.assertFalse(any("click to resize" in str(t) for t in texts))

    def test_a_language_switch_moves_no_chrome_box_and_keeps_every_font_bold(self):
        """#v2.8.0, item 1. The boxes were pinned in pixels at build time, so
        DE (the longest labels: RADIERER, WIEDERH., SPEICHERN) has to land in
        exactly the same rectangles as EN, in the same family, still bold -
        only the point size may give."""
        pairs = self.ui._chrome_pairs()
        self.assertTrue(pairs)
        before = {key: (btn.winfo_reqwidth(), btn.winfo_reqheight()) for btn, key in pairs}
        for code in ("tr", "de", "pl", "en"):
            self.ui.set_language(code)
            self.root.update_idletasks()
            for btn, key in self.ui._chrome_pairs():
                self.assertEqual((btn.winfo_reqwidth(), btn.winfo_reqheight()),
                                 before[key], f"{key} moved in {code}")
                family, size, *rest = self.root.tk.splitlist(btn.cget("font"))
                self.assertEqual(family, theme.FONT_FAMILY, f"{key} in {code}")
                self.assertIn("bold", rest, f"{key} in {code}")
                self.assertGreaterEqual(int(size), theme.MIN_FONT_SIZE)

    def test_a_pinned_button_shrinks_the_size_rather_than_the_box(self):
        btn = self.ui._save_button
        self.assertIsNotNone(btn.pinned)
        width = btn.winfo_reqwidth()
        btn.configure(text="A RIDICULOUSLY LONG LABEL NO LANGUAGE WOULD EVER USE")
        self.root.update_idletasks()
        self.assertEqual(btn.winfo_reqwidth(), width)
        _family, size, *_ = self.root.tk.splitlist(btn.cget("font"))
        self.assertLess(int(size), theme.FONT_SIZE)

    def test_the_row_menu_offers_open_file_location_and_the_library_knows_the_path(self):
        """#v2.8.0, item 2: the row menu can show the artist where the file is."""
        drawing = self.lib.drawings[0]
        path = self.lib.path_for(drawing)
        self.assertIsNotNone(path)
        self.assertTrue(Path(path).is_file())
        labels = self.ui._rows[id(drawing)]["popup"].labels()
        self.assertIn(i18n.t("open_location"), labels)

    def test_the_export_background_choice_is_remembered(self):
        self.assertIsNone(self.settings.export_background)  # transparent, as before
        self.settings.export_background = "FFFFFF"
        self.assertEqual(self.settings.export_background, "FFFFFF")
        self.settings.export_background = None
        self.assertIsNone(self.settings.export_background)

    def test_every_image_export_asks_about_the_background(self):
        """#v2.8.0: PNG, SVG and JPG, with and without a grid, all six of
        them. The JSON export and the engine sprite are deliberately NOT in
        this list - JSON has no pixels, and a garden sprite that arrived with
        a background baked into its alpha would render as an opaque square."""
        asked = []
        self.ui._ask_export_background = lambda *a, **kw: (asked.append((a, kw)), app.CANCELLED)[1]
        for call in (lambda: self.ui._export_png(self.lib.drawings[0]),
                     lambda: self.ui._export_png(self.lib.drawings[0], grid=True),
                     lambda: self.ui._export_svg(self.lib.drawings[0]),
                     lambda: self.ui._export_svg(self.lib.drawings[0], grid=True),
                     lambda: self.ui._export_jpg(self.lib.drawings[0]),
                     lambda: self.ui._export_jpg(self.lib.drawings[0], grid=True)):
            call()  # CANCELLED, so no save dialog ever opens
        self.assertEqual(len(asked), 6)
        # JPEG is the one that must not offer transparency.
        self.assertEqual([kw.get("allow_transparent", True) for _a, kw in asked],
                         [True, True, True, True, False, False])

    def test_the_row_menu_lists_jpg_with_grid(self):
        labels = self.ui._rows[id(self.lib.drawings[0])]["popup"].labels()
        self.assertIn(i18n.t("export_jpg_grid"), labels)

    def test_no_native_menu_or_dialog_is_left(self):
        """#v2.8.0: every popup is the kit's own, in the kit's colours - the
        native Menu, messagebox, simpledialog and colorchooser came up grey."""
        source = Path(app.__file__).read_text(encoding="utf-8")
        for native in ("tk.Menu(", "messagebox.", "simpledialog.", "colorchooser"):
            self.assertNotIn(native, source, native)
        menu = self.ui._rows[id(self.lib.drawings[0])]["popup"]
        self.assertIsInstance(menu, dialogs.PopupMenu)
        menu.tk_popup(10, 10)
        self.assertIsNotNone(menu._win)
        menu.unpost()
        self.assertIsNone(menu._win)

    def test_a_menu_opens_upwards_rather_than_off_the_screen(self):
        area = (0, 0, 1000, 800)
        # room below: below and to the right of the point, like a native menu
        self.assertEqual(dialogs.place_menu(100, 200, 160, 300, area), (100, 200))
        # none: it ends at the top of the button it hangs from, never over it...
        self.assertEqual(dialogs.place_menu(100, 700, 160, 300, area, flip_y=680), (100, 380))
        # ...or at the point itself when it hangs from no button
        self.assertEqual(dialogs.place_menu(100, 700, 160, 300, area), (100, 400))
        # never past the right-hand edge, never above or left of the screen
        self.assertEqual(dialogs.place_menu(950, 10, 160, 300, area), (840, 10))
        self.assertEqual(dialogs.place_menu(-50, 100, 160, 900, area), (0, 0))
        # a monitor left of the main one has negative coordinates, and a menu
        # opened there stays there
        self.assertEqual(dialogs.place_menu(-1500, 100, 160, 300, (-1920, 0, 0, 1080)),
                         (-1500, 100))

    def test_the_menu_answers_the_arrow_keys_and_enter(self):
        ran = []
        menu = dialogs.PopupMenu(self.root)
        menu.add_command(label="one", command=lambda: ran.append(1))
        menu.add_separator()
        menu.add_command(label="two", command=lambda: ran.append(2))
        menu.tk_popup(10, 10)
        self.addCleanup(menu.unpost)
        rows = [row for row, _command in menu._rows]
        self.assertEqual([r.cget("text") for r in rows], ["one", "two"], "a separator is no stop")
        self.assertEqual(rows[0].cget("activebackground"), theme.ACCENT,
                         "the row about to run wears the accent, like the selected tool")
        menu._step(+1)
        self.assertEqual(rows[0].cget("bg"), theme.ACCENT)
        menu._step(+1)
        self.assertEqual((rows[0].cget("bg"), rows[1].cget("bg")), (theme.PANEL, theme.ACCENT),
                         "one lit row at a time")
        menu._step(+1)
        self.assertEqual(menu._active, 0, "and round again")
        menu._step(-1)
        menu._invoke_active()
        self.assertEqual(ran, [2])
        self.assertIsNone(menu._win, "choosing closes it")

    def _answer(self, act):
        """Do `act(dialog)` to the next modal dialog from inside its own
        `wait_window`, which is the only place a modal dialog can be answered.
        The dialog is destroyed afterwards whatever `act` did, so a broken
        answer fails the test rather than hanging it."""
        def found(widget):
            # anywhere in the tree: a question asked over a dialog is ITS child
            for child in widget.winfo_children():
                if isinstance(child, dialogs.Dialog):
                    yield child
                yield from found(child)

        def go():
            try:
                act(list(found(self.root))[-1])
            finally:
                for w in list(found(self.root)):
                    if w.winfo_exists():
                        w.destroy()
        self.root.after(10, go)

    @staticmethod
    def _press(dialog, text):
        """Click the button reading `text` in `dialog`."""
        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, theme.Button):
                    yield child
                yield from buttons(child)
        next(b for b in buttons(dialog) if b.cget("text") == text).invoke()

    def test_the_kits_message_boxes_answer_like_the_native_ones(self):
        self._answer(lambda dlg: self._press(dlg, i18n.t("yes")))
        self.assertTrue(dialogs.askyesno("t", "Delete it?", parent=self.root, icon="warning"))
        self._answer(lambda dlg: self._press(dlg, i18n.t("no")))
        self.assertFalse(dialogs.askyesno("t", "Delete it?", parent=self.root))
        self._answer(lambda dlg: dlg.cancel())                   # Esc, or the window's X
        self.assertFalse(dialogs.askyesno("t", "Delete it?", parent=self.root))

        seen = []

        def rename(dlg):
            entry = next(w for w in dlg.body.winfo_children() if isinstance(w, tkinter.Entry))
            seen.append(entry.get())
            entry.delete(0, "end")
            entry.insert(0, "icon")
            self._press(dlg, i18n.t("ok"))
        self._answer(rename)
        self.assertEqual(dialogs.askstring("t", "New name:", initialvalue="icon copy",
                                           parent=self.root), "icon")
        self.assertEqual(seen, ["icon copy"], "it opens on the current name")
        self._answer(lambda dlg: self._press(dlg, i18n.t("cancel")))
        self.assertIsNone(dialogs.askstring("t", "New name:", parent=self.root))

        strips = []

        def look(dlg):
            def frames(widget):
                for child in widget.winfo_children():
                    if isinstance(child, tkinter.Frame) and str(child.cget("width")) == "3":
                        yield child
                    yield from frames(child)
            strips.extend(f.cget("bg") for f in frames(dlg))
            self._press(dlg, i18n.t("ok"))
        self._answer(look)
        dialogs.showerror("t", "Could not save", parent=self.root)
        self._answer(look)
        dialogs.showinfo("t", "Imported", parent=self.root)
        self.assertEqual(strips, [theme.ERROR, theme.ACCENT])

    def test_the_colour_dialog_reports_every_change(self):
        seen = []
        dlg = app.ColourDialog(self.root, "232F28", on_change=seen.append)
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        self.assertEqual((dlg.colour, dlg.entry.get()), ("#232f28", "#232f28"))
        self.assertEqual(seen, [], "opening it is not a change")
        dlg._picked((1, 2, 3))                                   # a click on the shade square
        self.assertEqual((dlg.colour, dlg.entry.get()), ("#010203", "#010203"))
        dlg.entry.delete(0, "end")
        dlg.entry.insert(0, "A0B0C0")
        dlg._typed()
        self.assertEqual(dlg.colour, "#a0b0c0")
        dlg.entry.insert("end", "F")                             # seven digits: not a colour
        dlg._typed()
        self.assertEqual(seen, ["#010203", "#a0b0c0"])
        self._press(dlg, i18n.t("ok"))
        self.assertEqual(dlg.result, "#a0b0c0")

    def test_the_grid_picker_previews_live_and_is_one_undo_step(self):
        """#v2.8.0: the grid's … used to open the Windows colour chooser. The
        kit's own picker repaints the checkerboard on every drag step; CANCEL
        puts it back and OK is one undo step, however far it travelled."""
        from unittest import mock
        self.ui.new_drawing(8, 8)
        start = self.ui.grid_colours()
        during = []

        def drag_then(answer):
            def fake(parent, current, title=None, on_change=None):
                self.assertEqual(current, start[0])
                for hexcol in ("#112233", "#445566"):
                    on_change(hexcol)
                    during.append(self.ui.grid_colours()[0])
                return answer
            return fake

        depth = len(self.ui.history._undo)
        with mock.patch.object(app, "ask_colour", drag_then("#445566")):
            self.ui._pick_grid_colour("c1")
        self.assertEqual(during, ["#112233", "#445566"], "the grid followed the picker")
        self.assertEqual(self.ui.grid_colours()[0], "#445566")
        self.assertEqual(self.settings.grid["c1"], "445566")
        self.assertEqual(len(self.ui.history._undo) - depth, 1, "one undo step for the drag")
        self.ui.undo()
        self.assertEqual(self.ui.grid_colours(), start)

        during.clear()
        with mock.patch.object(app, "ask_colour", drag_then(None)):    # CANCEL
            self.ui._pick_grid_colour("c1")
        self.assertEqual(during, ["#112233", "#445566"])
        self.assertEqual(self.ui.grid_colours(), start, "cancel puts it back")
        self.assertIsNone(self.ui._grid_preview)
        self.assertEqual(len(self.ui.history._undo) - depth, 0, "and records nothing")

    def test_the_background_dialog_previews_exactly_what_it_will_export(self):
        drawing = self.lib.drawings[0]
        dialog = app.BackgroundDialog(self.root, None, drawing=drawing, grid="FF0000")
        self.addCleanup(dialog.destroy)
        self.assertIs(dialog.result, app.CANCELLED)  # closing it must not export
        self.assertIsNone(dialog._choice)  # transparent, the default
        self.assertIsNotNone(dialog._image)  # the preview was drawn
        cells = engine_io.render(drawing)
        scale = max(1, min(app.BackgroundDialog.PREVIEW // len(cells[0]),
                           app.BackgroundDialog.PREVIEW // len(cells)))
        self.assertEqual(dialog._image.width(), len(cells[0]) * scale)
        dialog._choose("FFFFFF")
        self.assertEqual(dialog._choice, "FFFFFF")
        dialog._confirm()
        self.assertEqual(dialog.result, "FFFFFF")

    def test_the_background_dialog_refuses_transparent_for_jpeg(self):
        dialog = app.BackgroundDialog(self.root, None, drawing=self.lib.drawings[0],
                                      allow_transparent=False)
        self.addCleanup(dialog.destroy)
        self.assertEqual(dialog._choice, "FFFFFF")  # not None: JPEG has no alpha
        dialog._choose(None)
        self.assertEqual(dialog._choice, "FFFFFF")  # and it stays refused

    def test_the_background_dialog_picks_a_colour_inline_and_updates_live(self):
        """#v2.8.0: COLOUR opens a picker under the buttons, not a second
        modal window, and every pick repaints the preview at once."""
        dialog = app.BackgroundDialog(self.root, None, drawing=self.lib.drawings[0])
        self.addCleanup(dialog.destroy)
        self.assertFalse(dialog._picker_shown)          # transparent to start
        dialog._choose(app.CHOOSE)
        self.assertTrue(dialog._picker_shown)
        self.assertEqual(dialog._choice, dialog.FALLBACK)
        first = dialog._image
        dialog._picked((255, 0, 0))                     # a click in the shade square
        self.assertEqual(dialog._choice, "FF0000")
        self.assertIsNot(dialog._image, first)          # the preview was redrawn
        self.assertEqual(dialog._hex.get(), "FF0000")
        dialog._choose("FFFFFF")                        # back to a flat answer
        self.assertFalse(dialog._picker_shown)
        dialog._choose(app.CHOOSE)                      # and it remembers the colour
        self.assertEqual(dialog._choice, "FF0000")

    def test_the_background_dialogs_hex_box_takes_a_code_and_ignores_rubbish(self):
        dialog = app.BackgroundDialog(self.root, "123456", drawing=self.lib.drawings[0])
        self.addCleanup(dialog.destroy)
        self.assertTrue(dialog._picker_shown)           # opened on a custom colour
        dialog._hex.delete(0, "end")
        dialog._hex.insert(0, "#00FF00")
        dialog._on_hex()
        self.assertEqual(dialog._choice, "00FF00")
        dialog._hex.delete(0, "end")
        dialog._hex.insert(0, "not a colour")
        dialog._on_hex()
        self.assertEqual(dialog._choice, "00FF00")      # unchanged
        self.assertEqual(dialog._hex.get(), "00FF00")   # and put back

    def test_the_tools_picker_and_the_dialog_picker_are_the_same_widget(self):
        """One control, two places - the export dialog must not grow its own."""
        self.assertIsInstance(self.ui._picker, app.ColourPicker)
        dialog = app.BackgroundDialog(self.root, None, drawing=self.lib.drawings[0])
        self.addCleanup(dialog.destroy)
        self.assertIsInstance(dialog._picker, app.ColourPicker)

    def test_a_move_undoes_in_one_press_not_two(self):
        """#v2.8.0. Lifting cleared the cells and dropping stamped them, as two
        entries - so the first Ctrl+Z after a move undid the DROP and left the
        artist with a hole where their block had been."""
        self.ui.new_drawing(12, 12)
        self.ui.history.current.paint(1, 1, "m")
        self.ui.set_tool("select")
        self.ui.select_region(1, 1, 2, 2)
        before = [list(r) for r in self.ui.history.current.cells]
        self.ui.on_canvas_press(1, 1)          # lifts
        self.ui.on_canvas_drag(5, 5)
        self.ui.on_canvas_release()
        self.assertTrue(self.ui.commit_floating())
        self.assertEqual(self.ui.history.current.get(5, 5), "m")
        self.ui.undo()
        self.assertEqual(self.ui.history.current.cells, before)

    def test_undo_with_a_block_still_in_the_air_puts_it_back(self):
        """Ctrl+Z mid-move drops the block AND restores the lifted cells."""
        self.ui.new_drawing(12, 12)
        self.ui.history.current.paint(1, 1, "m")
        self.ui.set_tool("select")
        self.ui.select_region(1, 1, 2, 2)
        before = [list(r) for r in self.ui.history.current.cells]
        self.ui.on_canvas_press(1, 1)
        self.ui.on_canvas_drag(5, 5)
        self.ui.on_canvas_release()
        self.assertIsNotNone(self.ui.floating)
        self.assertIsNone(self.ui.history.current.get(1, 1), "lifted off")
        self.ui.undo()
        self.assertIsNone(self.ui.floating, "the block is gone")
        self.assertEqual(self.ui.history.current.cells, before)
        self.assertFalse(self.ui.history.can_undo(), "and it left no entry behind")

    def test_undo_with_a_pasted_block_in_the_air_just_cancels_the_paste(self):
        self.ui.new_drawing(10, 10)
        self.ui.history.current.paint(1, 1, "m")
        self.ui.select_region(1, 1, 1, 1)
        self.assertTrue(self.ui.copy_selection())
        self.assertTrue(self.ui.paste(5, 5))
        self.ui.undo()
        self.assertIsNone(self.ui.floating)
        self.assertEqual(self.ui.history.current.get(1, 1), "m", "the source is untouched")
        self.assertIsNone(self.ui.history.current.get(5, 5))

    def test_delete_with_a_block_in_the_air_is_one_undoable_delete(self):
        self.ui.new_drawing(10, 10)
        self.ui.history.current.paint(1, 1, "m")
        self.ui.set_tool("select")
        self.ui.select_region(1, 1, 2, 2)
        before = [list(r) for r in self.ui.history.current.cells]
        self.ui.on_canvas_press(1, 1)       # lifts
        self.assertTrue(self.ui.delete_selection())
        self.assertIsNone(self.ui.floating)
        self.assertIsNone(self.ui.history.current.get(1, 1))
        self.ui.undo()
        self.assertEqual(self.ui.history.current.cells, before)

    def test_undo_walks_everything_in_the_order_it_happened(self):
        """#v2.8.0. Strokes are not the only thing an artist does on purpose.
        Changing a grid colour and pressing Ctrl+Z has to give back the grid
        colour, not the last brush stroke - and the entries have to queue,
        not jump. Up to #v2.7.0 the one non-stroke kind (a corner-drag zoom)
        lived in a list of its own that Ctrl+Z drained FIRST."""
        self.ui.new_drawing(8, 8)
        self.ui.set_grid_colours(c1="111111")
        self.ui.history.begin_stroke()
        self.ui.history.current.paint(0, 0, "m")
        self.ui.history.end_stroke()
        self.ui.set_grid_colours(c1="222222")
        self.ui.history.begin_stroke()
        self.ui.history.current.paint(1, 0, "l")
        self.ui.history.end_stroke()
        self.assertEqual(self.ui.grid_colours()[0], "#222222")

        self.ui.undo()                                   # the second stroke
        self.assertIsNone(self.ui.history.current.get(1, 0))
        self.assertEqual(self.ui.grid_colours()[0], "#222222", "no queue jumping")
        self.ui.undo()                                   # then the grid colour
        self.assertEqual(self.ui.grid_colours()[0], "#111111")
        self.assertEqual(self.ui.history.current.get(0, 0), "m")
        self.ui.undo()                                   # then the first stroke
        self.assertIsNone(self.ui.history.current.get(0, 0))
        self.ui.undo()                                   # then the first grid colour
        self.assertNotEqual(self.ui.grid_colours()[0], "#111111")

        for _ in range(4):
            self.ui.redo()
        self.assertEqual(self.ui.grid_colours()[0], "#222222")
        self.assertEqual(self.ui.history.current.get(0, 0), "m")
        self.assertEqual(self.ui.history.current.get(1, 0), "l")

    def test_zoom_goes_in_far_enough_for_one_pixel_whatever_the_grid_size(self):
        """#v2.8.0. 48 px a cell was the old ceiling, and it was there because
        the whole drawing was rendered at that scale. The viewport renderer
        makes a repaint cost a paneful whatever the zoom is, so a 64x64 tree
        goes exactly as far in as a 16x16 sprite."""
        for w, h in ((16, 16), (64, 64)):
            self.ui.new_drawing(w, h)
            self.assertEqual(self.ui.max_zoom(), app.MAX_ZOOM)
            self.ui.set_zoom(10 ** 6)
            self.assertEqual(self.ui.zoom_level, app.MAX_ZOOM, f"{w}x{h}")
            self.assertGreaterEqual(self.ui.zoom_level, 900,
                                    "one cell has to be able to fill the pane")
            self.ui.set_zoom(0)
            self.assertEqual(self.ui.zoom_level, app.MIN_ZOOM)

    def _camera(self, width=1000, height=800, origin=(0, 0)):
        """Pretend the pane is `width` x `height` with its corner at `origin`.

        Tk reports a 1x1 canvas for a window it has not mapped - on Windows
        and X11; Aqua lays an unmapped window out all the same, at a size no
        test chose - and the tests never map one, so a camera test run
        against the real widget would be measuring the fallback instead of the
        code. The arithmetic under test is all in these three seams, so they
        are the honest place to stand the test up - and `_scroll_to` is
        captured rather than performed, because the canvas's own view is the
        part that needs a window."""
        moved = []
        self.ui._viewport = lambda: (width, height)
        self.ui._view_origin = lambda: origin
        self.ui._scroll_to = lambda vx, vy: moved.append((vx, vy))
        return moved

    def test_the_view_only_renders_the_cells_inside_the_pane(self):
        """The whole point of the rewrite: what is rendered is bounded by the
        PANE, not by the drawing times the zoom. At 1024 px a cell the old
        whole-drawing render wanted a 64x64 grid as a 65536-pixel square."""
        self.ui.new_drawing(64, 64)
        self._camera(1000, 800)
        self.ui.zoom_level = app.MAX_ZOOM
        c0, r0, c1, r1 = self.ui._visible_cells()
        self.assertLessEqual((c1 - c0 + 1) * (r1 - r0 + 1), 9,
                             "at 1024px a cell only a couple are on screen")
        self.ui._draw_main()
        img = self.ui._images["main"]
        self.assertLessEqual(img.width(), 1000 + 2 * app.MAX_ZOOM)
        self.assertLessEqual(img.height(), 800 + 2 * app.MAX_ZOOM)

    def test_the_visible_tile_follows_the_camera(self):
        self.ui.new_drawing(64, 64)
        self._camera(400, 400, origin=(0, 0))
        self.ui.zoom_level = 32
        self.assertEqual(self.ui._visible_cells(), (0, 0, 12, 12))
        self._camera(400, 400, origin=(32 * 20, 32 * 10))
        self.assertEqual(self.ui._visible_cells(), (20, 10, 32, 22))
        self._camera(400, 400, origin=(32 * 60, 32 * 60))
        self.assertEqual(self.ui._visible_cells(), (60, 60, 63, 63),
                         "clamped to the drawing, not the pane")

    def test_the_camera_always_keeps_at_least_one_cell_on_screen(self):
        """#v2.8.0: the view is free of the drawing's top-left corner now, but
        it can never be scrolled to somewhere the drawing is not."""
        self.ui.new_drawing(16, 16)
        cw = ch = 400
        self._camera(cw, ch)
        self.ui.zoom_level = z = 32
        span = 16 * z
        x0, y0, x1, y1 = self.ui._scroll_bounds()
        # The leading edge may range over [z - pane, span - z]: at either end
        # exactly one cell of the drawing is still inside the frame.
        self.assertEqual((x0, x1 - cw), (z - cw, span - z))
        self.assertEqual((y0, y1 - ch), (z - ch, span - z))
        for vx in (x0, x1 - cw):
            self._camera(cw, ch, origin=(vx, y0))
            self.assertIsNotNone(self.ui._visible_cells())

    def test_one_cell_wider_than_the_pane_still_has_somewhere_to_sit(self):
        """The bounds must not invert when a single cell overflows the pane."""
        self.ui.new_drawing(2, 2)
        self._camera(300, 300)
        self.ui.zoom_level = 1024
        x0, y0, x1, y1 = self.ui._scroll_bounds()
        self.assertLessEqual(x0, x1 - 300)
        self.assertLessEqual(y0, y1 - 300)

    def test_a_wheel_zoom_keeps_the_cell_under_the_pointer_under_the_pointer(self):
        self.ui.new_drawing(32, 32)
        moved = self._camera(400, 400, origin=(160, 160))
        self.ui.zoom_level = 16
        focus = (300, 250)
        # the cell the pointer is over, before
        cx, cy = (160 + focus[0]) / 16, (160 + focus[1]) / 16
        self.ui.zoom(+1, focus=focus)
        self.assertGreater(self.ui.zoom_level, 16)
        z = self.ui.zoom_level
        self.assertTrue(moved, "the camera moved to follow the pointer")
        vx, vy = moved[-1]
        # the same cell is still under the same point on screen
        self.assertAlmostEqual((vx + focus[0]) / z, cx, delta=0.001)
        self.assertAlmostEqual((vy + focus[1]) / z, cy, delta=0.001)

    def test_zoom_to_fit_centres_the_drawing_instead_of_pinning_it_top_left(self):
        self.ui.new_drawing(16, 16)
        moved = self._camera(1000, 800)
        self.ui.centre_view()
        z = self.ui.zoom_level
        self.assertTrue(moved)
        vx, vy = moved[-1]
        self.assertEqual(vx, (16 * z - 1000) / 2)
        self.assertEqual(vy, (16 * z - 800) / 2)

    def test_the_wheel_step_scales_so_the_whole_range_stays_reachable(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_zoom(app.MIN_ZOOM)
        notches = 0
        while self.ui.zoom_level < self.ui.max_zoom() and notches < 200:
            self.ui.zoom(+1)
            notches += 1
        self.assertEqual(self.ui.zoom_level, self.ui.max_zoom())
        self.assertLess(notches, 40, "a flat +2 step would be a hundred notches")

    def test_closing_with_a_block_in_the_air_lands_it_first(self):
        """An open lift must never reach the disk as a clear with no undo."""
        self.ui.new_drawing(10, 10)
        self.ui.history.current.paint(1, 1, "m")
        self.ui.set_tool("select")
        self.ui.select_region(1, 1, 1, 1)
        self.ui.on_canvas_press(1, 1)
        self.ui.nudge_floating(3, 0)
        drawing = self.ui._selected
        self.root.destroy = lambda: None   # let close() run without taking the test's root
        self.ui.close()
        self.assertEqual(drawing.get(4, 1), "m")
        self.assertIsNone(drawing.get(1, 1))

    def test_the_row_menu_dots_are_bigger_without_moving_the_row(self):
        """#v2.8.0: a 7x15 glyph in a 19px button was too small to aim at."""
        row = self.ui._rows[id(self.lib.drawings[0])]
        button = row["menu"]
        self.root.update_idletasks()
        _family, size, *rest = self.root.tk.splitlist(button.cget("font"))
        self.assertGreater(int(size), theme.FONT_SIZE)
        self.assertIn("bold", rest)
        # The thumbnail sets the row height, and it has not changed.
        self.assertLessEqual(button.winfo_reqheight(), row["row"].winfo_reqheight())
        self.assertLessEqual(button.winfo_reqwidth(), 24)

    def test_the_last_mixed_export_colour_survives_a_white_export(self):
        """#v2.8.0: the ANSWER and the COLOUR are remembered separately, so
        one transparent export does not throw away a mixed colour."""
        dialog = app.BackgroundDialog(self.root, None, drawing=self.lib.drawings[0])
        self.addCleanup(dialog.destroy)
        dialog._picked((18, 52, 86))
        self.assertEqual(dialog._choice, "123456")
        dialog._confirm()
        self.settings.export_background = dialog.result
        self.settings.export_colour = dialog._custom

        # next export: the artist picks WHITE
        second = app.BackgroundDialog(self.root, self.settings.export_background,
                                      drawing=self.lib.drawings[0],
                                      last_colour=self.settings.export_colour)
        self.addCleanup(second.destroy)
        self.assertEqual(second._choice, "123456", "it opens on the remembered colour")
        second._choose("FFFFFF")
        second._confirm()
        self.settings.export_background = second.result
        self.settings.export_colour = second._custom
        self.assertEqual(self.settings.export_background, "FFFFFF")
        self.assertEqual(self.settings.export_colour, "123456", "the colour is still there")

        # third: COLOUR goes straight back to it, no picker round trip
        third = app.BackgroundDialog(self.root, self.settings.export_background,
                                     drawing=self.lib.drawings[0],
                                     last_colour=self.settings.export_colour)
        self.addCleanup(third.destroy)
        self.assertEqual(third._choice, "FFFFFF")
        third._choose(app.CHOOSE)
        self.assertEqual(third._choice, "123456")

    def test_zooming_out_goes_all_the_way_to_one_pixel_a_cell(self):
        """#v2.8.0. It briefly stopped where the drawing fit the pane; 1x is
        the sprite at the size the game draws it, which is a thing an artist
        wants to look at, so the floor is 1 in every camera mode."""
        self.assertEqual(app.MIN_ZOOM, 1)
        self.ui.new_drawing(16, 16)
        for mode in app.CAMERA_MODES:
            self.ui.set_camera_mode(mode)
            self.ui.set_zoom(0)
            self.assertEqual(self.ui.zoom_level, 1, mode)
            self.assertIsNotNone(self.ui._visible_cells(), f"{mode}: still on screen at 1x")

    def test_fit_is_still_the_zoom_that_shows_the_whole_drawing(self):
        self.ui.new_drawing(16, 16)
        cw, ch = self.ui._viewport()
        self.assertEqual(self.ui.fit_zoom(), min(cw // 16, ch // 16))
        self.ui.zoom_to_fit()
        self.assertLessEqual(16 * self.ui.zoom_level, cw)
        self.assertLessEqual(16 * self.ui.zoom_level, ch)

    def test_an_anchored_mode_is_as_free_as_free_when_zoomed_in(self):
        """Zoomed in, the seven alignments are all the same thing: the same
        one-cell rule FREE gets. The alignment only answers a question that
        exists when there is slack - and anything tighter would stop a zoom
        about a pointer near an edge from keeping its cell under the pointer,
        which is the bug that sent this round back (#v2.8.0)."""
        self.ui.new_drawing(16, 16)
        cw = ch = 400
        self._camera(cw, ch)
        self.ui.zoom_level = z = 64         # 1024px of art in a 400px pane
        span = 16 * z
        for mode in (app.CAM_TOP_LEFT, app.CAM_BOTTOM_RIGHT, app.CAM_CENTRE,
                     app.CAM_LEFT, app.CAM_RIGHT, app.CAM_TOP_RIGHT,
                     app.CAM_BOTTOM_LEFT, app.CAM_FREE):
            self.ui.camera_mode = mode
            x0, y0, x1, y1 = self.ui._scroll_bounds()
            self.assertEqual((x0, x1 - cw), (z - cw, span - z), mode)
            self.assertEqual((y0, y1 - ch), (z - ch, span - z), mode)

    def test_an_anchored_mode_parks_against_its_edge_when_zoomed_out(self):
        """Zoomed out there IS slack, and this is what the seven are for."""
        self.ui.new_drawing(16, 16)
        cw = ch = 400
        self._camera(cw, ch)
        self.ui.zoom_level = 8              # 128px of art in a 400px pane
        span, slack = 16 * 8, 16 * 8 - 400  # negative: the edge sits left of the art
        cases = {
            app.CAM_TOP_LEFT: (0, 0),
            app.CAM_TOP_RIGHT: (slack, 0),
            app.CAM_BOTTOM_LEFT: (0, slack),
            app.CAM_BOTTOM_RIGHT: (slack, slack),
            app.CAM_LEFT: (0, slack // 2),
            app.CAM_CENTRE: (slack // 2, slack // 2),
            app.CAM_RIGHT: (slack, slack // 2),
        }
        for mode, (wantx, wanty) in cases.items():
            self.ui.camera_mode = mode
            x0, y0, x1, y1 = self.ui._scroll_bounds()
            self.assertEqual((x0, x1 - cw), (wantx, wantx), mode)
            self.assertEqual((y0, y1 - ch), (wanty, wanty), mode)
        self.assertEqual(span, 128)

    def test_every_mode_with_room_zooms_about_the_pointer(self):
        """The cursor-follow is not a FREE-mode privilege: any axis that has
        somewhere to go follows the pointer (#v2.8.0). LOCK does not zoom at
        all, and has a test of its own."""
        self.ui.new_drawing(32, 32)
        focus = (300, 250)
        for mode in app.CAMERA_MODES:
            if mode == app.CAM_LOCK:
                continue
            self.ui.camera_mode = mode
            moved = self._camera(400, 400, origin=(160, 160))
            self.ui.zoom_level = 32         # 1024px of art in a 400px pane: room on both axes
            cx, cy = (160 + focus[0]) / 32, (160 + focus[1]) / 32
            self.ui.zoom(+1, focus=focus)
            z = self.ui.zoom_level
            self.assertGreater(z, 32, mode)
            self.assertTrue(moved, mode)
            vx, vy = moved[-1]
            self.assertAlmostEqual((vx + focus[0]) / z, cx, delta=0.001, msg=mode)
            self.assertAlmostEqual((vy + focus[1]) / z, cy, delta=0.001, msg=mode)

    def test_every_camera_mode_still_zooms_and_keeps_a_cell_on_screen(self):
        """Every mode but LOCK leaves the zoom free, and no mode may let the
        drawing off screen entirely."""
        self.ui.new_drawing(16, 16)
        for mode in app.CAMERA_MODES:
            if mode == app.CAM_LOCK:
                continue
            self.ui.set_camera_mode(mode)
            self.ui.set_zoom(app.MAX_ZOOM)
            self.assertEqual(self.ui.zoom_level, app.MAX_ZOOM, mode)
            self.ui.set_zoom(0)
            self.assertEqual(self.ui.zoom_level, app.MIN_ZOOM, mode)
            self._camera(400, 400)
            self.ui.zoom_level = 64
            x0, y0, x1, y1 = self.ui._scroll_bounds()
            for origin in ((x0, y0), (x1 - 400, y1 - 400)):
                self._camera(400, 400, origin=origin)
                self.assertIsNotNone(self.ui._visible_cells(), f"{mode} at {origin}")

    def test_lock_freezes_the_zoom_as_well_as_the_view(self):
        """#v2.8.0: "lock halinde kamera acisi sabit olmasi lazim" - a locked
        camera that still zoomed out was not locked. Wheel, keys, FIT and
        set_zoom all leave it where it is, and FREE gives the zoom back."""
        self.ui.new_drawing(16, 16)
        self._camera(400, 400)
        # The pane is laid out and fitted, as a real session is: FIT is the
        # button, not the first fit - which Aqua, laying out the test's
        # withdrawn window, would otherwise run at the first redraw.
        self.ui._fitted = True
        self.ui.set_zoom(32)
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.ui.zoom(-1)
        self.ui.zoom(+1, focus=(10, 10))
        self.ui.set_zoom(app.MIN_ZOOM)
        self.ui.zoom_to_fit()
        self.ui.fit_pressed()
        self.ui._cam_fit_button.invoke()
        self.assertEqual(self.ui.zoom_level, 32)
        self.ui.set_camera_mode(app.CAM_FREE)
        self.ui.set_zoom(app.MIN_ZOOM)
        self.assertEqual(self.ui.zoom_level, app.MIN_ZOOM)

    def test_lock_swallows_every_pan_and_says_why(self):
        """The wheel, Shift+wheel, Space+drag, the middle button, the
        scrollbars and a stroke dragged against the edge: none of them move a
        LOCKed view, and the ones the artist aimed at the camera say "camera
        locked" - a dead wheel with no word of explanation reads as a frozen
        app. Said steadily: the LOCK button used to blink with every notch,
        which read as LOCK and the zoom fighting."""
        self.ui.new_drawing(32, 32)
        self._camera(400, 400, origin=(100, 100))
        self.ui.zoom_level = 32
        self.ui._fitted = True                   # past the first fit, as a real session is
        self.ui.set_camera_mode(app.CAM_LOCK)
        scrolled = []
        canvas = self.ui.canvas
        for name in ("xview", "yview", "xview_scroll", "yview_scroll", "scan_mark", "scan_dragto"):
            setattr(canvas, name, lambda *a, _n=name, **kw: scrolled.append(_n))
        canvas.winfo_width = canvas.winfo_height = lambda: 400

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui._set_status("")
        lock = self.ui._cam_mode_buttons[app.CAM_LOCK]
        fades = []
        for _notch in range(5):                  # a wheel spun under LOCK
            self.ui.zoom(-1)
            self.assertEqual(lock.cget("bg"), theme.ACCENT, "LOCK stays lit, no blink")
            fades.append(self.ui._status_fade)
        self.ui._wheel_pan(1, 0)
        self.assertEqual(self.ui._status.cget("text"), i18n.t("cam_locked"))
        self.assertEqual(self.ui._status.cget("fg"), theme.ACCENT)
        pending = [f for f in self.root.tk.splitlist(self.root.tk.call("after", "info"))
                   if f in fades or f == self.ui._status_fade]
        self.assertEqual(pending, [self.ui._status_fade],
                         "one fade waiting, not one per notch flickering the words")
        self.ui._pan_start(Ev(50, 50))
        self.ui._pan_move(Ev(90, 90))
        self.ui._xview("moveto", 0.5)
        self.ui._yview("scroll", 1, "units")
        self.ui._autoscroll(Ev(2, 2))            # a stroke against the top-left edge
        self.assertEqual(scrolled, [], "nothing asked the canvas to move")
        self.assertEqual(self.ui._locked_at, (100, 100))
        self.assertEqual(self.ui.zoom_level, 32)
        # Space still means "not a brush" under LOCK, but promises no pan.
        self.ui._space_down(type("E", (), {"widget": canvas})())
        self.assertTrue(self.ui._panning)
        self.assertEqual(str(canvas.cget("cursor")), "")
        self.ui._space_up()

    def test_the_fit_button_dims_under_lock(self):
        self.ui.new_drawing(16, 16)
        self._camera(400, 400)
        fit = self.ui._cam_fit_button
        self.assertEqual(fit._rest["fg"], theme.ON_SURFACE)
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.assertEqual(fit._rest["fg"], theme.ON_DIM)
        self.ui.set_camera_mode(app.CAM_CENTRE)
        self.assertEqual(fit._rest["fg"], theme.ON_SURFACE)

    def test_under_lock_each_drawing_keeps_its_own_frozen_view(self):
        """Framed and locked on A, a look at B, back to A: A is exactly as it
        was left. B, seen for the first time under LOCK, is fitted, centred
        and frozen there. Leaving LOCK forgets all of it."""
        a = self.ui.new_drawing(16, 16)
        b = self.ui.new_drawing(8, 8)
        self._camera(400, 400, origin=(137, 249))
        self.ui._pane_known = lambda: True
        self.ui.select(a)
        self.ui.zoom_to_fit()                    # the 80ms timer, in FREE
        self.ui.zoom_level = 64
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.assertEqual(self.ui._locked_at, (137, 249))

        self.ui.select(b)
        self.assertEqual(self.ui.zoom_level, 50, "B fitted: 400px / 8 cells")
        self.assertEqual(self.ui._locked_at, (0, 0), "and centred: 8 x 50 fills 400 exactly")
        self.ui.zoom(-1)
        self.assertEqual(self.ui.zoom_level, 50, "and frozen")

        self.ui.select(a)
        self.assertEqual((self.ui.zoom_level, self.ui._locked_at), (64, (137, 249)))

        self.ui.set_camera_mode(app.CAM_FREE)
        self.assertEqual(self.ui._lock_frames, {})
        self.assertIsNone(self.ui._locked_at)

    def test_starting_in_lock_freezes_the_fitted_centred_view(self):
        """Up to the second test pass a kit started in LOCK held the canvas
        origin, which pinned the drawing to the pane's top-left corner."""
        self.ui.new_drawing(16, 16)
        self._camera(400, 400)
        self.ui.camera_mode = app.CAM_LOCK       # as the settings file restores it
        self.ui._locked_at = None
        self.ui.zoom_to_fit()                     # what the 80ms timer does
        self.assertEqual(self.ui.zoom_level, 25)
        self.assertEqual(self.ui._locked_at, (0, 0), "16 x 25 = 400: centred is flush")
        self.assertTrue(self.ui._camera_frozen())
        self.ui.new_drawing(8, 4)
        self.ui.zoom_to_fit()
        z = self.ui.zoom_level
        self.assertEqual(z, 50)
        self.assertEqual(self.ui._locked_at, ((8 * z - 400) // 2, (4 * z - 400) // 2))

    def test_lock_reframes_only_when_the_drawing_has_left_the_frame(self):
        """A resize from the Size dialog keeps a frozen view - unless it left
        nothing of the drawing inside it, which only leaving LOCK could fix."""
        self.ui.new_drawing(32, 32)
        self._camera(400, 400, origin=(900, 900))
        self.ui._pane_known = lambda: True
        self.ui._fitted = True
        self.ui.zoom_level = 64                  # 2048px of art
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.ui.resize(24, 24)                   # 1536px: (900, 900) still sees some
        self.assertEqual((self.ui.zoom_level, self.ui._locked_at), (64, (900, 900)))
        self.ui.resize(8, 8)                     # 512px: nothing left in the frame
        self.assertEqual(self.ui.zoom_level, 50)
        self.assertEqual(self.ui._locked_at, (0, 0))
        self.assertTrue(self.ui._camera_frozen(), "re-framed, and still locked")

    def test_the_camera_mode_persists_and_is_rejected_if_unknown(self):
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.assertEqual(self.settings.camera, app.CAM_LOCK)
        with self.assertRaises(ValueError):
            self.ui.set_camera_mode("sideways")

    def test_the_camera_bar_buttons_are_pinned_chrome_like_the_rest(self):
        keys = {key for _btn, key in self.ui._chrome_pairs()}
        for key in ("cam_fit", "cam_free"):
            self.assertIn(key, keys, "the worded buttons are pinned like the rest")
        self.assertIsNotNone(self.ui._cam_fit_button.pinned)
        # The other eight are glyphs - an arrow at a corner needs no word -
        # so the caption on the right is what names the mode, translated.
        self.assertEqual(len(self.ui._cam_mode_buttons), len(app.CAMERA_MODES))
        for mode in app.CAMERA_MODES:
            self.ui.set_camera_mode(mode)
            self.assertEqual(self.ui._cam_name_label.cget("text"),
                             i18n.t(app.CAMERA_NAMES[mode]))

    def test_the_ready_colours_are_six_full_rows_sorted_by_similarity(self):
        """#v2.8.0: two more rows, and the whole set re-ordered."""
        import colorsys
        self.assertEqual(len(app.READY), 48)
        self.assertEqual(len(app.READY) % app.SWATCH_COLS, 0, "no ragged last row")
        self.assertEqual(len(set(app.READY)), len(app.READY), "no duplicates")

        def chroma(h):
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (max(r, g, b) - min(r, g, b)) / 255

        neutral_from = min(i for i, h in enumerate(app.READY) if chroma(h) < 0.12)
        for h in app.READY[neutral_from:]:
            self.assertLess(chroma(h), 0.12, "the neutrals are one run at the end")
        hues = []
        for h in app.READY[:neutral_from]:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            hues.append(round(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 24))
        self.assertEqual(hues, sorted(hues), "the chromatic ones run through the spectrum")

    def test_a_wheel_notch_is_reversible_in_every_mode(self):
        """#v2.8.0. The step used to be computed from the current zoom -
        `z + max(2, z // 4)` took 16 up to 20 and 20 back down to 15 - so a
        stray notch left the artist slightly off the zoom they had chosen.
        The ladder is a fixed list, so up-then-down returns exactly. (Not
        under LOCK, which holds the zoom.)"""
        self.ui.new_drawing(16, 19)
        self._camera(400, 400)
        for mode in app.CAMERA_MODES:
            if mode == app.CAM_LOCK:
                continue
            self.ui.camera_mode = mode
            for z in self.ui.zoom_stops():
                self.ui.zoom_level = z
                self.ui.zoom(+1)
                up = self.ui.zoom_level
                self.ui.zoom(-1)
                if up != z:                     # not already at the ceiling
                    self.assertEqual(self.ui.zoom_level, z, f"{mode} at {z}")

    def test_the_wheel_reaches_both_ends_of_the_range(self):
        self.ui.new_drawing(16, 19)
        self._camera(400, 400)
        self.ui.zoom_level = app.MAX_ZOOM
        for _ in range(len(app.ZOOM_STOPS) + 5):
            self.ui.zoom(-1)
        self.assertEqual(self.ui.zoom_level, self.ui.min_zoom())
        for _ in range(len(app.ZOOM_STOPS) + 5):
            self.ui.zoom(+1)
        self.assertEqual(self.ui.zoom_level, self.ui.max_zoom())

    def test_a_zoom_between_two_stops_moves_on_rather_than_snapping_back(self):
        """The corner handle leaves a level that is not on the ladder."""
        self.ui.new_drawing(16, 19)
        self._camera(400, 400)
        self.ui.zoom_level = 20                 # between 16 and 24
        self.ui.zoom(+1)
        self.assertEqual(self.ui.zoom_level, 24)
        self.ui.zoom_level = 20
        self.ui.zoom(-1)
        self.assertEqual(self.ui.zoom_level, 16)

    def test_fit_uses_the_one_definition_and_refits_once_the_pane_is_real(self):
        """FIT read `winfo_width` itself while every other camera method went
        through `_viewport`, so the two disagreed exactly when the pane was
        not laid out - which is when FIT runs, 80ms after a drawing opens."""
        self.ui.new_drawing(16, 16)
        self._camera(400, 400)
        # A pane Tk has not laid out: 1x1. Said, not assumed - Aqua lays out
        # even the withdrawn window the tests run in.
        self.ui.canvas.winfo_width = self.ui.canvas.winfo_height = lambda: 1
        self.ui.zoom_to_fit()
        self.assertEqual(self.ui.zoom_level, self.ui.fit_zoom())
        self.assertLessEqual(16 * self.ui.zoom_level, 400)
        # So that fit was against NOMINAL_VIEW - and the app knows it, and
        # will fit again for real.
        self.assertFalse(self.ui._pane_known())
        self.assertFalse(self.ui._fitted)

    def test_the_status_message_lives_in_the_camera_bar_now(self):
        """#v2.8.0: it cost SAVE fourteen characters of width; up in the top
        right corner it costs nothing and is nearer the eye."""
        # Beside the scroller, not inside it: a message must not scroll away.
        self.assertIs(self.ui._status.master, self.ui._cam_scroller.master)
        self.assertIsNot(self.ui._status.master, self.ui._cam_strip)
        self.ui._set_status("saved", flash=True)
        self.assertEqual(self.ui._status.cget("text"), "saved")
        # and SAVE now fills its row on its own
        siblings = self.ui._save_button.master.winfo_children()
        self.assertEqual(siblings, [self.ui._save_button])

    def test_the_camera_bar_only_shows_a_scrollbar_when_it_overflows(self):
        self.ui._cam_scroller.configure(width=2000)
        self.root.update_idletasks()
        self.ui._sync_camera_bar()
        self.assertFalse(self.ui._cam_hbar_shown, "plenty of room")
        # Pretend the pane is narrower than the strip needs.
        self.ui._cam_scroller.winfo_width = lambda: 120
        self.ui._sync_camera_bar()
        self.assertTrue(self.ui._cam_hbar_shown, "eleven buttons in 120px")
        self.ui._cam_scroller.winfo_width = lambda: 2000
        self.ui._sync_camera_bar()
        self.assertFalse(self.ui._cam_hbar_shown)

    def test_the_zoom_readout_sits_over_the_previews_and_follows_the_zoom(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_zoom(32)
        self.ui._draw_main()
        self.assertEqual(self.ui._zoom_label.cget("text"), "32 px")
        self.ui.set_zoom(64)
        self.ui._draw_main()
        self.assertEqual(self.ui._zoom_label.cget("text"), "64 px")

    def test_the_grid_block_is_two_rows_with_the_pickers_on_the_caption_line(self):
        """#v2.8.0. It was three rows: a title, a caption row, then entries
        with DEFAULT eating a third of them. The pickers moved up beside the
        names they open and DEFAULT moved under the word "Grid", so the block
        is two rows and both colour fields have their full width."""
        block = self.ui._grid_entries["c1"].master
        self.assertEqual(int(self.ui._grid_title.grid_info()["row"]), 0)
        for i, key in enumerate(("c1", "c2")):
            caption, _k = self.ui._grid_captions[key]
            head = caption.master
            self.assertEqual(int(head.grid_info()["row"]), 0, "captions on the Grid line")
            # column 1 holds WHITE over BLACK since the ninth test pass
            self.assertEqual(int(head.grid_info()["column"]), 2 + i)
            self.assertIs(self.ui._grid_pickers[key].master, head,
                          "the picker is on the caption line, not beside the entry")
            entry = self.ui._grid_entries[key]
            self.assertEqual(int(entry.grid_info()["row"]), 1)
            self.assertEqual(int(entry.grid_info()["column"]), 2 + i)
        info = self.ui._grid_default_button.grid_info()
        self.assertEqual((int(info["row"]), int(info["column"])), (1, 0),
                         "DEFAULT under the word Grid")
        rows = {int(w.grid_info()["row"]) for w in block.grid_slaves()}
        self.assertEqual(rows, {0, 1}, "two rows, not three")
        # the two colour fields share the width alike ("eşit olsun")
        self.assertEqual(block.grid_columnconfigure(2)["weight"],
                         block.grid_columnconfigure(3)["weight"])
        self.assertEqual(block.grid_columnconfigure(2)["uniform"],
                         block.grid_columnconfigure(3)["uniform"])

    def test_the_zoom_readout_sits_in_the_1x_column(self):
        """#v2.8.0: in the gap over the 1x preview, costing no row."""
        self.assertIs(self.ui._zoom_label.master, self.ui.preview_1x.master)
        self.assertIs(self.ui._current_label.master, self.ui.preview_1x.master)

    def test_the_grid_block_and_the_readout_speak_the_chosen_language(self):
        for code in i18n.LANGS:
            self.ui.set_language(code)
            self.assertEqual(self.ui._grid_title.cget("text"), i18n.t("grid"))
            self.assertEqual(self.ui._grid_captions["c1"][0].cget("text"), i18n.t("colour_1"))
            self.assertEqual(self.ui._grid_captions["c2"][0].cget("text"), i18n.t("colour_2"))
            self.assertEqual(self.ui._grid_default_button.cget("text"), i18n.t("default"))
            self.assertEqual(self.ui._current_label.cget("text"), i18n.t("current"))

    def test_a_grid_change_undoes_and_redoes(self):
        """#v2.8.0, reported as "I changed the grid, pressed Ctrl+Z, nothing
        happened"."""
        self.ui.new_drawing(8, 8)
        before = self.ui.grid_colours()
        self.ui.set_grid_colours(c1="ABCDEF")
        self.assertEqual(self.ui.grid_colours()[0], "#abcdef")
        self.ui.undo()
        self.assertEqual(self.ui.grid_colours(), before)
        self.ui.redo()
        self.assertEqual(self.ui.grid_colours()[0], "#abcdef")

    def test_the_grid_lines_toggle_undoes_and_a_no_op_records_nothing(self):
        self.ui.new_drawing(8, 8)
        was = self.ui.show_grid
        self.ui.set_show_grid(not was)
        self.assertNotEqual(self.ui.show_grid, was)
        self.ui.undo()
        self.assertEqual(self.ui.show_grid, was)
        depth = len(self.ui.history._undo)
        self.ui.set_show_grid(was)                     # already there
        self.ui.set_grid_colours(c1="not a colour")    # rejected by settings
        self.assertEqual(len(self.ui.history._undo), depth,
                         "a change that changed nothing leaves no entry")

    def test_the_symmetry_line_undoes(self):
        self.ui.new_drawing(16, 16)
        self.ui.set_symmetry_mode(symmetry.MIRROR)
        self.ui.place_symmetry_bar(7, 7)
        self.assertIsNotNone(self.ui.symmetry_bar)
        self.ui.undo()
        self.assertIsNone(self.ui.symmetry_bar, "the line goes back")
        self.ui.undo()
        self.assertEqual(self.ui.symmetry_mode, symmetry.OFF, "then the mode")
        self.ui.redo()
        self.assertEqual(self.ui.symmetry_mode, symmetry.MIRROR)
        self.ui.redo()
        self.assertIsNotNone(self.ui.symmetry_bar)

    def test_the_four_edges_resize_the_drawing_as_one_undo_each(self):
        """#v2.8.0: the grab that used to sit on the bottom-right corner and
        change the ZOOM is four edge grabs that change the DRAWING."""
        self.ui.new_drawing(8, 8)
        d = self.ui.history.current
        d.paint(0, 0, "m")
        d.paint(7, 7, "l")
        self.assertEqual(d.resize_edge("right", -2), -2)
        self.assertEqual((self.ui.history.current.width, self.ui.history.current.height), (6, 8))
        self.assertEqual(d.resize_edge("left", -1), -1)
        self.assertEqual(self.ui.history.current.width, 5)
        self.assertIsNone(d.get(0, 0), "the left column went, and the art with it")
        self.assertEqual(d.resize_edge("top", 2), 2)
        self.assertEqual(self.ui.history.current.height, 10)
        self.assertEqual(d.resize_edge("bottom", 1), 1)
        self.assertEqual((d.width, d.height), (5, 11))
        with self.assertRaises(ValueError):
            d.resize_edge("sideways", 1)

    def test_an_edge_never_takes_the_last_row_or_column(self):
        self.ui.new_drawing(3, 3)
        d = self.ui.history.current
        self.assertEqual(d.resize_edge("right", -99), -2, "clamped, not emptied")
        self.assertEqual(d.width, 1)
        self.assertEqual(d.resize_edge("right", -1), 0, "and then nothing happens")
        self.assertEqual(d.width, 1)

    def test_an_edge_drag_is_one_undo_however_many_cells_it_moved(self):
        self.ui.new_drawing(10, 10)
        before = (self.ui.history.current.width, self.ui.history.current.height)
        depth = len(self.ui.history._undo)
        self.ui.history.begin_stroke()                 # what _on_press does
        for _ in range(4):
            self.ui.history.current.resize_edge("right", -1)
        self.assertTrue(self.ui.history.end_stroke())  # what _on_release does
        self.ui._after_change()
        self.assertEqual(self.ui.history.current.width, 6)
        self.assertEqual(len(self.ui.history._undo) - depth, 1, "one entry for the drag")
        self.ui.undo()
        self.assertEqual((self.ui.history.current.width, self.ui.history.current.height), before)

    def test_the_edge_grabs_are_off_when_they_would_cover_the_drawing(self):
        """The bands are EDGE_GRAB wide each side; on a small drawing at a low
        zoom they meet in the middle and every press meant to paint would
        resize. Zoom in to resize (#v2.8.0)."""
        self.ui.new_drawing(16, 19)

        class Ev:
            x = y = 0

        self.ui.canvas.canvasx = lambda _v: 0
        self.ui.canvas.canvasy = lambda _v: 0
        self.ui.zoom_level = 1
        self.assertEqual(self.ui._hit_edge(Ev()), (), "16px of art, 20px of band")
        self.ui.zoom_level = 4 * app.EDGE_GRAB
        self.assertEqual(self.ui._hit_edge(Ev()), ("left", "top"), "the corner")

    def test_the_edge_grab_knows_which_edge_the_pointer_is_on(self):
        self.ui.new_drawing(10, 10)
        self.ui.zoom_level = 20
        span = 10 * 20

        class Ev:
            x = y = 0

        def at(x, y):
            self.ui.canvas.canvasx = lambda _v: x
            self.ui.canvas.canvasy = lambda _v: y
            return self.ui._hit_edge(Ev())

        self.assertEqual(at(0, span // 2), ("left",))
        self.assertEqual(at(span, span // 2), ("right",))
        self.assertEqual(at(span // 2, 0), ("top",))
        self.assertEqual(at(span // 2, span), ("bottom",))
        # The corners belong to two edges at once (#v2.8.0).
        self.assertEqual(at(0, 0), ("left", "top"))
        self.assertEqual(at(span, 0), ("right", "top"))
        self.assertEqual(at(0, span), ("left", "bottom"))
        self.assertEqual(at(span, span), ("right", "bottom"))
        self.assertEqual(at(span // 2, span // 2), (), "the middle is for painting")
        self.assertEqual(at(span + 200, span // 2), (), "and so is far away")

    def test_lock_freezes_the_view_exactly_where_it_was_framed(self):
        """#v2.8.0. The two half-locks centred the axis they froze; an artist
        who has framed a view wants THAT view held, on both axes."""
        self.ui.new_drawing(16, 16)
        cw = ch = 400
        self._camera(cw, ch, origin=(137, 249))
        self.ui._fitted = True   # framed by the artist: past the first fit
        self.ui.zoom_level = 64
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.assertEqual(self.ui._locked_at, (137, 249))
        x0, y0, x1, y1 = self.ui._scroll_bounds()
        self.assertEqual((x0, x1 - cw), (137, 137), "no horizontal range at all")
        self.assertEqual((y0, y1 - ch), (249, 249), "nor vertical")
        # and it holds at every zoom
        for z in self.ui.zoom_stops():
            self.ui.zoom_level = z
            x0, y0, x1, y1 = self.ui._scroll_bounds()
            self.assertEqual((x0, y0), (137, 249), f"z={z}")

    def test_picking_a_colour_is_one_undo_step(self):
        """#v2.8.0, reported as "I right-clicked a colour and Ctrl+Z would not
        take it back". Every way of choosing ink goes through set_ink."""
        self.ui.new_drawing(8, 8)
        self.ui.history.current.paint(2, 2, "m")
        start = self.ui.ink
        self.ui.set_ink((10, 20, 30, 255))
        self.assertEqual(self.ui.ink, (10, 20, 30, 255))
        self.ui.undo()
        self.assertEqual(self.ui.ink, start)
        self.ui.redo()
        self.assertEqual(self.ui.ink, (10, 20, 30, 255))
        # the eyedropper is the same path
        self.ui.on_canvas_pick(2, 2)
        self.assertNotEqual(self.ui.ink, (10, 20, 30, 255))
        self.ui.undo()
        self.assertEqual(self.ui.ink, (10, 20, 30, 255))

    def test_a_drag_across_the_shade_square_is_one_undo_step(self):
        """It fires on every motion event; without coalescing a single drag
        would leave one undo entry per pixel of travel."""
        self.ui.new_drawing(8, 8)
        start = self.ui.ink
        depth = len(self.ui.history._undo)

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui._picker.pick_shade(Ev(10, 10))                      # press
        for x in range(11, 40):
            self.ui._picker.pick_shade(Ev(x, 10), continuing=True)  # drag
        self.assertEqual(len(self.ui.history._undo) - depth, 1, "one entry for the drag")
        self.ui.undo()
        self.assertEqual(self.ui.ink, start)

    def test_the_eraser_size_and_favourites_undo_too(self):
        self.ui.new_drawing(8, 8)
        was = tuple(self.ui.eraser_size)
        self.ui.set_eraser_size(4, 3)
        self.assertEqual(tuple(self.ui.eraser_size), (4, 3))
        self.ui.undo()
        self.assertEqual(tuple(self.ui.eraser_size), was)

        before = self.settings.favourites
        self.ui.set_ink((1, 2, 3, 255))
        self.ui._add_ink_to_favourites()
        self.assertIn("010203", self.settings.favourites)
        self.ui.undo()
        self.assertEqual(self.settings.favourites, before)

    def test_an_edge_drag_measures_from_where_it_started(self):
        """#v2.8.0. Measuring each step against the LIVE edge ran away on the
        left and the top: growing there inserts cells at the origin, so the
        distance to the edge changed without the pointer moving and the next
        event added more. Two pixels of travel became a dozen columns."""
        self.ui.new_drawing(16, 16)
        self.ui.zoom_level = z = 20
        self.ui._viewport = lambda: (400, 400)
        origin = [0, 0]
        self.ui._view_origin = lambda: tuple(origin)
        self.ui._scroll_to = lambda vx, vy: origin.__setitem__(slice(None), [vx, vy])

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui.history.begin_stroke()
        self.ui._edge_drag = {"edges": ("left",), "x": 100, "y": 100, "w": 16, "h": 16}
        # three events, the pointer creeping left by one cell each time
        for step in (1, 2, 3):
            self.ui._drag_edge(Ev(100 - step * z, 100))
            self.assertEqual(self.ui.history.current.width, 16 + step,
                             f"one cell per cell of travel, not {step} events' worth")
        # and back: the size follows the pointer, it does not accumulate
        self.ui._drag_edge(Ev(100, 100))
        self.assertEqual(self.ui.history.current.width, 16)

    def test_a_corner_drag_moves_both_edges(self):
        self.ui.new_drawing(16, 16)
        self.ui.zoom_level = z = 20
        self.ui._viewport = lambda: (400, 400)
        self.ui._view_origin = lambda: (0, 0)
        self.ui._scroll_to = lambda vx, vy: None

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui.history.begin_stroke()
        self.ui._edge_drag = {"edges": ("right", "bottom"), "x": 320, "y": 320,
                              "w": 16, "h": 16}
        self.ui._drag_edge(Ev(320 - 2 * z, 320 - 3 * z))
        d = self.ui.history.current
        self.assertEqual((d.width, d.height), (14, 13), "both axes at once")

    def test_a_left_edge_drag_under_lock_moves_the_lock_with_the_art(self):
        """Growing on the left inserts cells at the origin, so canvas
        coordinates move under the art. LOCK held its point where it was and
        the art jumped a cell per cell added while the grabbed edge stayed
        put; the frozen point moves with the art now, and the view with it."""
        self.ui.new_drawing(16, 16)
        self.ui.zoom_level = z = 20
        self.ui._viewport = lambda: (400, 400)
        origin = [40, 60]
        self.ui._view_origin = lambda: tuple(origin)
        self.ui._scroll_to = lambda vx, vy: origin.__setitem__(slice(None), [vx, vy])
        self.ui._fitted = True
        self.ui.set_camera_mode(app.CAM_LOCK)
        self.assertEqual(self.ui._locked_at, (40, 60))

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui.history.begin_stroke()
        self.ui._edge_drag = {"edges": ("left", "top"), "x": 100, "y": 100, "w": 16, "h": 16}
        self.ui._drag_edge(Ev(100 - 2 * z, 100 - 3 * z))    # two cells left, three up
        d = self.ui.history.current
        self.assertEqual((d.width, d.height), (18, 19))
        self.assertEqual(self.ui._locked_at, (40 + 2 * z, 60 + 3 * z))
        self.assertEqual(tuple(origin), (40 + 2 * z, 60 + 3 * z), "the view went with it")
        self.assertEqual(self.ui.zoom_level, z)

    def test_undoing_a_left_edge_drag_keeps_the_art_still_too(self):
        """The drag kept the untouched art still; its undo used to take the
        columns back and let the art jump sideways by that much - under LOCK
        with no way to pan it back. The view follows in every mode now, and
        LOCK's frozen point with it."""

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        for mode in (app.CAM_LOCK, app.CAM_FREE):
            self.ui.new_drawing(16, 16)
            self.ui.zoom_level = z = 20
            self.ui._viewport = lambda: (400, 400)
            origin = [40, 60]
            self.ui._view_origin = lambda: tuple(origin)
            self.ui._scroll_to = lambda vx, vy: origin.__setitem__(slice(None), [vx, vy])
            self.ui._fitted = True
            self.ui.set_camera_mode(mode)
            origin[:] = [40, 60]
            if mode == app.CAM_LOCK:
                self.ui._locked_at = (40, 60)
            # the whole gesture, through the same handlers the canvas binds
            self.ui.history.begin_stroke()
            self.ui._edge_drag = {"edges": ("left",), "x": 100, "y": 100, "w": 16, "h": 16}
            self.ui._drag_edge(Ev(100 - 2 * z, 100))
            self.ui._on_release(Ev(100 - 2 * z, 100))
            self.assertEqual(self.ui.history.current.width, 18, mode)
            self.assertEqual(tuple(origin), (40 + 2 * z, 60), mode)

            self.ui.undo()
            self.assertEqual(self.ui.history.current.width, 16, mode)
            self.assertEqual(tuple(origin), (40, 60), f"{mode}: the art did not jump")
            if mode == app.CAM_LOCK:
                self.assertEqual(self.ui._locked_at, (40, 60))
            self.ui.redo()
            self.assertEqual(self.ui.history.current.width, 18, mode)
            self.assertEqual(tuple(origin), (40 + 2 * z, 60), f"{mode}: nor on redo")

    # ---- #v2.8.0, second test pass: edges, sizes, big drawings ---------------

    def test_the_edge_band_is_only_a_sliver_inside_the_drawing(self):
        """"24x'den itibaren küçülünce kenarlarda çizmek zorlaşıyor": the
        band was EDGE_GRAB either side of an edge, 40% of an edge cell at
        24x and all of it at 8x. Outside the art it still is; inside, it is
        an eighth of a cell, never more than 3px, and nothing below 8x."""
        self.ui.new_drawing(16, 16)

        class Ev:
            x = y = 0

        def at(x, y):
            self.ui.canvas.canvasx = lambda _v: x
            self.ui.canvas.canvasy = lambda _v: y
            return self.ui._hit_edge(Ev())

        for z, inside in ((24, 3), (64, 3), (16, 2), (8, 1), (6, 0)):
            self.ui.zoom_level = z
            span, mid = 16 * z, 8 * z
            self.assertEqual(min(app.EDGE_GRAB_INSIDE, z // 8), inside)
            if inside:
                self.assertEqual(at(inside - 1, mid), ("left",), f"{z}x: the outermost {inside}px")
                self.assertEqual(at(span - inside, mid), ("right",), f"{z}x")
                self.assertEqual(at(mid, inside - 1), ("top",), f"{z}x")
                self.assertEqual(at(mid, span - inside), ("bottom",), f"{z}x")
            self.assertEqual(at(inside, mid), (), f"{z}x: one pixel further in, it paints")
            self.assertEqual(at(span - inside - 1, mid), (), f"{z}x")
            self.assertEqual(at(mid, inside), (), f"{z}x")
            self.assertEqual(at(mid, span - inside - 1), (), f"{z}x")
            self.assertEqual(at(-app.EDGE_GRAB, mid), ("left",), f"{z}x: outside, the whole band")
            self.assertEqual(at(span + app.EDGE_GRAB, mid), ("right",), f"{z}x")
            self.assertEqual(at(-app.EDGE_GRAB, -app.EDGE_GRAB), ("left", "top"), f"{z}x: a corner")

    def test_a_drawing_can_be_any_size_now(self):
        """"en fazla 64x64 yapabiliyoruz, o limiti tamamen kaldıralım": 64
        cells a side was the cap, the biggest tree. The eraser keeps its own."""
        d = self.ui.new_drawing(200, 120)
        self.assertEqual((d.width, d.height), (200, 120))
        self.ui.resize(300, 90)
        self.assertEqual((self.ui.history.current.width, self.ui.history.current.height), (300, 90))
        self.ui.set_eraser_size(500, 500)
        self.assertEqual(tuple(self.ui.eraser_size), (app.ERASER_MAX, app.ERASER_MAX))

    def test_the_size_dialog_asks_before_a_huge_drawing_and_refuses_a_typo(self):
        made = []

        def dialog(cols, rows):
            dlg = app.SizeDialog(self.root, "New drawing", (32, 32), app.size_presets(),
                                 lambda c, r: made.append((c, r)), verb="CREATE")
            self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
            for entry, value in ((dlg._cols_entry, cols), (dlg._rows_entry, rows)):
                entry.delete(0, "end")
                entry.insert(0, str(value))
            return dlg

        dialog(300, 200)._custom()                              # past 64, no question
        self.assertEqual(made, [(300, 200)])
        self._answer(lambda q: self._press(q, i18n.t("no")))
        dialog(600, 600)._custom()                              # 360 000 cells: asked
        self.assertEqual(made, [(300, 200)], "said no")
        self._answer(lambda q: self._press(q, i18n.t("yes")))
        dialog(600, 600)._custom()
        self.assertEqual(made, [(300, 200), (600, 600)], "said yes")
        self._answer(lambda q: self._press(q, i18n.t("ok")))
        dialog(60000, 600)._custom()                            # a typo for 600
        self.assertEqual(len(made), 2, "refused, in words")

    def test_the_previews_and_thumbnail_of_a_big_drawing_fit_their_boxes(self):
        """A 300-wide drawing at 1x is 300px - wider than the whole tools
        pane - and its thumbnail would have been 300px in a 64px row."""
        d = self.ui.new_drawing(300, 150)
        self.assertEqual(self.ui._one_x_label.cget("text"), "1/5x", "and says it is not 1x")
        self.assertEqual((int(self.ui.preview_1x.cget("width")),
                          int(self.ui.preview_1x.cget("height"))), (60, 30))
        self.assertLessEqual(int(self.ui.preview_squint.cget("width")), app.INNER_W - 72)
        thumb = self.ui._images[("thumb", id(d))]
        self.assertLessEqual(max(thumb.width(), thumb.height()), app.THUMB_PX)
        self.ui.new_drawing(16, 16)
        self.assertEqual(self.ui._one_x_label.cget("text"), "1x")

    def test_the_view_renders_only_what_is_on_screen_and_exactly_that(self):
        """The main view renders the visible cells and a one-cell margin, then
        trims it. That must equal the whole drawing's render cut to the view -
        rims and all, which is why the margin - with the checker tone
        wherever the art is empty, so the image has no see-through pixel for
        Tk to build a mask for."""
        flower = next(d for d in self.lib.drawings if engine_io.has_letters(d))
        self.ui.select(flower)
        d = self.ui.history.current
        full = engine_io.render(d)
        tones = [model.hex_to_rgba(tone) for tone in self.ui.grid_colours()]
        k = self.ui._checker_cells()
        for c0, r0, c1, r1 in ((0, 0, d.width - 1, d.height - 1), (3, 4, 9, 11), (5, 5, 5, 5),
                               (0, 2, d.width - 1, 2)):
            tile = self.ui._tile(d, (c0, r0, c1, r1))
            self.assertEqual((len(tile), len(tile[0])), (r1 - r0 + 1, c1 - c0 + 1))
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    want = full[r][c]
                    if want[3] == 0:
                        want = tones[(c // k + r // k) % 2]
                    self.assertEqual(tile[r - r0][c - c0], want, (c0, r0, c1, r1, c, r))

    # ---- #v2.8.0, third test pass: below 1x, faithful corner pictures, the fold ----

    def test_a_big_drawing_zooms_out_to_its_corner_picture_and_no_further(self):
        """"sağ alttaki en küçük kısma kadar küçülme olsun hep": a 600-wide
        drawing stopped at 1 px a cell while the corner showed it at 1/10x.
        The view goes there now, in exact fractions."""
        from fractions import Fraction
        self._camera(900, 800)
        self.ui.new_drawing(600, 600)
        self.assertEqual(self.ui.min_zoom(), Fraction(1, 10))
        self.assertEqual(self.ui._one_x_label.cget("text"), "1/10x", "the corner's own 1/n")
        self.assertIn(Fraction(1, 10), self.ui.zoom_stops())
        self.ui.zoom_level = self.ui.fit_zoom()
        self.assertEqual(self.ui.zoom_level, 1)
        for _ in range(12):
            self.ui.zoom(-1)
        self.assertEqual(self.ui.zoom_level, Fraction(1, 10), "that far, and no further")
        self.assertEqual(self.ui._zoom_label.cget("text"), "1/10 px")
        self.ui._draw_main()
        img = self.ui._images["main"]
        self.assertEqual((img.width(), img.height()), (60, 60))

        class Ev:
            x, y = 3, 7

        self.ui.canvas.canvasx = lambda v: v
        self.ui.canvas.canvasy = lambda v: v
        self.assertEqual(self.ui._grid_at(Ev()), (30, 70), "3 // (1/10) is 30 - in floats it is 29")
        for _ in range(12):
            self.ui.zoom(+1)
        self.assertGreater(self.ui.zoom_level, 1, "and back up the same ladder")
        self.ui.new_drawing(16, 16)
        self.assertEqual(self.ui.min_zoom(), 1, "a sprite the 1x box holds still stops at 1x")
        self.assertEqual(self.ui.zoom_stops()[0], 1)

    def test_fit_goes_below_1x_for_a_drawing_bigger_than_the_pane(self):
        from fractions import Fraction
        self._camera(900, 800)
        self.ui.new_drawing(1000, 1000)
        self.assertEqual(self.ui.fit_zoom(), Fraction(1, 2))
        self.ui.zoom_to_fit()
        self.assertEqual(self.ui.zoom_level, Fraction(1, 2))
        self.assertTrue(all(isinstance(v, int) for v in self.ui._scroll_bounds()),
                        "no fraction reaches Tk - it would arrive as the string '7/2'")
        units = []
        self.ui.canvas.xview_scroll = lambda n, what: units.append(n)
        self.ui._wheel_pan(1, 0)
        self.assertEqual(units, [-1], "a pan is a whole pixel at least")

    def test_the_view_below_1x_is_each_blocks_average_on_the_checker(self):
        self.ui.new_drawing(40, 30)
        d = self.ui.history.current
        self.ui.history.begin_stroke()
        for c in range(40):
            d.paint(c, 7, (250, 10, 10, 255))                   # a line one cell thin
        self.ui.history.end_stroke()
        self.ui._after_change()                                 # how the kit hears of a change
        n = 4
        tile = self.ui._tile(d, (0, 0, 39, 29), n)
        self.assertEqual((len(tile[0]), len(tile)), (10, 8))    # 30 / 4, rounded up
        averaged = raster._reduce_by_hand(engine_io.render(d), n)
        tones = [model.hex_to_rgba(tone) for tone in self.ui.grid_colours()]
        k = n * app.CHECKER_MIN_PX              # a square of 4 screen px, n cells each
        for j, line in enumerate(averaged):
            for i, px in enumerate(line):
                tone = tones[((i * n) // k + (j * n) // k) % 2]
                want = raster.over(px, tone)
                # Pillow averages and mixes in 8 bits: a step or two either way
                self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(tile[j][i], want)),
                                (i, j, tile[j][i], want))
        self.assertTrue(all(px[0] > px[1] + 40 for px in tile[1]), "the line, a quarter strong")
        self.assertTrue(all(px[3] == 255 for line in tile for px in line), "opaque, for Tk")

    def test_the_corner_pictures_of_a_big_drawing_keep_a_one_cell_line(self):
        """"squint ve 1/11x çok doğru değil ... bazı kısımlar aktarılmamış":
        they kept every n-th cell, so a thin line was there or not by luck."""
        self.ui.new_drawing(600, 600)
        d = self.ui.history.current
        self.ui.history.begin_stroke()
        for r in range(600):
            d.paint(37, r, (255, 0, 0, 255))
        self.ui.history.end_stroke()
        self.ui._after_change()
        bg = model.hex_to_rgba(theme.BG)
        for key, n in (("preview_1x", 10), ("preview_squint", 4)):
            img = self.ui._images[key]
            for y in (0, img.height() // 2, img.height() - 1):
                r, g, _b = img.get(37 // n, y)
                self.assertGreater(r, bg[0] + 15, f"{key}: the line at row {y}")
                self.assertGreater(r, g, key)

    def test_folding_the_library_takes_its_scrollbar_with_it(self):
        """"üç çizgiye basınca altındaki scroll down, up kısmı yok olmuyor"."""
        bar = self.ui._library_scrollbar
        self.assertEqual(bar.winfo_manager(), "pack")
        self.ui.toggle_library()
        self.assertEqual(bar.winfo_manager(), "", "gone with the list")
        self.assertEqual(self.ui._library_toggle.winfo_manager(), "pack", "the ☰ stays")
        self.ui.toggle_library()
        self.assertEqual(bar.winfo_manager(), "pack")
        self.assertEqual(self.ui._library_rail.pack_slaves(), [self.ui._library_toggle, bar],
                         "back under the ☰, not above it")

    # ---- #v2.8.0, fifth test pass: the eraser's outline, the artist, big drawings ----

    def test_the_erasers_outline_follows_it_while_it_erases(self):
        """"silgiye basınca kayboluyor": the outline was skipped while
        erasing, so it vanished - or stayed where the stroke began."""
        self.ui.new_drawing(20, 20)
        self.ui.zoom_level = 10
        self.ui.set_tool("erase")
        self.ui.set_eraser_size(3, 3)
        self.ui.canvas.canvasx = lambda v: v
        self.ui.canvas.canvasy = lambda v: v

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui._on_motion(Ev(55, 55))                           # over cell (5, 5)
        self.assertTrue(self.ui.canvas.find_withtag("ghost"))
        self.ui._on_press(Ev(55, 55))
        self.ui._on_drag(Ev(125, 55))                            # erasing, now at (12, 5)
        ghost = self.ui.canvas.find_withtag("ghost")
        self.assertEqual(len(ghost), 1, "one outline, none left behind")
        x0, _y0, x1, _y1 = self.ui.canvas.coords(ghost[0])
        self.assertEqual((round(x0), round(x1)), (111, 139), "around cells 11 to 13")
        self.ui._draw_main()                                     # a full repaint mid-stroke
        self.assertTrue(self.ui.canvas.find_withtag("ghost"), "and a repaint keeps it")
        self.ui._on_release(Ev(125, 55))

    def test_a_big_eraser_over_the_edge_erases_instead_of_resizing(self):
        """"silginin yarısı alanın dışına çıkınca silginin çizgisinin
        takılmasını engelleyelim": with the pointer past the edge the press
        caught on the grab and resized, though half the eraser was on the art."""
        self.ui.new_drawing(20, 20)
        d = self.ui.history.current
        for r in range(20):
            d.paint(0, r, (9, 9, 9, 255))                        # the left column
        self.ui.zoom_level = 10
        self.ui.set_tool("erase")
        self.ui.set_eraser_size(5, 5)
        self.ui.canvas.canvasx = lambda v: v
        self.ui.canvas.canvasy = lambda v: v

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        # 5 px left of the drawing - inside the grab band - with the eraser's
        # right half over column 0
        self.assertEqual(self.ui._hit_edge(Ev(-5, 100)), (), "no grab while the eraser reaches")
        self.ui._on_press(Ev(-5, 100))
        self.ui._on_release(Ev(-5, 100))
        self.assertEqual(self.ui.history.current.width, 20, "not resized")
        self.assertIsNone(self.ui.history.current.get(0, 10), "the border cell under it is gone")
        self.assertIsNotNone(self.ui.history.current.get(0, 2), "and only under it")
        self.ui.set_eraser_size(1, 1)
        self.assertEqual(self.ui._hit_edge(Ev(-5, 100)), ("left",), "a 1x1 eraser off the art: a grab")

    def test_the_artist_is_a_layer_of_its_own(self):
        """"üç noktalara artist ekleyelim ... artistlerin baş harfi ... her
        artist için random farklı bir renk": its own field, beside the label."""
        d = self.lib.drawings[0]
        row = self.ui._rows[id(d)]
        self.assertEqual(row["artist"].winfo_manager(), "", "no artist, no initial")
        self.assertIn(i18n.t("artist"), row["popup"].labels())
        self.ui.set_artist(d, "  mia ")
        self.assertEqual((d.artist, d.label), ("mia", "flower"), "the label is left alone")
        self.assertEqual(store.load(self.lib._paths[id(d)]).artist, "mia", "saved with it")
        self.assertEqual(row["artist"].cget("text"), "M")
        self.assertEqual(row["artist"].cget("fg"), f"#{self.settings.artist_colour('mia').lower()}")
        slaves = row["row"].pack_slaves()
        menu = slaves.index(row["menu"])
        initial, chip = slaves.index(row["artist"]), slaves.index(row["chip"])
        self.assertEqual((initial, chip), (menu + 1, menu + 2),
                         "packed from the right: dots, then the initial, then the label")
        self.ui.set_artist(d, "")
        self.assertEqual(row["artist"].winfo_manager(), "")

    def test_the_filter_lists_by_artist_too_and_with_the_labels(self):
        """"sol üstte artiste göre filtreleme olsun all içinde" - one checklist
        for labels and artists (sixth test pass: "ben hangi şeyin tikini
        seçtiysem onlar gözüksün"): whatever is ticked is listed."""
        a = self.lib.drawings[0]                                 # a flower
        mir = [d for d in self.lib.drawings if d.artist == PATCH]
        self.assertEqual(len(mir), 5, "Drawing Patch 1 came in signed")
        self.ui.set_artist(a, "Ola")
        self.ui.toggle_artist_filter("Ola")
        self.assertEqual(self.ui.visible_drawings(), [a], "from ALL: just Ola's")
        self.ui.toggle_artist_filter(PATCH)
        self.assertEqual({id(d) for d in self.ui.visible_drawings()}, {id(a)} | {id(d) for d in mir},
                         "a second tick adds Mir's")
        self.ui.toggle_artist_filter("Ola")
        self.assertEqual({id(d) for d in self.ui.visible_drawings()}, {id(d) for d in mir})
        self.ui.toggle_label_filter("tree")
        trees = {id(d) for d in self.lib.drawings if d.label == "tree"}
        self.assertEqual({id(d) for d in self.ui.visible_drawings()}, {id(d) for d in mir} | trees,
                         "Mir's, and every tree")
        self.assertIn(f"TREE + {PATCH.upper()}" if len(f"TREE + {PATCH}") <= 16
                      else i18n.t("n_chosen", n=2), self.ui._filter_button.cget("text"))
        self.ui.clear_filters()
        self.assertEqual(len(self.ui.visible_drawings()), SEEDED)

        self.ui._post_filter_menu()
        menu = self.ui._filter_menu
        self.addCleanup(menu.unpost)
        self.assertIn(i18n.t("artists"), [item[1] for item in menu._items if item[0] == "caption"])
        row = next(r for r, _c in menu._rows if PATCH in r.cget("text"))
        self.assertEqual(row.cget("fg"), f"#{self.settings.artist_colour(PATCH).lower()}",
                         "an artist's row in the artist's colour")
        row.invoke()
        self.assertEqual(self.ui._filter, {("artist", PATCH)})
        self.assertIsNotNone(menu._win, "a checklist stays open")

    def test_a_new_drawing_under_an_artist_filter_is_theirs(self):
        self.ui.set_artist(self.lib.drawings[0], "Ola")          # so Mir is not everyone
        self.ui.set_artist_filter(PATCH)
        d = self.ui.new_drawing(8, 8)
        self.assertEqual(d.artist, PATCH)
        self.assertTrue(self.ui._rows[id(d)]["row"].winfo_manager())
        e = self.ui.import_png(self._png())[0]
        self.assertEqual(e.artist, "")
        self.assertEqual(self.ui._filter, {("artist", PATCH), ("label", "import")},
                         "the import's label joins the ticks, so it shows")
        self.assertTrue(self.ui._rows[id(e)]["row"].winfo_manager())

    def test_a_huge_drawing_is_rendered_once_per_change(self):
        """"fit kısmı çok büyüklerde çalışmıyor": FIT on a 4096-wide drawing
        took seconds, turning the same cells into pixels for every picture."""
        from fractions import Fraction
        from unittest import mock
        self.ui._viewport = lambda: (875, 740)
        self.ui.new_drawing(1200, 900)
        self.ui.zoom_level = Fraction(1, 2)
        self.ui.history.begin_stroke()
        self.ui.history.current.paint(5, 5, (1, 2, 3, 255))
        self.ui.history.end_stroke()
        with mock.patch.object(engine_io, "render", wraps=engine_io.render) as render:
            self.ui._after_change()                              # thumbnail, previews, view
            self.ui.fit_pressed()
            self.ui.zoom(-1)
            self.ui.zoom(-1)
        self.assertEqual(render.call_count, 1, "one render, cut and averaged by every picture")
        self.assertEqual(self.ui.zoom_level, Fraction(1, 4))

    # ---- #v2.8.0, sixth test pass: the filter, the checkerboard, FIT, F12, the artist's mark ----

    def test_what_is_ticked_is_what_is_listed(self):
        """"Hero'yu seçebilirim ... sonrasında other'a basarım ve bir tane
        daha, tüm other'lar ve diğerleri gözükür" - and no row stays ticked
        over a list that does not show it (sixth test pass: "Hero seçtim ...
        diğer her şeyin tiki gözüküyor, bu saçma")."""
        hero = self.lib.drawings[:2]
        for d in hero:
            self.ui.set_artist(d, "Hero")
            self.ui.set_label(d, "other")
        loose = self.lib.drawings[2]
        self.ui.set_label(loose, "other")                        # an OTHER nobody signed
        self.ui.toggle_artist_filter("Hero")
        self.assertEqual([id(d) for d in self.ui.visible_drawings()], [id(d) for d in hero])
        self.assertFalse(self.ui.label_shown("other"), "only Hero is ticked, no label")
        self.assertFalse(self.ui.artist_shown(PATCH))
        self.ui.toggle_label_filter("other")
        self.assertEqual({id(d) for d in self.ui.visible_drawings()},
                         {id(d) for d in hero} | {id(loose)}, "one more: every OTHER as well")
        # NO ARTIST picked from ALL is that row alone, and only its drawings
        self.ui.clear_filters()
        self.ui.toggle_artist_filter("")
        self.assertEqual(self.ui._filter, {("artist", "")})
        self.assertTrue(all(d.artist == "" for d in self.ui.visible_drawings()))
        self.assertFalse(self.ui.label_shown("flower"), "no label left ticked over it")
        self.ui.toggle_artist_filter("")
        self.assertIsNone(self.ui._filter, "and unticked again: ALL")

    def test_filtering_keeps_the_rows_in_the_librarys_order(self):
        """"karışıyorlar birbirlerine": a row that came back was packed at
        the end, so every change of filter shuffled the list."""
        def listed():
            rows = {str(self.ui._rows[id(d)]["row"]): d for d in self.lib.drawings}
            return [rows[str(w)] for w in self.ui._list_frame.pack_slaves() if str(w) in rows]

        self.ui.toggle_artist_filter(PATCH)
        self.assertEqual([id(d) for d in listed()], [id(d) for d in self.ui.visible_drawings()])
        self.ui.clear_filters()
        self.assertEqual([id(d) for d in listed()], [id(d) for d in self.lib.drawings])
        for label in ("tree", "bush", "tree"):
            self.ui.toggle_label_filter(label)
        self.ui.clear_filters()
        self.assertEqual([id(d) for d in listed()], [id(d) for d in self.lib.drawings])

    def test_the_checkerboard_is_two_by_two_cells_on_every_drawing(self):
        """"arkadaki gridlerin 2x2 2x2'den farklı bir şekle geçmiş": ten
        squares a side, cut to cells, came out 2, 2, 1, 2, 1 cells wide on a
        flower - and as 16 x 6 slabs on a 160 x 60 banner."""
        from fractions import Fraction
        for w, h in ((16, 16), (160, 60)):
            self.ui.new_drawing(w, h)
            d = self.ui.history.current
            tones = [model.hex_to_rgba(tone) for tone in self.ui.grid_colours()]
            for z, k in ((20, 2), (4, 2), (3, 2), (2, 2), (1, 4)):
                self.ui.zoom_level = z
                self.assertEqual(self.ui._checker_cells(), k, (w, h, z))
                tile = self.ui._tile(d, (0, 0, w - 1, h - 1))
                for r in (0, 1, 2, h - 1):
                    for c in (0, 1, 2, 3, 4, 5, w - 1):
                        self.assertEqual(tile[r][c], tones[(c // k + r // k) % 2], (w, h, z, c, r))
        self.ui.zoom_level = Fraction(1, 3)
        self.assertEqual(self.ui._checker_cells(), 12, "below 1x: 4 px of 3-cell blocks")

    def test_fit_follows_the_pane_until_the_artist_moves_the_camera(self):
        """"fit halen düzgün değil" on a 160 x 60: FIT was a one-off, so the
        ☰ left the fitted art off-centre in a wider pane, and a fit made for
        the wide pane ran off the edge of the narrow one."""
        pane = [755, 716]
        self.ui._viewport = lambda: tuple(pane)
        self.ui._pane_known = lambda: True
        self.ui.new_drawing(160, 60)
        self.ui.fit_pressed()
        self.assertEqual(self.ui.zoom_level, 4)
        pane[0] = 957                                            # the library folded away
        self.ui._redraw_viewport()
        self.assertEqual(self.ui.zoom_level, 5, "fitted again to the wider pane")
        pane[0] = 755
        self.ui._redraw_viewport()
        self.assertEqual(self.ui.zoom_level, 4, "and back")
        self.ui.zoom(+1)                                         # the artist takes the camera
        pane[0] = 957
        self.ui._redraw_viewport()
        self.assertEqual(self.ui.zoom_level, 6, "a zoom of their own is left alone")
        self.ui.fit_pressed()
        self.assertEqual(self.ui.zoom_level, 5)
        self.ui._wheel_pan(1, 0)
        pane[0] = 755
        self.ui._redraw_viewport()
        self.assertEqual(self.ui.zoom_level, 5, "and so is a pan")

    def test_below_1x_the_free_camera_keeps_a_pixel_of_the_drawing_on_screen(self):
        from fractions import Fraction
        self._camera(755, 716)
        self.ui.new_drawing(160, 60)
        self.ui.zoom_level = Fraction(1, 3)
        x0, y0, x1, y1 = self.ui._scroll_bounds()
        self.assertLessEqual(x0, 1 - 755, "the drawing can go to the far edge...")
        self.assertGreaterEqual(x0 + 755, 1, "...but one pixel of it stays in the pane")

    def test_f12_is_the_test_builds_and_saves_the_window_and_its_numbers(self):
        """"snapshot sadece test modunda olsun": a release build has no F12
        and its help does not mention one."""
        from unittest import mock
        from PIL import Image
        self.assertFalse(self.root.bind_all("<F12>"), "not in a release build")
        help_rows = app.HelpOverlay(self.root, lambda: None, None, test_build=False)
        self.addCleanup(help_rows.destroy)
        def texts(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    yield child.cget("text")
                yield from texts(child)
        self.assertNotIn("F12", list(texts(help_rows)))
        self.root._artkit_test_window = True        # what run_art_kit_test.py's window carries
        self.ui._bind_keys()
        self.assertTrue(self.root.bind_all("<F12>"), "the TEST build's, on every window")
        self.ui.new_drawing(160, 60)
        with mock.patch.object(app.snapshot, "grab", return_value=Image.new("RGB", (4, 3))):
            self.ui.take_snapshot()
        folder = self.lib.root.parent / "snapshots"
        pngs, jsons = sorted(folder.glob("*.png")), sorted(folder.glob("*.json"))
        self.assertEqual((len(pngs), len(jsons)), (1, 1))
        state = json.loads(jsons[0].read_text(encoding="utf-8"))
        self.assertEqual(state["drawing"]["cells"], [160, 60])
        self.assertEqual(state["screenshot"], pngs[0].name)
        self.assertIsNone(state["grab_error"])
        self.assertIn(state["camera"]["zoom"], (str(self.ui.zoom_level),))
        self.assertIn("pane", state["camera"])
        with mock.patch.object(app.snapshot, "grab", side_effect=OSError("screen grab failed")):
            self.ui.take_snapshot()
        states = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")]
        self.assertEqual(len(states), 2, "the numbers are kept even with no picture")
        self.assertIn("screen grab failed", [s_ for s_ in states if s_["grab_error"]][0]["grab_error"])
        self.assertEqual(self.ui._status.cget("text"), i18n.t("snapshot_failed"))

    def test_the_export_dialog_asks_for_the_signature_and_shows_it(self):
        d = next(d for d in self.lib.drawings if d.artist == PATCH)
        dialog = app.BackgroundDialog(self.root, None, drawing=d, signature="none")
        self.addCleanup(dialog.destroy)
        plain = dialog._image
        dialog._sign(provenance.CORNER)
        self.assertEqual(dialog.signature, "corner")
        self.assertIsNot(dialog._image, plain, "the preview shows it")
        self.assertIn("©", dialog._sign_hints[provenance.CORNER].cget("text"))
        self.assertTrue(dialog._meta_button.cget("text").startswith(dialogs.TICKED))
        dialog._toggle_metadata()
        self.assertFalse(dialog.metadata)
        self.assertTrue(dialog._meta_button.cget("text").startswith(dialogs.UNTICKED))
        # a drawing no one is named for cannot be signed - and says how
        nobody = next(d for d in self.lib.drawings if not d.artist)
        other = app.BackgroundDialog(self.root, None, drawing=nobody, signature="corner")
        self.addCleanup(other.destroy)
        self.assertEqual(str(other._sign_buttons[provenance.CORNER].cget("state")), "disabled")
        self.assertEqual(other._sign_note.cget("text"), i18n.t("sign_no_artist"))
        other._sign(provenance.WATERMARK)
        self.assertEqual(other.signature, "corner", "the choice is kept for one that can")

    def test_an_export_is_signed_named_and_written_down(self):
        """1, 2 and 4 of the proposal: the name on the picture and inside the
        file, and every export in the record - the engine sprite recorded
        but left clean."""
        from unittest import mock
        from PIL import Image
        d = next(d for d in self.lib.drawings if d.artist == PATCH)
        self.settings.export_signature = "corner"
        out = Path(self.tmp.name) / "out.png"
        with mock.patch.object(self.ui, "_ask_export_background", return_value=None), \
                mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(out)):
            self.ui._export_png(d)
        with Image.open(out) as img:
            text, pixels = dict(img.text), img.convert("RGBA").tobytes()
        self.assertEqual(text["Author"], PATCH)
        self.assertIn("©", text["Copyright"])
        plain = bytes(v for row in engine_io.composed(d, 16) for px in row for v in px)
        self.assertNotEqual(pixels, plain, "signed in the corner")
        log = self.ui.export_log_path()
        entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((entry["kind"], entry["artist"], entry["signature"]), ("png", PATCH, "corner"))
        self.assertEqual(entry["sha256"], provenance.digest(out.read_bytes()))
        self.assertIn(f"xmp.iid:{entry['export_id']}", text["XML:com.adobe.xmp"])
        self.assertEqual(entry["drawing_sha256"],
                         provenance.digest(self.lib.path_for(d).read_bytes()))

        sprite = Path(self.tmp.name) / "sprite.png"
        with mock.patch.object(app, "engine_sprite_dir", lambda: Path(self.tmp.name)), \
                mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(sprite)):
            self.ui._export_engine_sprite(d)
        with Image.open(sprite) as img:
            self.assertNotIn("Author", img.text, "the game's sprite stays clean")
        entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((entry["kind"], entry["signature"], entry["metadata"]),
                         ("engine", "none", False))
        self.assertEqual(provenance.verify(log), (2, 0))

    # ---- #v2.8.0, seventh test pass: languages, the eraser's speed, the chrome ----

    def test_the_eraser_writes_into_the_picture_not_onto_the_canvas(self):
        """"eraser çalışırken ... çok fps düşüyor": every erased cell was a
        canvas rectangle of its own - 38,000 after one stroke of a 16 x 16
        eraser across a 160-cell drawing, all redrawn on every move."""
        self.ui.new_drawing(40, 20)
        d = self.ui.history.current
        self.ui.history.begin_stroke()
        for r in range(20):
            for c in range(40):
                d.paint(c, r, (200, 30, 30, 255))
        self.ui.history.end_stroke()
        self.ui._after_change()
        self.ui.zoom_level = 4
        self.ui._draw_main()
        before = len(self.ui.canvas.find_all())
        self.ui.set_tool("erase")
        self.ui.set_eraser_size(8, 8)
        self.ui.on_canvas_press(10, 10)
        for c in range(11, 30):
            self.ui.on_canvas_drag(c, 10)
        self.assertLessEqual(len(self.ui.canvas.find_all()), before, "not one item added")
        img = self.ui._images["main"]
        c0, r0, n = self.ui._tile_box
        k = self.ui._checker_cells()
        tone = self.ui.grid_colours()[(20 // k + 10 // k) % 2]
        got = img.get((20 - c0) * 4 + 1, (10 - r0) * 4 + 1)
        self.assertEqual("#%02x%02x%02x" % tuple(got[:3]), tone, "cleared to the checker at once")
        kept = img.get((20 - c0) * 4 + 1, (1 - r0) * 4 + 1)
        self.assertEqual(tuple(kept[:3]), (200, 30, 30), "and the rest untouched")
        self.ui.on_canvas_release()
        self.assertIsNone(d.get(20, 10))
        self.assertIsNotNone(d.get(20, 1))

    def test_paint_goes_into_the_picture_too(self):
        self.ui.new_drawing(10, 10)
        self.ui.zoom_level = 6
        self.ui._draw_main()
        before = len(self.ui.canvas.find_all())
        self.ui.set_tool("draw")
        self.ui.set_ink((10, 200, 30, 255))
        self.ui.on_canvas_press(2, 3)
        self.ui.on_canvas_drag(5, 3)
        self.assertEqual(len(self.ui.canvas.find_all()), before)
        c0, r0, _n = self.ui._tile_box
        self.assertEqual(tuple(self.ui._images["main"].get((4 - c0) * 6, (3 - r0) * 6)[:3]),
                         (10, 200, 30))
        self.ui.on_canvas_release()

    def test_switching_language_retexts_every_heading_and_the_row_menus(self):
        """"symmetry, squint, colour, ready colours, favourite colours, ink
        ... soldaki üç noktalı menü ... farklı dillerde çalışmıyor"."""
        self.ui.set_language("tr")
        self.addCleanup(lambda: self.ui.set_language("en"))
        for widget, key in ((self.ui._ink_title, "ink"), (self.ui._fav_title, "favourites"),
                            (self.ui._ready_title, "ready"), (self.ui._colour_title, "colour"),
                            (self.ui._sym_title, "symmetry"), (self.ui._squint_label, "squint")):
            self.assertEqual(widget.cget("text"), i18n.STRINGS["tr"][key], key)
        row = self.ui._rows[id(self.lib.drawings[0])]
        self.assertIn(i18n.STRINGS["tr"]["duplicate"], row["popup"].labels(), "built in English, read now")
        self.assertEqual(app.size_presets()[0][0], i18n.STRINGS["tr"]["preset_flower"])

    def test_the_filter_arrow_points_at_the_words_and_turns_down_while_open(self):
        """"all'un yanındaki ikon biraz daha net olsun, yana doğru ... basınca
        aşağı döndürsün"."""
        # Drawn triangles (ninth test pass: the font's ▶ could turn into an emoji)
        shut, open_ = (str(self.ui._filter_icons[k]) for k in (False, True))
        btn = self.ui._filter_button
        self.assertEqual(str(btn.cget("image")), shut)
        self.ui._post_filter_menu()
        self.assertEqual(str(btn.cget("image")), open_)
        self.ui._filter_menu.unpost()
        self.assertEqual(str(btn.cget("image")), shut)
        self.assertTrue(btn.cget("text").strip().startswith(i18n.t("all")))

    def test_the_status_corner_shows_the_whole_message(self):
        """"sağ üstte durum raporunda metnin hepsi görünmüyor": fourteen
        characters wide, "exported House3.png" read "rted House3.png"."""
        self.ui._set_status("exported Begonia 1 (grid).png", flash=True)
        self.assertEqual(self.ui._status.cget("text"), "exported Begonia 1 (grid).png")
        self.assertEqual(str(self.ui._status.cget("width")), "0", "as wide as the message")
        long = "exported " + "x" * 80 + ".png"
        self.ui._set_status(long)
        shown = self.ui._status.cget("text")
        self.assertEqual(len(shown), app.STATUS_MAX)
        self.assertTrue(shown.startswith("exported") and shown.endswith(".png"), "cut in the middle")

    def test_the_colour_pager_sits_at_the_far_right_as_solid_arrows(self):
        """"sağ sol en sağda olsun ve biraz daha belirgin olsun"."""
        strip = self.ui._colour_strip
        strip.configure(width=300)
        strip.winfo_width = lambda: 300
        strip.set_colours([("%06X" % (i * 99991 % 0xFFFFFF), 100 - i) for i in range(30)])
        hits = {what: (x0, x1) for x0, x1, what in strip._hits if what in ("prev", "next")}
        self.assertEqual(hits["next"][1], 300, "the right-hand arrow ends at the edge")
        self.assertEqual(hits["prev"][1], hits["next"][0], "the left one right before it")
        arrows = strip.find_withtag("arrow")
        self.assertEqual([strip.type(a) for a in arrows], ["image", "image"],
                         "drawn smooth (ninth test pass: \"pikselli duruyor\")")

    def test_the_export_dialog_signs_with_either_mark_or_both_and_keeps_the_record_optional(self):
        d = next(d for d in self.lib.drawings if d.artist == PATCH)
        dialog = app.BackgroundDialog(self.root, None, drawing=d, signature="none")
        self.addCleanup(dialog.destroy)
        dialog._sign(provenance.CORNER)
        dialog._sign(provenance.WATERMARK)
        self.assertEqual(dialog.signature, provenance.BOTH, "ikisini de: both at once")
        self.assertTrue(all(str(b.cget("bg")) == theme.ACCENT for b in dialog._sign_buttons.values()))
        dialog._sign(provenance.CORNER)
        self.assertEqual(dialog.signature, provenance.WATERMARK)
        self.assertTrue(dialog.log)
        self.assertTrue(dialog._log_button.cget("text").startswith(dialogs.TICKED))
        dialog._toggle_log()
        self.assertFalse(dialog.log)
        self.assertTrue(dialog._log_button.cget("text").startswith(dialogs.UNTICKED))

    def test_an_export_is_not_written_down_when_the_artist_says_so(self):
        from unittest import mock
        d = next(d for d in self.lib.drawings if d.artist == PATCH)
        self.settings.export_log = False
        out = Path(self.tmp.name) / "quiet.png"
        with mock.patch.object(self.ui, "_ask_export_background", return_value=None), \
                mock.patch.object(app.filedialog, "asksaveasfilename", return_value=str(out)):
            self.ui._export_png(d)
        self.assertTrue(out.exists())
        self.assertFalse(self.ui.export_log_path().exists())

    # ---- #v2.8.0, eighth test pass: dialogs in place, symmetry per drawing, LOOK, GUIDE ----

    def test_a_dialog_is_shown_only_once_it_stands_where_it_belongs(self):
        """"grid colour 1 ve 2'de üç noktaya basınca sol üstten bir menü
        anlık gözüküp kayıyor": the dark title bar's update mapped each new
        window in the corner Windows gives it, before it was moved."""
        dlg = dialogs.Dialog(self.root, "t")
        self.assertEqual(float(dlg.attributes("-alpha")), 0.0, "unseen while it is built")
        seen = []

        def look(d):
            seen.append((float(d.attributes("-alpha")), d.winfo_geometry()))
            d.cancel()
        self.root.after(30, lambda: look(dlg))
        dlg.run()
        self.assertEqual(seen[0][0], 1.0, "shown once placed")
        drawing = self.lib.drawings[0]
        bg = app.BackgroundDialog(self.root, None, drawing=drawing)
        self.addCleanup(bg.destroy)
        self.assertEqual(float(bg.attributes("-alpha")), 1.0)
        menu = dialogs.PopupMenu(self.root)
        menu.add_command("x")
        menu.tk_popup(10, 10)
        self.addCleanup(menu.unpost)
        # Revealed once placed. (Whether Windows then maps an override-redirect
        # window at all depends on the session: this headless one never does.)
        self.assertEqual(float(menu._win.attributes("-alpha")), 1.0, "placed, then shown")

    def test_each_drawing_keeps_its_own_symmetry(self):
        """"mirror ve stick açık kalıyor, farklı bir ekrana geçince ... alanın
        dışında kalmış": the line followed the artist into the next drawing,
        off its edge when that one was smaller."""
        from art_kit import symmetry
        big = self.ui.new_drawing(40, 40)
        self.ui.set_symmetry_mode(symmetry.MIRROR)
        self.ui.place_symmetry_bar(30, 20)
        small = self.ui.new_drawing(8, 8)
        self.assertEqual(self.ui.symmetry_mode, symmetry.OFF, "a drawing never given a line")
        self.assertIsNone(self.ui.symmetry_bar)
        self.ui.select(big)
        self.assertEqual(self.ui.symmetry_mode, symmetry.MIRROR, "and the line comes back with its own")
        self.assertEqual((self.ui.symmetry_bar.col, self.ui.symmetry_bar.row), (30, 20))
        self.ui.select(small)
        self.ui.select(big)
        self.ui.resize(20, 20)                                   # the line's column went with the cells
        self.assertIsNone(self.ui.symmetry_bar, "a line left outside is taken away")
        self.assertEqual(self.ui.symmetry_mode, symmetry.MIRROR)
        self.assertTrue(self.ui._placing_bar, "the next click places it again")

    def test_look_shows_the_art_plain_and_draws_nothing(self):
        """"squint ... sağına check Look ekleyelim, orada çizim kapalı olsun,
        sadece bakma için olsun"."""
        from art_kit import symmetry
        self.ui.new_drawing(12, 12)
        d = self.ui.history.current
        d.paint(3, 3, (250, 0, 0, 255))
        self.ui._after_change()
        self.ui.zoom_level = 20
        self.ui.set_symmetry_mode(symmetry.MIRROR)
        self.ui.place_symmetry_bar(6, 6)
        self.ui._draw_main()
        self.assertTrue(self.ui.canvas.find_withtag("grid"))
        self.ui.set_looking(True)
        self.assertTrue(self.ui._look_button.cget("text").startswith(dialogs.TICKED))
        self.assertFalse(self.ui.canvas.find_withtag("grid"), "no cell lines")
        self.assertFalse(self.ui.canvas.find_withtag("symmetry"), "no symmetry line")
        plain = model.hex_to_rgba(theme.CANVAS_BG)
        tile = self.ui._tile(d, (0, 0, 11, 11))
        self.assertEqual({tile[r][c] for r in (0, 1, 2) for c in (0, 1, 2)}, {plain},
                         "no checkerboard: the canvas's own colour")
        self.assertEqual(tile[3][3][:3], (250, 0, 0))
        before = [list(row) for row in d.cells]
        self.ui.canvas.canvasx = lambda v: v
        self.ui.canvas.canvasy = lambda v: v

        class Ev:
            def __init__(self, x, y): self.x, self.y = x, y

        self.ui._on_press(Ev(90, 90))
        self.ui._on_drag(Ev(150, 90))
        self.ui._on_release(Ev(150, 90))
        self.ui.undo()
        self.assertEqual(self.ui.history.current.cells, before, "nothing drawn, nothing undone")
        self.assertEqual(self.ui._status.cget("text"), i18n.t("look_only"))
        self.assertEqual(self.ui._hit_edge(Ev(-3, 100)), (), "no edge to grab either")
        self.ui.set_looking(False)
        self.assertTrue(self.ui.canvas.find_withtag("grid"))

    def test_the_guide_is_called_guide_and_ends_with_how_the_work_is_protected(self):
        """"Help'in adı Guide olsun" and "en altta copyright önlemlerinin nasıl
        çalıştığını anlatan bir kısım" - in the language of the moment."""
        self.assertEqual(self.ui._help_button.cget("text"), "GUIDE")
        self.ui.set_language("tr")
        self.addCleanup(lambda: self.ui.set_language("en"))
        rows = app.protection_rows()
        self.assertEqual(rows[1], (i18n.STRINGS["tr"]["gp_title"], None))
        self.assertIn((i18n.STRINGS["tr"]["gp_hash_k"], i18n.STRINGS["tr"]["gp_hash"]), rows)
        guide = app.HelpOverlay(self.root, lambda: None, None)
        self.addCleanup(guide.destroy)

        def texts(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    yield child.cget("text")
                yield from texts(child)
        shown = list(texts(guide))
        self.assertIn(i18n.STRINGS["tr"]["gp_title"], shown)
        self.assertEqual(shown[-1], i18n.STRINGS["tr"]["gp_later"], "at the very bottom")

    # ---- #v2.8.0, ninth test pass: grid presets, names renamed and taken off, the chrome ----

    def test_the_grid_has_white_and_black_grounds_ready(self):
        """"boş olan yere iki tane hazır stil gelsin, üste White, alta Black ...
        iki renk direkt siyah veya direkt beyaz olsun"."""
        white, black = self.ui._grid_presets["grid_white"], self.ui._grid_presets["grid_black"]
        self.assertEqual((int(white.grid_info()["row"]), int(black.grid_info()["row"])), (0, 1),
                         "WHITE over BLACK")
        white.invoke()
        self.assertEqual(self.ui.grid_colours(), ("#ffffff", "#ffffff"))
        self.assertLess(int(self.ui.grid_line_colour()[1:3], 16), 255, "lines darker than white")
        black.invoke()
        self.assertEqual(self.ui.grid_colours(), ("#000000", "#000000"))
        self.assertGreater(int(self.ui.grid_line_colour()[1:3], 16), 0, "and lighter than black")
        self.ui.undo()
        self.assertEqual(self.ui.grid_colours(), ("#ffffff", "#ffffff"), "a step like any other")
        # each caption flush against its … ("colour 1 ve 2 üç nokta hizasına")
        for key, (caption, _k) in self.ui._grid_captions.items():
            slaves = caption.master.pack_slaves()
            self.assertEqual(slaves, [self.ui._grid_pickers[key], caption])
            self.assertEqual(caption.pack_info()["side"], "right")

    def test_a_label_is_renamed_and_taken_off_everywhere(self):
        """"artistlerin adını değiştirme ve silme opsiyonu gelsin, aynı şekilde
        labellarda da"."""
        from unittest import mock
        a, b = self.lib.drawings[0], self.lib.drawings[1]
        for d in (a, b):
            self.ui.set_label(d, "wip")
        self.ui.toggle_label_filter("wip")
        self.assertEqual(self.ui.rename_label("wip", "draft"), 2)
        self.assertEqual((a.label, b.label), ("draft", "draft"))
        self.assertEqual(store.load(self.lib.path_for(a)).label, "draft", "saved")
        self.assertEqual(self.ui._filter, {("label", "draft")}, "the tick went with it")
        with mock.patch.object(app.dialogs, "askyesno", return_value=False):
            self.assertFalse(self.ui.delete_label("draft"), "asked first")
        with mock.patch.object(app.dialogs, "askyesno", return_value=True):
            self.assertTrue(self.ui.delete_label("draft"))
        self.assertEqual((a.label, b.label), ("", ""))
        self.assertIsNone(self.ui._filter, "a tick on a label no one has left is ALL again")

    def test_an_artist_is_renamed_with_their_colour_and_taken_off_everywhere(self):
        from unittest import mock
        a, b = self.lib.drawings[0], self.lib.drawings[1]
        for d in (a, b):
            self.ui.set_artist(d, "Hero")
        colour = self.settings.artist_colour("Hero")
        self.assertEqual(self.ui.rename_artist("Hero", "HeroDev999"), 2)
        self.assertEqual((a.artist, b.artist), ("HeroDev999", "HeroDev999"))
        self.assertEqual(self.settings.artist_colour("HeroDev999"), colour, "the colour went along")
        self.assertNotIn("Hero", self.settings.data["artist_colours"])
        self.assertEqual(self.ui._rows[id(a)]["artist"].cget("fg"), f"#{colour.lower()}")
        with mock.patch.object(app.dialogs, "askyesno", return_value=True):
            self.assertTrue(self.ui.delete_artist("HeroDev999"))
        self.assertEqual((a.artist, b.artist), ("", ""))
        self.assertNotIn("HeroDev999", self.settings.data["artist_colours"])

    def test_the_label_and_artist_dialogs_have_a_menu_beside_every_name(self):
        """"label ve artist ekle bölümünde üç nokta olsun, oradan labellar çıkarılsın"."""
        from unittest import mock
        d = self.lib.drawings[0]
        renamed = []
        dlg = app.LabelDialog(self.root, d, self.lib.labels(), lambda text: None,
                              names_of=self.lib.labels,
                              on_rename=lambda old, new: renamed.append((old, new)),
                              on_delete=lambda name, parent=None: True)
        self.addCleanup(dlg.destroy)
        cells = dlg._grid.winfo_children()
        self.assertEqual(len(cells), len(self.lib.labels()))
        self.assertTrue(all(any(isinstance(w, theme.Button) and w.cget("text") == "⋮"
                                for w in cell.winfo_children()) for cell in cells))
        dots = next(w for w in cells[0].winfo_children() if w.cget("text") == "⋮")
        dots.invoke()
        self.addCleanup(dlg._menu.unpost)
        self.assertEqual(dlg._menu.labels(), [i18n.t("rename"), i18n.t("delete")])
        with mock.patch.object(app.dialogs, "askstring", return_value="  leafy "):
            dlg._rename("flower")
        self.assertEqual(renamed, [("flower", "leafy")])

    def test_the_counter_starts_with_the_total(self):
        """"empty ve pixels'in başına total pikseli de yazalım"."""
        self.ui.new_drawing(10, 6)
        self.ui.history.current.paint(1, 1, (1, 2, 3, 255))
        self.ui._after_change()
        self.assertTrue(self.ui._counter_label.cget("text").startswith(
            f"{i18n.t('total_pixels', n=60)} · {i18n.t('empty_pixels', n=59)} · "
            f"{i18n.t('pixels', n=1)}"))

    def test_the_guide_rows_are_ruled_off_and_flush_left(self):
        """"her bölüm çizgi ile ayrılsın, aralardaki mesafe korunsun ve
        başlıklar sola doğru entegre olsun" - and a drawn close button."""
        guide = app.HelpOverlay(self.root, lambda: None, None)
        self.addCleanup(guide.destroy)

        def widgets(widget):
            for child in widget.winfo_children():
                yield child
                yield from widgets(child)
        everything = list(widgets(guide))
        rules = [w for w in everything if isinstance(w, tk.Frame) and str(w.cget("height")) == "1"]
        titled = sum(1 for k, v in app.HELP_TEXT + app.protection_rows() if k and v is not None)
        self.assertGreater(len(rules), titled // 2, "a line between one row and the next")
        texts = [w.cget("text") for w in everything if isinstance(w, tk.Label)]
        self.assertFalse([x for x in texts if x.startswith(" ")], "no indented titles")
        if guide._close_icon is not None:
            close = next(w for w in everything if isinstance(w, theme.Button)
                         and str(w.cget("image")) == str(guide._close_icon))
            self.assertEqual(close.pack_info()["side"], "right")

    def test_every_row_of_the_tools_pane_is_as_wide_as_the_colour_panels(self):
        """"kenarlardan kısaltılsın eşit olsun": the rows stretched into the room
        a hidden scrollbar leaves and ran past the swatch grids."""
        scroller = self.ui._tools_scroller
        self.assertEqual(int(float(scroller.itemcget(self.ui._tools_window, "width"))), app.INNER_W)
        self.assertEqual(app._pads((3, 11)), (3, 11))
        self.assertEqual(app._pads("8 14"), (8, 14))
        self.assertEqual(app._pads(5), (5, 5))
