"""Tested-layout parsers for Sony DualShock 4 and DualSense sensor reports.

Offsets are based on the Linux hid-playstation report structures. These
functions parse input only; they never send feature or output reports.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import MotionState, TouchContact


@dataclass(frozen=True)
class SonySensorFrame:
    motion: MotionState
    touchpads: tuple[TouchContact, ...]
    battery: float | None
    charging: bool
    battery_full: bool
    mic_muted: bool
    headphones_connected: bool
    touchpad_packet_counter: int
    sensor_timestamp: int


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little", signed=False)


def _s16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little", signed=True)


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little", signed=False)


def _touch_point(data: bytes, offset: int) -> TouchContact:
    contact = data[offset]
    x = data[offset + 1] | ((data[offset + 2] & 0x0F) << 8)
    y = ((data[offset + 2] >> 4) & 0x0F) | (data[offset + 3] << 4)
    active = (contact & 0x80) == 0
    return TouchContact(
        active=active, x=x, y=y, pressure=1.0 if active else 0.0,
        tracking_id=contact & 0x7F,
    )


def parse_dualshock4_report(report: bytes) -> SonySensorFrame | None:
    """Parse DS4 USB (0x01) and Bluetooth (0x11) input reports."""
    if not report:
        return None
    report_id = report[0]
    if report_id == 0x01 and len(report) >= 64:
        common = 1
        touch_count_offset = common + 32
        max_touch_reports = 3
    elif report_id == 0x11 and len(report) >= 78:
        common = 3
        touch_count_offset = common + 32
        max_touch_reports = 4
    else:
        return None

    timestamp = _u16(report, common + 9)
    gyro = tuple(_s16(report, common + 12 + i * 2) for i in range(3))
    accel = tuple(_s16(report, common + 18 + i * 2) for i in range(3))
    # Sony DS4 sensors use 1024 counts per degree/second and 8192 counts per g.
    motion = MotionState(
        gyro_x=gyro[0] / 1024.0,
        gyro_y=gyro[1] / 1024.0,
        gyro_z=gyro[2] / 1024.0,
        accel_x=accel[0] / 8192.0,
        accel_y=accel[1] / 8192.0,
        accel_z=accel[2] / 8192.0,
        raw_gyro_pitch=gyro[0],
        raw_gyro_yaw=gyro[1],
        raw_gyro_roll=gyro[2],
        raw_accel_x=accel[0],
        raw_accel_y=accel[1],
        raw_accel_z=accel[2],
    )

    status0 = report[common + 29]
    battery_level = status0 & 0x0F
    battery = min(100.0, battery_level * 10.0)
    charging = bool(status0 & 0x10)
    battery_full = battery_level >= 11

    count = min(report[touch_count_offset], max_touch_reports)
    touch_start = touch_count_offset + 1
    touchpads: tuple[TouchContact, ...] = ()
    touch_counter = 0
    if count > 0 and len(report) >= touch_start + count * 9:
        latest = touch_start + (count - 1) * 9
        touch_counter = report[latest]
        touchpads = (
            _touch_point(report, latest + 1),
            _touch_point(report, latest + 5),
        )

    return SonySensorFrame(
        motion=motion,
        touchpads=touchpads,
        battery=battery,
        charging=charging,
        battery_full=battery_full,
        mic_muted=False,
        headphones_connected=False,
        touchpad_packet_counter=touch_counter,
        sensor_timestamp=timestamp,
    )


def parse_dualsense_report(report: bytes) -> SonySensorFrame | None:
    """Parse DualSense USB (0x01) and Bluetooth (0x31) input reports."""
    if not report:
        return None
    report_id = report[0]
    if report_id == 0x01 and len(report) >= 64:
        body = 1
    elif report_id == 0x31 and len(report) >= 78:
        # Bluetooth adds a sequence/tag header before the common input body.
        body = 3
    else:
        return None

    gyro = tuple(_s16(report, body + 15 + i * 2) for i in range(3))
    accel = tuple(_s16(report, body + 21 + i * 2) for i in range(3))
    timestamp = _u32(report, body + 27)
    motion = MotionState(
        gyro_x=gyro[0] / 1024.0,
        gyro_y=gyro[1] / 1024.0,
        gyro_z=gyro[2] / 1024.0,
        accel_x=accel[0] / 8192.0,
        accel_y=accel[1] / 8192.0,
        accel_z=accel[2] / 8192.0,
        raw_gyro_pitch=gyro[0],
        raw_gyro_yaw=gyro[1],
        raw_gyro_roll=gyro[2],
        raw_accel_x=accel[0],
        raw_accel_y=accel[1],
        raw_accel_z=accel[2],
    )

    # Two 4-byte touch contacts follow the reserved byte.
    touchpads = (
        _touch_point(report, body + 32),
        _touch_point(report, body + 36),
    )
    status0 = report[body + 52]
    status1 = report[body + 53]
    battery_level = status0 & 0x0F
    battery = min(100.0, battery_level * 10.0)
    charging = bool(status0 & 0xF0)
    battery_full = battery_level >= 10

    return SonySensorFrame(
        motion=motion,
        touchpads=touchpads,
        battery=battery,
        charging=charging,
        battery_full=battery_full,
        mic_muted=bool(status1 & 0x04),
        headphones_connected=bool(status1 & 0x01),
        touchpad_packet_counter=report[body + 6],
        sensor_timestamp=timestamp,
    )


def parse_sony_report(vendor_id: int, product_id: int, report: bytes) -> SonySensorFrame | None:
    if vendor_id != 0x054C:
        return None
    if product_id in (0x05C4, 0x09CC):
        return parse_dualshock4_report(report)
    if product_id in (0x0CE6, 0x0DF2):
        return parse_dualsense_report(report)
    return None
