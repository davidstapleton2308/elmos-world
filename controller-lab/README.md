# Elmo's Controller Lab

**An independent controller compatibility laboratory for Elmo's World.**

The long-term goal is a Steam Input-style mapping system that can read a physical
controller, normalize its controls, and present one or more virtual controller
identities to Windows games.

This folder is intentionally self-contained so it can be split into its own
GitHub repository later without depending on Elmo's launcher code.

## The architecture

    Physical controller(s)
      Xbox / DualShock / DualSense / Switch / 8BitDo / generic HID
                       |
                       v
              SDL physical-input adapters
                       |
                       v
              Canonical ControllerState
       semantic buttons, sticks, triggers, d-pad, motion,
               touch contacts, battery, extra axes
                       |
                       v
             Mapping and action engine
      remapping, deadzones, curves, sensitivity, action layers
                       |
                       v
              Virtual device profiles
       Xbox 360 / Xbox One / Xbox Series / DS4 / DualSense /
       Switch Pro / Steam personas / generic HID / wheels / HOTAS
                       |
                       v
          Windows virtual-device backend
              HIDMaestro SDK (pinned 2.1.0)
                       |
                       v
        XInput / DirectInput / HID / SDL / WGI / GameInput

## Current virtual profile catalogue

The pinned SDK's Windows smoke test currently loads **337 profiles**, with
**240 marked deployable**. The catalogue includes 90 gamepads, 68 wheels,
20 joysticks, 18 pedal sets, 5 HOTAS devices, 4 arcade sticks and 3 flight
sticks, plus keyboards, mice and other HID devices. This is a catalogue
count, not a claim that every profile has passed real-hardware or game testing.

## What exists in v0.1

- A canonical controller model independent of physical vendor and target profile.
- SDL physical-controller discovery with mapped SDL input preferred over raw joystick indices.
- Per-profile button remapping, radial stick deadzones, outer/anti-deadzones,
  response curves, sensitivity, trigger shaping, hold/toggle action layers,
  tap/hold/double-tap actions, turbo pulses and chorded button combinations.
- Virtual keyboard and mouse outputs, including button-to-key actions, trigger
  modifiers, left-stick WASD, right-stick mouse movement, touchpad-as-mouse or
  touchpad-as-right-stick, and gyro-to-mouse/gyro-to-stick aiming.
- A Windows JSON-lines bridge using HIDMaestro's profile-based virtual device engine.
- A catalog browser command that reads the SDK's embedded profile catalogue.
- Explicit virtual driver installation, create, state streaming and disposal commands.
- A synthetic demo source so output profiles can be exercised without a physical pad.
- Offline Python regression tests for the mapping layer and persistent per-device/per-game profiles.
- Read-only API visibility probes for XInput, SDL, Windows Gaming Input and optional HIDAPI.
- A localhost browser Gamepad API page and cross-controller matrix integration.
- Optional raw HID sensor capture and tested report parsers for DualShock 4 and DualSense USB/Bluetooth IMU, touchpad and battery data.
- An automated cross-controller matrix that compares API visibility before and
  after virtual-device creation and checks for device leaks after teardown.

## Why this backend

We evaluated the Windows virtual-device options. ViGEmBus is retired and
archived. LizardByte's newer libvirtualhid supports several useful identities,
but its Windows Virtual HID Driver currently requires a paid machine license.
HIDMaestro offers a MIT-licensed SDK with a broad data-driven controller
catalog and support for the Windows input APIs we need, so it is the first
backend we are integrating. This is a backend choice, not a dependency of the
mapping engine: the canonical model and mapping layer remain ours.

The SDK is pinned to HIDMaestro 2.1.0 and its release archive is SHA-256
verified before use. Its own LICENSE and third-party notices are staged beside
the runtime. Do not remove those notices when redistributing a build.

## Requirements

- Windows 10/11 x64 for the first hardware-output target.
- Python 3.10+, pygame-ce and hidapi (for Sony raw motion/touchpad capture).
- .NET 10 SDK for building the bridge.
- Administrator approval for installing the virtual-device driver and creating
  virtual Windows HID devices.

The SDK's driver installer creates a local signing certificate and installs
driver packages. **The setup/build scripts only download and build the SDK;
they do not install a driver, create a certificate, or change Windows settings.**
Driver installation is a separate, explicit action that triggers a UAC prompt.

## Build

Open PowerShell in this folder:

~~~powershell
.\scripts\Build-ControllerLab.ps1
~~~

The script downloads the pinned SDK release, verifies its SHA-256, stages
HIDMaestro.Core.dll, and publishes the bridge. It also runs a driver-free
catalog smoke test.

## Open the graphical Controller Lab

The GUI provides physical-device selection, virtual-profile selection, face-button
remapping, keyboard/mouse actions, stick tuning, touchpad modes and a hold/toggle
action layer. Profiles are saved per physical GUID, game and virtual target.

~~~powershell
# Browse devices and edit profiles without administrator access
.\scripts\Run-ControllerLab.ps1 gui

# Create real virtual devices after the driver is installed
.\scripts\Run-ControllerLab-Elevated.ps1 gui
~~~

The elevated launch asks Windows for UAC approval. It does not install or upgrade
the driver; driver setup remains a separate explicit action.

## Inspect devices and profiles

~~~powershell
.\scripts\Run-ControllerLab.ps1 devices
.\scripts\Run-ControllerLab.ps1 profiles --search xbox
.\scripts\Run-ControllerLab.ps1 profiles --search dualsense
.\scripts\Run-ControllerLab.ps1 status
.\scripts\Run-ControllerLab.ps1 probe
.\scripts\Run-ControllerLab.ps1 probe --profile dualsense
~~~

## Run the virtual profile regression sweep

After the explicit driver setup, run this elevated command:

~~~powershell
.\scripts\Run-ControllerLab-Elevated.ps1 sweep
~~~

## Cross-controller compatibility matrix

Run the same physical controller through several virtual identities, or use a
synthetic source first:

~~~powershell
.\scripts\Run-ControllerLab-Elevated.ps1 matrix --device 0 --targets xbox-360-wired,xbox-series-xs-bt,dualsense,dualshock-4-v2,switch-pro,steam-controller
.\scripts\Run-ControllerLab-Elevated.ps1 matrix --demo --duration 1
.\scripts\Run-ControllerLab-Elevated.ps1 matrix --device 0 --browser --duration 2

# Standalone browser Gamepad API probe
.\scripts\Run-ControllerLab.ps1 browser-probe
~~~

For each target the matrix snapshots XInput, SDL, optional HIDAPI and
Windows Gaming Input visibility, creates the virtual device, streams a test
state, compares newly visible device instances, removes the virtual device,
and checks for leaked devices. It saves a JSON report under
LocalAppData/ElmosControllerLab/reports. XInput profiles must appear in a new
XInput slot; HID profiles must appear through SDL, HIDAPI or Windows Gaming
Input. With `--browser`, the matrix also opens a localhost Gamepad API page
and records browser-visible devices. The standalone `browser-probe` command
can be used without administrator access. Native GameInput and Steam-specific
conformance checks remain future work.


The bridge creates each deployable profile that does not require the separate
composite USB/IP transport. It sends keyboard reports to keyboard profiles,
mouse reports to mouse profiles, and representative button/axis/d-pad states
to gamepad, wheel and joystick profiles, then disposes each virtual device.
It reports per-profile pass/fail progress and saves the complete JSON report
under LocalAppData/ElmosControllerLab/reports. This validates the profile's
create, state-submit and cleanup path; it does not yet prove that every game
API or every game recognizes each device. API enumeration is the next test layer.


## Install the virtual-device driver

Only when ready to create actual Windows virtual controllers:

~~~powershell
.\scripts\Install-ControllerLab-Driver.ps1
~~~

Review and approve the Windows UAC prompt. This installs the HIDMaestro driver
and its local signing certificate. It is not required just to browse profiles,
inspect physical controllers, or run the Python mapping tests.

## First virtual-device tests

Try these after the explicit driver setup:

~~~powershell
.\scripts\Run-ControllerLab-Elevated.ps1 emulate --profile xbox-360-wired --demo
.\scripts\Run-ControllerLab-Elevated.ps1 emulate --profile dualsense --demo
.\scripts\Run-ControllerLab-Elevated.ps1 emulate --profile switch-pro --demo
.\scripts\Run-ControllerLab-Elevated.ps1 emulate --profile dualsense --demo --actions-demo
~~~

The demo sends a synthetic pattern through the same mapping and output path as
a physical controller. The actions-demo option additionally creates a virtual
keyboard and mouse and tests Space/Shift, trigger modifiers, WASD and mouse aim.
Run it through the elevated script after approving UAC.
Press Ctrl+C to send a neutral frame and remove the virtual device. The SDK bridge refuses composite USB personas in this first
version because they require a separate USB/IP transport installation flow.

For a physical controller, connect it over USB or Bluetooth, inspect it with
devices, then run emulate with the SDL index shown in that list. SDL-mapped
input is preferred. Raw-only devices are shown as unmapped and use a basic
fallback layout; that fallback is not a claim of correct button identity.

## Known limitations — deliberately not hidden

- SDL supplies standardized buttons, sticks, triggers and d-pad input.
  The optional HIDAPI reader currently adds raw IMU, touchpad and battery data
  for supported DualShock 4 and DualSense USB/Bluetooth report layouts. Other
  vendors' motion protocols still need dedicated adapters.
- The read-only probe checks SDL visibility, XInput slots, optional HIDAPI and
  Windows Gaming Input RawGameController enumeration. Native GameInput and
  browser Gamepad API probes remain future work.
- The bridge can submit standard buttons, axes, triggers, d-pad, motion and
  touch contacts to profiles. Exact raw Sony motion calibration and vendor
  feature reports still need dedicated physical-device adapters.
- Composite USB personas are discovered but not yet enabled for creation.
- Output feedback is surfaced from the virtual device. Routing rumble, LEDs,
  adaptive triggers and haptics back to the physical source is a next milestone.
- This first UI is a CLI and a test harness, not the finished Steam-like UI.
- Some anti-cheat systems may reject virtual controllers. The project will not
  hide virtual devices or bypass anti-cheat.
- A virtual PlayStation identity does not reproduce a Sony security chip or
  guarantee authentication to a physical PlayStation console.

## Roadmap

1. **Input and output validation:** build a physical-to-virtual test matrix:
   PS4 -> Xbox 360/Series, Xbox -> DualShock 4/DualSense, Switch Pro -> Xbox,
   and cross-pairs in both directions.
2. **Profile editor:** edit and persist physical source maps and virtual target
   profiles per game and per device GUID.
3. **Advanced Steam Input mappings:** action sets, deeper mode shifts,
   macro recording/playback, radial menus, touchpad gestures, and a full visual
   editor for per-game layers and complex bindings.
4. **Analog controls:** independent trigger thresholds, stick response curves,
   anti-deadzone, outer deadzone, gyro smoothing and bias calibration, plus
   multi-finger trackpad gestures.
5. **Feedback:** route virtual rumble/FFB/haptics back to the physical device;
   support LEDs, battery, adaptive triggers and microphone state where available.
6. **Compatibility matrix:** automatically enumerate each virtual identity in
   DirectInput, XInput, SDL, WGI/GameInput and browser Gamepad; record pass/fail,
   latency, axis/button counts and cleanup results.
7. **Elmo's World integration:** embed the stable mapping engine and device
   session API into the launcher after the lab passes hardware tests.

## Upstream backend references

- HIDMaestro: https://github.com/hifihedgehog/HIDMaestro
- HIDMaestro release v2.1.0: https://github.com/hifihedgehog/HIDMaestro/releases/tag/v2.1.0
- SDL GameController: https://wiki.libsdl.org/SDL2/CategoryGameController
- Microsoft Virtual HID Framework: https://learn.microsoft.com/windows-hardware/drivers/hid/virtual-hid-framework--vhf-

Mapping profiles are saved independently by physical SDL GUID, game identity
and virtual target profile under LocalAppData/ElmosControllerLab/mappings.json.
The CLI loads the matching profile automatically during emulate. A future
visual editor will write to this same store.

The project is our own mapping and test system. HIDMaestro is an external,
replaceable Windows virtual-device backend and remains subject to its MIT
license and bundled third-party notices.
