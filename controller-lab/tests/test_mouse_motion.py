import math
from elmos_controller_lab.mouse_motion import MouseDeltaAccumulator


def test_small_movements_accumulate_instead_of_vanishing():
    accumulator = MouseDeltaAccumulator()
    assert [accumulator.consume(0.2, -0.2) for _ in range(5)] == [
        (0, 0), (0, 0), (0, 0), (0, 0), (1, -1)
    ]


def test_reversal_cancels_residual_without_drift():
    accumulator = MouseDeltaAccumulator()
    total_x = total_y = 0
    for delta in ([0.17] * 100 + [-0.17] * 100):
        x, y = accumulator.consume(delta, -delta)
        total_x += x
        total_y += y
    assert (total_x, total_y) == (0, 0)
    assert accumulator.consume(0.0, 0.0) == (0, 0)


def test_reset_discards_residual():
    accumulator = MouseDeltaAccumulator()
    accumulator.consume(0.8, 0.8)
    accumulator.reset()
    assert accumulator.consume(0.3, 0.3) == (0, 0)


def test_nonfinite_input_resets_and_never_emits_malformed_delta():
    accumulator = MouseDeltaAccumulator()
    accumulator.consume(0.8, 0.8)
    assert accumulator.consume(float("nan"), 1) == (0, 0)
    assert accumulator.consume(0.3, 0.3) == (0, 0)


def test_large_input_is_bounded():
    assert MouseDeltaAccumulator().consume(1e30, -1e30) == (32767, -32767)


def test_polling_rate_independent_total_for_constant_velocity():
    # Simulate one second at multiple report rates. Integral is 17 pixels.
    for hz in (60, 120, 240):
        accumulator = MouseDeltaAccumulator()
        totals = [0, 0]
        for _ in range(hz):
            dx, dy = accumulator.consume(17.0 / hz, -17.0 / hz)
            totals[0] += dx
            totals[1] += dy
        assert tuple(totals) == (17, -17), hz


def test_near_integer_roundoff_does_not_force_true_fractional_motion():
    accumulator = MouseDeltaAccumulator()
    assert accumulator.consume(0.999, -0.999) == (0, 0)
    assert accumulator.consume(0.001, -0.001) == (1, -1)
