"""Console-free PyInstaller entrypoint for Elmos Controller Lab commands."""
from __future__ import annotations

import sys
from pathlib import Path

# The controller package is embedded by ControllerRuntime.spec.
from elmos_controller_lab.lab import main


if __name__ == "__main__":
    raise SystemExit(main())
