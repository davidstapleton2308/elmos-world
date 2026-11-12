"""Deterministic tests for heartbeat scheduling without real hardware."""
import pytest

from elmos_controller_lab.healthy_lease import HealthyFrameLease


class Clock:
    now = 0.0
    def __call__(self):
        return self.now


class Bridge:
    def __init__(self):
        self.calls = []
        self.fail = False

    def send_state(self, slot, state):
        if self.fail:
            raise RuntimeError("state transport failed")
        self.calls.append(("state", slot, state))

    def heartbeat(self, slot):
        if self.fail:
            raise RuntimeError("heartbeat transport failed")
        self.calls.append(("heartbeat", slot))


def test_changed_state_immediate_and_idle_heartbeat():
    clock, bridge = Clock(), Bridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    assert lease.submit({"buttons": ["A"]}) == "state"
    clock.now = 0.99
    assert lease.submit({"buttons": ["A"]}) == "idle"
    clock.now = 1.0
    assert lease.submit({"buttons": ["A"]}) == "heartbeat"
    clock.now = 1.5
    assert lease.submit({"buttons": ["B"]}) == "state"
    assert [call[0] for call in bridge.calls] == ["state", "heartbeat", "state"]


def test_nested_mutation_is_not_mistaken_for_idle():
    clock, bridge = Clock(), Bridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    state = {"axes": {"left_x": 0.0}}
    lease.submit(state)
    state["axes"]["left_x"] = 0.8
    assert lease.submit(state) == "state"


def test_failed_heartbeat_is_not_recorded_as_success():
    clock, bridge = Clock(), Bridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    lease.submit({"buttons": []})
    clock.now = 1.0
    bridge.fail = True
    with pytest.raises(RuntimeError):
        lease.submit({"buttons": []})
    bridge.fail = False
    assert lease.submit({"buttons": []}) == "heartbeat"


def test_failed_state_is_retried():
    clock, bridge = Clock(), Bridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    bridge.fail = True
    with pytest.raises(RuntimeError):
        lease.submit({"buttons": ["A"]})
    bridge.fail = False
    assert lease.submit({"buttons": ["A"]}) == "state"


def test_interval_guard():
    for interval in (-1, 0, 3, 4):
        with pytest.raises(ValueError):
            HealthyFrameLease(Bridge(), "slot", interval=interval)
