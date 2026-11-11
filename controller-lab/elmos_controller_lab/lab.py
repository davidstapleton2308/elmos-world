"""Command-line controller laboratory. UI and launcher integration can sit on this API."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

from .bridge import BridgeClient, BridgeError
from .mapping import Mapper, MappingProfile
from .model import ControllerState, neutral_state
from .sdl_source import SDLInputSource


def print_json(value):
    print(json.dumps(value, indent=2, default=str))


def command_devices(_args):
    source = SDLInputSource()
    try:
        print_json(source.list_devices())
    finally:
        source.close()


def command_status(args):
    with BridgeClient(args.bridge) as bridge:
        print_json(bridge.request("status"))


def command_profiles(args):
    with BridgeClient(args.bridge) as bridge:
        result = bridge.request("profiles")
    profiles = result.get("profiles", [])
    if args.search:
        term = args.search.casefold()
        profiles = [p for p in profiles if term in " ".join(str(p.get(k, "")) for k in ("id", "name", "vendor", "type")).casefold()]
    if not args.include_non_gamepads:
        profiles = [p for p in profiles if p.get("type") in ("gamepad", "joystick", "arcade", "wheel")]
    print_json({"driverInstalled": result.get("driverInstalled"), "count": len(profiles), "profiles": profiles})


def command_install(args):
    with BridgeClient(args.bridge) as bridge:
        print_json(bridge.request("install-driver", timeout=120))


def _demo_state(t: float) -> ControllerState:
    return ControllerState(
        device_id="demo", name="Elmo's Synthetic Controller",
        buttons={"south"} if int(t * 2) % 2 == 0 else {"east"},
        axes={
            "left_x": math.sin(t * 1.3),
            "left_y": math.cos(t * 1.3),
            "right_x": math.sin(t * 0.7),
            "right_y": math.cos(t * 0.7),
            "left_trigger": (math.sin(t * 1.7) + 1) * 0.5,
            "right_trigger": (math.cos(t * 1.1) + 1) * 0.5,
        },
        dpad={"up"} if int(t) % 4 == 0 else set(),
    )


def command_emulate(args):
    events = []
    def on_event(event):
        events.append(event)
        if event.get("event_name", "").startswith("output"):
            print("[device feedback]", json.dumps(event, default=str), flush=True)
        elif event.get("event_name") == "error":
            print("[bridge error]", event.get("message"), file=sys.stderr, flush=True)

    with BridgeClient(args.bridge, on_event=on_event) as bridge:
        status = bridge.request("status")
        if not status.get("driverInstalled"):
            raise BridgeError("Virtual controller driver is not installed. Run the explicit install-driver command first.")
        if not status.get("elevated"):
            raise BridgeError("Virtual device creation requires an elevated session. Run Install-ControllerLab-Driver.ps1 and approve UAC.")
        created = bridge.request("create", slot=args.slot, profile_id=args.profile)
        print("Created virtual device:", created["profile"]["name"], flush=True)
        mapper = Mapper(MappingProfile())
        source = None
        if not args.demo:
            source = SDLInputSource()
            devices = source.list_devices()
            print_json({"physical_devices": devices})
            if not devices:
                raise BridgeError("No physical controller found. Connect one over USB/Bluetooth or use --demo.")
            if not any(d["index"] == args.device for d in devices):
                raise BridgeError(f"No SDL device at index {args.device}.")
        start = time.monotonic()
        try:
            while True:
                now = time.monotonic()
                if args.demo:
                    physical = _demo_state(now - start)
                else:
                    physical = source.read(args.device)
                mapped = mapper.map(physical)
                bridge.send_state(args.slot, mapped.to_wire())
                time.sleep(1.0 / max(30, min(250, args.rate)))
        except KeyboardInterrupt:
            print("\nStopping virtual controller…", flush=True)
        finally:
            try:
                bridge.send_state(args.slot, neutral_state().to_wire())
                time.sleep(0.03)
                bridge.request("destroy", slot=args.slot, timeout=15)
            except Exception as exc:
                print("Cleanup warning:", exc, file=sys.stderr)
            if source:
                source.close()


def build_parser():
    parser = argparse.ArgumentParser(prog="elmos-controller-lab")
    parser.add_argument("--bridge", help="Path to Elmos.ControllerLab.Bridge.exe")
    sub = parser.add_subparsers(dest="command", required=True)
    devices = sub.add_parser("devices", help="List physical SDL controllers")
    devices.set_defaults(func=command_devices)
    status = sub.add_parser("status", help="Check virtual-device driver status")
    status.set_defaults(func=command_status)
    profiles = sub.add_parser("profiles", help="Browse the virtual-controller profile catalog")
    profiles.add_argument("--search", default="")
    profiles.add_argument("--include-non-gamepads", action="store_true")
    profiles.set_defaults(func=command_profiles)
    install = sub.add_parser("install-driver", help="Explicitly install the Windows virtual-device driver")
    install.set_defaults(func=command_install)
    emulate = sub.add_parser("emulate", help="Feed a physical or synthetic controller into a virtual identity")
    emulate.add_argument("--profile", required=True, help="HIDMaestro profile id, e.g. xbox-360-wired or dualsense")
    emulate.add_argument("--slot", default="virtual-0")
    emulate.add_argument("--device", type=int, default=0, help="Physical SDL controller index")
    emulate.add_argument("--demo", action="store_true", help="Use a synthetic input stream instead of a physical controller")
    emulate.add_argument("--rate", type=int, default=120)
    emulate.set_defaults(func=command_emulate)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (BridgeError, RuntimeError, OSError) as exc:
        print(f"Controller Lab: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
