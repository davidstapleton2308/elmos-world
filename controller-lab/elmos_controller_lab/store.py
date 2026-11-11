"""Per-device, per-game, per-target mapping profile persistence."""
from __future__ import annotations

from dataclasses import asdict, fields
import json
import os
from pathlib import Path
from typing import Any

from .mapping import ActionLayer, MappingProfile, StickTuning


def default_store_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    return root / "ElmosControllerLab" / "mappings.json"


def _only_known(cls: type, value: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in value.items() if k in names}


def profile_from_dict(value: dict[str, Any]) -> MappingProfile:
    left = value.get("left_stick", {})
    right = value.get("right_stick", {})
    layer_value = value.get("layer")
    layer = None
    if isinstance(layer_value, dict):
        layer = ActionLayer(**_only_known(ActionLayer, layer_value))
    return MappingProfile(
        name=str(value.get("name", "Default")),
        button_map=dict(value.get("button_map", {})) if isinstance(value.get("button_map"), dict) else {},
        dpad_map=dict(value.get("dpad_map", {})) if isinstance(value.get("dpad_map"), dict) else {},
        left_stick=StickTuning(**_only_known(StickTuning, left)) if isinstance(left, dict) else StickTuning(),
        right_stick=StickTuning(**_only_known(StickTuning, right)) if isinstance(right, dict) else StickTuning(),
        trigger_deadzone=float(value.get("trigger_deadzone", 0.02)),
        trigger_exponent=float(value.get("trigger_exponent", 1.0)),
        trigger_key_threshold=float(value.get("trigger_key_threshold", 0.55)),
        keyboard_map=dict(value.get("keyboard_map", {})) if isinstance(value.get("keyboard_map"), dict) else {},
        trigger_keyboard_map=dict(value.get("trigger_keyboard_map", {})) if isinstance(value.get("trigger_keyboard_map"), dict) else {},
        mouse_map=dict(value.get("mouse_map", {})) if isinstance(value.get("mouse_map"), dict) else {},
        left_stick_as_wasd=bool(value.get("left_stick_as_wasd", False)),
        right_stick_mouse=bool(value.get("right_stick_mouse", False)),
        mouse_sensitivity=float(value.get("mouse_sensitivity", 14.0)),
        mouse_deadzone=float(value.get("mouse_deadzone", 0.15)),
        touchpad_mode=str(value.get("touchpad_mode", "off")),
        touchpad_sensitivity=float(value.get("touchpad_sensitivity", 1.0)),
        action_bindings=dict(value.get("action_bindings", {})) if isinstance(value.get("action_bindings"), dict) else {},
        chord_map=dict(value.get("chord_map", {})) if isinstance(value.get("chord_map"), dict) else {},
        gyro_mode=str(value.get("gyro_mode", "off")),
        gyro_sensitivity=float(value.get("gyro_sensitivity", 10.0)),
        gyro_deadzone=float(value.get("gyro_deadzone", 0.8)),
        layer=layer,
    )


class MappingStore:
    """Atomic JSON store keyed by physical GUID, game identity and virtual target."""
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_store_path()

    @staticmethod
    def key(device_guid: str, game_id: str, target_profile_id: str) -> str:
        parts = (device_guid or "unknown", game_id or "default", target_profile_id or "default")
        if any(len(str(part)) > 512 for part in parts):
            raise ValueError("Mapping key component is too long.")
        return "|".join(str(part) for part in parts)

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("profiles", {}), dict):
                return value
        except (OSError, ValueError, TypeError):
            pass
        return {"schema": 1, "profiles": {}}

    def get(self, device_guid: str, game_id: str, target_profile_id: str) -> MappingProfile:
        data = self._read()
        value = data.get("profiles", {}).get(self.key(device_guid, game_id, target_profile_id), {})
        return profile_from_dict(value) if isinstance(value, dict) else MappingProfile()

    def save(self, device_guid: str, game_id: str, target_profile_id: str,
             profile: MappingProfile) -> None:
        data = self._read()
        profiles = data.setdefault("profiles", {})
        profiles[self.key(device_guid, game_id, target_profile_id)] = asdict(profile)
        data["schema"] = 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def delete(self, device_guid: str, game_id: str, target_profile_id: str) -> bool:
        data = self._read()
        profiles = data.setdefault("profiles", {})
        key = self.key(device_guid, game_id, target_profile_id)
        if key not in profiles:
            return False
        del profiles[key]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)
        return True
