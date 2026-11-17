"""Elmos Input: native DualShock -> ViGEmBus Xbox 360 emulation.

No DS4Windows executable or profile is used. vgamepad is an open-source
ViGEmClient binding; the signed ViGEmBus kernel driver is still a dependency.
The SDL input monitor owns physical controller reads; this engine only converts
its normalized snapshots into Xbox 360 reports and owns the virtual device.
"""
from __future__ import annotations
import os
import threading
import time

BUTTONS = {
    'a': 'XUSB_GAMEPAD_A', 'b': 'XUSB_GAMEPAD_B',
    'x': 'XUSB_GAMEPAD_X', 'y': 'XUSB_GAMEPAD_Y',
    'lb': 'XUSB_GAMEPAD_LEFT_SHOULDER',
    'rb': 'XUSB_GAMEPAD_RIGHT_SHOULDER',
    'back': 'XUSB_GAMEPAD_BACK', 'start': 'XUSB_GAMEPAD_START',
    'guide': 'XUSB_GAMEPAD_GUIDE',
    'up': 'XUSB_GAMEPAD_DPAD_UP', 'down': 'XUSB_GAMEPAD_DPAD_DOWN',
    'left': 'XUSB_GAMEPAD_DPAD_LEFT', 'right': 'XUSB_GAMEPAD_DPAD_RIGHT',
}

def clamp(value, low, high):
    try:
        return max(low, min(high, float(value)))
    except (ValueError, TypeError):
        return 0.0

def frame_from_snapshot(snapshot):
    """Pure, testable Sony SDL -> Xbox 360 semantic mapping."""
    if not snapshot.get('connected') or snapshot.get('mode') != 'mapped SDL':
        return None
    # Don't inadvertently feed virtual Xbox devices back into themselves.
    name = str(snapshot.get('name') or '').lower()
    if not any(x in name for x in ('wireless controller', 'dualshock', 'dualsense', 'sony')):
        return None
    axes = snapshot.get('axes') or [0, 0, 0, 0]
    if len(axes) < 4:
        return None
    buttons = snapshot.get('buttons') or {}
    triggers = snapshot.get('triggers') or [0, 0]
    if len(triggers) != 2:
        triggers = [0, 0]
    return {
        'buttons': [value for key, value in BUTTONS.items() if buttons.get(key)],
        'axes': [clamp(v, -1, 1) for v in axes[:4]],
        'triggers': [clamp(v, 0, 1) for v in triggers],
        'name': str(snapshot.get('name') or '')[:90],
    }

def apply_frame(pad, vg, frame):
    pad.reset()
    for item in frame['buttons']:
        pad.press_button(button=getattr(vg.XUSB_BUTTON, item))
    lx, ly, rx, ry = frame['axes']
    # SDL Y+ is down; Xbox Y+ is up.
    pad.left_joystick_float(x_value_float=lx, y_value_float=-ly)
    pad.right_joystick_float(x_value_float=rx, y_value_float=-ry)
    pad.left_trigger_float(value_float=frame['triggers'][0])
    pad.right_trigger_float(value_float=frame['triggers'][1])
    pad.update()

class NativeInput:
    def __init__(self, source):
        self.source = source
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._state = dict(running=False, connected=False, backend='ViGEmBus / Xbox 360',
                           message='Elmos Input not started', device='')
    def status(self):
        with self._lock:
            return dict(self._state)
    def _publish(self, **values):
        with self._lock:
            self._state.update(values)
    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='Elmos native Xbox bridge', daemon=True)
            self._thread.start()
        return self.status()
    def stop(self, game_active=False):
        # A virtual target cannot outlive its feeder process. Do not kill games.
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.2)
        return self.status()
    def _run(self):
        pad = None
        try:
            if os.name != 'nt':
                self._publish(message='Xbox emulation requires Windows')
                return
            try:
                import vgamepad as vg
            except ImportError:
                self._publish(message='vgamepad dependency missing from Elmos World build')
                return
            from elmos_input_driver import is_installed
            if not is_installed():
                self._publish(message='ViGEmBus is not installed. Install the signed bus driver to enable Xbox 360 output.')
                return
            # Another mapper can fight over the same physical device or create double input.
            # Never terminate or modify a separately started program.
            from subprocess import run, CREATE_NO_WINDOW
            result = run(['tasklist.exe', '/FI', 'IMAGENAME eq DS4Windows.exe', '/NH'],
                         capture_output=True, text=True, timeout=4,
                         creationflags=CREATE_NO_WINDOW)
            if 'DS4Windows.exe' in result.stdout:
                self._publish(message='Close the separate DS4Windows process before enabling Elmos Input.')
                return
            while not self._stop.is_set():
                frame = frame_from_snapshot(self.source.snapshot())
                if frame is None:
                    if pad is not None:
                        pad.reset()
                        pad.update()
                        del pad
                        pad = None
                    self._publish(connected=False, running=True,
                                  message='Waiting for a mapped DualShock 4 or DualSense controller', device='')
                    self._stop.wait(0.04)
                    continue
                if pad is None:
                    pad = vg.VX360Gamepad()
                apply_frame(pad, vg, frame)
                self._publish(connected=True, running=True,
                              message='Elmos Input is sending Xbox 360 controller reports',
                              device=frame['name'])
                self._stop.wait(0.01)
        except Exception as exc:
            self._publish(message='Xbox 360 bridge error: ' + str(exc)[:220], connected=False)
        finally:
            if pad is not None:
                try:
                    pad.reset()
                    pad.update()
                    del pad
                except Exception:
                    pass
            self._publish(running=False, connected=False)

from controller_input import monitor
native_input = NativeInput(monitor)
