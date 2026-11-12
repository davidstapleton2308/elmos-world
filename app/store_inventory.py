"""Read-only installed-store inventory for independent game identity checks.

This module never launches store clients or downloaded executables and never
writes to Steam, Epic, GOG, or game directories. A store manifest is trusted
only when its product identity is corroborated by a separately discovered,
existing installation path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
from functools import lru_cache
from typing import Any


MAX_MANIFEST_BYTES = 256 * 1024
MAX_STEAM_MANIFESTS = 5000
_BAD_PATH_PARTS = {"..", "."}


def parse_keyvalues(text: str) -> dict[str, Any]:
    """Parse the bounded quoted-string subset used by Steam text VDF files."""
    if not isinstance(text, str) or len(text) > 2_000_000:
        raise ValueError("VDF is missing or too large")
    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end + 1
            continue
        if ch in "{}":
            tokens.append(ch)
            i += 1
            continue
        if ch != '"':
            raise ValueError(f"Unexpected VDF token at character {i}")
        i += 1
        value = []
        while i < len(text):
            ch = text[i]
            if ch == '"':
                i += 1
                break
            if ch == "\\":
                i += 1
                if i >= len(text):
                    raise ValueError("Truncated VDF escape")
                escaped = text[i]
                value.append({"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"'} .get(escaped, "\\" + escaped))
                i += 1
            else:
                value.append(ch)
                i += 1
        else:
            raise ValueError("Unterminated VDF string")
        tokens.append("".join(value))

    def parse_object(index: int, nested: bool) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(tokens):
            key = tokens[index]
            if key == "}":
                if not nested:
                    raise ValueError("Unexpected VDF closing brace")
                return result, index + 1
            if key == "{":
                raise ValueError("VDF object has no key")
            index += 1
            if index >= len(tokens):
                raise ValueError("VDF key has no value")
            if tokens[index] == "{":
                value, index = parse_object(index + 1, True)
            elif tokens[index] == "}":
                raise ValueError("VDF key has an empty value")
            else:
                value = tokens[index]
                index += 1
            result[key] = value
        if nested:
            raise ValueError("VDF object is missing a closing brace")
        return result, index

    parsed, offset = parse_object(0, False)
    if offset != len(tokens):
        raise ValueError("Unexpected trailing VDF data")
    return parsed


def _read_text(path: Path) -> str:
    try:
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            return ""
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_text(path))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _safe_existing_directory(candidate: str | Path, *, boundary: str | Path | None = None) -> Path | None:
    try:
        raw = Path(candidate).expanduser()
        if not raw.is_absolute() or any(part in _BAD_PATH_PARTS for part in raw.parts):
            return None
        # Inspect original components before resolve(); otherwise a symlink or
        # junction is hidden when resolve() replaces it with its target path.
        if boundary is not None:
            raw_root = Path(boundary)
            if _is_reparse(raw_root):
                return None
            cursor = raw
            while cursor != raw_root and cursor != cursor.parent:
                if _is_reparse(cursor):
                    return None
                cursor = cursor.parent
            if cursor != raw_root:
                return None
            root = raw_root.resolve(strict=True)
        else:
            cursor = raw
            while cursor != cursor.parent:
                if _is_reparse(cursor):
                    return None
                cursor = cursor.parent
            root = None
        resolved = raw.resolve(strict=True)
        if not resolved.is_dir():
            return None
        if root is not None and not resolved.is_relative_to(root):
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _registry_steam_root() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg
        locations = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        )
        for hive, key_name in locations:
            try:
                with winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ) as key:
                    value, _ = winreg.QueryValueEx(key, "SteamPath")
                    path = _safe_existing_directory(value)
                    if path:
                        return path
            except OSError:
                continue
    except ImportError:
        pass
    return None


def _steam_libraries(steam_root: Path) -> list[Path]:
    result = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    text = _read_text(vdf)
    if not text:
        return result
    try:
        root = parse_keyvalues(text)
        libraries = root.get("libraryfolders", root.get("LibraryFolders", {}))
        if not isinstance(libraries, dict):
            return result
        for value in libraries.values():
            path_value = value.get("path") if isinstance(value, dict) else value
            if not isinstance(path_value, str) or not path_value.strip():
                continue
            path = _safe_existing_directory(path_value)
            if path and path not in result:
                result.append(path)
    except ValueError:
        # A malformed libraryfolders.vdf cannot invalidate already verified
        # Steam root evidence; other libraries are simply not considered.
        return result
    return result


def _steam_records(steam_root: Path) -> list[dict[str, Any]]:
    records = []
    for library in _steam_libraries(steam_root):
        manifests = sorted((library / "steamapps").glob("appmanifest_*.acf"))[:MAX_STEAM_MANIFESTS]
        common = _safe_existing_directory(library / "steamapps" / "common")
        if not common:
            continue
        for manifest in manifests:
            match = re.fullmatch(r"appmanifest_(\d{1,12})\.acf", manifest.name, re.I)
            if not match or _is_reparse(manifest):
                continue
            try:
                parsed = parse_keyvalues(_read_text(manifest)).get("AppState", {})
            except ValueError:
                continue
            if not isinstance(parsed, dict):
                continue
            appid = str(parsed.get("appid", ""))
            name = str(parsed.get("name", "")).strip()
            installdir = str(parsed.get("installdir", "")).strip()
            if appid != match.group(1) or not name or not installdir:
                continue
            try:
                flags = int(str(parsed.get("StateFlags", "0")), 10)
            except ValueError:
                continue
            # StateFlags bit 2 means fully installed. Downloading/updating
            # manifests are not considered an installed inventory record.
            if not flags & 4:
                continue
            if Path(installdir).is_absolute() or any(part in _BAD_PATH_PARTS for part in Path(installdir).parts):
                continue
            install = _safe_existing_directory(common / installdir, boundary=common)
            if not install:
                continue
            records.append({
                "source": "steam",
                "productId": appid,
                "title": name[:140],
                "installPath": str(install),
                "manifestPath": str(manifest),
                "libraryPath": str(library),
            })
    return records


def _epic_records(program_data: str | Path | None) -> list[dict[str, Any]]:
    base = Path(program_data) if program_data else Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    manifests = base / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not manifests.is_dir() or _is_reparse(manifests):
        return []
    records = []
    for path in sorted(manifests.glob("*.item"))[:5000]:
        if _is_reparse(path):
            continue
        item = _read_json(path)
        app_name = str(item.get("AppName", "")).strip()
        title = str(item.get("DisplayName", "")).strip()
        install_value = item.get("InstallLocation")
        if not app_name or not title or not isinstance(install_value, str):
            continue
        if item.get("bIsIncompleteInstall") is True:
            continue
        install = _safe_existing_directory(install_value)
        if not install:
            continue
        launch_exe = item.get("LaunchExecutable")
        if isinstance(launch_exe, str) and launch_exe.strip():
            relative = Path(launch_exe)
            if relative.is_absolute() or any(part in _BAD_PATH_PARTS for part in relative.parts):
                continue
            exe = install / relative
            if not exe.is_file() or _is_reparse(exe):
                continue
        records.append({
            "source": "epic",
            "productId": app_name,
            "catalogItemId": str(item.get("CatalogItemId", "")),
            "title": title[:140],
            "installPath": str(install),
            "manifestPath": str(path),
        })
    return records


def _gog_records() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    records = []
    try:
        import winreg
    except ImportError:
        return records
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GOG.com\Games"),
        (winreg.HKEY_CURRENT_USER, r"Software\GOG.com\Games"),
    )
    for hive, root_name in roots:
        try:
            with winreg.OpenKey(hive, root_name, 0, winreg.KEY_READ) as root:
                count = winreg.QueryInfoKey(root)[0]
                for index in range(min(count, 5000)):
                    try:
                        sub_name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, sub_name, 0, winreg.KEY_READ) as key:
                            values = {}
                            for value_name in ("path", "gameName", "gameId", "gameID", "name"):
                                try:
                                    values[value_name], _ = winreg.QueryValueEx(key, value_name)
                                except OSError:
                                    pass
                        install = _safe_existing_directory(values.get("path", ""))
                        title = str(values.get("gameName") or values.get("name") or "").strip()
                        product_id = str(values.get("gameId") or values.get("gameID") or sub_name)
                        if not install or not title or not product_id:
                            continue
                        records.append({
                            "source": "gog",
                            "productId": product_id,
                            "title": title[:140],
                            "installPath": str(install),
                            "manifestPath": "",
                        })
                    except OSError:
                        continue
        except OSError:
            continue
    return records


def collect_inventory(*, steam_root: str | Path | None = None,
                      program_data: str | Path | None = None) -> list[dict[str, Any]]:
    """Collect verified, read-only installed-game records from supported stores."""
    root = _safe_existing_directory(steam_root) if steam_root else _registry_steam_root()
    if root:
        steam = _steam_records(root)
    else:
        steam = []
    epic = _epic_records(program_data)
    gog = _gog_records()
    seen = set()
    records = []
    for record in steam + epic + gog:
        key = (record["source"], record["productId"], os.path.normcase(record["installPath"]))
        if key not in seen:
            seen.add(key)
            records.append(record)
    return records


def match_candidate(folder: str | Path, files: list[str | Path],
                    records: list[dict[str, Any]]) -> dict[str, Any]:
    """Corroborate a local product manifest against an independent installed record."""
    folder = Path(folder)
    claims: list[tuple[str, str]] = []
    for raw in files:
        path = Path(raw)
        if path.parent != folder and path.parent.name.casefold() != ".egstore":
            continue
        steam_id = re.fullmatch(r"appmanifest_(\d{1,12})\.acf", path.name, re.I)
        if steam_id:
            try:
                appstate = parse_keyvalues(_read_text(path)).get("AppState", {})
                claimed = str(appstate.get("appid", "")) if isinstance(appstate, dict) else ""
                if claimed == steam_id.group(1):
                    claims.append(("steam", claimed))
            except ValueError:
                pass
        elif path.name.casefold() == "steam_appid.txt":
            value = _read_text(path).strip()
            if re.fullmatch(r"\d{1,12}", value):
                claims.append(("steam", value))
        else:
            gog = re.fullmatch(r"goggame-(\d{1,20})\.info", path.name, re.I)
            if gog:
                claims.append(("gog", gog.group(1)))
            elif path.suffix.casefold() == ".item" and path.parent.name.casefold() == ".egstore":
                item = _read_json(path)
                app_name = str(item.get("AppName", "")).strip()
                catalog_id = str(item.get("CatalogItemId", "")).strip()
                if app_name:
                    claims.append(("epic", app_name))
                if catalog_id:
                    claims.append(("epic-catalog", catalog_id))
    matches = []
    for source, product_id in claims:
        for record in records:
            if record.get("source") != ("epic" if source == "epic-catalog" else source):
                continue
            if str(record.get("productId", "")) == product_id or (
                source == "epic-catalog" and str(record.get("catalogItemId", "")) == product_id
            ):
                matches.append(record)
    titles = {str(item.get("title", "")).casefold(): item for item in matches}
    if len(titles) > 1:
        return {"matched": False, "conflict": True, "title": "", "records": matches[:8]}
    if not matches:
        return {"matched": False, "conflict": False, "title": "", "records": []}
    selected = matches[0]
    return {
        "matched": True,
        "conflict": False,
        "title": selected["title"],
        "source": selected["source"],
        "productId": selected["productId"],
        "installPath": selected["installPath"],
        "records": matches[:8],
    }


@lru_cache(maxsize=1)
def installed_inventory() -> list[dict[str, Any]]:
    """Process-local snapshot; clear the cache after a store installation."""
    return collect_inventory()
