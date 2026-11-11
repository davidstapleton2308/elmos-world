"""High-precision, non-destructive Smart Discovery regression fixtures."""
from pathlib import Path
import os
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
from smart_discovery import inspect_entry, scan_downloads, move_verified, display_title


def touch(path, size=200_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as file:
        file.truncate(size)
    return path


class DiscoveryFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.downloads=self.base/'Downloads';self.downloads.mkdir()
        self.games=self.base/'Gaming'/'Games'
        self.emulators=self.base/'Gaming'/'Emulators'

    def tearDown(self):
        self.temp.cleanup()

    def look(self,path,age=0):
        return inspect_entry(path,min_age=age)

    def unity(self,name,exe=None):
        folder=self.downloads/name;folder.mkdir()
        binary=exe or display_title(name).replace(' ','')
        touch(folder/(binary+'.exe'))
        touch(folder/'UnityPlayer.dll')
        (folder/(binary+'_Data')).mkdir()
        return folder

    def test_title_normalization_preserves_real_numbers(self):
        cases={
            'Silent.Hill.2.SteamRIP.com':'Silent Hill 2',
            '7.Days.to.Die.SteamRIP.com':'7 Days to Die',
            'Control.UE.SteamRIP.com':'Control Ultimate Edition',
            'Outer.Wilds.v1.2.3.SteamRIP.com':'Outer Wilds',
            'Buckshot_Roulette [SteamRip]':'Buckshot Roulette'
        }
        for before,after in cases.items():
            with self.subTest(before=before):
                self.assertEqual(display_title(before),after)

    def test_valid_unity_folder_is_ready(self):
        folder=self.unity('Outer.Wilds.SteamRIP.com','OuterWilds')
        result=self.look(folder)
        self.assertEqual(result['kind'],'game')
        self.assertEqual(result['action'],'ready')
        self.assertGreaterEqual(result['confidence'],96)

    def test_inconsistent_executable_stays_in_review(self):
        folder=self.unity('Silent Hill 2','RandomToolbar')
        self.assertNotEqual(self.look(folder)['action'],'ready')

    def test_archive_not_moved(self):
        for ext in ('.zip','.rar','.7z'):
            item=touch(self.downloads/('Sekiro.SteamRIP.com'+ext))
            self.assertEqual(self.look(item)['kind'],'archive')
            self.assertEqual(self.look(item)['action'],'ignore')

    def test_loose_executables_and_installers_never_moved(self):
        for name in ('setup.exe','Setup_s.exe','installer.msi','update.exe','CCleaner.exe'):
            item=touch(self.downloads/name)
            self.assertEqual(self.look(item)['kind'],'installer')
            self.assertEqual(self.look(item)['action'],'ignore')

    def test_known_emulator_with_config(self):
        folder=self.downloads/'Xenia Canary';folder.mkdir()
        touch(folder/'xenia_canary.exe')
        touch(folder/'xenia-canary-config.toml',100)
        item=self.look(folder)
        self.assertEqual(item['kind'],'emulator')
        self.assertEqual(item['action'],'ready',item)
        self.assertEqual(item['emulator']['platform'],'Xbox 360')

    def test_emulator_without_supporting_config_needs_review(self):
        folder=self.downloads/'Dolphin emulator';folder.mkdir()
        touch(folder/'Dolphin.exe')
        self.assertEqual(self.look(folder)['kind'],'emulator')
        self.assertNotEqual(self.look(folder)['action'],'ready')

    def test_rom_or_disc_needs_review(self):
        self.assertEqual(self.look(touch(self.downloads/'SSX.iso'))['action'],'review')

    def test_installer_only_folder_is_not_game(self):
        folder=self.downloads/'Unrelated Utility';folder.mkdir()
        touch(folder/'setup.exe')
        self.assertEqual(self.look(folder)['kind'],'installer')

    def test_random_exe_folder_not_auto_moved(self):
        folder=self.downloads/'Music Player';folder.mkdir()
        touch(folder/'MusicPlayer.exe')
        self.assertNotEqual(self.look(folder)['action'],'ready')

    def test_partial_download_blocks_movement(self):
        folder=self.unity('Outer Wilds','OuterWilds')
        touch(folder/'transfer.crdownload')
        self.assertNotEqual(self.look(folder)['action'],'ready')

    def test_new_download_blocks_movement(self):
        folder=self.unity('Outer Wilds','OuterWilds')
        self.assertNotEqual(self.look(folder,age=120)['action'],'ready')

    def test_verified_move_preserves_file_and_folder(self):
        folder=self.unity('Outer Wilds','OuterWilds')
        result=self.look(folder)
        moved=move_verified(result,self.downloads,self.games,self.emulators,min_age=0)
        self.assertFalse(folder.exists())
        self.assertTrue(Path(moved['exe']).is_file())
        self.assertTrue(Path(moved['path']).is_dir())

    def test_conflicting_destination_prevents_move(self):
        folder=self.unity('Hades','Hades')
        self.games.mkdir(parents=True)
        (self.games/'Hades').mkdir()
        with self.assertRaises(FileExistsError):
            move_verified(self.look(folder),self.downloads,self.games,self.emulators,min_age=0)
        self.assertTrue(folder.exists())

    def test_review_folder_cannot_be_force_moved(self):
        folder=self.downloads/'Desktop utilities';folder.mkdir()
        touch(folder/'settings.exe')
        with self.assertRaises(ValueError):
            move_verified(self.look(folder),self.downloads,self.games,self.emulators,min_age=0)

    def test_symlink_and_nested_symlink_are_blocked(self):
        if not hasattr(os,'symlink'):self.skipTest('Symlink unavailable')
        folder=self.unity('Outer Wilds','OuterWilds')
        alias=self.downloads/'alias'
        try:alias.symlink_to(folder,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink permission unavailable')
        self.assertEqual(self.look(alias)['action'],'ignore')
        link=folder/'bad-link'
        try:link.symlink_to(self.downloads,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink permission unavailable')
        self.assertNotEqual(self.look(folder)['action'],'ready')

    def test_scan_is_read_only(self):
        self.unity('Outer Wilds','OuterWilds')
        touch(self.downloads/'setup.exe')
        before={str(p.relative_to(self.downloads)) for p in self.downloads.rglob('*')}
        result=scan_downloads(self.downloads,min_age=0)
        after={str(p.relative_to(self.downloads)) for p in self.downloads.rglob('*')}
        self.assertEqual(before,after)
        self.assertEqual(len(result),2)


if __name__ == '__main__':
    unittest.main()
