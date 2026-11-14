# Unified 3.2 — Elmos World

An additive feature preset built on the preserved Classic 3.1.1 experience.

## Includes
- The same visual foundation and artwork treatment as Classic 3.1.1.
- Per-game Elmos Input configuration from each game's Configure panel.
- Physical controller selection and virtual identity selection.
- Optional per-game controller auto-start, with an explicit UAC approval at runtime.
- Access to the full Elmos Controller Lab mapping editor.
- Existing Game Intelligence and Smart Discovery screens.

## Preset policy
Classic 3.1.1 remains a separate, byte-for-byte preserved preset. This folder is independently versioned; future visual changes belong here or in another new preset, never in Classic.

## Safety
- The virtual driver is never installed silently.
- Auto-start is off until enabled per game.
- Controller runtime watches the launched game PID and releases virtual devices when it exits.
- The bridge has its own 3-second input lease watchdog as a second cleanup layer.
- Game Intelligence background auto-moves remain disabled until Windows filesystem safety gates are proven.
