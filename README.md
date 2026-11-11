# Elmos World

A custom controller-friendly Windows game launcher with game discovery, artwork, library management, and a built-in Update Center.

## Windows build

This repository uses GitHub Actions to compile Elmos World 3.1.1 into a standalone application and Windows Setup installer.

**Source bundle:** Upload `Elmos_World_3.1.1_GitHub_Ready.zip` to the root of this repository (keep its exact name). The workflow extracts the full project from this archive and builds it on a Windows runner.

Then open **Actions → Build Elmos World 3.1.1 → Run workflow**. The installer appears under the completed run's **Artifacts**.

After a successful build and a real Windows installation test, run the workflow again with **Publish release** enabled to create GitHub release `v3.1.1`. This publishes the installer and its SHA-256 checksum, which the application's Update Center requires.

## Update mechanism

Elmos World checks the latest public GitHub release under `davidstapleton2308/elmos-world`, compares versions, and offers **Update & Restart** when a newer Windows installer and matching `.sha256` asset are available.

**Security:** checksums protect against download corruption, but do not provide publisher authentication. Use code signing and protect repository release permissions before broad distribution.

## Version
3.1.1 (Windows installer not yet built or tested).
