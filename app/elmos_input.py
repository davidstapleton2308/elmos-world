"""Elmo's Input: opt-in per-game gamepad translation.

Steam Input *inspired*, not Valve code. Direct PlayStation -> virtual Xbox 360
for games requiring XInput. Native input is the default. Never installs
drivers, hides devices, intercepts keys, or injects into unrelated programs.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

MODES = ("native", "xbox360")
BUTTONS = {
    "a": "XUSB_GAMEPAD_A", "b": "XUSB_GAMEPAD_B",
    "x": "XUSB_GAMEPAD_X", "y": "XUSB_GAMEPAD_Y",
    "lb": "XUSB_GAMEPAD_LEFT_SHOULDER", "rb": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "back": "XUSB_GAMEPAD_BACK", "start": "XUSB_GAMEPAD_START",
    "ls": "XUSB_GAMEPAD_LEFT_THUMB", "rs": "XUSB_GAMEPAD_RIGHT_THUMB",
    "up": "XUSB_GAMEPAD_DPAD_UP", "down": "XUSB_GAMEPAD_DPAD_DOWN",
    "left": "XUSB_GAMEPAD_DPAD_LEFT", "right": "XUSB_GAMEPAD_DPAD_RIGHT",
}
FACE_BUTTONS = ("a", "b", "x", "y")


def apply_bindings(buttons, bindings):
    """Map physical gamepad buttons to virtual outputs, with OR for duplicates."""
    source = buttons or {}
    layout = bindings or {}
    result = {k: False for k in BUTTONS}
    for physical in BUTTONS:
        destination = layout.get(physical, physical)
        if destination not in BUTTONS:
            destination = physical
        result[destination] |= bool(source.get(physical, False))
    return result


DEFAULT_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ElmosWorld" / "input_profiles.json"


def clamp(value, low, high):
    try:
        number = float(value)
        if number != number:  # NaN
            return 0.0
        return max(low, min(high, number))
    except (ValueError, TypeError, OverflowError):
        return 0.0


def stick_axis(value, deadzone=0.12):
    """Calibrate noisy SDL stick readings while retaining full output range."""
    n = clamp(value, -1.0, 1.0)
    a = abs(n)
    if a <= deadzone:
        return 0.0
    return (1.0 if n > 0 else -1.0) * min(1.0, (a - deadzone) / (1.0 - deadzone))


def normalize(buttons, axes, triggers):
    """Pure conversion that can be tested without Windows or a controller."""
    axes = list(axes or ())
    triggers = list(triggers or ())
    a = [stick_axis(axes[i]) if i < len(axes) else 0.0 for i in range(4)]
    t = [clamp(triggers[i], 0.0, 1.0) if i < len(triggers) else 0.0 for i in range(2)]
    b = {name: bool((buttons or {}).get(name, False)) for name in BUTTONS}
    # The PS/Guide button is reserved for Elmo's in-game menu, not forwarded.
    return b, a, t


class Xbox360Sink:
    """Optional vgamepad adapter; ViGEmBus must already be installed.

    Constructed only after an explicit per-game opt-in. Packaging the Python
    binding does not grant permission to install a system driver.
    """
    def __init__(self):
        try:
            import vgamepad as vg
            self.vg = vg
            self.pad = vg.VX360Gamepad()
            self.neutral()
        except Exception as exc:
            raise RuntimeError(
                "Virtual Xbox is unavailable. An existing compatible ViGEmBus "
                "driver is required. No driver was installed or changed. "
                "Details: " + str(exc)[:220]
            ) from exc

    def send(self, buttons, axes, triggers):
        b, a, t = normalize(buttons, axes, triggers)
        pad = self.pad
        vg = self.vg
        pad.reset()
        for key, constant in BUTTONS.items():
            if b[key]:
                pad.press_button(button=getattr(vg.XUSB_BUTTON, constant))
        # SDL stick Y grows downward; Xbox XInput stick Y grows upward.
        pad.left_joystick_float(x_value_float=a[0], y_value_float=-a[1])
        pad.right_joystick_float(x_value_float=a[2], y_value_float=-a[3])
        pad.left_trigger_float(t[0])
        pad.right_trigger_float(t[1])
        pad.update()

    def neutral(self):
        self.pad.reset()
        self.pad.update()

    def close(self):
        try:
            self.neutral()
        finally:
            # Releasing the wrapper removes this session's virtual controller.
            self.pad = None


class InputManager:
    """Only one tracked game may own a translated controller at a time."""
    def __init__(self, path=DEFAULT_PATH, factory=Xbox360Sink):
        self.path = Path(path)
        self.factory = factory
        self.lock = threading.RLock()
        self.modes = self._load()
        self.bindings = self._load_bindings()
        self.game_id = None
        self.pid = None
        self.sink = None
        self.active_mode = "native"
        self.paused = True
        self.error = ""
        self.last_feed = 0.0
        self.last_neutral = True
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True, name="Elmos input watchdog")
        self._watchdog.start()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            games = data.get("games", {})
            return {k: v for k, v in games.items()
                    if isinstance(k, str) and isinstance(v, str) and v in MODES} if isinstance(games, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _load_bindings(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            records = data.get("buttonBindings", {}) if isinstance(data, dict) else {}
            if not isinstance(records, dict):
                return {}
            return {game: {k: v for k, v in profile.items() if k in BUTTONS and v in BUTTONS}
                    for game, profile in records.items()
                    if isinstance(game, str) and isinstance(profile, dict)}
        except (OSError, ValueError, TypeError):
            return {}

    def get_mode(self, game_id):
        with self.lock:
            return self.modes.get(game_id, "native")

    def set_mode(self, game_id, mode):
        return self.set_profile(game_id, mode, None)

    def set_profile(self, game_id, mode, bindings=None):
        if not isinstance(game_id, str) or not game_id or len(game_id) > 512:
            raise ValueError("Select a valid library game.")
        if mode not in MODES:
            raise ValueError("Unknown input mode.")
        if bindings is not None:
            if not isinstance(bindings, dict) or any(k not in BUTTONS or v not in BUTTONS
                                                        for k, v in bindings.items()):
                raise ValueError("Invalid gamepad button layout.")
        with self.lock:
            if self.game_id is not None:
                raise RuntimeError("Finish the active game before changing controller output.")
            new_modes = dict(self.modes)
            new_bindings = dict(self.bindings)
            if mode == "native":
                new_modes.pop(game_id, None)
            else:
                new_modes[game_id] = mode
            if bindings is not None:
                custom = {key: value for key, value in bindings.items() if key != value}
                if custom:
                    new_bindings[game_id] = custom
                else:
                    new_bindings.pop(game_id, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"schema": 2, "games": new_modes,
                                              "buttonBindings": new_bindings}, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
            self.modes = new_modes
            self.bindings = new_bindings
            return {"ok": True, "id": game_id, "mode": mode,
                    "bindings": dict(new_bindings.get(game_id, {}))}

    def status(self, game_id=""):
        with self.lock:
            return {
                "mode": self.modes.get(game_id, "native"),
                "bindings": dict(self.bindings.get(game_id, {})),
                "modes": list(MODES),
                "running": self.game_id is not None,
                "activeGameId": self.game_id,
                "activeMode": self.active_mode,
                "virtualConnected": self.sink is not None,
                "paused": self.paused,
                "error": self.error,
                "driverNote": "Xbox mode requires an existing ViGEmBus driver and may need HidHide to prevent double input.",
            }

    def prepare(self, game_id):
        """Create optional virtual hardware before spawning the game."""
        with self.lock:
            if self.game_id is not None:
                raise RuntimeError("An input session is already active.")
            mode = self.modes.get(game_id, "native")
            self.error = ""
            sink = None
            if mode == "xbox360":
                try:
                    sink = self.factory()
                except Exception as exc:
                    self.error = str(exc)[:300]
                    raise
            self.game_id = game_id
            self.active_mode = mode
            self.pid = None
            self.sink = sink
            self.paused = True  # Don't send inputs into the library while launching.
            self.last_neutral = True
            self.last_feed = time.monotonic()
            return mode

    def activate(self, pid):
        with self.lock:
            if self.game_id is None:
                raise RuntimeError("No prepared input session.")
            self.pid = int(pid)
            # Safe because feed also checks the actual foreground PID.
            self.paused = False

    def resume(self):
        with self.lock:
            if self.game_id is not None:
                self.paused = False
                self.last_feed = time.monotonic()

    def pause(self):
        with self.lock:
            self.paused = True
            self._neutral()

    def _neutral(self):
        if self.sink is not None and not self.last_neutral:
            self.sink.neutral()
        self.last_neutral = True

    def _game_is_foreground(self):
        if os.name != 'nt' or self.pid is None:
            return True
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.argtypes = []
            user32.GetForegroundWindow.restype = ctypes.c_void_p
            user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            owner = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            return owner.value == self.pid
        except Exception:
            return False

    def feed(self, buttons, axes, triggers, connected, mapped, source_name=""):
        """SDL monitor callback. Never let translation faults kill the reader."""
        with self.lock:
            if self.sink is None:
                return
            self.last_feed = time.monotonic()
            if self.paused or not connected or not mapped or not self._game_is_foreground():
                try:
                    self._neutral()
                except Exception as exc:
                    self.error = str(exc)[:300]
                    self.stop()
                return
            # Refuse to read the new virtual Xbox controller as its own input.
            if "xbox 360" in str(source_name).lower() or "vigem" in str(source_name).lower():
                self._neutral()
                self.error = "Only a virtual Xbox was detected. Connect the physical controller."
                return
            try:
                self.sink.send(apply_bindings(buttons, self.bindings.get(self.game_id, {})), axes, triggers)
                self.last_neutral = False
            except Exception as exc:
                self.error = "Virtual Xbox input failed: " + str(exc)[:200]
                self.stop()

    def _watchdog_loop(self):
        while True:
            time.sleep(0.1)
            with self.lock:
                if self.sink is not None and not self.last_neutral and time.monotonic() - self.last_feed > 0.30:
                    try:
                        self._neutral()
                    except Exception as exc:
                        self.error = str(exc)[:300]
                        self.stop()

    def stop_if(self, game_id, pid):
        with self.lock:
            if self.game_id == game_id and self.pid == pid:
                self.stop()

    def stop(self):
        with self.lock:
            self.paused = True
            sink = self.sink
            self.sink = None
            self.game_id = None
            self.pid = None
            self.active_mode = "native"
            self.last_neutral = True
            if sink:
                try:
                    sink.close()
                except Exception as exc:
                    self.error = "Virtual controller cleanup: " + str(exc)[:200]


input_manager = InputManager()

import atexit
atexit.register(input_manager.stop)
