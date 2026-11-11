"""Frame-rate-independent fractional mouse movement accumulator.

Converts finite floating-point movement to integer relative events without
discarding subpixel motion on each frame. One accumulator per mapping session.
"""
from __future__ import annotations

import math


class MouseDeltaAccumulator:
    def __init__(self) -> None:
        self._x = 0.0
        self._y = 0.0

    def reset(self) -> None:
        self._x = self._y = 0.0

    def consume(self, dx: float, dy: float) -> tuple[int, int]:
        if not math.isfinite(dx) or not math.isfinite(dy):
            self.reset()
            return (0, 0)
        # Bound extreme malformed input; prevent integer overflow downstream.
        dx = max(-32767.0, min(32767.0, dx))
        dy = max(-32767.0, min(32767.0, dy))
        x = self._x + dx
        y = self._y + dy
        # Binary floating-point can leave a value such as 16.999999999999996\n        # after repeated increments. Snap only values within roundoff of\n        # an integer; otherwise truncation creates a spurious one-pixel drift.\n        if math.isclose(x, round(x), rel_tol=0.0, abs_tol=1e-12):\n            x = float(round(x))\n        if math.isclose(y, round(y), rel_tol=0.0, abs_tol=1e-12):\n            y = float(round(y))\n        ix, iy = math.trunc(x), math.trunc(y)
        self._x, self._y = x - ix, y - iy
        return ix, iy
