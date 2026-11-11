"""Source-level regression checks for the Windows bridge lease watchdog.

These do not replace a Windows runtime or HID hardware test.
"""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "bridge" / "Program.cs").read_text(encoding="utf-8")


def test_watchdog_uses_monotonic_time_and_bounded_lease():
    assert "Stopwatch.GetTimestamp()" in SOURCE
    assert "Stopwatch.GetElapsedTime(entry.Value) < InputTimeout" in SOURCE
    assert "TimeSpan.FromSeconds(3)" in SOURCE
    assert "new Timer(CheckInputLeases, null, 250, 250)" in SOURCE


def test_each_input_type_renews_lease_after_successful_submission():
    for submit in (
        "controller.SubmitState(in frame);",
        "controller.SubmitKeyboard(modifiers, keys.ToArray());",
        "controller.SubmitMouse(in frame);",
    ):
        assert submit + "\n                RenewLease(slot);" in SOURCE


def test_expired_devices_are_removed_and_disposed_under_lock():
    start = SOURCE.index("private static void CheckInputLeases")
    end = SOURCE.index("private static bool IsElevated", start)
    method = SOURCE[start:end]
    assert "lock (DeviceLock)" in method
    assert "LastInputTick.Remove(entry.Key);" in method
    assert "Controllers.Remove(entry.Key, out var device)" in method
    assert "device.Dispose();" in method
    assert 'event_name = "watchdog_expired"' in method


def test_command_execution_and_final_cleanup_are_synchronized():
    assert "lock (DeviceLock) result = Execute(root);" in SOURCE
    assert "Watchdog?.Dispose();" in SOURCE
    assert "LastInputTick.Clear();" in SOURCE
