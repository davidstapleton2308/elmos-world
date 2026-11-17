"""Safe conditional driver download/install checks for the classic controller backend."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import elmos_input_driver as d

class DriverSafetyTests(unittest.TestCase):
    def test_expected_vendor_hash_and_source(self):
        self.assertEqual(d.VIGEM_SHA256,'89220a7865076b342892f98865f3499fb7c4cfd673159e89d352c360fd014c6a')
        self.assertIn('github.com/nefarius/ViGEmBus/releases/download/v1.22.0',d.VIGEM_URL)

    def test_existing_driver_skips_all_downloads_and_installers(self):
        with patch.object(d.os,'name','nt'),patch.object(d,'is_installed',return_value=True),\
             patch.object(d,'download_verified') as download,\
             patch.object(d.subprocess,'run') as run:
            result=d.install_if_missing()
        self.assertEqual(result['status'],'already-installed')
        download.assert_not_called()
        run.assert_not_called()

    def test_bad_driver_archive_cannot_be_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'driver.exe'
            with patch.object(d,'managed_driver_file',return_value=file),\
                 patch.object(d.urllib.request,'urlopen',return_value=io.BytesIO(b'invalid installer')):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    d.download_verified()
            self.assertFalse(file.exists())

    def test_uac_is_not_bypassed(self):
        s=(ROOT/'app'/'elmos_input_driver.py').read_text(encoding='utf-8')
        self.assertIn("'-Verb RunAs",s)
        self.assertIn("if is_installed():return",s)
        self.assertIn("'/exenoui /qn /norestart'",s)
        self.assertNotIn('ConsentPromptBehaviorAdmin',s)
        self.assertNotIn('EnableLUA',s)

    def test_known_ds4_archive_source_and_checksum(self):
        import ds4_companion as c
        self.assertIn('github.com/ds4windowsapp/DS4Windows/releases/download/',c.ARCHIVE_URL)
        self.assertIn('ryochan7/ds4windows-3-3-3.zip',c.ARCHIVE_URL)
        self.assertEqual(c.ARCHIVE_SHA256,'cf5619bcb51b82e4e1765276e9f67fb1e2d23dff968a653657acf35bafff8bf4')

if __name__=='__main__':
    unittest.main()
