"""Heartbeat protocol regression checks.

Source checks do not replace Windows bridge integration tests.
"""
from pathlib import Path
from unittest.mock import Mock

from elmos_controller_lab.bridge import BridgeClient

SOURCE = (Path(__file__).resolve().parents[1] / "bridge" / "Program.cs").read_text(encoding="utf-8")


def test_heartbeat_renews_only_existing_slot():
    start = SOURCE.index('case "heartbeat":')
    end = SOURCE.index('case "profiles":', start)
    handler = SOURCE[start:end]
    assert 'Controllers.ContainsKey(slot)' in handler
    assert 'RenewLease(slot);' in handler
    assert 'SubmitState' not in handler
    assert 'return new { renewed = true, slot };' in handler


def test_heartbeat_uses_acknowledged_request():
    client = BridgeClient()
    client.request = Mock(return_value={"renewed": True, "slot": "idle-0"})
    assert client.heartbeat("idle-0") is None
    client.request.assert_called_once_with("heartbeat", timeout=2.0, slot="idle-0")


def test_heartbeat_does_not_change_watchdog_timeout():
    assert 'TimeSpan.FromSeconds(3)' in SOURCE
    assert 'Stopwatch.GetElapsedTime(entry.Value) < InputTimeout' in SOURCE
