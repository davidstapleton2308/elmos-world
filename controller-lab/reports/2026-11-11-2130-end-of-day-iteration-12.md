# Elmo Input — End-of-day cumulative engineering report
**2026-11-11 21:30 America/Chicago · Iteration 12**

## Verified branch baseline
- Repository: `davidstapleton2308/elmos-world`, branch `feature/elmos-controller-lab`, directory `controller-lab/`.
- Inspected head: `46f2ad63793ca8d6ae63e12c280ace7c230e6c39` (iteration 11 report).
- [GitHub Actions run 43141683890](https://github.com/davidstapleton2308/elmos-world/actions/runs/43141683890) completed **successfully**: `python-regression (windows-latest)`, `python-regression (ubuntu-latest)`, and `windows-virtual-bridge-build` all succeeded. This is build/test evidence, **not** actual device or game compatibility validation.
- The intermediate [run 43135286745](https://github.com/davidstapleton2308/elmos-world/actions/runs/43135286745) failed, but subsequent test and report snapshots passed, including the final pre-report run above.

## Iteration-by-iteration history
| Iteration | Time (Central) | Main engineering result | Evidence status |
|---|---|---|---|
| 01 | 10:30 | Initial controller-lab baseline and gyro precision investigation | Historical report in repository |
| 02 | 11:30 | Gyro fractional pixel correction and multi-rate cases | Later corrected in iteration 03 |
| 03 | 12:30 | Fixed escaped-newline comment defect that disabled intended correction | Later CI passed |
| 04 | 13:30 | SDL instance-ID selection to prevent hotplug controller swapping | Later CI passed |
| 05 | 14:30 | Best-effort virtual-device destroy even after neutral-state send fails | Later CI passed |
| 06 | 15:30 | Bridge-side 3-second inactivity watchdog | Later CI passed |
| 07 | 16:30 | Watchdog callback exception containment | Later CI passed |
| 08 | 17:30 | Bridge heartbeat command and Python client support | Later CI passed |
| 09 | 18:30 | HealthyFrameLease: changed states immediate, idle heartbeat only after healthy reads | Later CI passed |
| 10 | 19:30 | Changed-state acknowledgment instead of fire-and-forget | Initial CI failure, later CI passed |
| 11 | 20:30 | Timestamp successful lease contact after acknowledgment; delayed-ack tests | [Run 43141683890](https://github.com/davidstapleton2308/elmos-world/actions/runs/43141683890) passed all three jobs |
| 12 | 21:30 | Final CI audit; design of next bounded sequence/epoch protocol; this cumulative report | Documentation only; no runtime code change |

## Technical research and next concrete design
Microsoft's [GameInput device callback documentation](https://learn.microsoft.com/en-us/gaming/gdk/docs/reference/input/gameinput/interfaces/igameinput/methods/igameinput_registerdevicecallback?view=gdk-2604) confirms device connect/disconnect notifications and status transitions; these should be treated as explicit lifecycle events, not as evidence that a previously cached device handle remains usable.

**Next protocol milestone: bounded, sequence-numbered state acknowledgments with slot generations.** This is a design, **not implemented**:
1. Negotiate `protocol_version=2` before enabling new fields; preserve legacy synchronous `state` and `heartbeat` on older bridges.
2. Allocate a fresh unpredictable session/slot generation on virtual-device creation. Every state frame and ACK carries generation plus monotonically increasing unsigned 64-bit sequence. On generation mismatch, reject; never silently rebind to a recycled slot.
3. Maintain a bounded in-flight window (start at 2, configurable 1–4); sequence numbers are never reused within a generation. Acknowledge `(generation, sequence, status)`; ignore duplicate/out-of-order ACKs for already completed frames. Do not interpret transport write success as device application success.
4. Coalesce *analog-only* pending frames to the latest state under backpressure, but preserve button/keyboard/mouse **edge transitions** in order; never coalesce away press/release pairs. If edge queue overflows, fail closed: send neutral state if possible, destroy slot, and surface an error. Bound queue capacity and memory.
5. Keep heartbeats dependent on a successful physical poll, not a free-running timer. The bridge's 3-second watchdog remains authoritative. Stop all sends on disconnect or stale generation.
6. Measure poll-to-bridge-apply latency with a monotonic timestamp at both ends and avoid comparing clocks across processes without calibration. Track local RTT separately, report p50/p95/p99 and drops, and benchmark 60/120/240 Hz at both unchanged and rapidly changing inputs. Do not claim a latency improvement before measurements.

**Required regression scenarios:** stale ACK after destroy/recreate; out-of-order and duplicate ACK; dropped ACK; bridge restart mid-flight; no controller poll while background task continues; simultaneous button press/release during backpressure; sequence overflow requiring new generation; heartbeat during prolonged idle; timeout and bounded cleanup; protocol v1 compatibility. Tests should include fake clock/transport and an isolated Windows bridge integration harness.

## Known limitations
- No actual Windows controller, HID, virtual driver, rumble, gyro hardware, or game was exercised in this run.
- GitHub CI passing does not establish real XInput/GameInput compatibility, low latency, driver safety, or correct haptics.
- Current changed-frame request is synchronous (timeout 2s), so high-rate input latency remains an open risk. The watchdog interval is 3s and must be verified with real bridge crash/restart scenarios.
- Remaining roadmap: safe device lifecycle and identity; sequence/epoch protocol; latency benchmarks; then action-set/chord/tap-hold/radial UI, trackpad/gyro/haptics, and Windows game compatibility.

## Exact evidence
- [Final pre-report branch head](https://github.com/davidstapleton2308/elmos-world/commit/46f2ad63793ca8d6ae63e12c280ace7c230e6c39)
- [Iteration 11 source change](https://github.com/davidstapleton2308/elmos-world/commit/4ba9bdd5ed680d57a1a0d34ce7f09a86dea912de)
- [Iteration 11 tests](https://github.com/davidstapleton2308/elmos-world/commit/ff929e58a99f8c50d91ae876f287e6869f3d9de2)
- [Successful final pre-report CI](https://github.com/davidstapleton2308/elmos-world/actions/runs/43141683890)
