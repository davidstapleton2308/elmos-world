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

    def test_installed_vigembus_service_is_detected(self):
        from unittest.mock import MagicMock
        service_output = (
            'SERVICE_NAME: ViGEmBus\\n'
            '        TYPE               : 1  KERNEL_DRIVER\\n'
            '        STATE              : 4  RUNNING\\n'
        )
        with patch.object(d.os, 'name', 'nt'), patch.object(
            d.subprocess, 'run',
            return_value=MagicMock(returncode=0, stdout=service_output)
        ) as query:
            self.assertTrue(d.is_installed())
        query.assert_called_once()

    def test_stopped_but_registered_vigembus_service_is_installed(self):
        from unittest.mock import MagicMock
        with patch.object(d.os, 'name', 'nt'), patch.object(
            d.subprocess, 'run',
            return_value=MagicMock(returncode=0, stdout='SERVICE_NAME: ViGEmBus\\nSTATE: 1 STOPPED')
        ):
            self.assertTrue(d.is_installed())

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

    def test_stale_uninstall_record_does_not_skip_driver_install(self):
        from unittest.mock import MagicMock
        with patch.object(d.os,'name','nt'), patch.object(d.subprocess,'run',
             return_value=MagicMock(returncode=1060,stdout='')) as call:
            self.assertFalse(d.is_installed())
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0][0], 'sc.exe')

    def test_uac_is_not_bypassed(self):
        s=(ROOT/'app'/'elmos_input_driver.py').read_text(encoding='utf-8')
        self.assertIn("-Verb RunAs -Wait -PassThru",s)
        self.assertIn("if is_installed():return",s)
        self.assertIn("'/exenoui /qn /norestart'",s)
        self.assertNotIn('ConsentPromptBehaviorAdmin',s)
        self.assertNotIn('EnableLUA',s)


if __name__=='__main__':
    unittest.main()
