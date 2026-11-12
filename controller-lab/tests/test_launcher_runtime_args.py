import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elmos_controller_lab.lab import build_parser


class LauncherRuntimeArgumentsTests(unittest.TestCase):
    def test_emulate_accepts_stable_guid_and_supervision_handles(self):
        args = build_parser().parse_args([
            "--bridge", "bridge.exe", "emulate",
            "--profile", "xbox-360-wired", "--game", "pc:outer-wilds",
            "--device", "2", "--device-guid", "030000004c050000c405000000010000",
            "--stop-file", "stop.flag", "--watch-file", "game.pid",
            "--status-file", "runtime.json",
        ])
        self.assertEqual(args.device, 2)
        self.assertEqual(args.device_guid, "030000004c050000c405000000010000")
        self.assertEqual(args.stop_file, "stop.flag")
        self.assertEqual(args.watch_file, "game.pid")
        self.assertEqual(args.status_file, "runtime.json")

    def test_first_game_launch_prefers_physical_ps4_over_virtual_xbox(self):
        from elmos_controller_lab.lab import choose_physical_device
        devices = [
            {"index": 0, "guid": "virtual", "name": "Xbox 360 Controller"},
            {"index": 1, "guid": "ps4", "name": "Wireless Controller"},
        ]
        self.assertEqual(choose_physical_device(devices)["guid"], "ps4")
        self.assertEqual(choose_physical_device(devices, "virtual", 0)["guid"], "virtual")
        self.assertIsNone(choose_physical_device(devices, "missing", 0))

    def test_gui_accepts_initial_game_and_virtual_profile(self):
        args = build_parser().parse_args([
            "--bridge", "bridge.exe", "gui",
            "--game", "pc:outer-wilds", "--profile", "dualsense",
        ])
        self.assertEqual(args.game, "pc:outer-wilds")
        self.assertEqual(args.profile, "dualsense")


if __name__ == "__main__":
    unittest.main()
