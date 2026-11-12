"""Safe launcher integration for the standalone Elmos Controller Lab.

The launcher never installs a driver automatically. Virtual-device creation is
started only after an explicit per-game opt-in and a Windows UAC approval.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$", re.I)
_GAME_ID_MAX = 512
_LOCK = threading.RLock()


def _local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ElmosControllerLab"


def _read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError, TypeError, UnicodeError):
        return default


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class ControllerRuntime:
    """Owns per-game virtual-output preferences and one supervised lab session."""

    def __init__(self, *, app_dir: str | Path | None = None,
                 data_dir: str | Path | None = None, runner_path: str | Path | None = None,
                 bridge_path: str | Path | None = None, platform: str | None = None,
                 shell_execute=None, popen=None):
        self.app_dir = Path(app_dir) if app_dir else Path(__file__).resolve().parent
        self.data_dir = Path(data_dir) if data_dir else _local_root()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = self.data_dir / "sessions"
        self.profiles_file = self.data_dir / "launcher_profiles.json"
        self.global_file = self.data_dir / "automatic_input.json"
        self.status_file = self.data_dir / "runtime_status.json"
        self.platform = platform or sys.platform
        self._shell_execute = shell_execute or self._shell_execute_windows
        self._popen = popen or subprocess.Popen
        self.runner_path = Path(runner_path) if runner_path else self._first_existing([
            self.app_dir / "controller-runtime" / "ElmosControllerRuntime.exe",
            self.app_dir.parent / "controller-runtime" / "ElmosControllerRuntime.exe",
            self.app_dir.parent / "dist" / "ElmosWorld" / "controller-runtime" / "ElmosControllerRuntime.exe",
        ])
        self.bridge_path = Path(bridge_path) if bridge_path else self._first_existing([
            self.app_dir / "controller-lab" / "bridge" / "publish" / "Elmos.ControllerLab.Bridge.exe",
            self.app_dir.parent / "controller-lab" / "bridge" / "publish" / "Elmos.Controller.Bridge.exe",
            self.app_dir.parent / "controller-lab" / "bridge" / "publish" / "Elmos.ControllerLab.Bridge.exe",
        ])

    @staticmethod
    def _first_existing(paths: list[Path]) -> Path:
        return next((p for p in paths if p.is_file()), paths[0])

    @staticmethod
    def _shell_execute_windows(executable: str, parameters: str, working_directory: str) -> int:
        if os.name != "nt":
            raise RuntimeError("Virtual Windows controllers are available only on Windows 10/11.")
        import ctypes
        shell = ctypes.windll.shell32
        shell.ShellExecuteW.restype = ctypes.c_void_p
        result = shell.ShellExecuteW(None, "runas", executable, parameters, working_directory, 0)
        return int(result or 0)

    def _profiles(self) -> dict[str, Any]:
        data = _read_json(self.profiles_file, {"schema": 1, "games": {}})
        if not isinstance(data, dict) or not isinstance(data.get("games"), dict):
            return {"schema": 1, "games": {}}
        return data

    def automatic_preferences(self) -> dict[str, Any]:
        prefs = _read_json(self.global_file, {})
        if not isinstance(prefs, dict):
            prefs = {}
        return {
            "enabled": prefs.get("enabled") is True,
            "defaultProfile": "xbox-360-wired",
            "driverApprovalRequired": True,
        }

    def set_automatic_preferences(self, enabled: bool) -> dict[str, Any]:
        if type(enabled) is not bool:
            raise ValueError("Automatic controller support must be on or off.")
        with _LOCK:
            _atomic_json(self.global_file, {"schema": 1, "enabled": enabled,
                                            "updatedAt": int(time.time())})
        return self.automatic_preferences()

    def get_game_profile(self, game_id: str) -> dict[str, Any]:
        game_id = str(game_id or "")
        if not game_id or len(game_id) > _GAME_ID_MAX:
            raise ValueError("Invalid game identity.")
        saved = self._profiles()["games"]
        value = saved.get(game_id, {})
        if not isinstance(value, dict):
            value = {}
        # When the user has enabled automatic translation once, unconfigured
        # games inherit it. Explicit per-game settings override the default.
        inherited_auto_start = self.automatic_preferences()["enabled"]
        profile_id = value.get("profileId", "xbox-360-wired")
        if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
            profile_id = "xbox-360-wired"
        device_index = value.get("deviceIndex", 0)
        if type(device_index) is not int or not 0 <= device_index <= 63:
            device_index = 0
        device_guid = value.get("deviceGuid", "")
        if not isinstance(device_guid, str) or len(device_guid) > 128 or any(ord(ch) < 32 for ch in device_guid):
            device_guid = ""
        return {
            "gameId": game_id,
            "profileId": profile_id,
            "deviceIndex": device_index,
            "deviceGuid": device_guid,
            "autoStart": value.get("autoStart", inherited_auto_start) is True,
            "inheritedAutoStart": "autoStart" not in value,
            "rate": 120,
        }

    def save_game_profile(self, game_id: str, profile_id: str,
                          device_index: int = 0, auto_start: bool = False,
                          device_guid: str = "") -> dict[str, Any]:
        game_id = str(game_id or "")
        if not game_id or len(game_id) > _GAME_ID_MAX:
            raise ValueError("Invalid game identity.")
        if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
            raise ValueError("Choose a valid virtual-controller profile.")
        if type(device_index) is not int or not 0 <= device_index <= 63:
            raise ValueError("Choose a valid physical controller index.")
        if type(auto_start) is not bool:
            raise ValueError("Automatic controller start must be enabled or disabled.")
        if not isinstance(device_guid, str) or len(device_guid) > 128 or any(ord(ch) < 32 for ch in device_guid):
            raise ValueError("Invalid physical controller identity.")
        with _LOCK:
            data = self._profiles()
            data["schema"] = 1
            data["games"][game_id] = {
                "profileId": profile_id,
                "deviceIndex": device_index,
                "deviceGuid": device_guid,
                "autoStart": auto_start,
                "updatedAt": int(time.time()),
            }
            _atomic_json(self.profiles_file, data)
        return self.get_game_profile(game_id)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if type(pid) is not int or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (OSError, ValueError):
            return False

    def status(self) -> dict[str, Any]:
        value = _read_json(self.status_file, {})
        if not isinstance(value, dict) or not value:
            return {"state": "stopped", "running": False, "message": "No virtual-controller session."}
        state = str(value.get("state", "stopped"))
        pid = value.get("pid", 0)
        updated = value.get("updatedAt", 0)
        if state in ("starting", "running", "stopping") and type(pid) is int and pid > 0:
            if not self._pid_alive(pid):
                value["state"] = "failed" if value.get("error") else "stopped"
                value["message"] = value.get("error") or "Controller runtime exited; virtual-device watchdog will release stale output."
                value["running"] = False
                _atomic_json(self.status_file, value)
                return value
        elif state == "starting" and (not isinstance(updated, (int, float)) or time.time() - updated > 45):
            value["state"] = "failed"
            value["message"] = "Controller startup did not complete. Check driver setup and the Windows UAC prompt."
            value["running"] = False
            _atomic_json(self.status_file, value)
            return value
        value["running"] = state == "running"
        return value

    def _write_status(self, state: str, **extra: Any) -> None:
        value = {
            "state": state,
            "running": state == "running",
            "pid": 0,
            "updatedAt": time.time(),
            **extra,
        }
        _atomic_json(self.status_file, value)

    def _elevated(self, arguments: list[str]) -> dict[str, Any]:
        if self.platform != "win32":
            raise RuntimeError("Virtual Windows controllers require Windows 10/11.")
        if not self.runner_path.is_file():
            raise RuntimeError("The Elmos Controller runtime is not installed in this build. Rebuild or update Elmos World.")
        if not self.bridge_path.is_file():
            raise RuntimeError("The Elmos virtual-device bridge is missing. Rebuild or update Elmos World.")
        params = subprocess.list2cmdline(arguments)
        result = int(self._shell_execute(str(self.runner_path), params, str(self.runner_path.parent)))
        if result <= 32:
            if result in (5, 1223):
                raise RuntimeError("Windows administrator approval was declined. No virtual device was created.")
            raise RuntimeError(f"Windows could not start the elevated controller helper (ShellExecute code {result}).")
        return {"accepted": True, "shellResult": result}

    def start(self, game_id: str, *, require_auto: bool = False) -> dict[str, Any]:
        config = self.get_game_profile(game_id)
        if require_auto and not config["autoStart"]:
            return {"started": False, "state": "disabled", "message": "Per-game controller auto-start is disabled."}
        current = self.status()
        if current.get("state") in ("starting", "running", "stopping"):
            if current.get("gameId") == game_id:
                return {"started": True, "alreadyRunning": True, "state": current.get("state")}
            raise RuntimeError("Another virtual-controller session is already active. Stop it before switching games.")
        if self.platform != "win32":
            raise RuntimeError("Virtual Windows controllers require Windows 10/11.")
        if not self.runner_path.is_file() or not self.bridge_path.is_file():
            raise RuntimeError("Controller Lab runtime files are missing from this installation.")
        session_id = secrets.token_hex(12)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        stop_file = self.sessions_dir / (session_id + ".stop")
        watch_file = self.sessions_dir / (session_id + ".gamepid")
        status = {
            "state": "starting", "running": False, "pid": 0, "sessionId": session_id,
            "gameId": game_id, "profileId": config["profileId"], "deviceIndex": config["deviceIndex"],
            "stopFile": str(stop_file), "watchFile": str(watch_file), "updatedAt": time.time(),
            "message": "Waiting for Windows administrator approval and virtual-device startup.",
        }
        _atomic_json(self.status_file, status)
        args = [
            "--bridge", str(self.bridge_path), "emulate",
            "--profile", config["profileId"], "--game", game_id,
            "--device", str(config["deviceIndex"]), "--rate", str(config["rate"]),
            "--stop-file", str(stop_file), "--watch-file", str(watch_file),
            "--status-file", str(self.status_file),
        ]
        if config.get("deviceGuid"):
            args += ["--device-guid", config["deviceGuid"]]
        try:
            result = self._elevated(args)
        except Exception as exc:
            status.update({"state": "failed", "running": False, "error": str(exc),
                           "message": str(exc), "updatedAt": time.time()})
            _atomic_json(self.status_file, status)
            raise
        return {"started": True, "state": "starting", "message": status["message"], **result}

    def start_for_game(self, game_id: str) -> dict[str, Any] | None:
        config = self.get_game_profile(game_id)
        if not config["autoStart"]:
            return None
        return self.start(game_id, require_auto=True)

    def attach_game_process(self, pid: int) -> bool:
        current = self.status()
        watch_file = current.get("watchFile")
        if current.get("state") not in ("starting", "running") or not watch_file:
            return False
        if type(pid) is not int or pid <= 0:
            return False
        path = Path(watch_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(str(pid), encoding="ascii")
        os.replace(temporary, path)
        return True

    def wait_ready(self, timeout: float = 3.0) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, min(float(timeout), 8.0))
        while time.monotonic() < deadline:
            status = self.status()
            if status.get("state") in ("running", "failed", "stopped"):
                return status
            time.sleep(0.15)
        return self.status()

    def stop(self) -> dict[str, Any]:
        current = self.status()
        if current.get("state") not in ("starting", "running", "stopping"):
            return {"requested": False, "state": current.get("state", "stopped"),
                    "message": "No active virtual-controller session."}
        stop_file = current.get("stopFile")
        if not stop_file:
            raise RuntimeError("The active controller session has no safe stop handle.")
        path = Path(stop_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stop", encoding="ascii")
        return {"requested": True, "state": "stop-requested",
                "message": "Stop requested. The helper will neutralize and destroy its virtual devices."}

    def open_gui(self, game_id: str = "", profile_id: str = "") -> dict[str, Any]:
        if self.platform != "win32":
            raise RuntimeError("The graphical Controller Lab is available on Windows.")
        if not self.runner_path.is_file() or not self.bridge_path.is_file():
            raise RuntimeError("Controller Lab runtime files are missing from this installation.")
        args = [str(self.runner_path), "--bridge", str(self.bridge_path), "gui"]
        if game_id:
            args += ["--game", str(game_id)]
        if profile_id and _PROFILE_ID.fullmatch(profile_id):
            args += ["--profile", profile_id]
        process = self._popen(args, cwd=str(self.runner_path.parent),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                              close_fds=True)
        return {"opened": True, "pid": getattr(process, "pid", None),
                "message": "Elmos Controller Lab opened in a separate window."}

    def install_driver(self) -> dict[str, Any]:
        result = self._elevated(["--bridge", str(self.bridge_path), "install-driver"])
        return {"requested": True, "message": "Driver setup requested. Review and approve the Windows UAC prompt.",
                **result}

    def catalog(self) -> dict[str, Any]:
        if not self.bridge_path.is_file():
            raise RuntimeError("The virtual-device bridge is missing from this installation.")
        candidates = [self.app_dir / "controller-lab", self.app_dir.parent / "controller-lab"]
        lab_root = next((p for p in candidates if (p / "elmos_controller_lab").is_dir()), None)
        if lab_root and str(lab_root) not in sys.path:
            sys.path.insert(0, str(lab_root))
        try:
            from elmos_controller_lab.bridge import BridgeClient
            with BridgeClient(self.bridge_path) as bridge:
                status = bridge.request("status", timeout=15)
                result = bridge.request("profiles", timeout=30)
        except Exception as exc:
            raise RuntimeError("Could not read the controller catalogue: " + str(exc)[:240]) from exc
        profiles = []
        for item in result.get("profiles", []):
            if "keyboard" in str(item.get("type", "")).casefold() or "mouse" in str(item.get("type", "")).casefold():
                continue
            profiles.append(item)
        return {
            "driverInstalled": bool(status.get("driverInstalled")),
            "driverPrepared": bool(status.get("driverPrepared")),
            "elevated": bool(status.get("elevated")),
            "profileCount": len(profiles),
            "profiles": profiles,
        }
