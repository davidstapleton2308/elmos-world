"""SDL physical-controller discovery and semantic input capture."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import ControllerState


BUTTON_CONSTANTS = {
    "south": "CONTROLLER_BUTTON_A",
    "east": "CONTROLLER_BUTTON_B",
    "west": "CONTROLLER_BUTTON_X",
    "north": "CONTROLLER_BUTTON_Y",
    "back": "CONTROLLER_BUTTON_BACK",
    "guide": "CONTROLLER_BUTTON_GUIDE",
    "start": "CONTROLLER_BUTTON_START",
    "left_stick": "CONTROLLER_BUTTON_LEFTSTICK",
    "right_stick": "CONTROLLER_BUTTON_RIGHTSTICK",
    "left_shoulder": "CONTROLLER_BUTTON_LEFTSHOULDER",
    "right_shoulder": "CONTROLLER_BUTTON_RIGHTSHOULDER",
    "up": "CONTROLLER_BUTTON_DPAD_UP",
    "right": "CONTROLLER_BUTTON_DPAD_RIGHT",
    "down": "CONTROLLER_BUTTON_DPAD_DOWN",
    "left": "CONTROLLER_BUTTON_DPAD_LEFT",
}
AXIS_CONSTANTS = {
    "left_x": "CONTROLLER_AXIS_LEFTX",
    "left_y": "CONTROLLER_AXIS_LEFTY",
    "right_x": "CONTROLLER_AXIS_RIGHTX",
    "right_y": "CONTROLLER_AXIS_RIGHTY",
    "left_trigger": "CONTROLLER_AXIS_TRIGGERLEFT",
    "right_trigger": "CONTROLLER_AXIS_TRIGGERRIGHT",
}


@dataclass
class SDLDevice:
    index: int
    instance_id: int
    guid: str
    name: str
    mapped: bool
    joystick: Any
    controller: Any = None
    vendor_id: int = 0
    product_id: int = 0


class SDLInputSource:
    """Reads one physical controller using SDL's standardized mapping when available.

    Unmapped devices fall back to a clearly marked raw layout. That layout is
    editable later in the lab; it is never presented as a guaranteed mapping.
    """
    def __init__(self):
        import pygame
        from pygame._sdl2 import controller
        self.pygame = pygame
        self.controller_api = controller
        self.devices: list[SDLDevice] = []
        self.refresh()

    def refresh(self) -> list[dict[str, Any]]:
        pygame = self.pygame
        for old in self.devices:
            try:
                if old.controller:
                    old.controller.quit()
            except Exception:
                pass
            try:
                old.joystick.quit()
            except Exception:
                pass
        self.devices = []
        pygame.init()
        pygame.joystick.init()
        try:
            self.controller_api.init()
        except Exception:
            pass
        pygame.event.pump()
        found: list[SDLDevice] = []
        for index in range(pygame.joystick.get_count()):
            try:
                joystick = pygame.joystick.Joystick(index)
                joystick.init()
                mapped = bool(self.controller_api.is_controller(index))
                ctl = None
                if mapped:
                    try:
                        ctl = self.controller_api.Controller(index)
                    except Exception:
                        mapped = False
                found.append(SDLDevice(
                    index=index,
                    instance_id=int(joystick.get_instance_id()),
                    guid=str(joystick.get_guid()),
                    name=str(joystick.get_name()),
                    mapped=mapped,
                    joystick=joystick,
                    controller=ctl,
                    vendor_id=int(getattr(joystick, "get_vendor", lambda: 0)() or 0),
                    product_id=int(getattr(joystick, "get_product", lambda: 0)() or 0),
                ))
            except Exception:
                continue
        self.devices = found
        return self.list_devices()

    def list_devices(self) -> list[dict[str, Any]]:
        return [{
            "index": d.index, "instance_id": d.instance_id, "guid": d.guid,
            "name": d.name, "mapped": d.mapped,
            "vendor_id": d.vendor_id, "product_id": d.product_id,
            "axes": d.joystick.get_numaxes(), "buttons": d.joystick.get_numbuttons(),
            "hats": d.joystick.get_numhats(),
        } for d in self.devices]

    @staticmethod
    def _constant(pygame: Any, controller_api: Any, name: str, fallback: int) -> int:
        return int(getattr(pygame, name, getattr(controller_api, name, fallback)))

    def read(self, index: int) -> ControllerState:
        self.pygame.event.pump()
        device = next((d for d in self.devices if d.index == index), None)
        if device is None:
            self.refresh()
            device = next((d for d in self.devices if d.index == index), None)
        if device is None:
            raise RuntimeError(f"Controller index {index} is no longer connected.")
        return self._read_device(device)

    def read_instance(self, instance_id: int) -> ControllerState:
        self.pygame.event.pump()
        device = next((d for d in self.devices if d.instance_id == instance_id), None)
        if device is None:
            self.refresh()
            device = next((d for d in self.devices if d.instance_id == instance_id), None)
        if device is None:
            raise RuntimeError(f"Controller instance {instance_id} is no longer connected.")
        return self._read_device(device)

    def _read_device(self, device: SDLDevice) -> ControllerState:
        pygame, api, joy, ctl = self.pygame, self.controller_api, device.joystick, device.controller
        buttons: set[str] = set()
        dpad: set[str] = set()
        axes = {"left_x": 0.0, "left_y": 0.0, "right_x": 0.0, "right_y": 0.0,
                "left_trigger": 0.0, "right_trigger": 0.0}
        if device.mapped and ctl is not None:
            for semantic, constant in BUTTON_CONSTANTS.items():
                code = self._constant(pygame, api, constant, -1)
                if code >= 0 and ctl.get_button(code):
                    if semantic in ("up", "right", "down", "left"):
                        dpad.add(semantic)
                    else:
                        buttons.add(semantic)
            for semantic, constant in AXIS_CONSTANTS.items():
                code = self._constant(pygame, api, constant, -1)
                if code < 0:
                    continue
                raw = float(ctl.get_axis(code)) / 32767.0
                if semantic in ("left_y", "right_y"):
                    raw = -raw  # Canonical convention: up is positive.
                if semantic.endswith("trigger"):
                    raw = max(0.0, min(1.0, raw))
                else:
                    raw = max(-1.0, min(1.0, raw))
                axes[semantic] = raw
        else:
            raw_axes = [float(joy.get_axis(i)) for i in range(min(joy.get_numaxes(), 16))]
            if raw_axes:
                axes["left_x"] = max(-1.0, min(1.0, raw_axes[0]))
            if len(raw_axes) > 1:
                axes["left_y"] = max(-1.0, min(1.0, -raw_axes[1]))
            if len(raw_axes) > 2:
                axes["right_x"] = max(-1.0, min(1.0, raw_axes[2]))
            if len(raw_axes) > 3:
                axes["right_y"] = max(-1.0, min(1.0, -raw_axes[3]))
            if len(raw_axes) > 4:
                axes["left_trigger"] = max(0.0, min(1.0, (raw_axes[4] + 1.0) * 0.5))
            if len(raw_axes) > 5:
                axes["right_trigger"] = max(0.0, min(1.0, (raw_axes[5] + 1.0) * 0.5))
            # Familiar raw fallback for common PlayStation and generic pads.
            raw_map = {
                "south": 0, "east": 1, "west": 2, "north": 3,
                "left_shoulder": 4, "right_shoulder": 5,
                "back": 8, "start": 9, "guide": 10,
            }
            for semantic, button_index in raw_map.items():
                if button_index < joy.get_numbuttons() and joy.get_button(button_index):
                    buttons.add(semantic)
            for hat_index in range(min(joy.get_numhats(), 4)):
                hx, hy = joy.get_hat(hat_index)
                if hy > 0: dpad.add("up")
                if hy < 0: dpad.add("down")
                if hx < 0: dpad.add("left")
                if hx > 0: dpad.add("right")
        return ControllerState(
            device_id=str(device.instance_id), name=device.name, guid=device.guid,
            buttons=buttons, axes=axes, dpad=dpad,
        ).normalized()

    def close(self) -> None:
        for device in self.devices:
            try:
                if device.controller:
                    device.controller.quit()
            except Exception:
                pass
            try:
                device.joystick.quit()
            except Exception:
                pass
        try:
            self.pygame.quit()
        except Exception:
            pass
