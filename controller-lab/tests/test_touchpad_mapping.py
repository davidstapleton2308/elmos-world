from elmos_controller_lab.mapping import Mapper, MappingProfile
from elmos_controller_lab.model import ControllerState, TouchContact


def test_touchpad_can_drive_relative_virtual_mouse():
    mapper = Mapper(MappingProfile(touchpad_mode="mouse", touchpad_sensitivity=0.5))
    first = mapper.map_actions(ControllerState(touchpads=[
        TouchContact(active=True, x=500, y=400, tracking_id=1)
    ]))
    second = mapper.map_actions(ControllerState(touchpads=[
        TouchContact(active=True, x=520, y=410, tracking_id=1)
    ]))
    assert (first.mouse_dx, first.mouse_dy) == (0, 0)
    assert (second.mouse_dx, second.mouse_dy) == (10, 5)


def test_touchpad_can_drive_right_stick_and_release_to_center():
    mapper = Mapper(MappingProfile(touchpad_mode="right_stick"))
    active = mapper.map_actions(ControllerState(touchpads=[
        TouchContact(active=True, x=1440, y=270, tracking_id=2)
    ]))
    released = mapper.map_actions(ControllerState(touchpads=[
        TouchContact(active=False, tracking_id=2)
    ]))
    assert active.gamepad.axes["right_x"] > 0.4
    assert active.gamepad.axes["right_y"] > 0.4
    assert released.gamepad.axes["right_x"] == 0
    assert released.gamepad.axes["right_y"] == 0
