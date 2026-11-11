"""Offline checks for release integrity. No Windows installer required."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'


class ReleasePackagingTests(unittest.TestCase):
    def test_essential_files_exist(self):
        for path in (
            ROOT / 'INSTALL_APP.bat', ROOT / 'Build_Release.bat',
            ROOT / 'build/ElmosWorld.spec', ROOT / 'build/ElmosWorld.iss',
            ROOT / 'build/version_file.txt',
            ROOT / '.github/workflows/build-windows-release.yml',
            APP / 'server.py', APP / 'app.js', APP / 'index.html',
            APP / 'elmos_world.ico', APP / 'launcher_entry.py',
        ):
            self.assertTrue(path.is_file(), f'Missing: {path}')

    def test_every_runtime_resource_is_bundled(self):
        spec = (ROOT / 'build/ElmosWorld.spec').read_text(encoding='utf-8')
        self.assertIn('ROOT = Path(SPECPATH).resolve().parent', spec)
        required = ['index.html', 'app.js', 'app.css', 'brand_emblem.svg',
                    'graphite_weave.svg', 'premium_31.css', 'elmos_world.ico']
        for resource in required:
            self.assertIn(resource, spec)
            self.assertTrue((APP / resource).is_file())

    def test_bootstrap_is_valid_and_has_health_check(self):
        text = (APP / 'launcher_entry.py').read_text(encoding='utf-8')
        ast.parse(text)
        self.assertIn("'--self-test'", text)
        self.assertIn('_MUTEX_NAME', text)
        self.assertIn('ElmosWorld', text)

    def test_installer_preserves_app_data_and_game_files(self):
        installer = (ROOT / 'build/ElmosWorld.iss').read_text(encoding='utf-8')
        self.assertIn('PrivilegesRequired=lowest', installer)
        self.assertIn('AppMutex=Local\\ElmosWorldDesktopApp', installer)
        self.assertIn('DefaultDirName={localappdata}', installer)
        self.assertNotIn('C:\\Gaming\\Games', installer)
        self.assertNotIn('UninstallDelete', installer)
        self.assertIn('3.1.1', installer)

    def test_versioned_upgrade_identity(self):
        text = (ROOT / 'build/ElmosWorld.iss').read_text(encoding='utf-8')
        self.assertIn('AppId={{3E87116F-2395-4932-9543-711795ECB357}', text)
        self.assertIn('ElmosWorld_Setup_3.1.1', text)

    def test_source_runtime_no_user_data_in_release(self):
        for forbidden in ('registry_v2.json', 'settings.json', 'arcade.json',
                          'grove_state.json', 'launch_profiles.json'):
            self.assertFalse((APP / forbidden).exists(), forbidden)


if __name__ == '__main__':
    unittest.main()

# A separate subclass keeps the original release tests untouched.
class BuilderFixTests(unittest.TestCase):
    def test_runtime_probe_is_not_pinned_to_python312(self):
        script = (ROOT / 'build/Build_Release.ps1').read_text(encoding='utf-8')
        self.assertIn('function Test-PythonRuntime', script)
        self.assertIn('function Find-PythonRuntime', script)
        for version in ('3.11', '3.12', '3.13'):
            self.assertIn(version, script)
        self.assertNotIn("& py -3.12 --version", script)
        self.assertIn('ProcessStartInfo', script)

    def test_missing_python_has_an_install_option(self):
        script = (ROOT / 'build/Build_Release.ps1').read_text(encoding='utf-8')
        self.assertIn('Python.Python.3.12', script)
        self.assertIn('Read-Host', script)
        self.assertIn('Find-PythonRuntime', script)

    def test_standalone_self_test_is_waited_on(self):
        script = (ROOT / 'build/Build_Release.ps1').read_text(encoding='utf-8')
        self.assertIn("-ArgumentList '--self-test' -Wait -PassThru", script)
        self.assertIn('$SelfTest.ExitCode', script)

    def test_app_code_kept_separate(self):
        self.assertTrue((ROOT / 'BUILDER_FIX_README.txt').exists())
