from elmos_controller_lab.sony_reports import (
    parse_dualshock4_report,
    parse_dualsense_report,
    parse_sony_report,
)


def _put_s16(report, offset, value):
    report[offset:offset + 2] = int(value).to_bytes(2, "little", signed=True)


def _put_u16(report, offset, value):
    report[offset:offset + 2] = int(value).to_bytes(2, "little", signed=False)


def _put_touch(report, offset, tracking_id, x, y):
    report[offset] = tracking_id
    report[offset + 1] = x & 0xFF
    report[offset + 2] = ((x >> 8) & 0x0F) | ((y & 0x0F) << 4)
    report[offset + 3] = (y >> 4) & 0xFF


def test_ds4_usb_sensor_and_touchpad_parse():
    report = bytearray(64)
    report[0] = 0x01
    _put_u16(report, 10, 0x1234)
    _put_s16(report, 13, 1024)
    _put_s16(report, 15, -2048)
    _put_s16(report, 19, 8192)
    report[30] = 0x08
    report[33] = 1
    report[34] = 77
    _put_touch(report, 35, 0x01, 500, 200)
    _put_touch(report, 39, 0x80, 0, 0)

    frame = parse_dualshock4_report(bytes(report))
    assert frame is not None
    assert frame.motion.gyro_x == 1.0
    assert frame.motion.gyro_y == -2.0
    assert frame.motion.accel_x == 1.0
    assert frame.motion.raw_gyro_pitch == 1024
    assert frame.sensor_timestamp == 0x1234
    assert frame.battery == 80
    assert frame.touchpad_packet_counter == 77
    assert frame.touchpads[0].active is True
    assert frame.touchpads[0].x == 500
    assert frame.touchpads[0].y == 200
    assert frame.touchpads[1].active is False


def test_ds4_bluetooth_header_offsets():
    report = bytearray(78)
    report[0] = 0x11
    _put_u16(report, 12, 0x2345)
    _put_s16(report, 15, 512)
    _put_s16(report, 21, 4096)
    report[32] = 0x1A
    report[35] = 1
    report[36] = 9
    _put_touch(report, 37, 0x02, 1000, 400)

    frame = parse_dualshock4_report(bytes(report))
    assert frame is not None
    assert frame.motion.gyro_x == 0.5
    assert frame.motion.accel_x == 0.5
    assert frame.charging is True
    assert frame.touchpads[0].x == 1000


def test_dualsense_usb_sensor_touchpad_and_status_parse():
    report = bytearray(64)
    report[0] = 0x01
    _put_s16(report, 16, 2048)
    _put_s16(report, 18, -1024)
    _put_s16(report, 22, 8192)
    report[28:32] = (987654).to_bytes(4, "little")
    _put_touch(report, 33, 0x03, 1200, 700)
    _put_touch(report, 37, 0x80, 0, 0)
    report[53] = 0x8B
    report[54] = 0x05

    frame = parse_dualsense_report(bytes(report))
    assert frame is not None
    assert frame.motion.gyro_x == 2.0
    assert frame.motion.gyro_y == -1.0
    assert frame.motion.accel_x == 1.0
    assert frame.sensor_timestamp == 987654
    assert frame.battery == 100
    assert frame.battery_full is True
    assert frame.charging is True
    assert frame.mic_muted is True
    assert frame.headphones_connected is True
    assert frame.touchpads[0].x == 1200
    assert frame.touchpads[0].y == 700


def test_dualsense_bluetooth_header_offsets():
    report = bytearray(78)
    report[0] = 0x31
    _put_s16(report, 18, 1024)
    _put_s16(report, 24, 8192)
    report[30:34] = (123456).to_bytes(4, "little")
    _put_touch(report, 35, 0x01, 600, 300)
    report[55] = 0x04

    frame = parse_dualsense_report(bytes(report))
    assert frame is not None
    assert frame.motion.gyro_x == 1.0
    assert frame.motion.accel_x == 1.0
    assert frame.sensor_timestamp == 123456
    assert frame.touchpads[0].active is True


def test_sony_parser_rejects_unknown_or_truncated_reports():
    assert parse_dualshock4_report(b"") is None
    assert parse_dualshock4_report(bytes([0x01]) + bytes(10)) is None
    assert parse_dualsense_report(bytes([0x99]) + bytes(80)) is None
    assert parse_sony_report(0x045E, 0x028E, bytes(64)) is None
