from elmos_controller_lab.mapping import ActionLayer, Mapper, MappingProfile
from elmos_controller_lab.model import ControllerState


def test_keyboard_mouse_trigger_and_stick_actions():
    profile = MappingProfile(
        keyboard_map={"south": ["Space", "LeftShift"], "dpad_up": ["Up"]},
        trigger_keyboard_map={"left_trigger": ["LeftControl"]},
        mouse_map={"right_trigger": "left"},
        left_stick_as_wasd=True,
        right_stick_mouse=True,
        mouse_sensitivity=20,
    )
    output = Mapper(profile).map_actions(ControllerState(
        buttons={"south"}, dpad={"up"},
        axes={"left_y": 0.9, "right_x": 0.8, "left_trigger": 0.8, "right_trigger": 0.9},
    ))
    assert {"Space", "W", "Up"} <= output.keyboard_keys
    assert {"LeftShift", "LeftControl"} <= output.keyboard_modifiers
    assert output.mouse_buttons == {"left"}
    assert output.mouse_dx > 0
    assert output.mouse_dy == 0


def test_action_layer_overrides_keyboard_and_mouse_actions():
    profile = MappingProfile(
        keyboard_map={"south": ["Space"]},
        layer=ActionLayer(
            activator="left_paddle", mode="hold",
            keyboard_map={"south": ["Q"]},
            mouse_map={"south": "right"},
            right_stick_mouse=False,
        ),
    )
    output = Mapper(profile).map_actions(ControllerState(buttons={"south", "left_paddle"}))
    assert output.keyboard_keys == {"Q"}
    assert output.mouse_buttons == {"right"}
