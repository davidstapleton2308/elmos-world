from elmos_controller_lab.model import ControllerState, MotionState, TouchContact


def test_canonical_y_and_trigger_ranges():
    state = ControllerState(axes={"left_x": 2, "left_y": -2, "left_trigger": 0.4, "right_trigger": 9}).normalized()
    assert state.axes["left_x"] == 1
    assert state.axes["left_y"] == -1
    assert state.axes["left_trigger"] == 0.4
    assert state.axes["right_trigger"] == 1


def test_wire_model_preserves_advanced_features():
    state = ControllerState(
        buttons={"south", "guide"}, dpad={"up", "right"},
        motion=MotionState(gyro_x=10, accel_y=1),
        touchpads=[TouchContact(active=True, x=900, y=500, pressure=0.7, tracking_id=2)],
        battery=87, charging=True,
    )
    wire = state.to_wire()
    assert wire["buttons"] == ["guide", "south"]
    assert wire["dpad"] == ["right", "up"]
    assert wire["motion"]["gyro_x"] == 10
    assert wire["touchpads"][0]["active"] is True
    assert wire["battery"] == 87
    assert wire["charging"] is True
