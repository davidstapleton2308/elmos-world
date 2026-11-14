# Game Intelligence Lab — final synthesis and iteration 13 (2026-11-11)

## Repository verification
Fetched experimental-branch app/smart_discovery.py blob e0fc204f7d022af6eef746e73c2f5d538befe22b and iteration-12 log blob 88b8d33d9475b7c6f0b4cc2928c4ae90ec0c0a20. Source still uses MAX_ITEMS=200, MAX_FILES=1800, _walk skips IGNORE_DIRS, manifest presence increases game confidence, _result marks stable >=96 ready, and move_verified performs a preflight destination check then os.rename. No production changes were made.

## Iteration 13: independent evidence and metamorphic testing
Ran Python 3 synthetic identity resolver with 11 cases (five valid canonical game/edition identities, five misleading store claims, one unknown ID), including a fake edition claim. Baseline naive manifest-to-catalog lookup: TP=5, FP=5, FN=0, precision=50%, recall=100%, 1 abstention. Gated independent installed-inventory record + verified path: TP=5, FP=0, FN=0, precision=100%, recall=100%, 6 abstentions. Both correctly identified edition for five positive fixtures. Metamorphic checks: three cosmetic folder-name changes and one path-verification invalidation passed. Zero filesystem moves. Test runtime 2.452 ms includes fixture setup; not a representative performance benchmark.

**Crucial limitation:** The 'trusted' inventory records are fixture-provided. This validates policy logic, NOT actual Steam/Epic/GOG record extraction, production precision, or artwork correctness. The naive baseline is NOT current full Smart Discovery. Emulator classification and artwork identity correctness were not measured. No actual false-positive moves occurred because no moves were attempted; this is not proof of move safety.

## Ranked roadmap (final synthesis)
P0: Keep automatic moves disabled until full-tree inventory completeness, junction/symlink rejection, transient detection, no-overwrite NTFS moves, durable journal, crash/concurrency recovery, and explicit user opt-in are tested on Windows with disposable directories. Current os.rename preflight is not sufficient evidence of no-overwrite under concurrent races.
P1: Implement read-only Steam libraryfolders.vdf + appmanifest_*.acf, Epic .item, and GOG Galaxy installed-game adapters. Independently validate inventory location and install path, not arbitrary manifests inside Downloads. Distinguish unknown edition from base edition; require canonical (provider, product ID, edition SKU) identity and conflict abstention.
P2: Build persistent fair discovery queue and a separate exhaustive safety inventory. Fix 200-entry starvation and 1800-entry incomplete detection; inspect ignored subdirectories for movement hazards. Test restarts, rename, stale event, junction, and large directory cases.
P3: Build an independently labeled fixture corpus: genuine freely redistributable games, utilities, emulator binaries from official sources, safe synthetic ROM headers and archives, obscure/repack-style names without copyrighted packages, plus adversarial spoofing. Measure per-class precision/recall, edition accuracy, abstention, false moves and p50/p95 scan times; compare with actual app baseline.
P4: Canonical artwork identity graph with per-asset provenance (cover/hero/logo/icon), exact game-vs-edition verification, source-independent fallback (official store art, locally supplied art, other licensed catalogs), checksum and licensing checks. Never silently select similarly named sequel art.
P5: ROM platform identification from validated headers/containers, multi-disc relationships, emulator identity/version detection and user-selected emulator mappings. Avoid running binaries and never treat extension alone as proof.
P6: After safety and identification benchmarks pass, implement review-first staging, audit trail, undo with integrity validation, and opt-in graduated automation. Consider emulator-development experiments only after core organizer reliability.

## Evidence limits and unresolved blockers
Earlier iterations 3–12 explored scanning completeness, scheduling, crash recovery, races and identity confidence, mostly with simplified simulations. None proves production accuracy. Need actual Windows NTFS integration, authentic store inventory fixtures, independently labeled artwork, executable PE resource checks and emulator tests. No main merge, release, game moves, downloaded copyrighted packages, executable runs, or security changes.

## Next best test
Implement a read-only Steam VDF/ACF parser with strict path binding, and 30+ independent positive/negative fixtures; verify edition abstention and compare with current Smart Discovery end-to-end. In parallel test Windows no-overwrite and journal recovery with dummy folders.
