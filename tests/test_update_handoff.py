"""Guard against the updater closing the application without installing."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'


class UpdateHandoffTests(unittest.TestCase):
    def test_worker_bundled(self):
        self.assertIn("'apply_update.ps1'", (ROOT / 'build/ElmosWorld.spec').read_text(encoding='utf-8'))
        self.assertTrue((APP / 'apply_update.ps1').exists())

    def test_worker_handles_already_exited_app(self):
        worker = (APP / 'apply_update.ps1').read_text(encoding='utf-8')
        self.assertIn('$null -eq $parent', worker)
        self.assertIn('Start-Process -FilePath $Installer', worker)
        self.assertIn("Set-UpdateState 'failed'", worker)
        self.assertIn('Restart-InstalledApp', worker)

    def test_failure_status_exposed(self):
        source = (APP / 'update_center.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn('def last_attempt()', source)
        self.assertIn("worker.poll()", source)


if __name__ == '__main__':
    unittest.main()
