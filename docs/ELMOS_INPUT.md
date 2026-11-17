# Elmos Input — controller integration contract

**Goal:** one Elmos World user experience using the user's proven DualShock 4
Bluetooth → classic DS4Windows 3.3.3 → ViGEmBus 1.22.0 workflow, without Steam
Input, while preserving any preexisting VIIPER device/backend.

## What starts on first launch

1. If an existing DS4Windows or VIIPER process is running, preserve it. Do not
   create a second virtual controller. If a configured DS4Windows executable
   exists in a known location, preserve and reuse its existing profiles.
2. Otherwise, check whether DS4Windows exists. When it is absent, download the
   exact archived x64 Ryochan7 3.3.3 ZIP from the ds4windowsapp GitHub release;
   verify SHA-256 `cf5619bcb51b82e4e1765276e9f67fb1e2d23dff968a653657acf35bafff8bf4`,
   extract it beneath `%LOCALAPPDATA%\ElmosWorld\ElmosInput`. Never overwrite
   an existing installation.
3. Check whether classic ViGEmBus is installed. If it is missing, download the
   **publisher's** ViGEmBus 1.22.0 installer; verify the Microsoft Winget
   manifest's SHA-256
   `89220a7865076b342892f98865f3499fb7c4cfd673159e89d352c360fd014c6a`.
   Run setup with publisher-documented quiet switches. **Windows UAC may still
   require administrator approval; don't attempt to disable it.** A restart may
   be needed before the controller works.
4. Start the existing/verified DS4Windows controller mapper only when the driver
   is ready. Elmos World owns only the mapper process it creates and stops it
   when exiting unless a launched game still needs it.

**Known tested behavior:** the user tested Sekiro without Steam Input and
reported a virtual controller labeled `VIIPER Controller`. That visible
device name is **not guaranteed** by the classic ViGEmBus driver: a different
VIIPER/USB-IP backend can be present. The user's later cleanup removed the
controller test folder and ViGEmBus 1.22.0 but left unidentified VIIPER pieces
in place. Do not infer VIIPER's binaries, installation location, driver version
or profile settings from that name alone.

## Not included in this automated bootstrap

- VIIPER USB-IP kernel driver installation; upstream versions have different
  driver ABIs and one release's installer has had a trusted-root CA caveat.
- HidHide, ScpVBus, FakerInput or BthPS3 installation.
- Reconstruction of personal DS4Windows profile bytes absent from the old chat.
- Bypassing Windows elevation, restarting without permission, killing unrelated
  controller processes, or overwriting an existing working stack.

The driver is a machine component and cannot be embedded invisibly into a
normal non-elevated launcher. This project keeps the first-launch orchestration
inside Elmos World and checks its preconditions before starting.
