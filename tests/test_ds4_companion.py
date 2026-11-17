"""Bundled Elmos Input regression checks: no runtime installers or unexpected changes."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import ds4_companion

class BundledInputTests(unittest.TestCase):
    def test_bundled_runtime_preferred_to_external_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            exe=root/'ElmosInput'/'DS4Windows'/'DS4Windows.exe'
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b'test executable')
            with patch.object(ds4_companion, '__file__', str(root/'ds4_companion.py')):
                self.assertEqual(ds4_companion.bundled_executable(),exe)
                self.assertEqual(ds4_companion.existing_executable(),exe)

    def test_missing_runtime_does_not_download_or_install_drivers(self):
        with patch.object(ds4_companion.os, 'name','nt'), \
             patch.object(ds4_companion, '_running_named',return_value=[]), \
             patch.object(ds4_companion,'existing_executable',return_value=None), \
             patch.object(ds4_companion,'status',return_value={'running':False}), \
             patch.object(ds4_companion.subprocess,'Popen') as popen:
            result=ds4_companion.start_existing()
        popen.assert_not_called()
        self.assertEqual(result['running'],False)

    def test_launch_path_is_not_a_driver_installer(self):
        s=(ROOT/'app'/'ds4_companion.py').read_text(encoding='utf-8')
        self.assertIn('bundled_executable()',s)
        self.assertNotIn('install_if_missing(',s)
        self.assertNotIn('install_missing_user_component(',s)
        self.assertNotIn('ARCHIVE_URL',s)
        self.assertNotIn('ViGEmBus_1.22.0',s)

    def test_build_preparation_requires_exact_hash_and_source(self):
        script=(ROOT/'build'/'prepare_elmos_input.ps1').read_text(encoding='utf-8')
        self.assertIn('VIIPERRC4.6.6',script)
        self.assertIn('b97daa4c605c778afaa64fcc8283e2218597a1b8bcf6b55cd2443302346ba4af',script)
        self.assertIn('CorrespondingSource',script)
        self.assertIn('DS4Windows-VIIPERRC4.6.6-SOURCE.zip',script)
        self.assertIn('VIIPER-0.1.9-rc4.6.6-SOURCE.zip',script)

if __name__=='__main__':
    unittest.main()
