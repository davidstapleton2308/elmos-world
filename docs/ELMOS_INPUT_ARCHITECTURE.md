# Elmo's Input — experimental controller compatibility

This is an independently developed **Steam Input-style** input layer, not an
implementation of Valve's proprietary Steam Input or a copy of Valve code.

## Current supported pathway

- DualShock 4 input from USB/Bluetooth using the existing SDL/pygame-ce reader.
- Native input is the safe default; games continue to see the physical device.
- Per-game Cross/Circle/Square/Triangle button remapping, saved with the profile.
- Per-game opt-in Virtual Xbox 360 mode through Python vgamepad and an existing,
  separately installed compatible ViGEmBus Windows driver.
- Xbox face buttons, shoulders, D-pad, thumb presses, analog sticks, L2/R2.
- Analog stick deadzones and reversal of SDL Y vs Xbox XInput Y.
- Virtual controller allocated before a direct game launch, released on exit.
- PS/Guide opens the existing native in-game menu; neutralize translated
  buttons when the menu is open or the game loses foreground focus.
- Neutralize inputs when the physical controller disconnects or stalls.
- No automatic driver installation, system elevation, device hiding, global
  keyboard hook, or automatic game file modifications.
- One physical controller; Windows games and emulators only.

## Input pipeline

    Physical DualShock 4 -> SDL GameController mapping
      |
      +--> Elmo's navigation and PS menu
      |
      +--> Game-specific Native/Virtual Xbox profile
             |
             +--> Native: leave physical controller alone
             |
             +--> Virtual Xbox: focus/PS/disconnect watchdog
                    -> vgamepad -> preinstalled ViGEmBus
                    -> Xbox 360 XInput virtual gamepad -> PC game

## Test it in the preview

1. Use the successful Windows preview artifact from the GitHub Actions
   Elmos Input Safety Tests run on the feature/elmos-input-xbox-bridge branch.
2. Extract the full portable folder. Run ElmosWorld.exe.
3. Navigate to Settings > Input Lab > Game controller compatibility.
4. Select a game. Native is the default. Try a game that already recognizes
   your PS4 controller before enabling virtual translation.
5. For games that only accept Xbox XInput, select Virtual Xbox 360.
   This needs a compatible ViGEmBus driver already installed on Windows.
   Elmo's World never installs the driver or requests admin access.
6. Launch the game directly, verify X/Y/A/B, sticks, L2/R2, and PS menu.
7. Exit normally; verify that the virtual controller disappears in joy.cpl.

The feature is not verified on a real PS4 controller yet. The automated tests
simulate input and validate syntax, output mapping, exit cleanup and session
control. The separate Windows packaging test validates runtime bundling.

## Device routing concerns

A game may see the DualShock 4 and virtual Xbox controller simultaneously,
causing double presses or a false Player 2. Do not run DS4Windows and
the Elmo virtual bridge together unless you know the device routes. HidHide
can address this, but must be configured separately and deliberately.

Some games spawn a child process, enumerate XInput only at startup,
need elevated access, block virtual devices, or use APIs other than XInput.
This preview gates output to the launched game's foreground PID, so such
games can require additional compatibility work. We do not bypass anti-cheat.

## Next milestones for Steam Input-like parity

1. Editable action bindings per game, keyboard/mouse and gamepad outputs.
2. Action sets/layers, hold-to-activate, chords, double-tap and radial menus.
3. Stick sensitivity, response curves, trigger threshold and calibration.
4. Gyro aiming, DualShock touchpad, rumble and LED control.
5. Multi-controller device routing, persistent device IDs and diagnostic UI.
6. Evaluate maintained HIDMaestro virtual XInput backend as an alternative
   to retired ViGEmBus, with explicit approval for any driver installation.

## Research

- https://partner.steamgames.com/doc/features/steam_controller
- https://wiki.libsdl.org/SDL3/CategoryGamepad
- https://pypi.org/project/vgamepad/
- https://github.com/nefarius/ViGEmBus
- https://github.com/nefarius/HidHide
- https://github.com/hifihedgehog/HIDMaestro

We can meaningfully reproduce controller translation and profiles, but cannot
promise full proprietary Steam Input feature or per-game compatibility parity.
