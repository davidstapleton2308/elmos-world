"""Undo safety tests: never overwrite or lose organized files."""
from pathlib import Path
import tempfile
import time
import os
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'app'))
from smart_discovery import inspect_folder, move_verified, undo_verified


class SmartUndoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.downloads=self.root/'Downloads';self.downloads.mkdir()
        self.games=self.root/'Gaming'/'Games'
        self.emu=self.root/'Gaming'/'Emulators'
        self.folder=self.downloads/'Outer Wilds';self.folder.mkdir()
        (self.folder/'OuterWilds.exe').write_bytes(bytes(160_000))
        (self.folder/'UnityPlayer.dll').write_bytes(bytes(100))
        (self.folder/'OuterWilds_Data').mkdir()
        completed=time.time()-300
        for path in [self.folder,*self.folder.rglob('*')]:
            os.utime(path,(completed,completed))
    def tearDown(self):
        self.tmp.cleanup()
    def move(self):
        item=inspect_folder(self.folder,min_age=0)
        self.assertEqual(item['action'],'ready')
        return move_verified(item,self.downloads,self.games,self.emu,min_age=0)

    def test_undo_restores_original_folder_and_exe(self):
        record=self.move()
        result=undo_verified(record,self.downloads,self.games,self.emu)
        self.assertTrue(self.folder.exists())
        self.assertTrue((self.folder/'OuterWilds.exe').exists())
        self.assertEqual(result['path'],str(self.folder))
        self.assertFalse(Path(record['path']).exists())

    def test_undo_refuses_to_overwrite_new_download_folder(self):
        record=self.move()
        self.folder.mkdir()
        (self.folder/'personal-notes.txt').write_text('keep me')
        with self.assertRaises(FileExistsError):
            undo_verified(record,self.downloads,self.games,self.emu)
        self.assertTrue((self.folder/'personal-notes.txt').exists())
        self.assertTrue(Path(record['path']).exists())

    def test_tampered_record_cannot_target_unrelated_directory(self):
        record=self.move()
        altered=dict(record,path=str(self.root/'Unrelated'))
        with self.assertRaises(ValueError):
            undo_verified(altered,self.downloads,self.games,self.emu)


if __name__=='__main__':
    unittest.main()
