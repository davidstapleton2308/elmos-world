# Elmos World — Smart Discovery v1 (November 2026)

## Goal

Recognize newly downloaded portable Windows games and supported emulators
without confusing them with installers, utilities, ROMs, user documents, or
unrelated applications. Favor safe **abstention** over false-positive moves.

This is a development milestone, not a claim of near-perfect coverage.
Filenames can lie, game builds vary, and no heuristics can certify the safety
of third-party executable files.

## Folder classification

The new module app/smart_discovery.py inventories the top-level Downloads
entries and known emulator folders. Each candidate is tagged as:

- GAME: an executable supported by independent game package evidence
  (Unity/Unreal structure, content assets, or real store manifest).
- EMULATOR: an exact-known emulator program plus supporting configuration.
- ROM: supported disc images/ROMs, always requiring review and system mapping.
- ARCHIVE: ZIP, RAR, 7z, etc., preview only; no automatic extraction.
- INSTALLER: loose EXE/MSI and installer-only folders; never launch or move.
- OTHER: unrelated files; leave alone.

A folder name is only a hypothesis, not trusted metadata. Known source/repack
tags are removed from the display title, but sequel numbers are preserved.

## Scoring, abstention and safety

A game candidate's heuristic score is computed from independent signals:

score = min(100, 35 + 35 * executable_name_match
                  + 30 * (Unity_or_Unreal_structure)
                  + 20 * store_manifest
                  + 16 * recognizable_content_assets)

Executable ambiguity, mismatched titles, missing independent structure,
unfinished downloads, and links/reparse points reduce confidence or block moves.
These **numbers are decision weights, NOT calibrated probabilities**.

Only completed, changed-file-rechecked folders scoring at least 96/100 can
be automatically organized, and only after the user enables auto-organizing.
Moving is a same-volume atomic directory rename into the configured Games
folder, or C:\Gaming\Emulators. Existing targets are never overwritten.
Cross-volume copies are deferred; no partial copy, deletes, or elevation.

No installer or downloaded executable is ever executed by Smart Discovery.
No antivirus settings are altered or bypassed.

## Emulator identification

Exact executable names for Xenia, PCSX2, Dolphin, RPCS3, Cemu, xemu, PPSSPP,
DuckStation, RetroArch, Ryujinx and other common emulators are differentiated
from PC games. A verified emulator is registered with its console platform,
but the scanner never supplies BIOS, firmware, ROMs, or changes emulator
configuration without a separate user action.

## Artwork

After a verified game is moved, its normalized title is looked up through
SteamGridDB only if the user already configured an API key. A single exact
matching game ID is required for automatic artwork. Ambiguous editions,
remakes, sequels or unavailable results remain without auto-applied art.
The existing manual Match Artwork function remains available.

## Distribution

GitHub Actions runs offline tests, compiles the Windows app, packages the
installer, checks its runtime, and publishes a versioned GitHub Release.
No laptop-side source deployment is required.

## Research-informed decisions

- Community Playnite importers reject installers, utilities, and ambiguous
  game EXEs rather than launching them to discover what they are.
- SteamRIP-style archives can contain _CommonRedist, an extracted preinstalled
  game directory, and misleading setup executables from unrelated downloads.
- RetroBat's emulator/ROM/BIOS directories are distinct. We never treat BIOS
  or console images as executable Windows PC games.

Reference points:
- https://github.com/Sam-GG/PlayniteAutoImport
- https://github.com/Neppale/auto-import
- https://github.com/Playnite/Docs/blob/main/docs/manual/library/games/addingGames.md
- https://github.com/RetroBat-Official/retrobat-wiki/blob/master/lang/en/get-started/retrobat-folder-structure.md
- https://www.reddit.com/r/SteamRip/comments/1golrfw
- https://github.com/SteamGridDB/node-steamgriddb

## Next validation milestones

1. Real annotated (opt-in, non-executable) folder-layout corpus with both
   portable games and unrelated apps; measure precision AND recall separately.
2. Read Windows PE ProductName, legitimate Steam appmanifest IDs, GOG metadata
   and registered-store manifests for better names even when folder names are
   random codes. Verify store metadata through trusted sources.
3. Preview exact canonical metadata, game edition, and art candidates before
   applying an uncertain match.
4. Consider archive inspection, safe extraction (zip-slip defenses and
   explicit confirmation), cross-volume staging with resumable verification,
   and undo journal as separate features.
5. Watch filesystem changes efficiently rather than rescanning all Downloads
   each minute; preserve responsiveness while gaming.

An accurate organizer must be willing to say **I don't know**.

## Source-manifest identity (additional evidence)

Read bounded, local, read-only GOG game info JSON, Steam ACF name fields, and
Epic .egstore item metadata when present. For a folder named "a2f83b19",
a GOG manifest declaring "Outer Wilds" can recover the actual name.
Contradictory metadata produces a review outcome, never a forced match.
Manifest metadata can be fabricated, so an engine/game binary and sufficiently
strong structural evidence are still required before organizing.

## Undo

Each completed move is journaled in LOCALAPPDATA/SteamMatch/smart_moves.json.
The Settings interface can undo the most recent move via an atomic same-volume
rename back to Downloads. Undo refuses to overwrite existing folders or
follow reparse points. It does not delete game files or artwork.
