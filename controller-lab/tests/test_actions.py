from elmos_controller_lab.actions import TemporalActionEngine
from elmos_controller_lab.mapping import Mapper, MappingProfile
from elmos_controller_lab.model import ControllerState


def test_tap_action_fires_on_release():
    engine = TemporalActionEngine()
    bindings = {"south": {"tap": {"gamepad": ["east"]}}}
    assert engine.process({"south"}, bindings, {}, 0.0).gamepad_buttons == set()
    released = engine.process(set(), bindings, {}, 0.1)
    assert released.gamepad_buttons == {"east"}


def test_hold_action_replaces_tap_after_threshold():
    engine = TemporalActionEngine()
    bindings = {"south": {
        "hold_ms": 200,
        "tap": {"keyboard": ["Space"]},
        "hold": {"keyboard": ["LeftShift"]},
    }}
    assert engine.process({"south"}, bindings, {}, 0.0).keyboard_keys == set()
    held = engine.process({"south"}, bindings, {}, 0.25)
    assert held.keyboard_modifiers == {"LeftShift"}
    assert engine.process(set(), bindings, {}, 0.3).keyboard_keys == set()


def test_double_tap_suppresses_pending_single_tap():
    engine = TemporalActionEngine()
    bindings = {"south": {
        "double_tap_ms": 250,
        "tap": {"gamepad": ["east"]},
        "double_tap": {"gamepad": ["north"]},
    }}
    engine.process({"south"}, bindings, {}, 0.0)
    engine.process(set(), bindings, {}, 0.05)
    double = engine.process({"south"}, bindings, {}, 0.1)
    assert double.gamepad_buttons == {"north"}
    assert engine.process(set(), bindings, {}, 0.15).gamepad_buttons == set()


def test_single_tap_waits_for_double_tap_window_then_fires():
    engine = TemporalActionEngine()
    bindings = {"south": {
        "double_tap_ms": 250,
        "tap": {"keyboard": ["Space"]},
        "double_tap": {"keyboard": ["Enter"]},
    }}
    engine.process({"south"}, bindings, {}, 0.0)
    engine.process(set(), bindings, {}, 0.05)
    result = engine.process(set(), bindings, {}, 0.31)
    assert result.keyboard_keys == {"Space"}


def test_turbo_pulses_at_configured_frequency():
    engine = TemporalActionEngine()
    bindings = {"south": {"turbo_hz": 10, "turbo": {"gamepad": ["south"]}}}
    assert engine.process({"south"}, bindings, {}, 0.01).gamepad_buttons == {"south"}
    assert engine.process({"south"}, bindings, {}, 0.06).gamepad_buttons == set()
    assert engine.process({"south"}, bindings, {}, 0.11).gamepad_buttons == {"south"}


def test_chord_emits_combined_action_and_suppresses_individual_buttons():
    profile = MappingProfile(chord_map={
        "left_shoulder+south": {"action": {"keyboard": ["F"]}, "suppress": True}
    })
    mapper = Mapper(profile)
    result = mapper.map_actions(ControllerState(buttons={"left_shoulder", "south"}))
    assert result.gamepad.buttons == set()
    assert result.keyboard_keys == {"F"}


def test_tap_binding_suppresses_default_gamepad_passthrough():
    profile = MappingProfile(action_bindings={
        "south": {"tap": {"gamepad": ["east"]}, "suppress": True}
    })
    mapper = Mapper(profile)
    pressed = mapper.map_actions(ControllerState(buttons={"south"}, timestamp=0.0))
    released = mapper.map_actions(ControllerState(timestamp=0.1))
    assert pressed.gamepad.buttons == set()
    assert released.gamepad.buttons == {"east"}
