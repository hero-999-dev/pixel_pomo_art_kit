import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from art_kit import paths


class DataDirTest(unittest.TestCase):
    def test_from_source_everything_stays_at_the_repo_root(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(paths.data_dir(), paths.program_dir())
            self.assertEqual(paths.data_dir(), Path(paths.__file__).resolve().parent.parent)

    def test_frozen_windows_uses_localappdata_never_the_exe_folder(self):
        exe = str(Path("somewhere") / "PixelPomoArtKit.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(sys, "executable", exe), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(Path("u") / "AppData" / "Local")}):
            data = paths.data_dir()
            legacy = paths.legacy_dirs()
        self.assertEqual(data, Path("u") / "AppData" / "Local" / "PixelPomoArtKit")
        self.assertEqual(legacy, [Path(exe).resolve().parent],
                         "the old beside-the-exe folder is where migration looks")

    def test_frozen_mac_uses_documents_and_has_no_legacy_folder(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(sys, "executable", "/Applications/PixelPomoArtKit.app/Contents/MacOS/x"):
            self.assertEqual(paths.data_dir(), Path.home() / "Documents" / "PixelPomoArtKit")
            self.assertEqual(paths.legacy_dirs(), [])


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = Path(self.tmp.name) / "old-exe-folder"
        self.data = Path(self.tmp.name) / "data"
        (self.old / "library").mkdir(parents=True)
        (self.old / "library" / "a.json").write_text("A", encoding="utf-8")
        (self.old / "library" / "b.json").write_text("B", encoding="utf-8")
        (self.old / "library" / "notes.txt").write_text("not a drawing", encoding="utf-8")
        (self.old / "settings.json").write_text("{}", encoding="utf-8")

    def test_copies_drawings_and_settings_and_leaves_the_old_folder_alone(self):
        copied = paths.migrate_legacy(self.data, [self.old])
        self.assertEqual(copied, 2)
        self.assertEqual((self.data / "library" / "a.json").read_text(encoding="utf-8"), "A")
        self.assertEqual((self.data / "library" / "b.json").read_text(encoding="utf-8"), "B")
        self.assertFalse((self.data / "library" / "notes.txt").exists())
        self.assertTrue((self.data / "settings.json").exists())
        self.assertTrue((self.old / "library" / "a.json").exists(), "copied, never moved")

    def test_never_overwrites_and_is_idempotent(self):
        (self.data / "library").mkdir(parents=True)
        (self.data / "library" / "a.json").write_text("NEWER", encoding="utf-8")
        self.assertEqual(paths.migrate_legacy(self.data, [self.old]), 1)
        self.assertEqual((self.data / "library" / "a.json").read_text(encoding="utf-8"), "NEWER")
        self.assertEqual(paths.migrate_legacy(self.data, [self.old]), 0, "second run copies nothing")

    def test_a_missing_legacy_folder_is_fine(self):
        self.assertEqual(paths.migrate_legacy(self.data, [Path(self.tmp.name) / "nope"]), 0)
        self.assertEqual(paths.migrate_legacy(self.data, [self.data]), 0, "data is not its own legacy")


if __name__ == "__main__":
    unittest.main()
