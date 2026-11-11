"""Platform-independent regression tests for Elmo's optional input service."""
import math
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "app"))
from elmos_input import InputManager, clamp, normalize, stick_axis


class FakeSink:
    def __init__(self):
        self.frames = []
        self.neutrals = 0
        self.closed = False

    def send(self, buttons, axes, triggers):
        self.frames.append((dict(buttons), list(axes), list(triggers)))

    def neutral(self):
        self.neutrals += 1

    def close(self):
        self.closed = True
        self.neutral()


class InputEngineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.created = []
        def make():
            sink = FakeSink()
            self.created.append(sink)
            return sink
        self.manager = InputManager(
            pathlib.Path(self.dir.name) / "input_profiles.json", factory=make
        )
        # Synthetic game PIDs do not own Windows foreground windows.
        self.manager._game_is_foreground = lambda: True

    def tearDown(self):
        self.manager.stop()
        self.dir.cleanup()

    def test_default_is_native_and_does_not_create_virtual_device(self):
        self.assertEqual(self.manager.get_mode("my-game"), "native")
        self.manager.prepare("my-game")
        self.manager.activate(101)
        self.manager.resume()
        self.manager.feed({"a": True}, [1, 0, 0, 0], [0, 0], True, True, "Wireless Controller")
        self.assertEqual(self.created, [])
        self.manager.stop_if("my-game", 101)
        self.assertFalse(self.manager.status()["running"])

    def test_mode_persistence_and_validation(self):
        self.manager.set_mode("game2", "xbox360")
        self.assertEqual(self.manager.get_mode("game2"), "xbox360")
        another = InputManager(self.manager.path, factory=FakeSink)
        self.assertEqual(another.get_mode("game2"), "xbox360")
        with self.assertRaises(ValueError):
            another.set_mode("game2", "unknown")
        self.manager.set_mode("game2", "native")
        self.assertEqual(self.manager.get_mode("game2"), "native")

    def test_inputs_stay_neutral_until_resumed(self):
        self.manager.set_mode("game", "xbox360")
        self.manager.prepare("game")
        self.manager.activate(100)
        self.manager.pause()
        sink = self.created[0]
        self.manager.feed({"a": True}, [1, 0, 0, 0], [0.3, 0], True, True, "Wireless Controller")
        self.assertEqual(sink.frames, [])
        self.manager.resume()
        self.manager.feed({"a": True}, [1, 0, 0, 0], [0.3, 0], True, True, "Wireless Controller")
        self.assertEqual(len(sink.frames), 1)
        self.manager.pause()
        self.assertGreaterEqual(sink.neutrals, 1)
        self.manager.stop_if("wrong", 100)
        self.assertTrue(self.manager.status()["running"])
        self.manager.stop_if("game", 100)
        self.assertTrue(sink.closed)

    def test_unmapped_or_disconnected_does_not_send(self):
        self.manager.set_mode("game", "xbox360")
        self.manager.prepare("game")
        self.manager.activate(55)
        self.manager.resume()
        sink = self.created[0]
        self.manager.feed({"b": True}, [0, 0, 0, 0], [0, 0], True, True, "Wireless Controller")
        self.manager.feed({"b": True}, [0, 0, 0, 0], [0, 0], True, False, "Wireless Controller")
        self.manager.feed({}, [], [], False, False, "")
        self.assertEqual(len(sink.frames), 1)
        self.assertEqual(sink.neutrals, 1)

    def test_no_virtual_controller_feedback_loop(self):
        self.manager.set_mode("game", "xbox360")
        self.manager.prepare("game")
        self.manager.activate(55)
        self.manager.resume()
        self.manager.feed({"a": True}, [0, 0, 0, 0], [0, 0], True, True, "Xbox 360 Controller")
        self.assertEqual(self.created[0].frames, [])
        self.assertIn("physical controller", self.manager.status()["error"])

    def test_watchdog_releases_stuck_button(self):
        self.manager.set_mode("game", "xbox360")
        self.manager.prepare("game")
        self.manager.activate(55)
        self.manager.resume()
        self.manager.feed({"a": True}, [0, 0, 0, 0], [0, 0], True, True, "Wireless Controller")
        time.sleep(0.48)
        self.assertGreaterEqual(self.created[0].neutrals, 1)

    def test_mode_cannot_change_during_game(self):
        self.manager.prepare("game")
        with self.assertRaises(RuntimeError):
            self.manager.set_mode("game", "xbox360")
        self.manager.stop()

    def test_math_and_button_normalization(self):
        self.assertEqual(stick_axis(0.03), 0.0)
        self.assertEqual(stick_axis(1.0), 1.0)
        self.assertEqual(stick_axis(-1.0), -1.0)
        self.assertEqual(clamp(float("nan"), -1, 1), 0.0)
        b, axes, triggers = normalize({"guide": True, "a": True}, [0.5, -0.5], [0.2, 2])
        self.assertTrue(b["a"])
        self.assertNotIn("guide", b)
        self.assertEqual(triggers, [0.2, 1.0])
        self.assertEqual(len(axes), 4)


if __name__ == "__main__":
    unittest.main()
