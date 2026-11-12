import unittest

from elmos_controller_lab.prerequisites import (
    EXIT_BRIDGE_MISSING, EXIT_BRIDGE_UNAVAILABLE, EXIT_DRIVER_MISSING,
    EXIT_DRIVER_UNPREPARED, EXIT_DRIVER_VERSION_MISMATCH, EXIT_READY,
    EXIT_UNSUPPORTED_PLATFORM, evaluate_prerequisites,
)


READY = {
    "driverInstalled": True, "driverPrepared": True,
    "backendSdkVersion": "2.1.0", "architecture": "X64",
}


class PrerequisiteEvaluationTests(unittest.TestCase):
    def test_ready_positive_control(self):
        result = evaluate_prerequisites(READY)
        self.assertTrue(result["ready"])
        self.assertEqual(result["exitCode"], EXIT_READY)

    def test_missing_driver_is_not_ready(self):
        result = evaluate_prerequisites({**READY, "driverInstalled": False, "driverPrepared": False})
        self.assertFalse(result["ready"])
        self.assertEqual(result["exitCode"], EXIT_DRIVER_MISSING)

    def test_installed_but_unprepared_is_distinct(self):
        result = evaluate_prerequisites({**READY, "driverPrepared": False})
        self.assertFalse(result["ready"])
        self.assertEqual(result["exitCode"], EXIT_DRIVER_UNPREPARED)

    def test_old_sdk_is_not_mistaken_for_ready(self):
        result = evaluate_prerequisites({**READY, "backendSdkVersion": "1.9.0"})
        self.assertFalse(result["ready"])
        self.assertEqual(result["exitCode"], EXIT_DRIVER_VERSION_MISMATCH)

    def test_missing_bridge_and_unavailable_bridge_fail_closed(self):
        self.assertEqual(evaluate_prerequisites(None, bridge_exists=False)["exitCode"], EXIT_BRIDGE_MISSING)
        self.assertEqual(evaluate_prerequisites(None)["exitCode"], EXIT_BRIDGE_UNAVAILABLE)

    def test_non_windows_and_wrong_architecture_fail_closed(self):
        self.assertEqual(evaluate_prerequisites(READY, platform="linux")["exitCode"], EXIT_UNSUPPORTED_PLATFORM)
        result = evaluate_prerequisites({**READY, "architecture": "ARM64"})
        self.assertEqual(result["exitCode"], EXIT_UNSUPPORTED_PLATFORM)

    def test_unknown_or_truthy_strings_never_count_as_installed(self):
        result = evaluate_prerequisites({
            "driverInstalled": "true", "driverPrepared": 1,
            "backendSdkVersion": "2.1.0", "architecture": "X64",
        })
        self.assertFalse(result["ready"])
        self.assertEqual(result["exitCode"], EXIT_DRIVER_MISSING)

    def test_extra_optional_hardware_does_not_affect_driver_readiness(self):
        # Physical controllers are optional at installation time; a user can
        # connect one after setup. Adding unrelated fields must not alter state.
        baseline = evaluate_prerequisites(READY)
        augmented = evaluate_prerequisites({**READY, "physicalControllers": [], "battery": None})
        self.assertEqual(baseline["exitCode"], augmented["exitCode"])

    def test_status_field_order_does_not_change_result(self):
        reordered = dict(reversed(list(READY.items())))
        self.assertEqual(evaluate_prerequisites(READY), evaluate_prerequisites(reordered))


if __name__ == "__main__":
    unittest.main()
