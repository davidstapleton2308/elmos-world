# Elmos World Unified Integration — Staging Plan

Status: STAGING / NOT RELEASE-READY
Date: 2026-11-12

## Non-negotiable visual preservation rule

The existing Elmos World 3.1.1 appearance is preserved as the immutable **Classic 3.1.1** preset under:
- app/presets/classic-3.1.1/

The preset contains exact Git blob copies of app.css, index.html, app.js, and every existing premium_*.css file (23–31, excluding no existing numbered file present at baseline). Its source baseline is commit 607d4ceb275816eb0d273aad4c2dfd3e5504f2a2.

A full source backup is also preserved at:
- backup/pre-unified-integration-2026-11-12

No redesign may overwrite the Classic preset. New visual work must use a separately named preset and Classic remains the default unless David explicitly selects another design. Functional changes must not silently alter layout, typography, colors, spacing, animation, artwork treatment, or navigation.

## Branches

- main: untouched stable baseline.
- backup/pre-unified-integration-2026-11-12: exact backup of main at 607d4ceb275816eb0d273aad4c2dfd3e5504f2a2.
- integration/elmos-world-unified: isolated integration staging branch.
- experiment/game-intelligence-2026-11-11: original Game Intelligence research source.
- feature/elmos-controller-lab: original Elmo Input laboratory source.

## Imported into the integration branch

- Full controller-lab source, GUI, mapping/action engine, Windows bridge, scripts, tests, hourly reports 1–12 and README.
- .github/workflows/controller-lab.yml.
- Full experiments/game-intelligence research archive, iterations 1–13 and final synthesis.
- Frozen Classic 3.1.1 visual preset.

## Proposed runtime architecture

1. Game Intelligence remains a fail-closed organizer: read-only discovery first, review-first for uncertain identity, explicit opt-in for moves, durable journal, undo, no overwrites, no installer execution, no elevation.
2. Elmo Input remains an independent service boundary. Controller bridge faults must not crash the launcher; launcher faults must not leave virtual devices stuck.
3. Shared integration uses versioned local APIs and stable game/controller profile identifiers. Keep the laboratory independently runnable until in-app parity is verified.
4. Classic UI is the active default. Any new controller screens or organizer views must be additive and available through a new named preset or opt-in panels until approved.
5. Installer/update work must stage, validate, back up, atomically switch, and restore the previous app on failure. User data and game libraries must remain outside replaceable application files.

## Research-backed limitations that must remain visible

### Game Intelligence
The final synthesis explicitly says its 100% precision/recall result came from 11 synthetic fixtures with fixture-provided trusted inventory, not real store adapters. No real production move safety, artwork accuracy, emulator classification, or Windows NTFS race behavior was established. Automatic moves must remain disabled until the listed P0 safety tests pass.

Priority validation:
- full-tree inventory and starvation/truncation handling
- symlink/junction/reparse-point rejection
- transient download detection
- no-overwrite NTFS move under concurrency
- durable journal and crash/restart/concurrency recovery
- real Steam VDF/ACF, Epic .item, and GOG installed-game evidence
- independently labelled corpus and precision/recall/edition metrics
- artwork identity and provenance checks
- safe ROM/emulator classification

### Elmo Input
The end-of-day report records 12 iterations and 3/3 CI jobs passing on the reported run (Windows Python tests, Ubuntu Python tests, Windows virtual bridge build). This is automated CI evidence only. Physical controller testing, measured 60/120/240 Hz latency, real-game compatibility, haptics, and end-to-end reconnect behavior remain unverified.

The next controller milestone is to benchmark throughput and latency, then implement sequence-numbered acknowledgments with device generations, bounded in-flight updates, and loss-safe press/release handling. Preserve heartbeat and healthy-frame lease protections.

The uploaded Iterations 7–12 report is also retained in the project context; it documents watchdog exception containment, heartbeat protocol, healthy-frame lease, acknowledged state delivery, corrected acknowledgment timing, and the final CI audit.

## Merge/release gates

Do not merge this staging branch into main or publish an installer until:
- all existing main tests pass unchanged;
- controller-lab CI passes from this integration branch;
- game-intelligence tests pass, including undo and precision fixtures;
- Windows integration tests use disposable directories and synthetic controller input;
- no hardware-only behavior is described as verified without physical testing;
- app starts and existing screens match Classic 3.1.1;
- user data, controller profiles, and game files survive update and rollback tests;
- a separate opt-in test build is produced and manually approved.

## Rollback

To restore source exactly, use backup/pre-unified-integration-2026-11-12 or commit 607d4ceb275816eb0d273aad4c2dfd3e5504f2a2. Do not reset or force-push main. To restore the old visual layer only, use the app/presets/classic-3.1.1 snapshot.
