"""Set a release version in the checked-out build copy of Elmos World.

Only the GitHub Actions runner working tree is changed. The source branch retains
its source-version baseline, while each successful commit build receives the next
available semantic patch version and installer filename.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE_FILES = (
    "app/update_center.py",
    "app/launcher_entry.py",
    "app/index.html",
    "build/ElmosWorld.iss",
    "build/version_file.txt",
    "release_manifest.json",
    "tests/test_release_structure.py",
)


def apply_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected version format MAJOR.MINOR.PATCH")
    manifest_file = ROOT / "release_manifest.json"
    old = json.loads(manifest_file.read_text(encoding="utf-8"))["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", old):
        raise ValueError("Invalid source version in release_manifest.json")
    if tuple(map(int, version.split("."))) < tuple(map(int, old.split("."))):
        raise ValueError("Refusing a version downgrade")

    old_tuple = "(" + ", ".join(old.split(".")) + ", 0)"
    new_tuple = "(" + ", ".join(version.split(".")) + ", 0)"
    for relative_path in RELEASE_FILES:
        path = ROOT / relative_path
        contents = path.read_text(encoding="utf-8")
        if old not in contents and old_tuple not in contents:
            raise RuntimeError(f"Expected version {old} not found in {relative_path}")
        contents = contents.replace(old_tuple, new_tuple)
        contents = contents.replace(old, version)
        # Classic is an immutable appearance preset identifier, not an app
        # version. Do not change its directory name when releasing a patch.
        contents = contents.replace("classic-" + version, "classic-3.1.1")
        path.write_text(contents, encoding="utf-8")

    updated = json.loads(manifest_file.read_text(encoding="utf-8"))
    if updated["version"] != version:
        raise RuntimeError("Release manifest version did not update")
    print(f"Prepared version {version} (source baseline {old})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python build/prepare_version.py MAJOR.MINOR.PATCH")
    apply_version(sys.argv[1])
