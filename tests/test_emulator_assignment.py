"""Emulator assignment tests: preserve existing ROM identity and media mappings."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from backend import Engine


class EmulatorAssignmentTests(unittest.TestCase):
    def make_engine(self, image):
        engine = Engine.__new__(Engine)
        engine.lock = threading.RLock()
        engine.extra = {
            'emulators': {'xenia': {'name': 'Xenia'}, 'dolphin': {'name': 'Dolphin'}},
            'roms': {'rom:stable-identity': {'name': 'Test Game', 'path': str(image), 'emulator': 'xenia'}},
        }
        engine.save = lambda: None
        return engine

    def test_reassignment_preserves_id_title_and_gamefile(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'game.iso'
            image.write_bytes(b'test')
            engine = self.make_engine(image)
            before = dict(engine.extra['roms']['rom:stable-identity'])
            result = engine.assign_rom_emulator('rom:stable-identity', 'dolphin')
            after = engine.extra['roms']['rom:stable-identity']
            self.assertTrue(result['ok'])
            self.assertEqual(after['emulator'], 'dolphin')
            self.assertEqual(after['name'], before['name'])
            self.assertEqual(after['path'], before['path'])
            self.assertEqual(list(engine.extra['roms']), ['rom:stable-identity'])
            self.assertTrue(image.exists())

    def test_refuse_unknown_emulator_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'game.iso'
            image.write_bytes(b'test')
            engine = self.make_engine(image)
            with self.assertRaises(RuntimeError):
                engine.assign_rom_emulator('rom:stable-identity', 'missing')
            self.assertEqual(engine.extra['roms']['rom:stable-identity']['emulator'], 'xenia')

    def test_refuse_non_rom_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'game.iso'
            image.write_bytes(b'test')
            engine = self.make_engine(image)
            with self.assertRaises(RuntimeError):
                engine.assign_rom_emulator('pc:some-id', 'xenia')


if __name__ == '__main__':
    unittest.main()
