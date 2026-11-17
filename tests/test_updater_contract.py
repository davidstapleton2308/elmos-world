"""Offline contract tests for Windows in-app updates and release packaging."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch
from io import BytesIO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import update_center


class UpdaterContractTests(unittest.TestCase):
    def test_semantic_version_comparison(self):
        self.assertEqual(update_center.ver_tuple('v3.1.15'), (3, 1, 15))
        self.assertGreater(update_center.ver_tuple('3.1.15'), update_center.ver_tuple('3.1.9'))
        self.assertIsNone(update_center.ver_tuple('latest'))

    def test_update_requires_installer_and_checksum(self):
        release = {
            'tag_name': 'v9.0.0',
            'html_url': 'https://github.com/davidstapleton2308/elmos-world/releases/tag/v9.0.0',
            'assets': [{'name': 'ElmosWorld_Setup_9.0.0.exe', 'browser_download_url':
                        'https://github.com/davidstapleton2308/elmos-world/releases/download/v9.0.0/setup.exe'}]
        }
        with patch.object(update_center, 'config', return_value={'repository': update_center.DEFAULT_REPOSITORY}), patch.object(
            update_center.urllib.request, 'urlopen', return_value=BytesIO(json.dumps(release).encode())
        ):
            outcome = update_center.latest()
        self.assertTrue(outcome['available'])
        self.assertFalse(outcome['installable'])

    def test_windows_worker_uses_installed_app_as_self_test(self):
        script = (ROOT / 'app' / 'apply_update.ps1').read_text(encoding='utf-8')
        self.assertIn("-ArgumentList '--self-test'", script)
        self.assertIn('if ($app.HasExited)', script)
        self.assertIn("Set-UpdateState 'complete'", script)

    def test_ci_does_not_use_whoami_as_installed_app(self):
        workflow = (ROOT / '.github/workflows/build-windows-release.yml').read_text(encoding='utf-8')
        self.assertNotIn('System32/whoami.exe', workflow)
        self.assertIn('-AppExe $installedApp', workflow)
        self.assertIn('--latest --target', workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)


if __name__ == '__main__':
    unittest.main()
