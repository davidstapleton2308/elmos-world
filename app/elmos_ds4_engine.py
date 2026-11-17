"""Elmos-managed DS4Windows controller engine (classic Xbox 360 / ViGEmBus).

This wraps the exact classic controller mapper the owner previously verified in
Sekiro. It is intentionally NOT a second Xbox virtual feeder, and does not
install HidHide, change other mapper profiles, or alter Windows startup tasks.

The archived DS4Windows 3.3.3 ZIP is pinned to the GitHub release SHA-256 and
bundled during the Windows release build. Profiles live in the per-user folder.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile

RELEASE_URL = (
    "https://github.com/ds4windowsapp/DS4Windows/releases/"
    "download/ryochan7/ds4windows-3-3-3.zip"
)
RELEASE_SHA256 = "cf5619bcb51b82e4e1765276e9f67fb1e2d23dff968a653657acf35bafff8bf4"
ARCHIVE_NAME = "ds4windows-3-3-3.zip"
MAX_ARCHIVE_SIZE = 25 * 1024 * 1024
MAX_UNPACKED_SIZE = 280 * 1024 * 1024


def base_dir():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ElmosWorld" / "ElmosInput"


def bundled_archive():
    return Path(__file__).resolve().parent / "engines" / ARCHIVE_NAME


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_archive():
    source = bundled_archive()
    if source.is_file():
        if sha256_file(source) != RELEASE_SHA256:
            raise RuntimeError("Bundled DS4Windows archive failed SHA-256 verification")
        return source
    cache = base_dir() / "downloads" / ARCHIVE_NAME
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file() and sha256_file(cache) == RELEASE_SHA256:
        return cache
    partial = cache.with_suffix(".partial")
    try:
        request = urllib.request.Request(RELEASE_URL, headers={"User-Agent": "ElmosWorld-Input/1.0"})
        with urllib.request.urlopen(request, timeout=45) as remote, partial.open("wb") as output:
            size = 0
            while True:
                block = remote.read(128 * 1024)
                if not block:
                    break
                size += len(block)
                if size > MAX_ARCHIVE_SIZE:
                    raise RuntimeError("DS4Windows archive exceeds expected download size")
                output.write(block)
        if sha256_file(partial) != RELEASE_SHA256:
            raise RuntimeError("Downloaded DS4Windows archive failed SHA-256 verification")
        os.replace(partial, cache)
        return cache
    finally:
        partial.unlink(missing_ok=True)


def _locate_executable(directory):
    options = [
        p for p in directory.rglob("DS4Windows.exe")
        if p.is_file() and len(p.relative_to(directory).parts) <= 5
    ]
    return min(options, key=lambda p: len(p.parts)) if options else None


def install_portable(archive):
    """Extract only the pinned classic package into Elmos-owned user data.

    Never overwrite an existing installation. A version marker enables
    idempotent reuse without touching a user's own DS4Windows folder.
    """
    root = base_dir()
    target = root / "classic-ds4windows-3.3.3"
    marker = target / ".elmos-archive-sha256"
    if marker.is_file() and marker.read_text(encoding="ascii").strip() == RELEASE_SHA256:
        exe = _locate_executable(target)
        if exe:
            return exe
    root.mkdir(parents=True, exist_ok=True)
    staging = root / "classic-ds4windows-3.3.3.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        with zipfile.ZipFile(archive) as package:
            files = package.infolist()
            if len(files) > 900:
                raise RuntimeError("Unexpected DS4Windows archive entry count")
            total = 0
            for item in files:
                rel = Path(item.filename.replace("\\", "/"))
                if rel.is_absolute() or ".." in rel.parts or ":" in item.filename:
                    raise RuntimeError("Unsafe path inside DS4Windows archive")
                total += item.file_size
                if total > MAX_UNPACKED_SIZE:
                    raise RuntimeError("DS4Windows archive expands beyond allowed size")
                # Ignore symlinks in third-party archives instead of following them.
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise RuntimeError("DS4Windows archive contains a symbolic link")
            package.extractall(staging)
        exe = _locate_executable(staging)
        if not exe:
            raise RuntimeError("Verified DS4Windows archive has no DS4Windows.exe")
        (staging / ".elmos-archive-sha256").write_text(RELEASE_SHA256, encoding="ascii")
        if target.exists():
            raise RuntimeError("Elmos DS4Windows folder needs manual repair; refusing to overwrite profiles")
        os.replace(staging, target)
        return _locate_executable(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _other_ds4windows_running():
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["tasklist.exe", "/FI", "IMAGENAME eq DS4Windows.exe", "/NH"],
            capture_output=True, text=True, timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return any("ds4windows.exe" in line.lower() for line in result.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        # Unknown is safer than spawning a second competing mapper.
        raise RuntimeError("Cannot check whether DS4Windows already runs")


class DS4Engine:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._owned_process = None
        self._exe = None
        self._state = {
            "backend": "DS4Windows 3.3.3 / ViGEmBus Xbox 360",
            "running": False, "connected": False, "virtualConnected": False,
            "driverInstalled": False, "driverState": "unknown",
            "controllerMode": "managed DS4Windows",
            "stage": "idle", "lastError": "", "device": "",
            "message": "Elmos Input has not started",
        }

    def _publish(self, **changes):
        with self._lock:
            self._state.update(changes)
            stage = self._state.get("stage", "")
            message = self._state.get("message", "")
        print("[Elmos DS4 Input] " + stage + ": " + message, flush=True)

    def status(self):
        with self._lock:
            state = dict(self._state)
            proc = self._owned_process
        if proc is not None and proc.poll() is not None and state["stage"] == "running":
            state.update(running=False, stage="exited", message="DS4Windows exited; select Start Elmos Input to restart")
        return state

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            if self._owned_process and self._owned_process.poll() is None:
                return self.status()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="Elmos DS4Windows controller engine", daemon=True)
            self._thread.start()
        return self.status()

    def _run(self):
        try:
            if os.name != "nt":
                self._publish(stage="unsupported", message="The DS4 controller engine requires Windows")
                return
            from elmos_input_driver import is_installed, install_if_missing
            self._publish(stage="driver-check", message="Checking ViGEmBus before starting DS4Windows")
            if not is_installed():
                self._publish(driverState="installing", stage="driver-install",
                              message="Installing missing ViGEmBus with normal Windows approval")
                result = install_if_missing()
                if result.get("status") not in ("installed", "already-installed") or not is_installed():
                    raise RuntimeError("ViGEmBus not ready: " + str(result.get("message") or result.get("status")))
            self._publish(driverInstalled=True, driverState="installed", stage="preparing-engine",
                          message="Preparing verified classic DS4Windows Xbox 360 engine")
            if _other_ds4windows_running():
                # Do not kill or duplicate a separately managed program.
                self._publish(stage="external-mapper", running=False,
                              message="DS4Windows is already running outside Elmos World; exit it before starting Elmos Input")
                return
            archive = verified_archive()
            if self._stop.is_set():
                return
            exe = install_portable(archive)
            if self._stop.is_set():
                return
            self._exe = exe
            self._publish(stage="launching", message="Starting Elmos-managed DS4Windows with Xbox 360 profile")
            proc = subprocess.Popen(
                [str(exe), "-m"], cwd=str(exe.parent),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                self._owned_process = proc
            # Let DS4Windows initialize its profile and ViGEm client.
            if self._stop.wait(3):
                return
            if proc.poll() is not None:
                raise RuntimeError("DS4Windows exited during startup (code " + str(proc.returncode) +
                                   "); check the DS4Windows log and Windows .NET Desktop Runtime")
            # Signal its built-in controller service; preserves default profile.
            try:
                subprocess.run([str(exe), "-command", "start"],
                               cwd=str(exe.parent),
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError) as exc:
                print("[Elmos DS4 Input] Optional service start command failed:", repr(exc), flush=True)
            self._publish(stage="running", running=True,
                          message="DS4Windows running. Xbox 360 output uses its Default profile; check joy.cpl. "
                                  "If first-time setup appears, select the Xbox 360 profile once.")
            while not self._stop.wait(1):
                if proc.poll() is not None:
                    self._publish(stage="exited", running=False,
                                  message="DS4Windows exited (code " + str(proc.returncode) + ")")
                    return
        except Exception as exc:
            import traceback
            self._publish(stage="error", running=False, lastError=repr(exc),
                          message="Elmos Input engine failed: " + str(exc)[:300])
            traceback.print_exc()
        finally:
            if self._stop.is_set():
                self._shutdown_owned()

    def _shutdown_owned(self):
        with self._lock:
            proc, exe = self._owned_process, self._exe
            self._owned_process = None
        if not proc or proc.poll() is not None:
            return
        # Send graceful shutdown only to the Elmos-created DS4 instance.
        if exe:
            try:
                subprocess.run([str(exe), "-command", "shutdown"], cwd=str(exe.parent),
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._publish(stage="stopped", running=False, virtualConnected=False,
                      message="Elmos Input stopped with Elmos World")

    def stop(self, game_active=False):
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=8)
        self._shutdown_owned()
        return self.status()


ds4_engine = DS4Engine()
