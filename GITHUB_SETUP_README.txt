ELMOS WORLD - GITHUB CONNECTION PRECONFIGURED

Repository expected: https://github.com/davidstapleton2308/elmos-world

1. Log into GitHub, go to https://github.com/new?name=elmos-world
2. Owner: davidstapleton2308; name: elmos-world; choose PUBLIC for simple unauthenticated app updates.
3. Do not initialize with a README, license or .gitignore. Click Create repository.
4. Upload the CONTENTS of the ElmosWorld_3.1.1 directory (not the ZIP) to repository root, including hidden .github/workflows folder. GitHub's Upload files or GitHub Desktop can do this.
5. In GitHub > Actions, run 'Build Elmos World Windows Setup' with 'Run workflow'. This produces a downloadable build artifact (not a release).
6. After verifying the Windows installer, publish tag v3.1.1 to trigger a GitHub Release with installer and checksum.
7. Elmos World now defaults to this repo for checking future versions; you may override it in Settings.

NOTE: Creating this ZIP did NOT create the repository, push code, publish a release, compile a Windows executable, or connect your installed local copy. This happens after repo creation and deploying this code.

IMPORTANT: This updater requires public releases and checks a checksum; it does not verify publisher signatures. Do not publish an update without Windows end-to-end testing.
