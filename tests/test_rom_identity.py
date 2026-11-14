from pathlib import Path
import tempfile
import unittest
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'app'))
from rom_identity import identify_rom, summarize_roms
from smart_discovery import inspect_entry


class RomIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_xbox_360_xex_header_maps_to_xenia(self):
        path=self.root/'default.xex';path.write_bytes(b'XEX2'+bytes(200))
        result=identify_rom(path)
        self.assertEqual(result['platform'],'Xbox 360')
        self.assertIn('Xenia',result['recommendedEmulators'])

    def test_wii_wbfs_header_maps_to_dolphin(self):
        path=self.root/'game.wbfs';path.write_bytes(b'WBFS'+bytes(200))
        result=identify_rom(path)
        self.assertEqual(result['platform'],'Wii')
        self.assertIn('Dolphin',result['recommendedEmulators'])

    def test_nes_magic_is_required(self):
        good=self.root/'good.nes';good.write_bytes(b'NES\x1a'+bytes(200))
        bad=self.root/'bad.nes';bad.write_bytes(b'NOPE'+bytes(200))
        self.assertEqual(identify_rom(good)['platform'],'Nintendo Entertainment System')
        self.assertFalse(identify_rom(bad)['identified'])

    def test_roms_remain_review_only(self):
        path=self.root/'game.xex';path.write_bytes(b'XEX2'+bytes(200))
        result=inspect_entry(path,min_age=0)
        self.assertEqual(result['kind'],'rom')
        self.assertEqual(result['action'],'review')
        self.assertIn('Xenia',result['reason'])

    def test_mixed_folder_reports_manual_mapping(self):
        a=self.root/'a.xex';a.write_bytes(b'XEX2'+bytes(200))
        b=self.root/'b.wbfs';b.write_bytes(b'WBFS'+bytes(200))
        summary=summarize_roms([a,b])
        self.assertEqual(summary['platform'],'Mixed/unknown')
        self.assertEqual(summary['emulators'],[])


if __name__=='__main__':unittest.main()
