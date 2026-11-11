"""Steam Input-inspired per-device mappings, stick shaping and action layers."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from .actions import TemporalActionEngine, radial_action_frame
from .model import AXES, BUTTONS, ControllerState, clamp
from .mouse_motion import MouseDeltaAccumulator


@dataclass
class StickTuning:
    deadzone: float = 0.12
    outer_deadzone: float = 0.0
    anti_deadzone: float = 0.0
    exponent: float = 1.0
    sensitivity: float = 1.0
    invert_x: bool = False
    invert_y: bool = False

    def validate(self) -> None:
        self.deadzone = clamp(self.deadzone, 0.0, 0.95, 0.12)
        self.outer_deadzone = clamp(self.outer_deadzone, 0.0, 0.5)
        self.anti_deadzone = clamp(self.anti_deadzone, 0.0, 0.5)
        self.exponent = clamp(self.exponent, 0.2, 4.0, 1.0)
        self.sensitivity = clamp(self.sensitivity, 0.05, 4.0, 1.0)


@dataclass
class ActionLayer:
    """A hold or toggle layer, activated by a physical semantic button."""
    activator: str = "left_paddle"
    mode: str = "hold"  # hold | toggle
    button_map: dict[str, str] = field(default_factory=dict)
    keyboard_map: dict[str, list[str]] = field(default_factory=dict)
    mouse_map: dict[str, str] = field(default_factory=dict)
    axis_sensitivity: float = 1.0
    left_stick_as_wasd: bool | None = None
    right_stick_mouse: bool | None = None
    mouse_sensitivity: float | None = None
    touchpad_mode: str | None = None
    touchpad_sensitivity: float | None = None
    action_bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    chord_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    gyro_mode: str | None = None
    gyro_sensitivity: float | None = None
    gyro_deadzone: float | None = None
    radial_menus: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class MappingProfile:
    name: str = "Default"
    button_map: dict[str, str | None] = field(default_factory=dict)
    dpad_map: dict[str, str | None] = field(default_factory=dict)
    left_stick: StickTuning = field(default_factory=StickTuning)
    right_stick: StickTuning = field(default_factory=StickTuning)
    trigger_deadzone: float = 0.02
    trigger_exponent: float = 1.0
    trigger_key_threshold: float = 0.55
    keyboard_map: dict[str, list[str]] = field(default_factory=dict)
    trigger_keyboard_map: dict[str, list[str]] = field(default_factory=dict)
    mouse_map: dict[str, str] = field(default_factory=dict)
    left_stick_as_wasd: bool = False
    right_stick_mouse: bool = False
    mouse_sensitivity: float = 14.0
    mouse_deadzone: float = 0.15
    touchpad_mode: str = "off"  # off | mouse | right_stick
    touchpad_sensitivity: float = 1.0
    action_bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    chord_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    gyro_mode: str = "off"  # off | mouse | right_stick
    gyro_sensitivity: float = 10.0
    gyro_deadzone: float = 0.8
    radial_menus: dict[str, dict[str, Any]] = field(default_factory=dict)
    layer: ActionLayer | None = None


def shape_stick(x: float, y: float, tuning: StickTuning) -> tuple[float, float]:
    """Radial deadzone + outer range + anti-deadzone + response curve."""
    tuning.validate()
    x = clamp(x, -1, 1)
    y = clamp(y, -1, 1)
    if tuning.invert_x:
        x = -x
    if tuning.invert_y:
        y = -y
    radius = math.hypot(x, y)
    if radius <= tuning.deadzone or radius == 0:
        return 0.0, 0.0
    direction_x, direction_y = x / radius, y / radius
    usable = max(1e-6, 1.0 - tuning.deadzone)
    magnitude = min(1.0, max(0.0, (radius - tuning.deadzone) / usable))
    if tuning.outer_deadzone:
        magnitude = min(1.0, magnitude / (1.0 - tuning.outer_deadzone))
    magnitude = magnitude ** tuning.exponent
    magnitude = min(1.0, magnitude * tuning.sensitivity)
    if tuning.anti_deadzone:
        magnitude = tuning.anti_deadzone + (1.0 - tuning.anti_deadzone) * magnitude
    return (
        clamp(direction_x * magnitude, -1, 1),
        clamp(direction_y * magnitude, -1, 1),
    )


@dataclass
class MappedOutput:
    gamepad: ControllerState
    keyboard_keys: set[str] = field(default_factory=set)
    keyboard_modifiers: set[str] = field(default_factory=set)
    mouse_buttons: set[str] = field(default_factory=set)
    mouse_dx: int = 0
    mouse_dy: int = 0
    mouse_wheel: int = 0
    mouse_pan: int = 0


class Mapper:
    def __init__(self, profile: MappingProfile | None = None):
        self.profile = profile or MappingProfile()
        self._layer_toggle = False
        self._last_activator = False
        self._current_layer_active = False
        self._last_touchpad: tuple[int, float, float] | None = None
        self._last_timestamp: float | None = None
        self._gyro_mouse_delta = MouseDeltaAccumulator()
        self.action_engine = TemporalActionEngine()
        self._active_action_bindings: dict[str, dict[str, Any]] = {}
        self._active_chord_map: dict[str, dict[str, Any]] = {}
        self._active_radial_menus: dict[str, dict[str, Any]] = {}
        self._radial_axes: dict[str, float] = {}

    def _is_suppressed(self, button: str) -> bool:
        binding = self._active_action_bindings.get(button)
        if isinstance(binding, dict) and binding.get("suppress", True):
            return True
        for chord, raw in self._active_chord_map.items():
            if isinstance(raw, dict) and raw.get("suppress", True):
                if button in {x.strip() for x in str(chord).split("+") if x.strip()}:
                    return True
        return False

    def map_actions(self, source: ControllerState) -> MappedOutput:
        """Map a physical snapshot to gamepad, virtual keyboard and virtual mouse outputs."""
        normalized = source.normalized()
        gamepad = self.map(normalized)
        p = self.profile
        layer = p.layer
        layer_active = self._current_layer_active
        keyboard_map = dict(p.keyboard_map)
        mouse_map = dict(p.mouse_map)
        if layer and layer_active:
            keyboard_map.update(layer.keyboard_map)
            mouse_map.update(layer.mouse_map)

        keys: set[str] = set()
        modifiers: set[str] = set()
        mouse_buttons: set[str] = set()
        modifier_names = {
            "leftcontrol", "leftshift", "leftalt", "leftgui",
            "rightcontrol", "rightshift", "rightalt", "rightgui",
        }

        def add_keys(values):
            if isinstance(values, str):
                values = [values]
            for value in values or ():
                name = str(value).strip()
                if not name:
                    continue
                if name.casefold() in modifier_names:
                    modifiers.add(name[0].upper() + name[1:])
                else:
                    keys.add(name[0].upper() + name[1:])

        for button in normalized.buttons:
            if layer and button == layer.activator:
                continue
            if self._is_suppressed(button):
                continue
            add_keys(keyboard_map.get(button, []))
            mouse_button = mouse_map.get(button)
            if mouse_button in ("left", "right", "middle", "back", "forward",
                                "button6", "button7", "button8", "button9", "button10"):
                mouse_buttons.add(mouse_button)

        for direction in normalized.dpad:
            add_keys(keyboard_map.get("dpad_" + direction, []))

        trigger_threshold = clamp(p.trigger_key_threshold, 0.05, 0.99, 0.55)
        for trigger in ("left_trigger", "right_trigger"):
            if normalized.axes.get(trigger, 0.0) >= trigger_threshold:
                add_keys(p.trigger_keyboard_map.get(trigger, []))
                mouse_button = mouse_map.get(trigger)
                if mouse_button in ("left", "right", "middle", "back", "forward",
                                    "button6", "button7", "button8", "button9", "button10"):
                    mouse_buttons.add(mouse_button)

        left_wasd = p.left_stick_as_wasd
        right_mouse = p.right_stick_mouse
        sensitivity = p.mouse_sensitivity
        if layer and layer_active:
            if layer.left_stick_as_wasd is not None:
                left_wasd = layer.left_stick_as_wasd
            if layer.right_stick_mouse is not None:
                right_mouse = layer.right_stick_mouse
            if layer.mouse_sensitivity is not None:
                sensitivity = layer.mouse_sensitivity

        if left_wasd:
            lx, ly = gamepad.axes["left_x"], gamepad.axes["left_y"]
            threshold = 0.45
            if ly >= threshold: add_keys(["W"])
            if ly <= -threshold: add_keys(["S"])
            if lx <= -threshold: add_keys(["A"])
            if lx >= threshold: add_keys(["D"])

        mouse_dx = mouse_dy = 0
        if right_mouse:
            rx, ry = gamepad.axes["right_x"], gamepad.axes["right_y"]
            deadzone = clamp(p.mouse_deadzone, 0.0, 0.95, 0.15)
            radius = math.hypot(rx, ry)
            if radius > deadzone:
                scale = min(1.0, (radius - deadzone) / max(1e-6, 1.0 - deadzone))
                sensitivity = clamp(sensitivity, 0.1, 500.0, 14.0)
                mouse_dx = int(round((rx / radius) * scale * sensitivity))
                mouse_dy = int(round((-ry / radius) * scale * sensitivity))

        touchpad_mode = p.touchpad_mode
        touchpad_sensitivity = p.touchpad_sensitivity
        if layer and layer_active:
            if layer.touchpad_mode is not None:
                touchpad_mode = layer.touchpad_mode
            if layer.touchpad_sensitivity is not None:
                touchpad_sensitivity = layer.touchpad_sensitivity
        touchpad_sensitivity = clamp(touchpad_sensitivity, 0.01, 10.0, 1.0)
        if touchpad_mode == "right_stick":
            contact = next((item for item in normalized.touchpads if item.active), None)
            if contact is None:
                gamepad.axes["right_x"] = 0.0
                gamepad.axes["right_y"] = 0.0
            else:
                tx = clamp((contact.x - 960.0) / 960.0, -1.0, 1.0)
                ty = clamp((540.0 - contact.y) / 540.0, -1.0, 1.0)
                gamepad.axes["right_x"], gamepad.axes["right_y"] = shape_stick(
                    tx, ty, p.right_stick
                )
            self._last_touchpad = None
        elif touchpad_mode == "mouse":
            contact = next((item for item in normalized.touchpads if item.active), None)
            if contact is None:
                self._last_touchpad = None
            else:
                current = (contact.tracking_id, contact.x, contact.y)
                if self._last_touchpad is not None and self._last_touchpad[0] == contact.tracking_id:
                    mouse_dx += int(round((contact.x - self._last_touchpad[1]) * touchpad_sensitivity))
                    mouse_dy += int(round((contact.y - self._last_touchpad[2]) * touchpad_sensitivity))
                self._last_touchpad = current
        else:
            self._last_touchpad = None

        gyro_mode = p.gyro_mode
        gyro_sensitivity = p.gyro_sensitivity
        gyro_deadzone = p.gyro_deadzone
        if layer and layer_active:
            if layer.gyro_mode is not None:
                gyro_mode = layer.gyro_mode
            if layer.gyro_sensitivity is not None:
                gyro_sensitivity = layer.gyro_sensitivity
            if layer.gyro_deadzone is not None:
                gyro_deadzone = layer.gyro_deadzone
        dt = (1.0 / 120.0 if self._last_timestamp is None else
              clamp(normalized.timestamp - self._last_timestamp, 0.001, 0.05, 1.0 / 120.0))
        self._last_timestamp = normalized.timestamp
        gyro_sensitivity = clamp(gyro_sensitivity, 0.01, 100.0, 10.0)
        gyro_deadzone = clamp(gyro_deadzone, 0.0, 50.0, 0.8)
        gyro_pitch = normalized.motion.gyro_x
        gyro_yaw = normalized.motion.gyro_y
        if abs(gyro_pitch) < gyro_deadzone:
            gyro_pitch = 0.0
        if abs(gyro_yaw) < gyro_deadzone:
            gyro_yaw = 0.0
        if gyro_mode == "mouse":
            gx, gy = self._gyro_mouse_delta.consume(
                gyro_yaw * dt * gyro_sensitivity,
                -gyro_pitch * dt * gyro_sensitivity,
            )
            mouse_dx += gx
            mouse_dy += gy
        elif gyro_mode == "right_stick":
            self._gyro_mouse_delta.reset()
            gain = gyro_sensitivity / 10.0
            gx = clamp(gyro_yaw / 200.0 * gain, -1.0, 1.0)
            gy = clamp(-gyro_pitch / 200.0 * gain, -1.0, 1.0)
            gamepad.axes["right_x"], gamepad.axes["right_y"] = shape_stick(gx, gy, p.right_stick)
        else:
            self._gyro_mouse_delta.reset()

        temporal = self.action_engine.process(
            normalized.buttons, self._active_action_bindings,
            self._active_chord_map, normalized.timestamp
        )
        for stick, config in self._active_radial_menus.items():
            temporal.merge(radial_action_frame(stick, self._radial_axes, config))
        gamepad.buttons.update(temporal.gamepad_buttons)
        keys.update(temporal.keyboard_keys)
        modifiers.update(temporal.keyboard_modifiers)
        mouse_buttons.update(temporal.mouse_buttons)

        return MappedOutput(
            gamepad=gamepad,
            keyboard_keys=keys,
            keyboard_modifiers=modifiers,
            mouse_buttons=mouse_buttons,
            mouse_dx=mouse_dx,
            mouse_dy=mouse_dy,
        )

    def map(self, source: ControllerState) -> ControllerState:
        p = self.profile
        source = source.normalized()
        layer_active = False
        layer = p.layer
        if layer:
            pressed = layer.activator in source.buttons
            if layer.mode == "toggle" and pressed and not self._last_activator:
                self._layer_toggle = not self._layer_toggle
            layer_active = self._layer_toggle if layer.mode == "toggle" else pressed
            self._last_activator = pressed
        self._current_layer_active = layer_active
        self._active_action_bindings = dict(p.action_bindings)
        self._active_chord_map = dict(p.chord_map)
        self._active_radial_menus = dict(p.radial_menus)
        if layer and layer_active:
            self._active_action_bindings.update(layer.action_bindings)
            self._active_chord_map.update(layer.chord_map)
            self._active_radial_menus.update(layer.radial_menus)

        active_button_map = dict(p.button_map)
        if layer and layer_active:
            active_button_map.update(layer.button_map)

        output_buttons: set[str] = set()
        for source_button in source.buttons:
            if layer and source_button == layer.activator:
                continue
            if self._is_suppressed(source_button):
                continue
            target = active_button_map.get(source_button, source_button)
            if target in BUTTONS:
                output_buttons.add(target)

        output_dpad: set[str] = set()
        for direction in source.dpad:
            target = p.dpad_map.get(direction, direction)
            if target in ("up", "right", "down", "left"):
                output_dpad.add(target)

        axes = dict(source.axes)
        lx, ly = shape_stick(axes.get("left_x", 0), axes.get("left_y", 0), p.left_stick)
        rx, ry = shape_stick(axes.get("right_x", 0), axes.get("right_y", 0), p.right_stick)
        layer_gain = clamp(layer.axis_sensitivity, 0.05, 4.0, 1.0) if layer and layer_active else 1.0
        axes["left_x"], axes["left_y"] = clamp(lx * layer_gain, -1, 1), clamp(ly * layer_gain, -1, 1)
        axes["right_x"], axes["right_y"] = clamp(rx * layer_gain, -1, 1), clamp(ry * layer_gain, -1, 1)
        trigger_deadzone = clamp(p.trigger_deadzone, 0.0, 0.95, 0.02)
        trigger_exponent = clamp(p.trigger_exponent, 0.2, 4.0, 1.0)
        for name in ("left_trigger", "right_trigger"):
            value = clamp(axes.get(name, 0), 0, 1)
            if value <= trigger_deadzone:
                value = 0.0
            else:
                value = ((value - trigger_deadzone) / (1.0 - trigger_deadzone)) ** trigger_exponent
            axes[name] = clamp(value, 0, 1)

        self._radial_axes = {key: axes.get(key, 0.0) for key in
                             ("left_x", "left_y", "right_x", "right_y")}
        for stick, config in self._active_radial_menus.items():
            if isinstance(config, dict) and config.get("suppress", True):
                axes[stick.replace("_stick", "_x")] = 0.0
                axes[stick.replace("_stick", "_y")] = 0.0

        return ControllerState(
            device_id=source.device_id,
            name=source.name,
            guid=source.guid,
            buttons=output_buttons,
            axes=axes,
            dpad=output_dpad,
            motion=source.motion,
            touchpads=source.touchpads,
            battery=source.battery,
            charging=source.charging,
            battery_full=source.battery_full,
            mic_muted=source.mic_muted,
            headphones_connected=source.headphones_connected,
            touchpad_packet_counter=source.touchpad_packet_counter,
            sensor_timestamp=source.sensor_timestamp,
            timestamp=source.timestamp,
            extra=source.extra,
        ).normalized()


def default_profile() -> MappingProfile:
    return MappingProfile()
