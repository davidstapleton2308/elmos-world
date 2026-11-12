"""Deterministic, read-only readiness classification for Elmos Controller Lab.

Exit codes are consumed by the Windows installer. A missing driver is a
recoverable optional feature, not a reason to abort the application install.
"""
from __future__ import annotations

EXPECTED_DRIVER_SDK_VERSION = "2.1.0"

EXIT_READY = 0
EXIT_DRIVER_MISSING = 10
EXIT_DRIVER_UNPREPARED = 11
EXIT_DRIVER_VERSION_MISMATCH = 12
EXIT_BRIDGE_UNAVAILABLE = 20
EXIT_BRIDGE_MISSING = 21
EXIT_UNSUPPORTED_PLATFORM = 30


def evaluate_prerequisites(status, *, bridge_exists=True, platform="win32"):
    """Convert bridge status into a stable installer-facing result.

    This function performs no I/O, installs nothing, and never treats an
    unknown result as success. A physical controller is intentionally not a
    prerequisite: it may be connected later.
    """
    if platform != "win32":
        return {
            "ready": False, "state": "unsupported_platform",
            "exitCode": EXIT_UNSUPPORTED_PLATFORM,
            "message": "Virtual controller translation requires Windows 10/11.",
            "driverInstalled": False, "driverPrepared": False,
        }
    if not bridge_exists:
        return {
            "ready": False, "state": "bridge_missing",
            "exitCode": EXIT_BRIDGE_MISSING,
            "message": "The bundled virtual-controller bridge is missing.",
            "driverInstalled": False, "driverPrepared": False,
        }
    if not isinstance(status, dict):
        return {
            "ready": False, "state": "bridge_unavailable",
            "exitCode": EXIT_BRIDGE_UNAVAILABLE,
            "message": "The virtual-controller bridge could not report its status.",
            "driverInstalled": False, "driverPrepared": False,
        }

    architecture = str(status.get("architecture") or "").upper()
    if architecture not in ("X64", "AMD64"):
        return {
            "ready": False, "state": "unsupported_architecture",
            "exitCode": EXIT_UNSUPPORTED_PLATFORM,
            "message": "The virtual-controller bridge did not positively report an x64 architecture.",
            "driverInstalled": bool(status.get("driverInstalled") is True),
            "driverPrepared": bool(status.get("driverPrepared") is True),
            "architecture": architecture or None,
        }

    installed = status.get("driverInstalled") is True
    prepared = status.get("driverPrepared") is True
    sdk_version = str(status.get("backendSdkVersion") or "")
    common = {
        "driverInstalled": installed,
        "driverPrepared": prepared,
        "backendSdkVersion": sdk_version,
        "architecture": architecture or None,
    }
    if not installed:
        return {
            **common, "ready": False, "state": "driver_missing",
            "exitCode": EXIT_DRIVER_MISSING,
            "message": "The Elmos virtual-controller driver is not installed.",
        }
    if sdk_version != EXPECTED_DRIVER_SDK_VERSION:
        return {
            **common, "ready": False, "state": "driver_version_mismatch",
            "exitCode": EXIT_DRIVER_VERSION_MISMATCH,
            "message": "The bridge did not positively confirm the expected driver SDK version.",
        }
    if not prepared:
        return {
            **common, "ready": False, "state": "driver_unprepared",
            "exitCode": EXIT_DRIVER_UNPREPARED,
            "message": "The virtual-controller driver is installed but has not been prepared for this Elmos build.",
        }
    return {
        **common, "ready": True, "state": "ready",
        "exitCode": EXIT_READY,
        "message": "Virtual-controller driver and preparation version are ready.",
    }
