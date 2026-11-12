"""Lease-aware gamepad output for a successfully polled controller.

No background timer: only a healthy physical read may call submit().
"""
from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Callable


class HealthyFrameLease:
    def __init__(self, bridge: Any, slot: str, *, interval: float = 1.0,
                 clock: Callable[[], float] = time.monotonic):
        if not 0 < interval < 3.0:
            raise ValueError("heartbeat interval must be positive and below the bridge's 3s lease")
        self.bridge = bridge
        self.slot = slot
        self.interval = interval
        self.clock = clock
        self._last_state: dict[str, Any] | None = None
        self._last_contact: float | None = None

    def submit(self, state: dict[str, Any]) -> str:
        """Call only after a successful physical read and mapping operation.

        Changed reports are sent immediately. Identical reports renew the lease
        at most once per interval. Exceptions propagate and never mark success.
        """
        now = self.clock()
        if self._last_state is None or state != self._last_state:
            self.bridge.send_state(self.slot, state)
            self._last_state = deepcopy(state)
            self._last_contact = now
            return "state"
        if self._last_contact is None or now - self._last_contact >= self.interval:
            self.bridge.heartbeat(self.slot)
            self._last_contact = self.clock()
            return "heartbeat"
        return "idle"
