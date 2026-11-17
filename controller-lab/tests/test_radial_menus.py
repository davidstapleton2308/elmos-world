from elmos_controller_lab.actions import radial_action_frame, radial_requires
from elmos_controller_lab.mapping import Mapper, MappingProfile
from elmos_controller_lab.model import ControllerState


def test_radial_8_way_resolves_diagonal_keyboard_action():
    config = {
        "deadzone": 0.25,
        "sectors_count": 8,
        "sectors": {"up_right": {"keyboard": ["E"]}},
    }
    result = radial_action_frame("right_stick", {"right_x": 0.7, "right_y": 0.7}, config)
    assert result.keyboard_keys == {"E"}


def test_radial_4_way_resolves_cardinal_gamepad_action():
    config = {
        "deadzone": 0.2,
        "sectors_count": 4,
        "sectors": {"up": {"gamepad": ["north"]}},
    }
    result = radial_action_frame("left_stick", {"left_x": 0.0, "left_y": 0.9}, config)
    assert result.gamepad_buttons == {"north"}


def test_radial_deadzone_emits_no_action():
    config = {"deadzone": 0.4, "sectors": {"right": {"keyboard": ["E"]}}}
    result = radial_action_frame("right_stick", {"right_x": 0.1, "right_y": 0.0}, config)
    assert result.keyboard_keys == set()


def test_mapper_suppresses_stick_and_emits_radial_sector():
    profile = MappingProfile(radial_menus={
        "right_stick": {
            "deadzone": 0.2,
            "sectors_count": 8,
            "suppress": True,
            "sectors": {"up": {"keyboard": ["1"]}},
        }
    })
    result = Mapper(profile).map_actions(ControllerState(axes={"right_y": 0.9}))
    assert result.gamepad.axes["right_y"] == 0
    assert result.keyboard_keys == {"1"}


def test_radial_output_requirements_detect_keyboard_and_mouse():
    menus = {"right_stick": {"sectors": {
        "up": {"keyboard": ["1"]}, "down": {"mouse": ["left"]}
    }}}
    assert radial_requires(menus, "keyboard") is True
    assert radial_requires(menus, "mouse") is True
    assert radial_requires(menus, "gamepad") is False
