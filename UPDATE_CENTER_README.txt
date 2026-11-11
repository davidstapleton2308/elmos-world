ELMOS WORLD 3.1.1 — UPDATE CENTER

This ZIP is the updated SOURCE and Windows builder, NOT a compiled Windows Setup.exe.

FIRST INSTALL / UPGRADE:
1. Extract this ZIP on Windows.
2. Run INSTALL_APP.bat to build/install v3.1.1 (requires Python and Inno Setup).
   Or upload this folder as a public GitHub repository and run the supplied Actions workflow.
3. In Settings > Update Center, enter YOUR GitHub owner/repository and save.
4. Make a tagged release such as v3.1.1, using the workflow to publish Setup.exe + .sha256.
5. Future releases must increment version in all build metadata and workflow asset filenames.
6. Open Elmos World > Settings to check for updates; click Update & Restart.

SAFETY:
- Active game blocks installation. Local data stays outside the install directory.
- Downloads must match a SHA-256 checksum attached to the same latest GitHub release.
- Installer is NOT code-signed. GitHub SHA256 detects corruption/mismatch, not a compromised publisher.
- Backups are kept in the existing restore_points directory.
- A failed install does not automatically roll back. Use the previous Setup.exe and restore backup.
- Only official releases in your configured repo should be trusted; public repos expose source.
- Requires internet access and a packaged Windows executable; browser/dev mode cannot auto-install.
- Windows update flow has not been end-to-end tested here; validate on Windows before relying on it.
