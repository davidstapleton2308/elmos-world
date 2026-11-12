import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from controller_runtime import ControllerRuntime
from elmos_controller_lab.lab import _write_runtime_status
from elmos_controller_lab.process import pid_alive


class ControllerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.data = self.root / "data"
        self.runner = self.app / "controller-runtime" / "ElmosControllerRuntime.exe"
        self.bridge = self.app / "controller-lab" / "bridge" / "publish" / "Elmos.ControllerLab.Bridge.exe"
        self.runner.parent.mkdir(parents=True)
        self.bridge.parent.mkdir(parents=True)
        self.runner.write_bytes(b"fixture")
        self.bridge.write_bytes(b"fixture")
        self.calls = []
        self.runtime = ControllerRuntime(
            app_dir=self.app, data_dir=self.data, runner_path=self.runner,
            bridge_path=self.bridge, platform="win32",
            shell_execute=lambda exe, params, cwd: self.calls.append((exe, params, cwd)) or 42,
            prerequisite_check=lambda: {"ready": True, "state": "ready", "message": "ready"},
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_default_profile_is_safe_and_auto_start_is_off(self):
        profile = self.runtime.get_game_profile("pc:outer-wilds")
        self.assertEqual(profile["profileId"], "xbox-360-wired")
        self.assertEqual(profile["deviceIndex"], 0)
        self.assertFalse(profile["autoStart"])

    def test_global_auto_support_enabled_for_game_launches(self):
        before = self.runtime.get_game_profile("new-game")
        self.assertFalse(before["autoStart"])
        prefs = self.runtime.set_automatic_preferences(True)
        self.assertTrue(prefs["enabled"])
        after = self.runtime.get_game_profile("new-game")
        self.assertTrue(after["autoStart"])
        self.assertTrue(after["inheritedAutoStart"])
        self.assertEqual(after["profileId"], "xbox-360-wired")
        self.runtime.save_game_profile("new-game", "dualsense", 0, False)
        self.assertFalse(self.runtime.get_game_profile("new-game")["autoStart"])
        self.runtime.set_automatic_preferences(False)
        self.assertFalse(self.runtime.get_game_profile("different-game")["autoStart"])
        with self.assertRaises(ValueError):
            self.runtime.set_automatic_preferences(1)

    def test_save_and_reload_per_game_profile(self):
        saved = self.runtime.save_game_profile("pc:outer-wilds", "dualsense", 1, True, "030000004c050000c405000000010000")
        self.assertEqual(saved["profileId"], "dualsense")
        self.assertEqual(saved["deviceIndex"], 1)
        self.assertEqual(saved["deviceGuid"], "030000004c050000c405000000010000")
        self.assertTrue(saved["autoStart"])
        data = json.loads(self.runtime.profiles_file.read_text(encoding="utf-8"))
        self.assertIn("pc:outer-wilds", data["games"])

    def test_reject_invalid_profile_and_device_index(self):
        with self.assertRaises(ValueError):
            self.runtime.save_game_profile("game", "../unsafe", 0, False)
        with self.assertRaises(ValueError):
            self.runtime.save_game_profile("game", "dualsense", -1, False)
        with self.assertRaises(ValueError):
            self.runtime.save_game_profile("game", "dualsense", 0, 1)

    def test_start_requires_auto_opt_in_and_build_files(self):
        self.runtime.set_automatic_preferences(False)
        result = self.runtime.start_for_game("game")
        self.assertIsNone(result)
        self.assertEqual(self.calls, [])
        self.runtime.save_game_profile("game", "xbox-360-wired", 0, True, "030000004c050000c405000000010000")
        result = self.runtime.start_for_game("game")
        self.assertTrue(result["started"])
        self.assertEqual(len(self.calls), 1)
        status = self.runtime.status()
        self.assertEqual(status["state"], "starting")
        self.assertIn("--stop-file", self.calls[0][1])
        self.assertIn("--watch-file", self.calls[0][1])
        self.assertIn("--device-guid", self.calls[0][1])

    def test_start_fails_closed_before_uac_when_driver_is_missing(self):
        self.runtime.save_game_profile("game", "xbox-360-wired", 0, True)
        self.runtime._prerequisite_check = lambda: {
            "ready": False, "state": "driver_missing",
            "message": "Install the Elmos virtual-controller driver first.",
        }
        with self.assertRaisesRegex(RuntimeError, "Install the Elmos virtual-controller driver"):
            self.runtime.start_for_game("game")
        self.assertEqual(self.calls, [], "Do not show the game-session UAC prompt when the driver is absent.")

    def test_install_driver_skips_uac_when_prerequisites_are_ready(self):
        result = self.runtime.install_driver()
        self.assertFalse(result["requested"])
        self.assertTrue(result["alreadyReady"])
        self.assertEqual(self.calls, [])

    def test_install_driver_requests_uac_when_driver_is_missing(self):
        self.runtime._prerequisite_check = lambda: {
            "ready": False, "state": "driver_missing",
            "message": "Driver missing.",
        }
        result = self.runtime.install_driver()
        self.assertTrue(result["requested"])
        self.assertEqual(len(self.calls), 1)
        self.assertIn("install-driver", self.calls[0][1])

    def test_attach_game_process_writes_watch_file(self):
        self.runtime.save_game_profile("game", "xbox-360-wired", 0, True)
        self.runtime.start_for_game("game")
        self.assertTrue(self.runtime.attach_game_process(12345))
        current = self.runtime.status()
        self.assertEqual(Path(current["watchFile"]).read_text(encoding="ascii"), "12345")

    def test_helper_status_keeps_launcher_session_controls(self):
        self.runtime.save_game_profile("game", "xbox-360-wired", 0, True)
        result = self.runtime.start_for_game("game")
        current = self.runtime.status()
        args = SimpleNamespace(status_file=self.runtime.status_file, game="game",
                               profile="xbox-360-wired", session_id=result["sessionId"],
                               stop_file=current["stopFile"], watch_file=current["watchFile"])
        _write_runtime_status(args, "running", frames=1)
        self.assertEqual(self.runtime.wait_ready(1)["state"], "running")
        self.assertTrue(self.runtime.attach_game_process(12345))
        self.assertEqual(Path(args.watch_file).read_text(encoding="ascii"), "12345")
        self.assertFalse(self.runtime.stop("previous-session")["requested"])
        self.assertTrue(self.runtime.stop(result["sessionId"])["requested"])
        self.assertTrue(Path(args.stop_file).is_file())

    def test_pid_check_leaves_live_game_process_running(self):
        with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as game:
            try:
                self.assertTrue(pid_alive(game.pid))
                self.assertIsNone(game.poll())
            finally:
                game.terminate()
                game.wait(timeout=5)
            self.assertFalse(pid_alive(game.pid))

    def test_stop_requests_graceful_virtual_device_release(self):
        self.runtime.save_game_profile("game", "xbox-360-wired", 0, True)
        self.runtime.start_for_game("game")
        result = self.runtime.stop()
        self.assertTrue(result["requested"])
        current = self.runtime.status()
        self.assertTrue(Path(current["stopFile"]).is_file())

    def test_uac_cancel_is_not_reported_as_success(self):
        self.runtime.save_game_profile("game", "xbox-360-wired", 0, True)
        self.runtime._shell_execute = lambda *_: 5
        with self.assertRaisesRegex(RuntimeError, "approval was declined"):
            self.runtime.start_for_game("game")
        self.assertEqual(self.runtime.status()["state"], "failed")

    def test_non_windows_start_is_blocked(self):
        runtime = ControllerRuntime(
            app_dir=self.app, data_dir=self.data / "nonwin",
            runner_path=self.runner, bridge_path=self.bridge, platform="linux",
        )
        runtime.save_game_profile("game", "xbox-360-wired", 0, True)
        with self.assertRaisesRegex(RuntimeError, "Windows 10/11"):
            runtime.start_for_game("game")


if __name__ == "__main__":
    unittest.main()
