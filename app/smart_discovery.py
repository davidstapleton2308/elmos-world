"""Smart Discovery v1: high-precision, fail-closed Windows game organization.

Read-only scanning is the default. Never executes installers, opens archives,
elevates a process, edits downloads, or guesses a game from a lone .exe.
Only a verified, unchanged folder may be renamed (same filesystem) following
the user's explicit opt-in. Uncertain matches must remain for review.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import stat
import time
from pathlib import Path

from game_discovery import KNOWN_EXES, blocked_exe, clean_game_title, candidates, words

EMULATORS = {
    'xenia.exe': ('Xenia', 'Xbox 360'),
    'xenia_canary.exe': ('Xenia Canary', 'Xbox 360'),
    'xenia-canary.exe': ('Xenia Canary', 'Xbox 360'),
    'pcsx2.exe': ('PCSX2', 'PlayStation 2'),
    'pcsx2-qt.exe': ('PCSX2', 'PlayStation 2'),
    'dolphin.exe': ('Dolphin', 'GameCube / Wii'),
    'rpcs3.exe': ('RPCS3', 'PlayStation 3'),
    'cemu.exe': ('Cemu', 'Wii U'),
    'xemu.exe': ('xemu', 'Xbox'),
    'ppssppwindows64.exe': ('PPSSPP', 'PlayStation Portable'),
    'ppssppwindows.exe': ('PPSSPP', 'PlayStation Portable'),
    'duckstation-qt-x64-releaseltcg.exe': ('DuckStation', 'PlayStation'),
    'duckstation-qt-x64-release.exe': ('DuckStation', 'PlayStation'),
    'retroarch.exe': ('RetroArch', 'Multi-system'),
    'azahar.exe': ('Azahar', 'Nintendo 3DS'),
    'mgba.exe': ('mGBA', 'Game Boy Advance'),
    'melonDS.exe'.lower(): ('melonDS', 'Nintendo DS'),
    'ryujinx.exe': ('Ryujinx', 'Nintendo Switch'),
    'shadps4.exe': ('shadPS4', 'PlayStation 4'),
}

ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.xz'}
ROMS = {'.iso', '.cso', '.chd', '.rvz', '.wbfs', '.gdi', '.wad', '.xex',
        '.nes', '.sfc', '.smc', '.gba', '.gbc', '.gb', '.nds',
        '.z64', '.n64', '.v64', '.3ds', '.cia', '.nsp', '.xci', '.cue'}
TRANSIENT = {'.crdownload', '.part', '.partial', '.download', '.tmp', '.aria2', '.!qb'}
IGNORE_DIRS = {
    '_commonredist', 'redist', 'redistributables', 'installer', 'installers',
    '_installer', 'prerequisites', 'prereqs', '__macosx', 'crack', 'fix',
    'patch', 'patches', 'plugins', 'screenshots', 'documents', 'backup',
    'backups', 'sdk', 'samples', 'mods', 'tools', 'uninstall', 'directx',
}
BLOCKED_FOLDERS = {'node_modules', '.git', 'appdata', 'windows', 'program files',
                   'program files (x86)', 'system32', 'drivers'}
RELEASE_LABEL = re.compile(
    r'(?i)(?:[\s._-]+(?:steam[\s._-]?rip(?:[\s._-]?com)?|gog[\s._-]?games|'
    r'fitgirl|elamigos|dodi|portable|pre[\s._-]?installed|repack|'
    r'win(?:64|32)|x64|x86|build[\s._-]?\d+|release))+$'
)
BRACKET_TAIL = re.compile(
    r'(?i)\s*[\[(](?:steamrip(?:\.com)?|gog|portable|repack|'
    r'pre-?installed|win64|x64|x86|build\s*\d+)[\])]\s*$'
)
WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_ITEMS = 200
MAX_FILES = 1800
MAX_DEPTH = 4


def display_title(name):
    value = str(name or '').strip()
    for _ in range(5):
        old = value
        value = BRACKET_TAIL.sub('', value).strip()
        value = clean_game_title(value)
        value = RELEASE_LABEL.sub('', value).strip(' ._-')
        if value == old:
            break
    return value[:130].strip(' .') or 'Unknown game'


def _safe_name(name):
    value = WINDOWS_INVALID.sub(' ', name)
    value = re.sub(r'\s+', ' ', value).strip(' .')
    if not value or value.upper() in {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'}:
        raise ValueError('Unsafe output folder name')
    return value[:120]


def _reparse(path):
    try:
        st = path.lstat()
        return stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _walk(folder):
    """Bounded, non-executing safety inventory; inspect ignored subfolders for links."""
    files, dirs = [], []
    queue = [(folder, 0)]
    links = False
    incomplete = False
    while queue:
        current, depth = queue.pop(0)
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            incomplete = True
            continue
        for entry in entries:
            if _reparse(entry):
                links = True
                continue
            if entry.is_dir():
                dirs.append(entry)
                if depth < MAX_DEPTH:
                    queue.append((entry, depth + 1))
                else:
                    incomplete = True
            elif entry.is_file():
                files.append(entry)
            if len(files) + len(dirs) >= MAX_FILES:
                incomplete = True
                break
        if incomplete and len(files) + len(dirs) >= MAX_FILES:
            break
    return files, dirs, links, incomplete


def _evidence_items(folder, files, dirs):
    """Exclude utility/backup folders from identity evidence, not safety scanning."""
    def ignored(path, is_dir=False):
        relative = path.relative_to(folder)
        parts = relative.parts if is_dir else relative.parts[:-1]
        return any(part.casefold() in IGNORE_DIRS for part in parts)
    return ([p for p in files if not ignored(p)],
            [p for p in dirs if not ignored(p, True)])


def _identity(title, exe):
    a = words(title)
    b = words(exe.stem)
    b = re.sub(r'(?:\s+(?:win64|win32|shipping|binaries|x64|x86))+$', '', b).strip() or b
    if not a or not b:
        return 0.0
    if a == b or a.replace(' ', '') == b.replace(' ', ''):
        return 1.0
    known = KNOWN_EXES.get(a)
    if known and known.casefold() == exe.name.casefold():
        return 1.0
    return max(
        difflib.SequenceMatcher(None, a, b).ratio(),
        len(set(a.split()) & set(b.split())) / max(1, len(set(a.split()))),
    )


def _item_id(path):
    return hashlib.sha256(str(path.absolute()).casefold().encode('utf-8')).hexdigest()[:24]


def _result(path, category, score, reason, title='', exe='', emulator=None, stable=True):
    action = 'review'
    if category in ('other', 'installer', 'archive'):
        action = 'ignore'
    if category == 'rom':
        action = 'review'
    if category in ('game', 'emulator') and score >= 96 and stable:
        action = 'ready'
    return {
        'id': _item_id(path), 'path': str(path), 'filename': path.name,
        'kind': category, 'title': title or display_title(path.stem if path.is_file() else path.name),
        'confidence': max(0, min(100, int(score))), 'action': action,
        'reason': reason[:300], 'exe': str(exe) if exe else '',
        'emulator': emulator or {}, 'stable': bool(stable),
    }


def _steam_manifest(files):
    return any(p.name.lower() == 'steam_appid.txt' or
               re.fullmatch(r'goggame-\d+\.info', p.name.lower()) or
               re.fullmatch(r'appmanifest_\d+\.acf', p.name.lower())
               for p in files)


def _game_signatures(folder, files, dirs, trusted_store_manifest=False):
    dnames = {p.name.casefold() for p in dirs}
    fnames = {p.name.casefold() for p in files}
    unity = 'unityplayer.dll' in fnames or any(
        name.endswith('_data') for name in dnames)
    unreal = any('win64-shipping.exe' in name for name in fnames) or (
        'engine' in dnames and ('content' in dnames or 'binaries' in dnames))
    assets = any(p.suffix.lower() in {'.pak', '.vpk', '.assets', '.uasset', '.rpf'}
                 for p in files)
    manifest = bool(trusted_store_manifest)  # local claims alone are not independent evidence
    # CommonRedist and steam_api alone do not establish product identity.
    return unity, unreal, assets, manifest


def _emulator_signature(exe, folder, files, dirs):
    definition = EMULATORS.get(exe.name.casefold())
    if not definition:
        return None
    simple = words(definition[0])
    namehint = simple in words(folder.name) or simple in words(exe.stem)
    support = any(p.suffix.lower() in {'.ini', '.toml', '.cfg', '.yml'}
                  and (simple.replace(' ', '') in p.name.lower() or
                       p.name.lower() in {'portable.txt', 'qt.ini', 'config.ini'})
                  for p in files)
    support |= any(p.name.lower() in {'portable.txt', 'xenia-canary-config.toml',
                                     'xenia.config.toml', 'retroarch.cfg',
                                     'pcsx2.ini', 'dolphin.ini'}
                   for p in files)
    support |= any(p.name.lower() in {'portable', 'resources', 'inis', 'sys', 'shaders',
                                     'user', 'config', 'gamefilters'}
                   for p in dirs)
    score = 78 + (8 if namehint else 0) + (18 if support else 0)
    return {
        'name': definition[0], 'platform': definition[1],
        'score': min(score, 100),
        'reason': 'Known emulator executable' + (' and supporting files' if support else
                                                  '; settings or supporting files not confirmed'),
    }


def inspect_folder(folder, *, min_age=120, now=None):
    folder = Path(folder)
    if not folder.is_dir() or _reparse(folder):
        return _result(folder, 'other', 0, 'Folder is unavailable or a reparse link')
    if folder.name.casefold() in IGNORE_DIRS | BLOCKED_FOLDERS:
        return _result(folder, 'other', 0, 'Protected utility or system folder')
    all_files, all_dirs, links, incomplete = _walk(folder)
    if links or incomplete:
        return _result(folder, 'other', 0, 'Nested links, unreadable paths or incomplete inventory; review manually')
    now = time.time() if now is None else now
    try:
        ages = [now - folder.stat().st_mtime]
        ages += [now - p.stat().st_mtime for p in (all_files + all_dirs)]
        stable = min(ages or [0]) >= min_age
    except OSError:
        stable = False
    if any(p.suffix.casefold() in TRANSIENT for p in all_files):
        stable = False
    files, dirs = _evidence_items(folder, all_files, all_dirs)
    exes = [p for p in files if p.suffix.casefold() == '.exe' and not blocked_exe(p)]
    installers = [p for p in files if p.suffix.casefold() == '.exe' and blocked_exe(p)]
    emulator_hits = []
    for p in exes:
        e = _emulator_signature(p, folder, files, dirs)
        if e:
            emulator_hits.append((e, p))
    if emulator_hits:
        emulator_hits.sort(key=lambda x: x[0]['score'], reverse=True)
        if len(emulator_hits) != 1 or any(
            _identity(display_title(folder.name), p) >= 0.85
            for p in exes if p != emulator_hits[0][1]
        ):
            return _result(folder, 'emulator', 65, 'Multiple possible emulator/game programs')
        e, exe = emulator_hits[0]
        return _result(folder, 'emulator', e['score'], e['reason'],
                       e['name'], exe, {'name': e['name'], 'platform': e['platform']},
                       stable=stable)

    if not exes:
        if installers:
            return _result(folder, 'installer', 15, 'Contains an installer but no verified game executable')
        roms = [p for p in files if p.suffix.casefold() in ROMS]
        if roms:
            return _result(folder, 'rom', 70, 'ROM/disc image: platform and emulator require review')
        return _result(folder, 'other', 0, 'No verified game executable')

    title = display_title(folder.name)
    # Remove known source tags from the outer folder without modifying game files.
    from game_discovery import inferred_title
    inferred, _ = inferred_title(folder)
    if inferred != folder.name and not re.fullmatch(r'(?:downloads?|new folder|folder)\s*\d*', folder.name, re.I):
        title = display_title(inferred)
    elif re.fullmatch(r'(?:downloads?|new folder|folder)\s*\d*', folder.name, re.I):
        title = display_title(inferred)

    # Bounded local manifests may suggest a title, but only an independently
    # verified installed-store record can increase identity confidence.
    from game_metadata import inspect_manifest_names
    from store_inventory import installed_inventory, match_candidate
    meta = inspect_manifest_names(folder, files)
    if meta['conflict']:
        return _result(folder, 'game', 45,
                       'Conflicting GOG/Steam/Epic game identity manifests; manual review required',
                       title)
    store_identity = match_candidate(folder, files, installed_inventory())
    if store_identity.get('conflict'):
        return _result(folder, 'game', 45,
                       'Store product ID resolves to conflicting installed titles; manual review required',
                       title)
    if store_identity.get('matched'):
        verified_title = display_title(store_identity.get('title', ''))
        if meta.get('title') and display_title(meta['title']).casefold() != verified_title.casefold():
            return _result(folder, 'game', 45,
                           'Local manifest title conflicts with independent installed-store identity',
                           verified_title)
        title = verified_title
    elif meta['title']:
        title = display_title(meta['title'])

    opts = candidates(folder, title)
    if not opts:
        return _result(folder, 'other', 20, 'No executable passed safe game candidate checks')
    exe = Path(opts[0]['path'])
    rival = len(opts) > 1 and opts[0]['score'] - opts[1]['score'] < 18
    ident = _identity(title, exe)
    unity, unreal, assets, manifest = _game_signatures(folder, files, dirs, store_identity.get('matched', False))
    # Avoid treating a random folder containing one .exe as a game.
    scores = [int(35 + 35 * ident), 30 if (unity or unreal) else 0,
              20 if manifest else 0, 16 if assets else 0]
    score = min(sum(scores), 100)
    structural = int(unity or unreal) + int(manifest) + int(assets)
    reason = 'Executable plus ' + ', '.join(
        x for test, x in ((unity, 'Unity structure'), (unreal, 'Unreal structure'),
                          (manifest, 'store manifest'), (assets, 'game content assets'))
        if test
    ) if structural else 'Only a game-like executable; independent structure not established'
    if not structural:
        score = min(score, 56)
    if ident < 0.65:
        score = min(score, 79)
        reason += '; executable identity does not match folder title'
    if rival:
        score = min(score, 75)
        reason += '; multiple similarly plausible executables'
    if installers and not structural:
        score = min(score, 45)
        reason += '; installer found without game structure'
    if store_identity.get('matched'):
        reason += '; independent '+str(store_identity.get('source','store')).upper()+' installed inventory confirms product ID '+str(store_identity.get('productId',''))
    elif meta['title']:
        reason += '; local manifest title is unverified against installed-store inventory ('+meta['source']+')'
    if not stable:
        reason += '; files are recent or download is incomplete'
    return _result(folder, 'game', score, reason, title, exe, stable=stable)


def inspect_entry(entry, min_age=120, now=None):
    entry = Path(entry)
    if _reparse(entry):
        return _result(entry, 'other', 0, 'Link or reparse point ignored')
    if entry.is_dir():
        return inspect_folder(entry, min_age=min_age, now=now)
    ext = entry.suffix.casefold()
    if ext in ARCHIVES:
        return _result(entry, 'archive', 0, 'Archive; inspect or extract manually, never auto-execute')
    if ext in ROMS:
        return _result(entry, 'rom', 25, 'Disc image/ROM: emulator mapping requires review')
    if ext in {'.exe', '.msi', '.msix'}:
        return _result(entry, 'installer', 0, 'Loose executable/installer; never automatically move or run')
    return _result(entry, 'other', 0, 'Not a game folder')


def scan_downloads(downloads, min_age=120):
    downloads = Path(downloads)
    if not downloads.is_dir() or _reparse(downloads):
        return []
    try:
        entries = sorted(downloads.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return []
    return [inspect_entry(p, min_age=min_age) for p in entries]


def discover_emulators(root, min_age=120):
    root = Path(root)
    if not root.is_dir() or _reparse(root):
        return []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return []
    return [inspect_folder(p, min_age=min_age) for p in entries if p.is_dir() and not _reparse(p)]


def move_verified(item, downloads, games_root, emulators_root, *, min_age=120):
    """Race-resistant, conservative rename; never overwrite or copy across disks."""
    src = Path(item['path'])
    base = Path(downloads).resolve()
    if src.parent.resolve() != base or _reparse(src) or not src.is_dir():
        raise ValueError('Only direct download folders can be organized automatically')
    current = inspect_folder(src, min_age=min_age)
    if current['action'] != 'ready' or current['kind'] != item['kind'] or current['id'] != item['id']:
        raise ValueError('Folder changed, is unverified, or still downloading')
    if current['title'] != item['title'] or current['exe'] != item['exe']:
        raise ValueError('Folder identity changed since it was scanned')
    destination_root = Path(games_root if current['kind'] == 'game' else emulators_root)
    if _reparse(destination_root):
        raise ValueError('Destination is a symlink/reparse point')
    if not destination_root.exists():
        destination_root.mkdir(parents=True, exist_ok=True)
    if not destination_root.is_dir() or _reparse(destination_root):
        raise ValueError('Destination is not a safe directory')
    target = destination_root / _safe_name(current['title'])
    # Do not nest the source inside itself, overwrite, or duplicate another copy.
    if target.exists() or target.is_symlink():
        raise FileExistsError('Already present: ' + str(target))
    if src.stat().st_dev != destination_root.stat().st_dev:
        raise OSError('Cross-volume move requires manual review; automatic partial copies are prohibited')
    # os.rename is atomic on the same filesystem and fails on a conflicting target.
    os.rename(src, target)
    exe_relative = Path(current['exe']).relative_to(src)
    return {
        'kind': current['kind'], 'name': current['title'],
        'path': str(target), 'exe': str(target / exe_relative),
        'emulator': current['emulator'], 'from': str(src),
    }


def undo_verified(record, downloads, games_root, emulators_root):
    """Reverse a recorded organization via rename only, never overwrite.

    The undo destination must be a top-level child of Downloads. This is not
    a generic move command: callers supply an entry created by Elmos World.
    """
    kind = record.get('kind')
    if kind not in ('game', 'emulator'):
        raise ValueError('Only recorded game/emulator moves can be undone')
    old = Path(record.get('from', ''))
    new = Path(record.get('path', ''))
    inbox = Path(downloads)
    root = Path(games_root if kind == 'game' else emulators_root)
    if (old.parent.resolve() != inbox.resolve() or
            new.parent.resolve() != root.resolve()):
        raise ValueError('Source or target is outside approved folders')
    if any(_reparse(p) for p in (inbox, root, new)):
        raise ValueError('Reparse points cannot be used during undo')
    if old.exists() or old.is_symlink():
        raise FileExistsError('Original Downloads folder already exists')
    if not new.is_dir():
        raise FileNotFoundError('Organized folder no longer exists')
    files, dirs, links, truncated = _walk(new)
    if links or truncated:
        raise ValueError('Folder contents changed to include links or too many files')
    exe = Path(record.get('exe', ''))
    if not exe.is_file() or not exe.is_relative_to(new):
        raise ValueError('Recorded game/emulator executable no longer exists')
    if new.stat().st_dev != inbox.stat().st_dev:
        raise ValueError('Cannot undo across disks without risk of partial copy')
    # The destination check is repeated immediately before atomic rename.
    if old.exists():
        raise FileExistsError('Cannot replace Downloads folder during undo')
    os.rename(new, old)
    return {'kind': kind, 'name': record.get('name', new.name),
            'from': str(new), 'path': str(old)}
