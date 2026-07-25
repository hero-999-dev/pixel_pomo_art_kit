import tempfile
import unittest
from pathlib import Path

from art_kit import app, store


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
        self.lib = store.Library(Path(self.tmp.name))
        self.lib.seed_from_engine()
        self.ui = app.ArtKitApp(self.root, self.lib)

    def test_it_opens_on_the_first_drawing_with_all_twenty_four_listed(self):
        self.assertEqual(len(self.lib.drawings), 24)
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
