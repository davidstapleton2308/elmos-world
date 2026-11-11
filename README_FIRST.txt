ELMOS WORLD 3.1.1 — SOFT LAUNCH / WINDOWS DESKTOP RELEASE
========================================================

THIS PACKAGE IS A WINDOWS BUILD KIT, NOT A PRECOMPILED EXE.
This revised build kit fixes a Python 3.12-only startup check that failed when
Windows had a different Python version or no Python runtime installed.
Python is needed for BUILDING on Windows, NOT for using the installed app.
The Windows Setup executable is generated on a Windows computer or via the
included GitHub Actions workflow. PyInstaller cannot create a trustworthy
Windows executable on this Linux packaging machine.

BUILD AND INSTALL ON YOUR WINDOWS LAPTOP
---------------------------------------
1. Extract the entire ZIP into a normal folder.
2. No need to guess which Python you have: the builder checks 64-bit Python 3.12, 3.13, or 3.11.
   If none is available, it offers to install Python 3.12 with winget.
   Alternatively get Python 3.12 x64 from https://www.python.org/downloads/windows/.
3. Double-click INSTALL_APP.bat to compile and then open the installer.
   Or use Build_Release.bat to create the installer without installing.
4. The script installs build-only Python packages in .buildvenv and builds
   dist\ElmosWorld\ElmosWorld.exe, with the matching icon.
5. It self-tests the compiled EXE before packaging. Then it uses Inno Setup to produce:
   dist_setup\ElmosWorld_Setup_3.1.1.exe
   If Inno Setup is missing it will try a standard winget install; if that
   fails, install it from https://jrsoftware.org/isdl.php and rerun the BAT.
6. INSTALL_APP.bat opens the resulting Setup.exe automatically. If you used
   Build_Release.bat, double-click Setup.exe yourself.
7. Use the new Elmos World desktop shortcut to open the standalone app.
   Python is NOT needed to use the installed compiled application.

The compiled installed app starts in its own fullscreen native WebView window.
The native PS-button menu and controller reader are included. It should not
open a console/PowerShell window in normal use.

UPDATING FROM YOUR OLD INSTALLATION
-----------------------------------
The old source-based C:\Gaming\ElmosWorld folder is NOT deleted or overwritten.
The new standalone app installs under:
  %LOCALAPPDATA%\Programs\Elmos World

Its built-in game library and preferences are read from the existing folders:
  %LOCALAPPDATA%\SteamMatch
  %LOCALAPPDATA%\ElmosWorld
Your game files remain wherever you already keep them (typically C:\Gaming).
Close your old Elmos World process before running the standalone app, and use
the NEW desktop shortcut created by Setup.

FUTURE UPDATES
--------------
Create a new numbered Setup.exe release using the SAME Inno Setup AppId.
Running the new Setup over the old installation updates app binaries while
leaving your game library, settings, and saved artwork data in AppData.
No background or automatic update mechanism is enabled in this release.

OPTIONAL GITHUB BUILD
---------------------
The .github/workflows/build-windows-release.yml file builds the installer on
a Windows runner. Place the contents of this ZIP in a GitHub repository and
run the workflow from Actions -> Build Elmos World Windows Setup -> Run workflow.
Download the Windows installer artifact when it finishes.
This workflow does NOT automatically publish a public release.

IMPORTANT NOTES
---------------
- WINDOWS 10/11, 64-bit. Microsoft Edge WebView2 Runtime required; it is
  normally installed on modern Windows versions.
- Build dependencies require internet during the initial compilation.
- Windows may show an 'Unknown publisher' warning because this personal soft
  launch executable is NOT code-signed. Do not bypass warnings for files from
  sources you don't trust.
- GeForce NOW launch entries still use shortcuts created by NVIDIA's app.
- This is a personal SOFT LAUNCH build, not a publicly audited installer.
- Use the included RELEASE_NOTES.txt and QA_CHECKLIST.txt for release testing.
- No changes to your working SSX/Xenia launch timing or game control logic.

BUILDER FIX (2026-11-11)
------------------------
- Detect x64 Python 3.11 / 3.12 / 3.13 via the Windows Python launcher or python.exe.
- Prevent the noisy PowerShell NativeCommandError when py.exe exists but 3.12 does not.
- Ask before installing Python 3.12 through winget if no supported version exists.
- Verify the compiled standalone app via --self-test before creating Setup.
- Keep release version 3.1.1 and the existing installer upgrade identity unchanged.
