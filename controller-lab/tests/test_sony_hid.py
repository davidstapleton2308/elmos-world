import sys
from types import SimpleNamespace
from unittest.mock import patch

from elmos_controller_lab.sony_hid import SonyHIDSensorReader


def test_sony_hid_reader_opens_shared_handle_and_reads_latest_report():
    report = bytearray(64)
    report[0] = 0x01
    report[13:15] = (1024).to_bytes(2, "little", signed=True)

    class FakeHandle:
        def __init__(self):
            self.opened_path = None
            self.nonblocking = False
            self.read_count = 0
            self.closed = False

        def open_path(self, path):
            self.opened_path = path

        def set_nonblocking(self, value):
            self.nonblocking = bool(value)

        def read(self, _size, timeout_ms=0):
            assert timeout_ms == 0
            self.read_count += 1
            return list(report) if self.read_count == 1 else []

        def close(self):
            self.closed = True

    handle = FakeHandle()
    fake_hid = SimpleNamespace(
        enumerate=lambda vendor, product: [{
            "path": b"fake-sony-controller", "usage_page": 1, "usage": 5,
        }],
        device=lambda: handle,
    )
    with patch.dict(sys.modules, {"hid": fake_hid}):
        reader = SonyHIDSensorReader.open(0x054C, 0x05C4)
        assert reader is not None
        assert handle.opened_path == b"fake-sony-controller"
        assert handle.nonblocking is True
        frame = reader.poll()
        assert frame is not None
        assert frame.motion.gyro_x == 1.0
        reader.close()
        assert handle.closed is True


def test_sony_hid_reader_ignores_non_sony_profiles():
    assert SonyHIDSensorReader.open(0x045E, 0x028E) is None
    assert SonyHIDSensorReader.open(0x054C, 0x1234) is None
