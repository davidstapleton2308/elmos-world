"""Steam Input-inspired per-device mappings, stick shaping and action layers."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping

from .model import AXES, BUTTONS, ControllerState, clamp


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
    axis_sensitivity: float = 1.0


@dataclass
class MappingProfile:
    name: str = "Default"
    button_map: dict[str, str | None] = field(default_factory=dict)
    dpad_map: dict[str, str | None] = field(default_factory=dict)
    left_stick: StickTuning = field(default_factory=StickTuning)
    right_stick: StickTuning = field(default_factory=StickTuning)
    trigger_deadzone: float = 0.02
    trigger_exponent: float = 1.0
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


class Mapper:
    def __init__(self, profile: MappingProfile | None = None):
        self.profile = profile or MappingProfile()
        self._layer_toggle = False
        self._last_activator = False

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

        active_button_map = dict(p.button_map)
        if layer and layer_active:
            active_button_map.update(layer.button_map)

        output_buttons: set[str] = set()
        for source_button in source.buttons:
            if layer and source_button == layer.activator:
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
            timestamp=source.timestamp,
            extra=source.extra,
        ).normalized()


def default_profile() -> MappingProfile:
    return MappingProfile()
