"""Offline tests for the archived DS4Windows mapper and Elmos ownership."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import elmos_ds4_engine as d


def make_zip(path, name="DS4Windows/DS4Windows.exe", value=b"fixture"):
    with zipfile.ZipFile(path, "w") as out:
        out.writestr(name, value)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManagedDS4Tests(unittest.TestCase):
    def test_archived_asset_and_checksum_are_pinned(self):
        self.assertIn("ds4windowsapp/DS4Windows/releases/download/ryochan7", d.RELEASE_URL)
        self.assertEqual(len(d.RELEASE_SHA256), 64)
        self.assertEqual(d.ARCHIVE_NAME, "ds4windows-3-3-3.zip")

    def test_verified_bundled_zip_never_downloads(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / d.ARCHIVE_NAME
            digest = make_zip(archive)
            with patch.object(d, "bundled_archive", return_value=archive), \
                 patch.object(d, "RELEASE_SHA256", digest), \
                 patch.object(d.urllib.request, "urlopen") as network:
                self.assertEqual(d.verified_archive(), archive)
                network.assert_not_called()

    def test_checksum_failure_does_not_run_untrusted_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / d.ARCHIVE_NAME
            make_zip(archive)
            with patch.object(d, "bundled_archive", return_value=archive):
                with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                    d.verified_archive()

    def test_extraction_idempotent_and_preserves_existing_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "test.zip"
            digest = make_zip(archive)
            with patch.object(d, "base_dir", return_value=root), \
                 patch.object(d, "RELEASE_SHA256", digest):
                exe = d.install_portable(archive)
                self.assertEqual(exe.name, "DS4Windows.exe")
                profile = root / "classic-ds4windows-3.3.3" / "Profiles" / "Default.xml"
                profile.parent.mkdir(exist_ok=True)
                profile.write_text("my original profile", encoding="utf-8")
                self.assertEqual(d.install_portable(archive), exe)
                self.assertEqual(profile.read_text(encoding="utf-8"), "my original profile")

    def test_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "bad.zip"
            make_zip(archive, "../escape.exe")
            with patch.object(d, "base_dir", return_value=root):
                with self.assertRaisesRegex(RuntimeError, "Unsafe path"):
                    d.install_portable(archive)
            self.assertFalse((root.parent / "escape.exe").exists())

    def test_running_existing_ds4windows_is_not_killed_or_duplicated(self):
        engine = d.DS4Engine()
        proc = MagicMock()
        proc.poll.return_value = None
        engine._thread = MagicMock()
        engine._thread.is_alive.return_value = True
        engine._owned_process = proc
        engine.start()
        engine._thread.start.assert_not_called()
        self.assertIs(engine._owned_process, proc)

    def test_shutdown_only_acts_on_owned_process(self):
        engine = d.DS4Engine()
        with patch.object(d.subprocess, "run") as cmd:
            engine._shutdown_owned()
            cmd.assert_not_called()

    def test_server_uses_exactly_one_active_mapper_and_stops_on_exit(self):
        server = (Path(__file__).resolve().parents[1] / "app" / "server.py").read_text()
        self.assertIn("ds4_engine.start()", server)
        self.assertNotIn("native_input.start()", server)
        self.assertIn("ds4_engine.stop(", server)
        self.assertIn("from elmos_ds4_engine import ds4_engine", server)

    def test_release_build_bundles_pinned_zip(self):
        root = Path(__file__).resolve().parents[1]
        spec = (root / "build" / "ElmosWorld.spec").read_text()
        workflow = (root / ".github/workflows/build-windows-release.yml").read_text()
        self.assertIn("'ds4windows-3-3-3.zip'", spec)
        self.assertIn(d.RELEASE_SHA256, workflow)


if __name__ == "__main__":
    unittest.main()
