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

    def test_the_export_dialog_does_not_default_into_the_game_assets(self):
        # pixel_pomo is read-only to this app; defaulting the picker there risks
        # clobbering a shipped sprite. The default must live outside that tree.
        self.assertNotIn("pixel_pomo", str(app.ENGINE_SPRITE_DIR).replace("\\", "/"))

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
