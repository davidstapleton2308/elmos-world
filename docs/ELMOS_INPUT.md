# Elmos Input — independent ViGEmBus Xbox 360 feeder

Elmos World now owns the controller mapping software. The application uses its SDL
controller reader to capture DualShock 4 / DualSense input, normalizes it, and
converts it to virtual Xbox 360 reports using the open-source vgamepad ViGEmClient
binding and a separately installed signed ViGEmBus driver.

There is **no DS4Windows executable, profile manager or download** in this code path.

## Driver and safety
- ViGEmBus is a kernel component and requires proper installation once with
  Windows permission; the engine never bypasses UAC.
- Existing ViGEmBus can be reused unchanged.
- The engine refuses to create a new virtual target while DS4Windows is running;
  users must close the independent DS4Windows process themselves.
- Virtual Xbox target is destroyed when the physical Sony pad disconnects.
- Physical controller is still visible to Windows unless configured separately
  with a suitable controller-hiding solution; games can see double input.
- No driver installation or HidHide changes occur automatically.
- Xbox 360 rumble pass-through and motion/touchpad mapping are not yet implemented.
- Only SDL-mapped Sony controllers are supported in the initial native feeder.
- Games need Windows hardware testing before the feeder is considered a DS4 replacement.

## Build and test
Use `python -m unittest discover -s tests` then the Windows GitHub Actions build.
Run on a personal Windows machine with ViGEmBus installed, close external
DS4Windows, connect Sony controller over Bluetooth or USB, open Elmos World,
verify Elmos Input status and Windows `joy.cpl` Xbox 360 output, then test Sekiro.

The ViGEmBus project is retired and remains a separate dependency, not our code.
