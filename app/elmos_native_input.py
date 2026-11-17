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
import traceback

BUTTONS = {
    'a': 'XUSB_GAMEPAD_A', 'b': 'XUSB_GAMEPAD_B',
    'x': 'XUSB_GAMEPAD_X', 'y': 'XUSB_GAMEPAD_Y',
    'lb': 'XUSB_GAMEPAD_LEFT_SHOULDER',
    'rb': 'XUSB_GAMEPAD_RIGHT_SHOULDER',
    'back': 'XUSB_GAMEPAD_BACK', 'start': 'XUSB_GAMEPAD_START',
    'guide': 'XUSB_GAMEPAD_GUIDE',
    'l3': 'XUSB_GAMEPAD_LEFT_THUMB', 'r3': 'XUSB_GAMEPAD_RIGHT_THUMB',
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
        self._retry_setup = threading.Event()
        self._thread = None
        self._state = dict(running=False, connected=False, virtualConnected=False,
                           driverInstalled=False, driverState='unknown',
                           controllerDetected=False, controllerMode='none', readerError='',
                           backend='ViGEmBus / Xbox 360',
                           message='Elmos Input not started', device='',
                           stage='idle', lastError='')
    def status(self):
        with self._lock:
            return dict(self._state)
    def _publish(self, **values):
        with self._lock:
            previous = (self._state.get('stage'), self._state.get('message'),
                        self._state.get('virtualConnected'))
            self._state.update(values)
            current = (self._state.get('stage'), self._state.get('message'),
                       self._state.get('virtualConnected'))
        # Launcher redirects stdout to LocalAppData/ElmosWorld/logs/launcher.log.
        # Log only transitions, not every 10ms input frame.
        if previous != current:
            print('[Elmos Input] ' + str(current[0]) + ': ' + str(current[1]) +
                  ' | virtualConnected=' + str(current[2]), flush=True)
    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                # Start is also the user's explicit retry of driver setup.
                self._retry_setup.set()
                return self.status()
            self._stop.clear()
            self._retry_setup.set()
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
        rumble_registered = False
        try:
            if os.name != 'nt':
                self._publish(message='Xbox emulation requires Windows')
                return
            from elmos_input_driver import is_installed, install_if_missing
            self._publish(running=True, driverState='checking', stage='driver-check',
                          message='Checking ViGEmBus driver…')
            # The Elmos-owned input worker stays alive for the entire app
            # session. Initial setup happens once on startup; a failed or
            # declined UAC request can be retried from Elmos Input settings.
            while not self._stop.is_set():
                if is_installed():
                    self._publish(driverInstalled=True, driverState='installed',
                                  stage='driver-ready',
                                  message='ViGEmBus installed; connecting virtual Xbox 360 controller…')
                    break
                self._publish(driverInstalled=False)
                if self._retry_setup.is_set():
                    self._retry_setup.clear()
                    if os.environ.get('ELMOS_INPUT_DISABLE_SETUP') == '1':
                        self._publish(driverState='missing',
                                      message='ViGEmBus missing (driver setup disabled in CI)')
                    else:
                        self._publish(driverState='installing',
                                      message='ViGEmBus missing; downloading verified driver and requesting Windows UAC approval…')
                        try:
                            def on_setup_progress(stage, detail):
                                self._publish(driverState=stage, message=detail)
                            setup = install_if_missing(progress=on_setup_progress)
                            outcome = str(setup.get('status') or 'error')
                            if outcome in ('installed','already-installed') and is_installed():
                                self._publish(driverInstalled=True, driverState='installed')
                                break
                            self._publish(driverState=outcome,
                                          message='ViGEmBus setup: ' + str(setup.get('message') or outcome) +
                                                  '. Select Start Elmos Input to retry; restart Windows if requested.')
                        except Exception as exc:
                            self._publish(driverState='error',
                                          message='ViGEmBus setup failed: ' + str(exc)[:350] +
                                                  '. Select Retry Elmos Input to try again.')
                self._stop.wait(0.5)
            if self._stop.is_set():
                return
            # vgamepad creates a global ViGEmClient bus connection at import time.
            # Import it only after the bus is confirmed available.
            self._publish(stage='loading-vgamepad',
                          message='Loading bundled vgamepad ViGEmClient library…')
            try:
                import vgamepad as vg
            except Exception as exc:
                self._publish(stage='error', driverState='installed', lastError=repr(exc),
                              message='ViGEmClient initialization failed: ' + str(exc)[:250])
                traceback.print_exc()
                return
            self._publish(stage='vgamepad-loaded', message='ViGEmClient library loaded successfully')
            # Another mapper can fight over the same physical device or create double input.
            # Never terminate or modify a separately started program.
            from subprocess import run, CREATE_NO_WINDOW
            try:
                result = run(['tasklist.exe', '/FI', 'IMAGENAME eq DS4Windows.exe', '/NH'],
                             capture_output=True, text=True, timeout=4,
                             creationflags=CREATE_NO_WINDOW)
            except Exception as exc:
                self._publish(stage='error', lastError=repr(exc),
                              message='Cannot check for conflicting DS4Windows process: ' + str(exc)[:170])
                traceback.print_exc()
                return
            if 'ds4windows.exe' in result.stdout.lower():
                self._publish(stage='conflicting-mapper',
                              message='Close DS4Windows.exe before enabling Elmos Input.')
                return
            # Create the XInput target FIRST, independently of the physical
            # controller mapping. Previously an SDL raw joystick prevented any
            # Xbox 360 device from appearing in joy.cpl.
            self._publish(stage='creating-xbox',
                          message='Creating a virtual Xbox 360 gamepad through ViGEmBus…')
            pad = vg.VX360Gamepad()
            # An XInput device must remain active even if optional vibration
            # feedback cannot be registered by this particular Windows stack.
            pad.reset()
            pad.update()
            self._publish(stage='xbox-created', running=True, virtualConnected=True,
                          message='Virtual Xbox 360 controller created; waiting for DualShock input')
            def on_rumble(client, target, large_motor, small_motor, led, user_data):
                try:
                    self.source.queue_rumble(large_motor / 255, small_motor / 255)
                except Exception:
                    pass
            try:
                pad.register_notification(callback_function=on_rumble)
                rumble_registered = True
            except Exception as exc:
                # Rumble is optional: no vibration support must never make
                # the virtual Xbox controller disappear from Windows.
                print('[Elmos Input] Optional rumble registration failed: ' + repr(exc), flush=True)
            last_neutral = True
            while not self._stop.is_set():
                source = self.source.snapshot()
                frame = frame_from_snapshot(source)
                detected = bool(source.get('connected'))
                mode = str(source.get('mode') or 'none')
                reader_error = str(source.get('error') or '')[:220]
                if frame is None:
                    if not last_neutral:
                        try: self.source.queue_rumble(0, 0)
                        except Exception: pass
                        pad.reset()
                        pad.update()
                        last_neutral = True
                    if detected and mode != 'mapped SDL':
                        message = 'Xbox 360 virtual device is ready, but your DS4 is only detected as a raw SDL joystick; controller mapping is required'
                    elif detected:
                        message = 'Xbox 360 virtual device is ready; input reader did not identify a Sony controller'
                    elif reader_error:
                        message = 'Xbox 360 virtual device is ready; ' + reader_error
                    else:
                        message = 'Xbox 360 virtual device is ready; waiting for DualShock 4'
                    self._publish(connected=False, running=True, virtualConnected=True,
                                  controllerDetected=detected, controllerMode=mode,
                                  readerError=reader_error, message=message, device='')
                    self._stop.wait(0.04)
                    continue
                apply_frame(pad, vg, frame)
                last_neutral = False
                self._publish(stage='forwarding-input', connected=True, running=True, virtualConnected=True,
                              controllerDetected=True, controllerMode=mode,
                              readerError=reader_error,
                              message='Elmos Input is sending Xbox 360 controller reports',
                              device=frame['name'])
                self._stop.wait(0.01)
        except Exception as exc:
            self._publish(stage='error', lastError=repr(exc),
                          message='Xbox 360 bridge error: ' + str(exc)[:250], connected=False)
            traceback.print_exc()
        finally:
            if pad is not None:
                try:
                    self.source.queue_rumble(0, 0)
                    if rumble_registered:
                        pad.unregister_notification()
                    pad.reset()
                    pad.update()
                    del pad
                except Exception:
                    pass
            self._publish(running=False, connected=False, virtualConnected=False,
                          stage='stopped' if self._stop.is_set() else self._state.get('stage'))

from controller_input import monitor
native_input = NativeInput(monitor)
