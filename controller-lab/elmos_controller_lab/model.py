"""Canonical controller state shared by physical inputs, mappings and virtual outputs."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any

BUTTONS = (
    "south", "east", "west", "north",
    "left_shoulder", "right_shoulder",
    "back", "start", "guide",
    "left_stick", "right_stick",
    "touchpad_click", "share", "misc1",
    "left_paddle", "right_paddle", "left_paddle2", "right_paddle2",
)
DPAD = ("up", "right", "down", "left")
AXES = ("left_x", "left_y", "right_x", "right_y", "left_trigger", "right_trigger")


def clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            return default
        return max(low, min(high, result))
    except (TypeError, ValueError, OverflowError):
        return default


@dataclass(frozen=True)
class TouchContact:
    active: bool = False
    x: float = 0.0
    y: float = 0.0
    pressure: float = 0.0
    tracking_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": bool(self.active),
            "x": int(clamp(self.x, 0, 1919)),
            "y": int(clamp(self.y, 0, 1079)),
            "pressure": clamp(self.pressure, 0, 1),
            "tracking_id": int(clamp(self.tracking_id, 0, 127)),
        }


@dataclass(frozen=True)
class MotionState:
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "gyro_x": clamp(self.gyro_x, -4000, 4000),
            "gyro_y": clamp(self.gyro_y, -4000, 4000),
            "gyro_z": clamp(self.gyro_z, -4000, 4000),
            "accel_x": clamp(self.accel_x, -16, 16),
            "accel_y": clamp(self.accel_y, -16, 16),
            "accel_z": clamp(self.accel_z, -16, 16),
        }


@dataclass
class ControllerState:
    """Device-independent snapshot.

    Stick axes use -1..1, with positive Y meaning up. Triggers use 0..1.
    Buttons and D-pad entries use semantic names, never vendor button numbers.
    """
    device_id: str = "synthetic"
    name: str = "Synthetic Controller"
    guid: str = ""
    buttons: set[str] = field(default_factory=set)
    axes: dict[str, float] = field(default_factory=dict)
    dpad: set[str] = field(default_factory=set)
    motion: MotionState = field(default_factory=MotionState)
    touchpads: list[TouchContact] = field(default_factory=list)
    battery: float | None = None
    charging: bool = False
    timestamp: float = field(default_factory=time.monotonic)
    extra: dict[str, float] = field(default_factory=dict)

    def normalized(self) -> "ControllerState":
        buttons = {str(x) for x in self.buttons if str(x) in BUTTONS}
        dpad = {str(x) for x in self.dpad if str(x) in DPAD}
        axes: dict[str, float] = {}
        for name in AXES:
            low, high = (0.0, 1.0) if "trigger" in name else (-1.0, 1.0)
            axes[name] = clamp(self.axes.get(name, 0.0), low, high)
        extra = {str(k): clamp(v, 0.0, 1.0) for k, v in self.extra.items()}
        battery = None if self.battery is None else clamp(self.battery, 0, 100)
        return ControllerState(
            device_id=str(self.device_id),
            name=str(self.name),
            guid=str(self.guid),
            buttons=buttons,
            axes=axes,
            dpad=dpad,
            motion=self.motion,
            touchpads=list(self.touchpads[:2]),
            battery=battery,
            charging=bool(self.charging),
            timestamp=float(self.timestamp),
            extra=extra,
        )

    def to_wire(self) -> dict[str, Any]:
        state = self.normalized()
        return {
            "device_id": state.device_id,
            "name": state.name,
            "guid": state.guid,
            "buttons": sorted(state.buttons),
            "axes": state.axes,
            "dpad": sorted(state.dpad),
            "motion": state.motion.to_dict(),
            "touchpads": [p.to_dict() for p in state.touchpads],
            "battery": state.battery,
            "charging": state.charging,
            "timestamp": state.timestamp,
            "extra_axes": state.extra,
        }


def neutral_state(device_id: str = "synthetic", name: str = "Synthetic Controller") -> ControllerState:
    return ControllerState(device_id=device_id, name=name, axes={k: 0.0 for k in AXES}).normalized()
