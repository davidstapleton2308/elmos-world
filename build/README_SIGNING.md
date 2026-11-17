# Elmos World — Windows Smart App Control release requirements

Windows Event 3077 on November 17, 2026 blocked the Inno Setup extracted .tmp installer engine (Error 4551). This is not resolved by making a checksum, post-signing only the outer installer, or turning off a script execution policy.

The repository now supports **CA-backed Authenticode signing**:
- `build/ElmosWorld.iss` uses `SignTool=elmos` and `SignedUninstaller=yes` when built with `/DELMOS_SIGNED`. This signs the temporary setup copies in addition to the outer setup and uninstaller.
- `build/Sign_Windows_Release.ps1` signs the bundled `.exe`, `.dll`, and `.pyd` files, then builds the Inno setup with the same signing identity and verifies the final installer.

## Prerequisites

1. Obtain a **trusted CA-issued Authenticode Code Signing certificate** that qualifies for Microsoft Smart App Control. A self-signed certificate, an Inno `ISSigTool` signature, or a locally-added root CA is not a substitute for this requirement.
2. Install the certificate securely in `Cert:\CurrentUser\My` with a usable private key. Never put the private key, PFX password, PFX file, or secret in GitHub source or chat.
3. Install Windows SDK SignTool and Inno Setup 6 on a trusted Windows build machine.
4. Build the app using the existing Windows PyInstaller process. **Do not execute the unsigned installer on a Smart App Control-protected machine.**
5. Run `powershell.exe -NoProfile -File build\Sign_Windows_Release.ps1 -Thumbprint <CERTIFICATE_THUMBPRINT>` on the Windows build machine. It does not disable App Control or modify installed games.
6. Verify the final code signature with `Get-AuthenticodeSignature`, and test install/update on a separate Smart App Control-enabled Windows device before releasing it.
7. Publish **only successfully signed and tested releases** under the existing `ElmosWorld_Setup_MAJOR.MINOR.PATCH.exe` GitHub asset naming convention. The updater's SHA-256 sidecar must be regenerated from the signed installer.

The existing public GitHub Actions workflow still produces **unsigned development installers** because no trusted signing identity is configured. Passing its automated Windows smoke tests proves only that it installed on GitHub's runner; it does **not** establish Smart App Control compatibility.

For production automation, configure a code-signing service (e.g. Microsoft Artifact Signing) under a publisher-controlled Azure account, authenticate with restricted permissions, sign all executable components including Inno's temporary engine, and gate GitHub Release publication on signature verification. Service enrollment, identity verification and payment require actions by the certificate owner.

No per-app Smart App Control exception is supported. Keep Windows security protections enabled while preparing signing.
