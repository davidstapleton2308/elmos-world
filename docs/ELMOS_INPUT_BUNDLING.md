# Elmos Input: bundled controller compatibility (preview)

This branch is a **packaging and lifecycle foundation**, not a claim that DS4Windows has
been rewritten into the Elmos World Python executable. The user sees one Elmos
installer, but an unmodified DS4Windows controller-mapping helper and its VIIPER
backend still run as separate operating-system processes.

## What this branch changes

- The Windows release build downloads the *pinned* DS4Windows 5 VIIPER bundle
  (hbashton VIIPERRC4.6.6), verifies its SHA-256, and embeds its complete
  portable contents in Elmos World's installed files.
- The package includes the corresponding DS4Windows and VIIPER source archives
  from the same release, with separately verified hashes. Preserve all upstream
  notices. Review GPL obligations before publishing.
- Elmos Input prefers this bundled runtime over independent user-installed
  copies. It does **not** download DS4Windows or install old ViGEmBus on every
  launch. Any pre-existing controller mapper is left alone.
- Elmos starts the helper without waiting for controller initialization, and
  keeps its existing game-aware exit policy.

## Important limitations before release

1. **Driver first run**: VIIPER uses Windows USB/IP infrastructure. First-time
   driver installation/repair requires normal Windows administrator approval.
   Never bypass UAC. The portable upstream runtime may display its own first
   run setup or window. This branch has not been verified to suppress that UI.
2. **Background UI**: this is not yet a truly windowless in-process mapper.
   No promise of invisible startup or silent shutdown can be made until tested
   on a Windows machine with Bluetooth DualShock 4 and the intended driver.
3. **One app versus one process**: distribution is one installer; OS processes
   remain separate. Building a native integrated input engine would require
   an audited SDL/HID-to-VIIPER feeder, ownership/lifetime handling, rumble,
   reconnects, driver setup, UI and cross-game regression testing.
4. **Controller output**: VIIPER can expose multiple virtual device types, but
   Xbox emulation is likely needed for some older PC games. PlayStation glyphs
   are controlled by each game's UI, not by Elmos World.
5. **Rollback**: uninstalling Elmos removes bundled *user-mode* runtime
   payloads. System-wide USB/IP drivers are not automatically uninstalled;
   other apps may depend on them. Elmos must never uninstall unrelated drivers.
6. **Games**: Elmos should avoid terminating controller support while a game
   it launched remains open.
7. **Security**: upstream release candidate bundles may be unsigned; archive
   checksum verification is not equivalent to Authenticode publisher trust.

## Verification gate

Do not merge/publish as a working controller update until Windows QA confirms:

- Build installs with bundled controller files and correct matching source;
- New Windows user: first driver setup with normal UAC then no repeat UAC;
- Bluetooth DS4 works in Sekiro and other XInput-only games without Steam;
- Only the Elmos World window appears in normal launches;
- Reconnects preserve selected profile; no phantom double-input;
- Closing Elmos while a launched game remains open keeps its controller;
- Closing the last game releases only the Elmos-owned helper;
- Uninstall removes the bundled files without damaging other controller apps;
- Windows portable release, in-app updater, and rollback all work.

Runtime is pinned deliberately; upgrade upstream controller components only
after separately checking compatibility and licenses.

Upstream: https://github.com/hbashton/DS4Windows/releases/tag/VIIPERRC4.6.6
