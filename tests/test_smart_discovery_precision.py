"""Broad synthetic regression corpus for Game/Emulator Smart Discovery.

This is a controlled test set, NOT a statistical estimate of accuracy against
all real-world downloads. It intentionally favors false-negative review over
irreversible false-positive moves.
"""
from pathlib import Path
import tempfile
import time
import os
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'app'))
from smart_discovery import inspect_folder, inspect_entry


def item(path,size=180_000):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as fh:fh.truncate(size)
    return path


class DiscoveryPrecisionCorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def inspect(self,path):
        return inspect_folder(path,min_age=0)

    def test_100_non_game_program_names_do_not_auto_move(self):
        prefixes=['Browser','Notepad','Editor','Photos','Videos','ZipTool',
                  'Updater','Installer','Cleaner','PDFReader','DriverTool',
                  'Markdown','Terminal','Runtime','Benchmark','Utility',
                  'FileManager','Backup','Downloader','ScreenRecorder']
        suffixes=['2023','2024','2025','2026','Pro']
        count=0
        for prefix in prefixes:
            for suffix in suffixes:
                name=f'{prefix} {suffix}'
                folder=self.folder/name;folder.mkdir()
                item(folder/(name.replace(' ','')+'.exe'))
                result=self.inspect(folder)
                self.assertNotEqual(result['action'],'ready',result)
                count+=1
        self.assertEqual(count,100)

    def test_25_installer_and_transient_variants_never_auto_move(self):
        titles=['Control','Elden Ring','Silent Hill 2','Outer Wilds','Hades']
        extensions=['setup.exe','installer.exe','unins000.exe','redist.exe','update.exe']
        count=0
        for title in titles:
            for utility in extensions:
                folder=self.folder/(title+' '+utility);folder.mkdir()
                item(folder/utility)
                result=self.inspect(folder)
                self.assertNotEqual(result['action'],'ready',result)
                count+=1
        self.assertEqual(count,25)

    def test_12_unreal_game_executable_variants_are_scanned(self):
        names=['Hogwarts Legacy','Palworld','The Finals','Mortal Kombat 11',
               'Lies of P','Remnant 2','The Invincible','RoboCop Rogue City',
               'Stray','The Outer Worlds','High on Life','Immortals of Aveum']
        for title in names:
            with self.subTest(title=title):
                folder=self.folder/title;folder.mkdir()
                exe=title.replace(' ','')+'-Win64-Shipping.exe'
                item(folder/'Binaries'/'Win64'/exe)
                (folder/'Engine').mkdir()
                (folder/'Content').mkdir()
                # Model completed downloads. Windows timestamps can be a moment
                # ahead of the test clock immediately after file creation.
                old_time=time.time()-300
                for path in [folder,*folder.rglob('*')]:
                    os.utime(path,(old_time,old_time))
                result=self.inspect(folder)
                self.assertEqual(result['kind'],'game',result)
                self.assertEqual(result['action'],'ready',result)

    def test_emulator_does_not_get_labeled_as_game(self):
        cases=[
            ('Dolphin','Dolphin.exe','Dolphin.ini'),
            ('PCSX2','pcsx2-qt.exe','pcsx2.ini'),
            ('Cemu','Cemu.exe','config.ini'),
            ('RPCS3','rpcs3.exe','config.ini'),
            ('RetroArch','retroarch.exe','retroarch.cfg'),
            ('Xenia Canary','xenia_canary.exe','xenia-canary-config.toml')
        ]
        for folder_name,exe,config in cases:
            with self.subTest(folder_name=folder_name):
                folder=self.folder/folder_name;folder.mkdir()
                item(folder/exe)
                item(folder/config,300)
                old_time=time.time()-300
                for path in [folder,*folder.rglob('*')]:
                    os.utime(path,(old_time,old_time))
                result=self.inspect(folder)
                self.assertEqual(result['kind'],'emulator',result)
                self.assertEqual(result['action'],'ready',result)

    def test_more_ambiguous_executables_remain_review_only(self):
        for title in ('Download Games','New Folder','My Games','Games Collection',
                      'Downloads 2026','Portable Installers','Roms'):
            folder=self.folder/title;folder.mkdir()
            item(folder/'Install.exe')
            item(folder/'Start.exe')
            item(folder/'Tools.exe')
            result=self.inspect(folder)
            self.assertNotEqual(result['action'],'ready',result)


if __name__ == '__main__':
    unittest.main()
