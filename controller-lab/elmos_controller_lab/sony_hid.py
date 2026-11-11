"""Optional raw HID sensor reader for supported Sony controllers.

It opens a shared read handle only. It does not send feature/output reports,
change firmware, pair devices, or take exclusive control of the controller.
"""
from __future__ import annotations

from typing import Any

from .sony_reports import SonySensorFrame, parse_sony_report


class SonyHIDSensorReader:
    def __init__(self, handle: Any, vendor_id: int, product_id: int, path: Any = None):
        self.handle = handle
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.path = path
        self.last_frame: SonySensorFrame | None = None
        self.error = ""

    @classmethod
    def open(cls, vendor_id: int, product_id: int, serial_number: str | None = None):
        if vendor_id != 0x054C or product_id not in (0x05C4, 0x09CC, 0x0CE6, 0x0DF2):
            return None
        try:
            import hid
            entries = hid.enumerate(vendor_id, product_id)
            candidates = [
                item for item in entries
                if item.get("path") and item.get("usage_page") == 0x01
                and item.get("usage") in (0x04, 0x05)
            ]
            if serial_number:
                matching = [item for item in candidates if item.get("serial_number") == serial_number]
                if matching:
                    candidates = matching
            if not candidates:
                candidates = [item for item in entries if item.get("path")]
            for item in candidates:
                handle = hid.device()
                try:
                    handle.open_path(item["path"])
                    handle.set_nonblocking(True)
                    return cls(handle, vendor_id, product_id, item.get("path"))
                except Exception:
                    try:
                        handle.close()
                    except Exception:
                        pass
            return None
        except Exception:
            return None

    def poll(self) -> SonySensorFrame | None:
        try:
            # Drain a small bounded number of reports so the caller gets the
            # newest sensor frame without blocking the SDL input loop.
            for _ in range(8):
                data = self.handle.read(128, timeout_ms=0)
                if not data:
                    break
                frame = parse_sony_report(self.vendor_id, self.product_id, bytes(data))
                if frame is not None:
                    self.last_frame = frame
        except Exception as exc:
            self.error = str(exc)
        return self.last_frame

    def close(self) -> None:
        try:
            self.handle.close()
        except Exception:
            pass
