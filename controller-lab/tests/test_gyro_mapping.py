from elmos_controller_lab.mapping import Mapper, MappingProfile
from elmos_controller_lab.model import ControllerState, MotionState


def test_gyro_to_mouse_integrates_rate_over_frame_time():
    mapper = Mapper(MappingProfile(gyro_mode="mouse", gyro_sensitivity=10, gyro_deadzone=0))
    first = mapper.map_actions(ControllerState(
        motion=MotionState(gyro_x=50, gyro_y=100), timestamp=1.0
    ))
    second = mapper.map_actions(ControllerState(
        motion=MotionState(gyro_x=50, gyro_y=100), timestamp=1.01
    ))
    assert first.mouse_dx == 8
    assert first.mouse_dy == -4
    assert second.mouse_dx == 10
    assert second.mouse_dy == -5


def test_gyro_deadzone_filters_sensor_drift():
    mapper = Mapper(MappingProfile(gyro_mode="mouse", gyro_sensitivity=10, gyro_deadzone=1.0))
    output = mapper.map_actions(ControllerState(
        motion=MotionState(gyro_x=0.2, gyro_y=-0.3), timestamp=1.0
    ))
    assert output.mouse_dx == 0
    assert output.mouse_dy == 0


def test_gyro_to_right_stick_uses_calibrated_angular_velocity():
    mapper = Mapper(MappingProfile(gyro_mode="right_stick", gyro_sensitivity=10, gyro_deadzone=0))
    output = mapper.map_actions(ControllerState(
        motion=MotionState(gyro_x=-50, gyro_y=100), timestamp=1.0
    ))
    assert output.gamepad.axes["right_x"] > 0.4
    assert output.gamepad.axes["right_y"] > 0.1
