# Elmos Input — managed classic DS4Windows Xbox 360 profile

## Why we changed the engine
On the owner's Windows laptop, ViGEmBus was installed and RUNNING, yet the
custom vgamepad bridge never demonstrated working controller input in Sekiro.
A previous DS4Windows 3.3.3 + ViGEmBus Xbox 360 profile **did** work.
Elmos World therefore uses the known classic DS4Windows mapper instead of
running its own competing XInput feeder. The older code remains for reference
but is **not started** by the launcher.

This classic engine uses ViGEmBus, not the newer VIIPER runtime. A Windows
device named "VIIPER Controller" can be left behind by a different controller
stack and is NOT proof that the old classic DS4Windows program produced it.

## Automatic lifecycle
- Elmos World starts the controller engine when the desktop launcher opens.
- The verified portable DS4Windows 3.3.3 archive ships inside the official
  Elmos World Windows installer. It is extracted once under:
  %LOCALAPPDATA%\ElmosWorld\ElmosInput\classic-ds4windows-3.3.3
- The archive digest is pinned to sha256
  cf5619bcb51b82e4e1765276e9f67fb1e2d23dff968a653657acf35bafff8bf4
  from ds4windowsapp/DS4Windows GitHub release "ryochan7".
  Archive owner is a mirror, not the original upstream publisher.
- Elmos checks the ViGEmBus driver and installs it only if absent, through
  regular Windows UAC.
- It launches DS4Windows minimized, starts the controller service using
  the classic DS4Windows command protocol, and keeps the process alive
  independently of which game is running.
- When Elmos closes, it stops **only its own started process**. Any
  external DS4Windows instance is left untouched and blocks duplicate launch.
- No HidHide installation, hiding, auto-start tasks, extra privilege
  prompts for routine launches, or changes to Steam Input.

## Profile and first-run caveat
The bundled classic release provides Xbox 360 output using the classic
DS4Windows profile system. On a new machine, DS4Windows may present a
first-run configuration prompt. Choose the per-user settings location and
create/select the Default Xbox 360 output profile if needed. Once configured,
DS4Windows reuses that profile on subsequent Elmos launches.

This wrapper is not yet hardware-verified. Use joy.cpl and a game like Sekiro
to test face buttons, sticks, triggers, D-pad, disconnect/reconnect, launch,
and close. The original Wireless Controller can remain visible in Windows:
HidHide is not installed. Double input is game-specific, and the game should
use the Xbox 360 output when available.

## Diagnostics
Elmos World > Settings > Elmos Input shows backend, stage, and last error.
Elmos writes messages to %LOCALAPPDATA%\ElmosWorld\logs\launcher.log .
If no virtual Xbox appears, inspect the DS4Windows log from its chosen
settings folder. Do not assume running ViGEmBus alone creates a virtual pad.

## License and provenance
DS4Windows classic is third-party GPL-3.0 software, not an OpenAI or Elmos
implementation. Its upstream archive/license and source pointers are at
https://github.com/ds4windowsapp/DS4Windows/releases/tag/ryochan7 .
The packaged ZIP must be redistributed with its license and notices intact;
the package is used unmodified. The local Elmos wrapper is separate.
