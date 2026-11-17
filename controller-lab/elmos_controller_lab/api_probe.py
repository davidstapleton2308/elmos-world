"""Read-only Windows gamepad API probes for virtual-profile verification."""
from __future__ import annotations

import ctypes
import sys
from typing import Any

from .sdl_source import SDLInputSource


class _XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("buttons", ctypes.c_ushort),
        ("left_trigger", ctypes.c_ubyte),
        ("right_trigger", ctypes.c_ubyte),
        ("left_x", ctypes.c_short),
        ("left_y", ctypes.c_short),
        ("right_x", ctypes.c_short),
        ("right_y", ctypes.c_short),
    ]


class _XInputState(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_uint), ("gamepad", _XInputGamepad)]


def probe_xinput() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"available": False, "reason": "Windows only", "devices": []}
    dll = None
    used = None
    for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            dll = ctypes.WinDLL(name)
            used = name
            break
        except OSError:
            continue
    if dll is None:
        return {"available": False, "reason": "No XInput runtime found", "devices": []}
    get_state = dll.XInputGetState
    get_state.argtypes = [ctypes.c_uint, ctypes.POINTER(_XInputState)]
    get_state.restype = ctypes.c_uint
    devices = []
    for slot in range(4):
        state = _XInputState()
        if get_state(slot, ctypes.byref(state)) == 0:
            pad = state.gamepad
            devices.append({
                "slot": slot,
                "packet": state.packet,
                "buttons_mask": int(pad.buttons),
                "left_trigger": int(pad.left_trigger),
                "right_trigger": int(pad.right_trigger),
                "left_stick": [int(pad.left_x), int(pad.left_y)],
                "right_stick": [int(pad.right_x), int(pad.right_y)],
            })
    return {"available": True, "runtime": used, "devices": devices}


def probe_sdl() -> dict[str, Any]:
    try:
        source = SDLInputSource()
        try:
            return {"available": True, "devices": source.list_devices()}
        finally:
            source.close()
    except Exception as exc:
        return {"available": False, "reason": str(exc), "devices": []}


def probe_hidapi(vendor_id: int | None = None, product_id: int | None = None) -> dict[str, Any]:
    try:
        import hid
    except Exception:
        return {"available": False, "reason": "Optional hidapi Python package is not installed", "devices": []}
    try:
        entries = hid.enumerate(vendor_id or 0, product_id or 0)
        devices = []
        for item in entries:
            devices.append({
                "vendor_id": item.get("vendor_id"),
                "product_id": item.get("product_id"),
                "manufacturer": item.get("manufacturer_string"),
                "product": item.get("product_string"),
                "serial": item.get("serial_number"),
                "usage_page": item.get("usage_page"),
                "usage": item.get("usage"),
                "interface": item.get("interface_number"),
            })
        return {"available": True, "devices": devices}
    except Exception as exc:
        return {"available": False, "reason": str(exc), "devices": []}


def run_probe(target_profile: dict[str, Any] | None = None, sdl_devices: list[dict[str, Any]] | None = None, bridge=None, browser_probe=None) -> dict[str, Any]:
    vendor_id = target_profile.get("vendorId") if target_profile else None
    product_id = target_profile.get("productId") if target_profile else None
    xinput = probe_xinput()
    sdl = probe_sdl() if sdl_devices is None else {"available": True, "devices": sdl_devices}
    hid = probe_hidapi(vendor_id, product_id)
    if bridge is not None:
        try:
            wgi = bridge.request("wgi", timeout=20)
        except Exception as exc:
            wgi = {"available": False, "reason": str(exc), "devices": []}
    else:
        wgi = {"available": False, "status": "not queried"}
    expected_xinput = bool(target_profile and target_profile.get("xinput"))
    expected_hid = bool(target_profile and target_profile.get("vendorId") and target_profile.get("productId"))
    browser = browser_probe.snapshot() if browser_probe is not None else {"available": False, "status": "not started", "devices": []}
    browser["available"] = browser_probe is not None
    return {
        "target": target_profile,
        "apis": {
            "xinput": xinput,
            "sdl_gamecontroller": sdl,
            "hidapi": hid,
            "directinput": {"available": sdl["available"], "note": "SDL/joystick visibility is a useful signal, not a full DirectInput conformance test."},
            "windows_gaming_input": wgi,
            "gameinput": {"available": False, "status": "not implemented in this probe"},
            "browser_gamepad": browser,
        },
        "expectations": {
            "xinput_expected": expected_xinput,
            "xinput_seen": bool(xinput.get("devices")),
            "hid_identity_expected": expected_hid,
            "hid_identity_seen": bool(hid.get("devices")) if expected_hid else None,
        },
    }
