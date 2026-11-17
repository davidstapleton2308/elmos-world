# Elmos Input — our native Sony-to-Xbox 360 engine

Elmos World now owns the runtime bridge. **No DS4Windows executable is
launched, downloaded, or bundled.** The prior DS4Windows 3.3.3 experiment was
removed from the application and build workflow.

## Architecture

1. The Elmos-owned `controller_input.py` SDL reader monitors the physical Sony
   controller, including the standard Windows **raw SDL joystick** layout.
2. `elmos_native_input.py` converts Sony controls to Xbox 360 semantic reports.
3. The `vgamepad` Python ViGEmClient binding sends reports to the existing
   **ViGEmBus** Windows kernel driver. Only the driver is third-party installed.
4. Elmos starts one virtual Xbox target at launcher startup and tears down that
   target when Elmos closes. It doesn't start or terminate other mappers.

No extra mapper UI, DS4Windows, HidHide, VIIPER driver installation, autostart
task, admin consent for normal use, or change to game installations.

## Root cause corrected

The original Elmos bridge refused to map *any* raw SDL joystick: 
`frame_from_snapshot` returned `None` unless the controller's SDL mode was
exactly `mapped SDL`. On many Windows Bluetooth PS4 connections SDL
exposes the physical DualShock as `raw SDL joystick`, leaving the virtual
Xbox device with no input. The launcher also used Xbox-oriented button indices
for raw PS4 devices, mapping Square to A and L3 to Guide incorrectly.

Both mapped SDL and common **raw Windows DS4** layouts are now accepted:
- Face buttons: Cross → A, Circle → B, Square → X, Triangle → Y
- Share/Options → Back/Start; L1/R1 → bumpers; L3/R3 → stick clicks; PS → Guide
- Left/right sticks use raw axes 0–3, invert Y for Xbox output
- L2/R2 use raw axes 4/5, or digital fallback when axes unavailable
- Hat 0 → D-pad

The mapping follows the documented physical DS4 → virtual Xbox semantics
reviewed in the open-source DS4Windows `Xbox360OutDevice` implementation
(CircumSpector/DS4Windows). No code was copied or bundled from that project.

## Driver

Only the signed ViGEmBus 1.22.0 Windows driver requires one-time Windows
approval. If already installed and running, Elmos reuses it. Its publisher
release is pinned with a checksum in `app/elmos_input_driver.py`.
The main software never attempts to hide the physical controller.

An *external* DS4Windows process should be closed before native bridge testing,
since competing virtual outputs would make results ambiguous. Elmos never
terminates it automatically.

## Testing and diagnostics

GitHub Actions can verify the native mappings, lifecycle code, PyInstaller
packaging and update worker, but it cannot test your laptop's Bluetooth
controller. For the hardware test:
1. Close separate controller-mapping apps, connect the PS4 controller over
   Bluetooth and open updated Elmos World.
2. Settings → Elmos Input should show `forwarding-input` and identify the DS4.
3. Check `joy.cpl` for the virtual Xbox 360 controller. Test sticks, D-pad,
   face buttons, triggers and PS/Guide. Then test Sekiro.
4. If the virtual Xbox isn't present or doesn't respond, check
   `%LOCALAPPDATA%\ElmosWorld\logs\launcher.log` for the exact
   `[Elmos Input]` stage and exception.

Seeing Wireless Controller in Windows Device Manager is expected: ViGEmBus
does not hide physical hardware. It is not proof of double input in a game.
