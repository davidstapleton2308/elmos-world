"""JSON-lines client for the isolated Windows virtual-device host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import uuid
from typing import Any, Callable


def default_bridge_path() -> Path:
    override = os.environ.get("ELMOS_CONTROLLER_BRIDGE")
    if override:
        return Path(override)
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / "bridge" / "publish" / "Elmos.ControllerLab.Bridge.exe",
        root / "bridge" / "bin" / "Release" / "net10.0-windows10.0.26100.0" / "win-x64" / "Elmos.ControllerLab.Bridge.exe",
        root / "bridge" / "bin" / "Release" / "net10.0-windows10.0.26100.0" / "Elmos.ControllerLab.Bridge.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


class BridgeError(RuntimeError):
    pass


class BridgeClient:
    def __init__(self, executable: str | Path | None = None,
                 on_event: Callable[[dict[str, Any]], None] | None = None):
        self.executable = Path(executable) if executable else default_bridge_path()
        self.on_event = on_event
        self.process: subprocess.Popen[str] | None = None
        self._pending: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._stderr_tail: queue.Queue[str] = queue.Queue(maxsize=100)
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        if not self.executable.exists():
            raise BridgeError(
                f"Virtual-device bridge not found: {self.executable}. "
                "Run scripts/Build-ControllerLab.ps1 first."
            )
        self.process = subprocess.Popen(
            [str(self.executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True, name="Elmos virtual bridge")
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True, name="Elmos bridge diagnostics")
        self._reader.start()
        self._stderr_reader.start()

    def _read_stdout(self) -> None:
        process = self.process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            if request_id:
                with self._lock:
                    target = self._pending.get(str(request_id))
                if target:
                    target.put(message)
            elif self.on_event:
                try:
                    self.on_event(message)
                except Exception:
                    pass
        with self._lock:
            pending = list(self._pending.values())
        for target in pending:
            target.put({"ok": False, "error": "BridgeClosed", "message": "Virtual bridge closed unexpectedly."})

    def _read_stderr(self) -> None:
        process = self.process
        if not process or not process.stderr:
            return
        for line in process.stderr:
            try:
                self._stderr_tail.put_nowait(line.rstrip())
            except queue.Full:
                try:
                    self._stderr_tail.get_nowait()
                    self._stderr_tail.put_nowait(line.rstrip())
                except queue.Empty:
                    pass

    def diagnostics(self) -> list[str]:
        rows: list[str] = []
        while True:
            try:
                rows.append(self._stderr_tail.get_nowait())
            except queue.Empty:
                return rows

    def request(self, op: str, timeout: float = 15.0, **payload: Any) -> dict[str, Any]:
        self.start()
        if not self.process or not self.process.stdin:
            raise BridgeError("Virtual bridge did not start.")
        request_id = uuid.uuid4().hex
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[request_id] = response_queue
        try:
            message = {"id": request_id, "op": op, **payload}
            with self._write_lock:
                self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
                self.process.stdin.flush()
            try:
                response = response_queue.get(timeout=timeout)
            except queue.Empty as exc:
                detail = "\n".join(self.diagnostics()[-8:])
                raise BridgeError(f"Bridge timed out during {op}. {detail}") from exc
            if not response.get("ok"):
                raise BridgeError(response.get("message", "Virtual bridge request failed."))
            return response.get("result", {})
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def send_state(self, slot: str, state: dict[str, Any]) -> None:
        self.start()
        if not self.process or not self.process.stdin:
            raise BridgeError("Virtual bridge is not running.")
        message = {"op": "state", "slot": slot, "state": state}
        with self._write_lock:
            self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.process.stdin.flush()

    def send_keyboard(self, slot: str, keys: list[str], modifiers: list[str] | None = None) -> None:
        self._send_unacknowledged({
            "op": "keyboard", "slot": slot, "keys": keys,
            "modifiers": modifiers or [],
        })

    def send_mouse(self, slot: str, buttons: list[str] | None = None,
                   x: int = 0, y: int = 0, wheel: int = 0, pan: int = 0) -> None:
        self._send_unacknowledged({
            "op": "mouse", "slot": slot, "buttons": buttons or [],
            "x": int(x), "y": int(y), "wheel": int(wheel), "pan": int(pan),
        })

    def _send_unacknowledged(self, message: dict[str, Any]) -> None:
        self.start()
        if not self.process or not self.process.stdin:
            raise BridgeError("Virtual bridge is not running.")
        with self._write_lock:
            self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\\n")
            self.process.stdin.flush()

    def close(self) -> None:
        process = self.process
        if not process:
            return
        if process.poll() is None:
            try:
                self.request("shutdown", timeout=5)
            except Exception:
                process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        self.process = None

    def __enter__(self) -> "BridgeClient":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
