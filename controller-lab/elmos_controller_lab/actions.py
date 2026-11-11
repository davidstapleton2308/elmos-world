"""Temporal and chorded button actions for Steam Input-style mappings."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from .model import BUTTONS


@dataclass
class ActionFrame:
    gamepad_buttons: set[str] = field(default_factory=set)
    keyboard_keys: set[str] = field(default_factory=set)
    keyboard_modifiers: set[str] = field(default_factory=set)
    mouse_buttons: set[str] = field(default_factory=set)

    def merge(self, other: "ActionFrame") -> None:
        self.gamepad_buttons.update(other.gamepad_buttons)
        self.keyboard_keys.update(other.keyboard_keys)
        self.keyboard_modifiers.update(other.keyboard_modifiers)
        self.mouse_buttons.update(other.mouse_buttons)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value if x]
    return []


def _action_frame(spec: dict[str, Any] | None) -> ActionFrame:
    spec = spec if isinstance(spec, dict) else {}
    keys = set()
    modifiers = set()
    modifier_names = {
        "leftcontrol", "rightcontrol", "leftshift", "rightshift",
        "leftalt", "rightalt", "leftgui", "rightgui",
    }
    for key in _values(spec.get("keyboard")):
        name = key.strip()
        if not name:
            continue
        normalized = name.casefold()
        if normalized in modifier_names:
            modifiers.add(name[0].upper() + name[1:])
        else:
            keys.add(name[0].upper() + name[1:])
    valid_mouse = {"left", "right", "middle", "back", "forward",
                   "button6", "button7", "button8", "button9", "button10"}
    return ActionFrame(
        gamepad_buttons={x for x in _values(spec.get("gamepad")) if x in BUTTONS},
        keyboard_keys=keys,
        keyboard_modifiers=modifiers,
        mouse_buttons={x for x in _values(spec.get("mouse")) if x in valid_mouse},
    )


@dataclass
class _ButtonRuntime:
    was_down: bool = False
    pressed_at: float = 0.0
    last_release: float | None = None
    pending_tap_until: float | None = None
    hold_fired: bool = False
    double_active: bool = False


class TemporalActionEngine:
    """Produces momentary tap/hold/double-tap/turbo and held chord outputs."""
    def __init__(self):
        self._runtime: dict[str, _ButtonRuntime] = {}

    def process(self, buttons: set[str], bindings: dict[str, Any],
                chords: dict[str, Any], timestamp: float) -> ActionFrame:
        output = ActionFrame()
        active_buttons = set(buttons)

        for button, raw in (bindings or {}).items():
            if not isinstance(raw, dict):
                continue
            runtime = self._runtime.setdefault(button, _ButtonRuntime())
            down = button in active_buttons
            if runtime.pending_tap_until is not None and timestamp > runtime.pending_tap_until:
                output.merge(_action_frame(raw.get("tap")))
                runtime.pending_tap_until = None
            hold_ms = max(0.0, min(5000.0, float(raw.get("hold_ms", 300))))
            double_ms = max(50.0, min(1000.0, float(raw.get("double_tap_ms", 250))))
            turbo_hz = max(0.0, min(30.0, float(raw.get("turbo_hz", 0))))
            if down and not runtime.was_down:
                if (runtime.last_release is not None and
                        timestamp - runtime.last_release <= double_ms / 1000.0 and
                        raw.get("double_tap")):
                    runtime.double_active = True
                    runtime.pending_tap_until = None
                else:
                    runtime.pressed_at = timestamp
                    runtime.hold_fired = False
                    runtime.double_active = False
            if down:
                if runtime.double_active:
                    output.merge(_action_frame(raw.get("double_tap")))
                elif turbo_hz > 0 and raw.get("turbo"):
                    phase = ((timestamp - runtime.pressed_at) * turbo_hz) % 1.0
                    if phase < 0.5 - 1e-9:
                        output.merge(_action_frame(raw.get("turbo")))
                elif raw.get("hold") and timestamp - runtime.pressed_at >= hold_ms / 1000.0:
                    runtime.hold_fired = True
                    output.merge(_action_frame(raw.get("hold")))
            if not down and runtime.was_down:
                duration = timestamp - runtime.pressed_at
                if not runtime.hold_fired and not runtime.double_active:
                    if raw.get("double_tap"):
                        runtime.pending_tap_until = timestamp + double_ms / 1000.0
                    elif raw.get("tap"):
                        output.merge(_action_frame(raw.get("tap")))
                runtime.last_release = timestamp
                runtime.double_active = False
            if not down and runtime.pending_tap_until is not None:
                if timestamp > runtime.pending_tap_until:
                    output.merge(_action_frame(raw.get("tap")))
                    runtime.pending_tap_until = None
            runtime.was_down = down

        for chord, raw in (chords or {}).items():
            if not isinstance(raw, dict):
                continue
            required = {x.strip() for x in str(chord).split("+") if x.strip()}
            if required and required.issubset(active_buttons):
                output.merge(_action_frame(raw.get("action", raw)))
        return output



def radial_action_frame(stick: str, axes: dict[str, float], config: dict[str, Any]) -> ActionFrame:
    """Resolve a 4/8-way stick direction to one action while outside its deadzone."""
    if stick not in ("left_stick", "right_stick") or not isinstance(config, dict):
        return ActionFrame()
    x = float(axes.get(stick.replace("_stick", "_x"), 0.0))
    y = float(axes.get(stick.replace("_stick", "_y"), 0.0))
    radius = math.hypot(x, y)
    try:
        deadzone = max(0.0, min(0.95, float(config.get("deadzone", 0.35))))
    except (TypeError, ValueError):
        deadzone = 0.35
    if radius < deadzone or radius == 0:
        return ActionFrame()
    count = 4 if int(config.get("sectors_count", 8)) == 4 else 8
    if count == 4:
        names = ("right", "up", "left", "down")
        width = 90.0
    else:
        names = ("right", "up_right", "up", "up_left",
                 "left", "down_left", "down", "down_right")
        width = 45.0
    angle = math.degrees(math.atan2(y, x)) % 360.0
    index = int(((angle + width / 2.0) % 360.0) // width) % count
    sectors = config.get("sectors", {})
    spec = sectors.get(names[index], {}) if isinstance(sectors, dict) else {}
    return _action_frame(spec)
