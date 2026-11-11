"""Command-line controller laboratory. UI and launcher integration can sit on this API."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

from .bridge import BridgeClient, BridgeError
from .api_probe import probe_hidapi, probe_xinput, run_probe
from .mapping import Mapper, MappingProfile
from .model import ControllerState, neutral_state
from .sdl_source import SDLInputSource
from .store import MappingStore


def print_json(value):
    print(json.dumps(value, indent=2, default=str))



def command_gui(args):
    from .gui import main as gui_main
    gui_main(args.bridge)


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
        profiles = [p for p in profiles if "keyboard" not in str(p.get("type", "")).casefold()
                    and "mouse" not in str(p.get("type", "")).casefold()]
    print_json({"driverInstalled": result.get("driverInstalled"), "count": len(profiles), "profiles": profiles})




def command_probe(args):
    target = None
    if args.profile:
        with BridgeClient(args.bridge) as bridge:
            profiles = bridge.request("profiles").get("profiles", [])
        target = next((p for p in profiles if p.get("id") == args.profile), None)
        if target is None:
            raise BridgeError(f"Unknown virtual profile: {args.profile}")
    print_json(run_probe(target))


def command_sweep(args):
    def on_event(event):
        if event.get("event_name") == "sweep_progress":
            print(f"[{event.get('completed')}/{event.get('total')}] {event.get('profile')}: {event.get('status')}", flush=True)
    with BridgeClient(args.bridge, on_event=on_event) as bridge:
        result = bridge.request("sweep", timeout=1200)
        print_json(result)



def _target_matches(device, profile):
    vendor = int(profile.get("vendorId") or 0)
    product = int(profile.get("productId") or 0)
    if vendor and product and device.get("vendor_id") and device.get("product_id"):
        return int(device["vendor_id"]) == vendor and int(device["product_id"]) == product
    expected = str(profile.get("displayName") or profile.get("name") or profile.get("id") or "").casefold()
    actual = str(device.get("name") or device.get("product") or "").casefold()
    return bool(expected and (expected in actual or actual in expected))


def _snapshot(profile, source=None):
    sdl_devices = source.refresh() if source else None
    report = run_probe(profile, sdl_devices=sdl_devices)
    return report


def command_matrix(args):
    def on_event(event):
        if event.get("event_name", "").startswith("output"):
            print("[device feedback]", json.dumps(event, default=str), flush=True)
        elif event.get("event_name") == "error":
            print("[bridge error]", event.get("message"), file=sys.stderr, flush=True)

    with BridgeClient(args.bridge, on_event=on_event) as bridge:
        status = bridge.request("status")
        if not status.get("driverInstalled") or not status.get("driverPrepared"):
            raise BridgeError("The pinned virtual driver must be explicitly installed first.")
        if not status.get("elevated"):
            raise BridgeError("The matrix creates Windows virtual devices. Run Run-ControllerLab-Elevated.ps1 and approve UAC.")

        catalog = bridge.request("profiles").get("profiles", [])
        by_id = {p.get("id"): p for p in catalog}
        target_ids = [x.strip() for x in args.targets.split(",") if x.strip()]
        source = None
        device_guid = "synthetic"
        physical_instance = None
        if not args.demo:
            source = SDLInputSource()
            devices = source.list_devices()
            print_json({"physical_devices": devices})
            selected = next((d for d in devices if d["index"] == args.device), None)
            if selected is None:
                raise BridgeError("The selected physical SDL controller was not found.")
            device_guid = selected.get("guid") or selected.get("name") or "unknown"
            physical_instance = selected["instance_id"]
            if source.attach_sensor_reader(physical_instance):
                print("Sony motion/touchpad sensor reader: attached", flush=True)

        results = []
        try:
            for index, target_id in enumerate(target_ids):
                profile = by_id.get(target_id)
                if not profile:
                    results.append({"profile": target_id, "status": "skip", "reason": "Profile id not found"})
                    continue
                if not profile.get("deployable") or profile.get("requiresUsbip"):
                    results.append({"profile": target_id, "status": "skip", "reason": "Not deployable or requires separate composite USB/IP transport"})
                    continue

                slot = f"matrix-{index}"
                baseline = _snapshot(profile, source)
                baseline_sdl = baseline["apis"]["sdl_gamecontroller"]["devices"]
                baseline_sdl_ids = {d.get("instance_id") for d in baseline_sdl}
                baseline_xinput = {d.get("slot") for d in baseline["apis"]["xinput"]["devices"]}
                baseline_hid_count = len(baseline["apis"]["hidapi"]["devices"])
                created = False
                target_result = {"profile": target_id, "name": profile.get("name"), "type": profile.get("type")}
                try:
                    bridge.request("create", slot=slot, profile_id=target_id)
                    created = True
                    if source:
                        devices_after_create = source.refresh()
                        if not any(d.get("instance_id") == physical_instance for d in devices_after_create):
                            raise BridgeError("The physical source controller disappeared during virtual device creation.")

                    mapper = Mapper(MappingStore().get(device_guid, args.game, target_id))
                    start = time.monotonic()
                    frames = 0
                    while time.monotonic() - start < max(0.25, min(15.0, args.duration)):
                        elapsed = time.monotonic() - start
                        physical = _demo_state(elapsed) if args.demo else source.read_instance(physical_instance)
                        bridge.send_state(slot, mapper.map(physical).to_wire())
                        frames += 1
                        time.sleep(1.0 / max(30, min(250, args.rate)))

                    after = _snapshot(profile, source)
                    after_sdl = after["apis"]["sdl_gamecontroller"]["devices"]
                    new_sdl = [d for d in after_sdl if d.get("instance_id") not in baseline_sdl_ids]
                    sdl_match = [d for d in new_sdl if _target_matches(d, profile)]
                    after_xinput = {d.get("slot") for d in after["apis"]["xinput"]["devices"]}
                    new_xinput = sorted(x for x in after_xinput - baseline_xinput if x is not None)
                    after_hid_count = len(after["apis"]["hidapi"]["devices"])
                    hid_expected = bool(profile.get("vendorId") and profile.get("productId"))
                    hid_visible = hid_expected and after_hid_count > baseline_hid_count
                    xinput_expected = bool(profile.get("xinput"))
                    api_visible = bool(new_xinput) if xinput_expected else bool(sdl_match or hid_visible)

                    bridge.send_state(slot, neutral_state().to_wire())
                    time.sleep(0.03)
                    bridge.request("destroy", slot=slot, timeout=30)
                    created = False

                    cleanup_deadline = time.monotonic() + 2.0
                    clean_snapshot = after
                    while time.monotonic() < cleanup_deadline:
                        clean_snapshot = _snapshot(profile, source)
                        clean_sdl = clean_snapshot["apis"]["sdl_gamecontroller"]["devices"]
                        leaked_sdl = [d for d in clean_sdl if d.get("instance_id") not in baseline_sdl_ids and _target_matches(d, profile)]
                        clean_xinput = {d.get("slot") for d in clean_snapshot["apis"]["xinput"]["devices"]}
                        leaked_xinput = clean_xinput - baseline_xinput
                        clean_hid_count = len(clean_snapshot["apis"]["hidapi"]["devices"])
                        if not leaked_sdl and not leaked_xinput and clean_hid_count <= baseline_hid_count:
                            break
                        time.sleep(0.15)
                    cleanup_ok = not leaked_sdl and not leaked_xinput and clean_hid_count <= baseline_hid_count
                    target_result.update({
                        "status": "pass" if api_visible and cleanup_ok else "fail",
                        "frames_sent": frames,
                        "xinput_expected": xinput_expected,
                        "new_xinput_slots": new_xinput,
                        "new_sdl_devices": sdl_match,
                        "hidapi_count_before": baseline_hid_count,
                        "hidapi_count_after": after_hid_count,
                        "api_visible": api_visible,
                        "cleanup_ok": cleanup_ok,
                        "leaked_sdl_devices": leaked_sdl,
                        "leaked_xinput_slots": sorted(x for x in leaked_xinput if x is not None),
                    })
                except Exception as exc:
                    target_result.update({"status": "error", "error": type(exc).__name__, "message": str(exc)})
                    if created:
                        try:
                            bridge.send_state(slot, neutral_state().to_wire())
                            bridge.request("destroy", slot=slot, timeout=30)
                        except Exception as cleanup_error:
                            target_result["cleanup_error"] = str(cleanup_error)
                results.append(target_result)
                print(f"[{index + 1}/{len(target_ids)}] {target_id}: {target_result['status']}", flush=True)
        finally:
            if source:
                source.close()

    report = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": device_guid,
        "demo": bool(args.demo),
        "game": args.game,
        "targets": results,
        "passed": sum(1 for r in results if r.get("status") == "pass"),
        "failed": sum(1 for r in results if r.get("status") in ("fail", "error")),
        "skipped": sum(1 for r in results if r.get("status") == "skip"),
    }
    import os
    from pathlib import Path
    folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ElmosControllerLab" / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / ("cross-controller-matrix-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_json(report)


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
    def on_event(event):
        if event.get("event_name", "").startswith("output"):
            print("[device feedback]", json.dumps(event, default=str), flush=True)
        elif event.get("event_name") == "error":
            print("[bridge error]", event.get("message"), file=sys.stderr, flush=True)

    with BridgeClient(args.bridge, on_event=on_event) as bridge:
        status = bridge.request("status")
        if not status.get("driverInstalled"):
            raise BridgeError("Virtual controller driver is not installed. Run the explicit install-driver command first.")
        if not status.get("driverPrepared"):
            raise BridgeError("The pinned virtual driver has not been explicitly prepared. Run Install-ControllerLab-Driver.ps1 first.")
        if not status.get("elevated"):
            raise BridgeError("Virtual device creation requires an elevated session. Run Run-ControllerLab-Elevated.ps1 and approve UAC.")

        source = None
        created_slots: list[str] = []
        try:
            device_guid = "synthetic"
            if not args.demo:
                source = SDLInputSource()
                devices = source.list_devices()
                print_json({"physical_devices": devices})
                if not devices:
                    raise BridgeError("No physical controller found. Connect one over USB/Bluetooth or use --demo.")
                selected = next((d for d in devices if d["index"] == args.device), None)
                if selected is None:
                    raise BridgeError(f"No SDL device at index {args.device}.")
                device_guid = selected["guid"] or selected["name"]
                sensor_ready = source.attach_sensor_reader(selected["instance_id"])
                if sensor_ready:
                    print("Sony motion/touchpad sensor reader: attached", flush=True)

            mapping = MappingStore().get(device_guid, args.game, args.profile)
            if args.actions_demo:
                mapping.keyboard_map.update({"south": ["Space"], "east": ["E"]})
                mapping.trigger_keyboard_map.update({"left_trigger": ["LeftShift"]})
                mapping.mouse_map.update({"right_trigger": "left"})
                mapping.left_stick_as_wasd = True
                mapping.right_stick_mouse = True
            mapper = Mapper(mapping)

            gamepad_result = bridge.request("create", slot=args.slot, profile_id=args.profile)
            created_slots.append(args.slot)
            print("Created virtual gamepad:", gamepad_result["profile"]["name"], flush=True)

            keyboard_slot = args.slot + "-keyboard"
            mouse_slot = args.slot + "-mouse"
            need_keyboard = bool(mapping.keyboard_map or mapping.trigger_keyboard_map or mapping.left_stick_as_wasd or
                                 (mapping.layer and (mapping.layer.keyboard_map or mapping.layer.left_stick_as_wasd)))
            need_mouse = bool(mapping.mouse_map or mapping.right_stick_mouse or
                              (mapping.layer and (mapping.layer.mouse_map or mapping.layer.right_stick_mouse)))
            if need_keyboard:
                result = bridge.request("create", slot=keyboard_slot, profile_id="microsoft-wired-keyboard-600")
                created_slots.append(keyboard_slot)
                print("Created virtual keyboard:", result["profile"]["name"], flush=True)
            if need_mouse:
                result = bridge.request("create", slot=mouse_slot, profile_id="microsoft-optical-mouse-tilt-wheel")
                created_slots.append(mouse_slot)
                print("Created virtual mouse:", result["profile"]["name"], flush=True)

            print(f"Input: {device_guid} | Game: {args.game} | Mapping: {mapping.name}", flush=True)
            start = time.monotonic()
            while True:
                now = time.monotonic()
                physical = _demo_state(now - start) if args.demo else source.read(args.device)
                output = mapper.map_actions(physical)
                bridge.send_state(args.slot, output.gamepad.to_wire())
                if need_keyboard:
                    bridge.send_keyboard(keyboard_slot, sorted(output.keyboard_keys), sorted(output.keyboard_modifiers))
                if need_mouse:
                    bridge.send_mouse(mouse_slot, sorted(output.mouse_buttons), output.mouse_dx,
                                      output.mouse_dy, output.mouse_wheel, output.mouse_pan)
                time.sleep(1.0 / max(30, min(250, args.rate)))
        except KeyboardInterrupt:
            print("\nStopping virtual controller outputs…", flush=True)
        finally:
            for slot in reversed(created_slots):
                try:
                    if slot.endswith("-keyboard"):
                        bridge.send_keyboard(slot, [], [])
                    elif slot.endswith("-mouse"):
                        bridge.send_mouse(slot, [], 0, 0, 0, 0)
                    else:
                        bridge.send_state(slot, neutral_state().to_wire())
                    time.sleep(0.03)
                    bridge.request("destroy", slot=slot, timeout=15)
                except Exception as exc:
                    print(f"Cleanup warning for {slot}:", exc, file=sys.stderr)
            if source:
                source.close()


def build_parser():
    parser = argparse.ArgumentParser(prog="elmos-controller-lab")
    parser.add_argument("--bridge", help="Path to Elmos.ControllerLab.Bridge.exe")
    sub = parser.add_subparsers(dest="command", required=True)
    gui = sub.add_parser("gui", help="Open the Controller Lab mapping and live-output interface")
    gui.set_defaults(func=command_gui)
    devices = sub.add_parser("devices", help="List physical SDL controllers")
    devices.set_defaults(func=command_devices)
    status = sub.add_parser("status", help="Check virtual-device driver status")
    status.set_defaults(func=command_status)
    profiles = sub.add_parser("profiles", help="Browse the virtual-controller profile catalog")
    profiles.add_argument("--search", default="")
    profiles.add_argument("--include-non-gamepads", action="store_true")
    profiles.set_defaults(func=command_profiles)
    probe = sub.add_parser("probe", help="Check what Windows currently exposes through XInput, SDL and optional HIDAPI")
    probe.add_argument("--profile", default="", help="Compare visibility with one virtual profile's VID/PID and XInput expectation")
    probe.set_defaults(func=command_probe)
    install = sub.add_parser("install-driver", help="Explicitly install the Windows virtual-device driver")
    install.set_defaults(func=command_install)
    sweep = sub.add_parser("sweep", help="Create, submit a test state to, and remove each supported virtual profile")
    sweep.set_defaults(func=command_sweep)
    matrix = sub.add_parser("matrix", help="Test one physical or synthetic source across multiple virtual profiles and Windows APIs")
    matrix.add_argument("--targets", default="xbox-360-wired,xbox-series-xs-bt,dualsense,dualshock-4-v2,switch-pro,steam-controller")
    matrix.add_argument("--device", type=int, default=0)
    matrix.add_argument("--demo", action="store_true")
    matrix.add_argument("--duration", type=float, default=1.0)
    matrix.add_argument("--rate", type=int, default=120)
    matrix.add_argument("--game", default="default")
    matrix.set_defaults(func=command_matrix)
    emulate = sub.add_parser("emulate", help="Feed a physical or synthetic controller into a virtual identity")
    emulate.add_argument("--profile", required=True, help="HIDMaestro profile id, e.g. xbox-360-wired or dualsense")
    emulate.add_argument("--slot", default="virtual-0")
    emulate.add_argument("--device", type=int, default=0, help="Physical SDL controller index")
    emulate.add_argument("--demo", action="store_true", help="Use a synthetic input stream instead of a physical controller")
    emulate.add_argument("--rate", type=int, default=120)
    emulate.add_argument("--game", default="default", help="Game identity used to load a device-specific mapping profile")
    emulate.add_argument("--actions-demo", action="store_true", help="Also test virtual keyboard/mouse output with a built-in WASD/mouse layout")
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
