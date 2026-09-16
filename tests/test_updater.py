import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from art_kit import updater, version


class FakeResponse(io.BytesIO):
    """Just enough of an HTTP response for updater.check/download."""

    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def fake_opener(payload, headers=None):
    calls = []

    def opener(req, timeout=None):
        calls.append(req)
        return FakeResponse(payload, headers)
    opener.calls = calls
    return opener


class VersionTest(unittest.TestCase):
    def test_parse_handles_tags_and_junk(self):
        self.assertEqual(version.parse("v2.5.0"), (2, 5, 0))
        self.assertEqual(version.parse("2.10.1"), (2, 10, 1))
        self.assertEqual(version.parse("v3.0.0-rc1"), (3, 0, 0))
        self.assertEqual(version.parse("garbage"), (0,))
        self.assertGreater(version.parse("v2.10.0"), version.parse("v2.9.9"))

    def test_the_running_version_is_a_real_triplet(self):
        self.assertEqual(len(version.parse(version.VERSION)), 3)


class ReleaseTest(unittest.TestCase):
    def test_a_release_knows_whether_it_is_newer(self):
        cur = version.parse(version.VERSION)
        newer = updater.Release({"tag_name": f"v{cur[0]}.{cur[1] + 1}.0", "assets": []})
        same = updater.Release({"tag_name": f"v{version.VERSION}", "assets": []})
        older = updater.Release({"tag_name": "v0.1.0", "assets": []})
        self.assertTrue(newer.is_newer)
        self.assertFalse(same.is_newer)
        self.assertFalse(older.is_newer)

    def test_check_parses_the_github_payload(self):
        payload = json.dumps({
            "tag_name": "v9.9.9", "html_url": "https://example/rel", "body": "notes",
            "assets": [{"name": "PixelPomoArtKit-windows.zip",
                        "browser_download_url": "https://example/win.zip"}],
        }).encode("utf-8")
        opener = fake_opener(payload)
        rel = updater.check(opener=opener)
        self.assertEqual(rel.tag, "v9.9.9")
        self.assertTrue(rel.is_newer)
        self.assertEqual(rel.assets[updater.WINDOWS_ASSET], "https://example/win.zip")
        self.assertEqual(rel.url, "https://example/rel")
        req = opener.calls[0]
        self.assertEqual(req.full_url, updater.API)
        self.assertIn("PixelPomoArtKit", req.get_header("User-agent"))

    def test_check_raises_on_a_bad_payload_rather_than_guessing(self):
        with self.assertRaises(ValueError):
            updater.check(opener=fake_opener(b"<html>rate limited</html>"))


class DownloadAndStageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_download_writes_the_file_reports_progress_and_leaves_no_part_file(self):
        body = b"x" * 600_000
        seen = []
        dest = updater.download("https://example/win.zip", self.dir / "win.zip",
                                progress=lambda d, t: seen.append((d, t)),
                                opener=fake_opener(body, {"Content-Length": str(len(body))}))
        self.assertEqual(dest.read_bytes(), body)
        self.assertEqual(seen[-1], (len(body), len(body)))
        self.assertFalse((self.dir / "win.zip.part").exists())

    def test_backup_library_zips_every_drawing(self):
        lib = self.dir / "library"
        lib.mkdir()
        (lib / "a.json").write_text("A", encoding="utf-8")
        (lib / "b.json").write_text("B", encoding="utf-8")
        out = updater.backup_library(self.dir, "v9.9.9")
        self.assertTrue(out.exists())
        self.assertIn("before-9.9.9", out.name)
        with zipfile.ZipFile(out) as zf:
            self.assertEqual(sorted(zf.namelist()), ["a.json", "b.json"])
        self.assertIsNone(updater.backup_library(self.dir / "empty", "v1"), "nothing to back up")

    def test_stage_windows_unpacks_the_exe_and_writes_a_handoff_script(self):
        zip_path = self.dir / "PixelPomoArtKit-windows.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("READ-ME-FIRST.txt", "hi")
            zf.writestr("PixelPomoArtKit.exe", b"NEW EXE BYTES")
        exe = self.dir / "app" / "PixelPomoArtKit.exe"
        exe.parent.mkdir()
        exe.write_bytes(b"OLD")
        new_exe, script = updater.stage_windows(zip_path, exe)
        self.assertEqual(new_exe.read_bytes(), b"NEW EXE BYTES")
        self.assertEqual(new_exe.parent, exe.parent)
        self.assertEqual(exe.read_bytes(), b"OLD", "the running exe is not touched here")
        text = script.read_text(encoding="ascii")
        self.assertIn(str(os.getpid()), text)
        self.assertIn("PixelPomoArtKit.old.exe", text, "the old exe is kept for a revert")
        self.assertIn(f'move /y "{new_exe}" "{exe}"', text)
        self.assertIn(f'start "" "{exe}"', text)

    def test_stage_windows_refuses_a_zip_without_the_exe(self):
        zip_path = self.dir / "odd.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("README.txt", "no exe here")
        with self.assertRaises(ValueError):
            updater.stage_windows(zip_path, self.dir / "PixelPomoArtKit.exe")


if __name__ == "__main__":
    unittest.main()
