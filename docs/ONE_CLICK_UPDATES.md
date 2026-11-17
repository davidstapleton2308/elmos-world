# One-click desktop update standard (for Elmos World and future apps)

Owner-approved behavior:
- Check for Updates only checks and displays availability; never installs.
- **Update & Restart is the user's consent.** No second browser confirm(), modal, typed confirmation, or manual installer in the normal workflow.
- Download HTTPS release assets from the explicitly configured trusted repository.
- Verify a SHA-256 checksum before attempting installation. For higher security, use trusted Authenticode signatures and restrict update publishers; hashes from the same compromised source are not independent proof of publisher identity.
- Background worker acknowledges startup before the app closes.
- App closes cleanly; worker installs over the existing application without deleting its data, games, ROMs or other files.
- Validate installed app with a self-test, restart and report update result.
- On error, keep clear persistent status and logs, try to reopen previous app, do not report success.
- No installation while games are running. Keep user data out of release build output.
- Every release must pass real Windows integration tests of the launched worker, installer, self-test and relaunch.
- Don't disable platform security or install broad exceptions to make updates work.
- New projects should include a comparable native updater as part of the **first installable release**, not as a later manual script.

Elmos World concrete path: Settings > Update Center > Check for updates > Update & Restart (one approval click). The user still chooses when installation begins; checking does not change files.

Tested on GitHub Windows runner for v3.1.23 and v3.1.24. The user independently reported successful in-app update on their personal Windows laptop when upgrading to v3.1.24. Future releases still require passing their own integration checks.
