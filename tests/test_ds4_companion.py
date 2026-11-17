"""Regression checks: no duplicate controller mapper, verified optional download."""
import io
import os
import sys
import tempfile
import unittest
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import ds4_companion

class DS4Tests(unittest.TestCase):
    def test_existing_installation_is_never_changed_or_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'DS4Windows.exe'
            exe.write_bytes(b'existing')
            with patch.object(ds4_companion,'existing_executable',return_value=exe),\
                 patch.object(ds4_companion,'managed_root',return_value=Path(tmp)),\
                 patch.object(ds4_companion.urllib.request,'urlopen') as network:
                result=ds4_companion.install_missing_user_component()
                self.assertFalse(result['installed'])
                network.assert_not_called()
                self.assertEqual(exe.read_bytes(),b'existing')

    def test_download_checksum_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ds4_companion,'existing_executable',return_value=None),\
                 patch.object(ds4_companion,'managed_root',return_value=Path(tmp)),\
                 patch.object(ds4_companion.urllib.request,'urlopen',
                                  return_value=io.BytesIO(b'not the verified archive')):
                with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                    ds4_companion.install_missing_user_component()
            self.assertFalse((Path(tmp)/'DS4Windows').exists())

    def test_validated_archive_does_not_modify_kernel_drivers(self):
        s=(ROOT/'app'/'ds4_companion.py').read_text(encoding='utf-8')
        self.assertIn('ARCHIVE_SHA256',s)
        self.assertIn('install_missing_user_component()',s)
        self.assertIn('if _running_named',s)
        self.assertNotIn("subprocess.run(['msiexec'",s)
        self.assertNotIn("subprocess.run(['pnputil'",s)
        self.assertNotIn('HidHideSetup.exe',s)
        self.assertIn("viiper.exe",s)

    def test_known_hash_matches_historical_verified_classic_build(self):
        self.assertEqual(ds4_companion.ARCHIVE_SHA256,
        'cf5619bcb51b82e4e1765276e9f67fb1e2d23dff968a653657acf35bafff8bf4')


if __name__=='__main__':
    unittest.main()
