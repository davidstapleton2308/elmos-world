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

    def request(self, op, *, timeout, slot, state):
        assert op == "state"
        assert timeout == 2.0
        if self.fail:
            raise RuntimeError("state transport failed")
        self.calls.append(("state", slot, state))
        return {"submitted": True, "slot": slot}

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


def test_rejected_state_never_advances_lease():
    clock, bridge = Clock(), Bridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    bridge.fail = True
    with pytest.raises(RuntimeError):
        lease.submit({"buttons": ["A"]})
    clock.now = 1.5
    bridge.fail = False
    assert lease.submit({"buttons": ["A"]}) == "state"
    assert bridge.calls == [("state", "slot", {"buttons": ["A"]})]


def test_changed_state_is_acknowledged_not_fire_and_forget():
    class RejectingBridge(Bridge):
        def send_state(self, *_args):
            raise AssertionError("unacknowledged state path must not be used")
    bridge = RejectingBridge()
    lease = HealthyFrameLease(bridge, "slot", clock=Clock())
    assert lease.submit({"buttons": []}) == "state"


def test_state_acknowledgement_time_starts_idle_lease():
    """A slow acknowledged request must not trigger an early heartbeat."""
    clock = Clock()

    class SlowBridge(Bridge):
        def request(self, op, *, timeout, slot, state):
            clock.now += 0.8
            return super().request(op, timeout=timeout, slot=slot, state=state)

    bridge = SlowBridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    assert lease.submit({"buttons": []}) == "state"
    clock.now = 1.0  # only 0.2s after the acknowledged state
    assert lease.submit({"buttons": []}) == "idle"
    clock.now = 1.8
    assert lease.submit({"buttons": []}) == "heartbeat"
    assert [call[0] for call in bridge.calls] == ["state", "heartbeat"]


def test_failed_delayed_ack_does_not_cache_state():
    clock = Clock()

    class SlowBridge(Bridge):
        def request(self, op, *, timeout, slot, state):
            clock.now += 0.8
            return super().request(op, timeout=timeout, slot=slot, state=state)

    bridge = SlowBridge()
    lease = HealthyFrameLease(bridge, "slot", clock=clock)
    bridge.fail = True
    with pytest.raises(RuntimeError):
        lease.submit({"buttons": ["A"]})
    bridge.fail = False
    assert lease.submit({"buttons": ["A"]}) == "state"
    assert [call[0] for call in bridge.calls] == ["state"]
