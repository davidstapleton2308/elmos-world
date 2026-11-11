"""Early PyInstaller runtime hook for true Windows GUI (no-console) executables.

PyInstaller leaves standard I/O streams at None for WINDOWED subsystem builds.
Libraries that assume stdout or stderr has .write/.flush can fail during their
import-time initialization, before the launcher starts or can log the problem.

This explicit runtime hook runs before PyInstaller's package-supplied hooks.
It doesn't allocate a console, open any windows, or require elevated privileges.
"""
import os
import sys

if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
