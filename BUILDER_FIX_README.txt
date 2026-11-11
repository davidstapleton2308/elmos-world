ELMOS WORLD 3.1.1 — WINDOWS BUILDER FIX
========================================

This is the same standalone release as before, with a corrected build script.
The original error occurred because the script demanded `py -3.12`.
The Windows Python launcher can exist even when that Python version is absent.

DO THIS
1. Close any old Elmos World windows or build prompts.
2. Extract this ZIP into a new folder (do not run from inside the ZIP).
3. Double-click INSTALL_APP.bat.
4. If asked to install Python 3.12 via winget, choose Y to allow the standard
   Windows Package Manager installation (or install Python yourself first).
5. Let the builder generate the standalone application and the Setup installer.
6. Follow the Setup prompt. Your existing library and game files remain in place.

ALREADY HAVE PYTHON?
If you have a supported 64-bit Python 3.11, 3.12 or 3.13, the build script
uses it without installing another version.

IF IT STOPS AGAIN
Copy the final error and the last few build output lines. If the EXE was
created but Inno Setup is missing, use the official Inno Setup installer at
https://jrsoftware.org/isdl.php and re-run INSTALL_APP.bat.

VERIFICATION LIMITATION
This environment validated the source files and packaging tests. Only a
Windows computer can compile and test the actual Windows EXE and installer.
