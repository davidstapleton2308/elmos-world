import math
from elmos_controller_lab.mapping import ActionLayer, Mapper, MappingProfile, StickTuning, shape_stick
from elmos_controller_lab.model import ControllerState, neutral_state


def test_neutral_stick_remains_neutral():
    assert shape_stick(0.0, 0.0, StickTuning()) == (0.0, 0.0)


def test_radial_deadzone_suppresses_noise():
    assert shape_stick(0.05, -0.04, StickTuning(deadzone=0.15)) == (0.0, 0.0)


def test_radial_deadzone_preserves_full_range():
    x, y = shape_stick(0.0, 1.0, StickTuning(deadzone=0.15))
    assert math.isclose(x, 0.0, abs_tol=1e-8)
    assert math.isclose(y, 1.0, abs_tol=1e-8)


def test_invert_and_sensitivity():
    x, y = shape_stick(0.5, 0.0, StickTuning(deadzone=0, invert_x=True, sensitivity=1.5))
    assert x < -0.7 and y == 0.0


def test_face_button_remapping():
    mapper = Mapper(MappingProfile(button_map={"south": "east", "east": "south"}))
    state = ControllerState(buttons={"south"}, axes={})
    out = mapper.map(state)
    assert out.buttons == {"east"}


def test_action_layer_hold_changes_mapping_and_sensitivity():
    profile = MappingProfile(
        layer=ActionLayer(activator="left_paddle", mode="hold",
                          button_map={"south": "north"}, axis_sensitivity=0.5)
    )
    mapper = Mapper(profile)
    normal = mapper.map(ControllerState(buttons={"south"}, axes={"left_x": 0.8}))
    shifted = mapper.map(ControllerState(buttons={"south", "left_paddle"}, axes={"left_x": 0.8}))
    assert normal.buttons == {"south"}
    assert shifted.buttons == {"north"}
    assert abs(shifted.axes["left_x"]) < abs(normal.axes["left_x"])


def test_action_layer_toggle_changes_on_rising_edge_only():
    mapper = Mapper(MappingProfile(layer=ActionLayer(
        activator="left_paddle", mode="toggle", button_map={"south": "north"})))
    assert mapper.map(ControllerState(buttons={"south"})).buttons == {"south"}
    assert mapper.map(ControllerState(buttons={"south", "left_paddle"})).buttons == {"north"}
    assert mapper.map(ControllerState(buttons={"south", "left_paddle"})).buttons == {"north"}
    assert mapper.map(ControllerState(buttons={"south"})).buttons == {"north"}
    assert mapper.map(ControllerState(buttons={"south", "left_paddle"})).buttons == {"south"}


def test_nan_inputs_cannot_escape_normalization():
    state = ControllerState(axes={"left_x": float("nan"), "left_trigger": float("inf")}).normalized()
    assert state.axes["left_x"] == 0
    assert state.axes["left_trigger"] == 0


def test_neutral_state_has_all_axes():
    assert set(neutral_state().axes) == {
        "left_x", "left_y", "right_x", "right_y", "left_trigger", "right_trigger"
    }
