"""What the TEST build promises (`run_art_kit_test.py`).

`TestPixelPomoArtKit.exe` is the pre-release channel: it runs code that has
not been pushed or released yet, against a copy of the artist's real drawings.
Two of its promises are the silent kind — nothing written while testing
unreleased code reaches the real library, and this build never swaps itself
for a release binary — so they are asserted here rather than trusted. Both
would keep "working" for a long time after they stopped being true.

The entry point is executed for real, the way the .exe does it, with `main()`
stubbed and the network booby-trapped.
"""
import json
import os
import runpy
import sys
import tempfile
import types
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from art_kit import paths, updater

ENTRY = Path(__file__).resolve().parent.parent / "run_art_kit_test.py"


class NetworkTouched(AssertionError):
    """Raised in place of opening a socket, so a test can prove none opened."""


def _boom(*_args, **_kwargs):
    raise NetworkTouched("the test build reached for the network")


class TestBuildTest(unittest.TestCase):
    def setUp(self):
        import tkinter

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.real = Path(self.tmp.name) / "PixelPomoArtKit"
        self.test = Path(self.tmp.name) / "PixelPomoArtKit-Test"

        # Put back everything the entry point patches. Without this the rest of
        # the suite would run against a redirected data folder and an updater
        # that cannot fail — which is exactly the kind of quiet breakage this
        # file exists to catch.
        for module, name in ((paths, "data_dir"), (updater, "check"),
                             (updater, "can_self_update"), (tkinter, "Tk")):
            self.addCleanup(setattr, module, name, getattr(module, name))
        self.addCleanup(paths.__dict__.pop, "_artkit_real_data_dir", None)
        saved = sys.modules.get("art_kit.__main__")
        self.addCleanup(lambda: sys.modules.__setitem__("art_kit.__main__", saved)
                        if saved is not None else sys.modules.pop("art_kit.__main__", None))
        self.original_check = updater.check

        # Frozen Windows on every host, so a macOS runner cannot be talked into
        # writing to a real ~/Documents.
        for patcher in (mock.patch.object(sys, "frozen", True, create=True),
                        mock.patch.object(sys, "platform", "win32"),
                        mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp.name}),
                        mock.patch.object(urllib.request, "urlopen", _boom)):
            patcher.start()
            self.addCleanup(patcher.stop)

        # The artist's library, as her machine has it.
        (self.real / "library").mkdir(parents=True)
        self._write(self.real, "gul_0_gul_0.json", "the real rose")
        self._write(self.real, "papatya_0.json", "the real daisy")
        self.before = self._snapshot(self.real)

    # -- helpers --------------------------------------------------------------
    def _write(self, folder, name, marker):
        (folder / "library" / name).write_text(
            json.dumps({"name": name, "pixels": [marker]}), encoding="utf-8")

    def _snapshot(self, folder):
        return {p.name: p.read_text(encoding="utf-8")
                for p in sorted((folder / "library").glob("*"))}

    def _run(self):
        """Execute the entry point exactly as the frozen .exe does."""
        stub = types.ModuleType("art_kit.__main__")
        started = []
        stub.main = lambda: started.append(True)
        sys.modules["art_kit.__main__"] = stub
        runpy.run_path(str(ENTRY), run_name="__main__")
        self.assertEqual(started, [True], "the entry point never started the app")

    # -- the data folder ------------------------------------------------------
    def test_it_writes_to_its_own_folder_not_the_artists(self):
        self._run()
        self.assertEqual(paths.data_dir(), self.test)
        self.assertNotEqual(paths.data_dir(), self.real)

    def test_it_starts_from_a_copy_of_the_real_drawings(self):
        self._run()
        copied = self._snapshot(self.test)
        self.assertEqual(set(copied), set(self.before),
                         "the test folder should open on the same drawings")
        self.assertEqual(copied, self.before, "and on the same pixels")

    def test_the_real_library_is_untouched_by_starting_the_test_build(self):
        self._run()
        self.assertEqual(self._snapshot(self.real), self.before)

    def test_nothing_written_in_the_test_folder_reaches_the_real_one(self):
        self._run()
        # unreleased code ruins a drawing and adds another, then restarts
        self._write(self.test, "gul_0_gul_0.json", "RUINED BY AN UNRELEASED BUG")
        self._write(self.test, "experiment.json", "test only")
        self._run()
        self.assertEqual(self._snapshot(self.real), self.before,
                         "a test-folder edit reached the artist's library")
        self.assertNotIn("experiment.json", self._snapshot(self.real))

    def test_restarting_does_not_clobber_work_done_in_the_test_folder(self):
        self._run()
        self._write(self.test, "gul_0_gul_0.json", "deliberately changed here")
        self._run()
        kept = json.loads((self.test / "library" / "gul_0_gul_0.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(kept["pixels"], ["deliberately changed here"],
                         "re-seeding overwrote the test copy")

    def test_a_new_real_drawing_shows_up_on_the_next_test_run(self):
        self._run()
        self._write(self.real, "kaktus_9.json", "drawn in the real kit")
        self._run()
        self.assertTrue((self.test / "library" / "kaktus_9.json").exists(),
                        "the test build went stale against the real library")

    # -- the updater ----------------------------------------------------------
    def test_the_startup_check_never_dials_out_and_finds_nothing_newer(self):
        self._run()
        release = updater.check()          # NetworkTouched if it opened a socket
        self.assertFalse(release.is_newer)
        self.assertEqual(release.assets, {}, "there is an asset it could swap in")

    def test_the_control_proves_that_trap_would_have_fired(self):
        """Without this, the test above passes just as happily on a check()
        that was never patched at all."""
        with self.assertRaises(NetworkTouched):
            self.original_check()

    def test_it_cannot_swap_itself_for_a_release_binary(self):
        self._run()
        self.assertFalse(updater.can_self_update(),
                         "a test build that self-updates becomes a release "
                         "binary wearing the test name")

    # -- the window -----------------------------------------------------------
    def test_the_window_says_it_is_a_test_build(self):
        import tkinter
        self._run()
        try:
            root = tkinter.Tk()
        except tkinter.TclError as exc:  # no display
            raise unittest.SkipTest(f"no Tk display: {exc}")
        self.addCleanup(root.destroy)
        root.withdraw()
        root.title("Pixel Pomo Art Kit")
        self.assertTrue(root.title().endswith("[TEST]"))
        # ArtKitApp rewrites the title for every drawing it opens
        root.title("Pixel Pomo Art Kit — gul")
        marked = root.title()
        self.assertTrue(marked.endswith("[TEST]"))
        self.assertIn("gul", marked)
        root.title(marked)
        self.assertEqual(root.title(), marked, "the suffix doubled up")


if __name__ == "__main__":
    unittest.main()
