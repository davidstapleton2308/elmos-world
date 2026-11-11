"""Optional, read-only public store screenshot discovery for Elmos World.

Store descriptions and screenshots are deliberately independent. A curated description
must never suppress screenshot lookup. No game executables, Steam files, or artwork
matches are modified. Images are saved under LOCALAPPDATA, outside application updates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

MAX_SHOTS = 6
MAX_IMAGE_SIZE = 5_000_000
VALID_HOSTS = (
    'steamstatic.com', 'akamaihd.net',
)
# A SteamGridDB title is not necessarily a Steam-store title. These only expand
# obviously abbreviated library titles; fuzzy matches or similarly named sequels
# are never auto-accepted.
TITLE_ALIASES = {
    'control ue': 'Control Ultimate Edition',
    'control ultimate edition': 'Control Ultimate Edition',
    'sekiro shadows die twice': 'Sekiro: Shadows Die Twice',
    'ssx 2012': '',  # This console-exclusive game does not have a Steam store page.
    'ssx tricky': '',
}


def normalize(name: str) -> str:
    name = unicodedata.normalize('NFKD', str(name or ''))
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', name.casefold()))


def search_title(title: str) -> str:
    norm = normalize(title)
    return TITLE_ALIASES.get(norm, title.strip())


def trusted_screenshot(url: str) -> bool:
    try:
        u = urllib.parse.urlsplit(url)
        host = (u.hostname or '').lower()
        return (u.scheme == 'https' and not u.username and not u.password
                and u.port in (None, 443)
                and any(host == suffix or host.endswith('.' + suffix)
                        for suffix in VALID_HOSTS)
                and u.path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
    except (ValueError, AttributeError):
        return False


def trusted_trailer(url: str) -> bool:
    """Only direct HTTPS video files from Steam's media CDN may play in-app."""
    try:
        candidate = urllib.parse.urlsplit(url)
        host = (candidate.hostname or '').lower()
        return (candidate.scheme == 'https' and not candidate.username and not candidate.password
                and candidate.port in (None, 443)
                and any(host == suffix or host.endswith('.' + suffix) for suffix in VALID_HOSTS)
                and candidate.path.lower().endswith(('.mp4', '.webm')))
    except (ValueError, AttributeError):
        return False


def store_trailer(data: dict) -> dict:
    for movie in sorted(data.get('movies') or [], key=lambda m: not m.get('highlight', False)):
        mp4 = movie.get('mp4') or {}
        for candidate in (mp4.get('max', ''), mp4.get('480', '')):
            # Older Steam APIs still expose HTTP URLs. Upgrade only a verified
            # Steam media host and never allow a redirect to a user-supplied host.
            if isinstance(candidate, str) and candidate.startswith('http://'):
                candidate = 'https://' + candidate[7:]
            if trusted_trailer(candidate):
                return {'title': str(movie.get('name', 'Game trailer'))[:100], 'url': candidate}
    return {}


def image_kind(data: bytes) -> str:
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return '.webp'
    return ''


def request_json(url: str):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 ElmosWorld/2.7',
                                               'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=9) as response:
        return json.load(response)


def discover_store(title: str, hint: str = '', json_fetch=request_json) -> dict:
    """Resolve only an unambiguous *exact* Steam Store match.

    Never silently substitute a remake, unrelated sequel, or matching-looking
    artwork from a different edition. A user may supply an explicit store title
    by matching artwork, but even then the Steam result must agree exactly.
    """
    candidates = []
    for label in (title, hint):
        resolved = search_title(str(label or ''))
        if resolved and normalize(resolved) not in {normalize(x) for x in candidates}:
            candidates.append(resolved)
    if not candidates:
        return {'status': 'unavailable', 'reason': 'No known Steam Store listing for this platform.'}
    for query in candidates[:2]:
        url = 'https://store.steampowered.com/api/storesearch/?' + urllib.parse.urlencode(
            {'term': query, 'l': 'english', 'cc': 'US'})
        found = json_fetch(url).get('items', [])
        exact = [x for x in found if normalize(x.get('name', '')) == normalize(query)]
        if len(exact) != 1:
            continue
        steamid = int(exact[0]['id'])
        url = 'https://store.steampowered.com/api/appdetails?' + urllib.parse.urlencode(
            {'appids': steamid, 'cc': 'US', 'l': 'english'})
        result = json_fetch(url).get(str(steamid), {})
        if not result.get('success'):
            continue
        data = result.get('data', {})
        if normalize(data.get('name', '')) != normalize(query):
            continue
        urls = []
        for shot in data.get('screenshots', []):
            address = shot.get('path_full') or shot.get('path_thumbnail') or ''
            if trusted_screenshot(address) and address not in urls:
                urls.append(address)
            if len(urls) >= MAX_SHOTS:
                break
        return {'status': 'found' if urls else 'unavailable', 'title': data.get('name', query),
                'appId': steamid, 'urls': urls, 'trailer': store_trailer(data),
                'reason': '' if urls else 'Steam does not list screenshots for this game.'}
    return {'status': 'unavailable', 'reason': 'No exact Steam Store title match. You can import screenshots in Configure.'}


def download_image(url: str) -> bytes:
    if not trusted_screenshot(url):
        raise ValueError('Untrusted screenshot URL')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 ElmosWorld/2.7'})
    with urllib.request.urlopen(req, timeout=12) as resp:
        if int(resp.headers.get('Content-Length') or 0) > MAX_IMAGE_SIZE:
            raise ValueError('Image too large')
        data = resp.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE or not image_kind(data):
        raise ValueError('Unsupported image format or excessive size')
    return data


class ScreenshotLibrary:
    """Screenshots are immutable once downloaded; manifest refreshes are atomic.

    A game ID is hashed before making a directory. Only manifest-listed local
    files can be served; no user-supplied filesystem paths become HTTP routes.
    """
    def __init__(self, root: Path, resolver=discover_store, downloader=download_image, pause_while_playing=None):
        self.root = Path(root)
        self.resolver = resolver
        self.downloader = downloader
        self.pause_while_playing = pause_while_playing or (lambda: False)
        self.lock = threading.RLock()
        self.jobs = set()
        self.pending = {}
        self._batch = False
        self._batch_progress = {'running': False, 'done': 0, 'total': 0}

    def folder(self, game_id: str) -> Path:
        digest = hashlib.sha256(str(game_id).encode('utf-8')).hexdigest()[:28]
        return self.root / digest

    def manifest(self, game_id: str):
        f = self.folder(game_id) / 'manifest.json'
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, game_id: str, contents: dict):
        folder = self.folder(game_id)
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder,
                                         prefix='manifest-', suffix='.tmp', delete=False) as output:
            json.dump(contents, output, indent=2)
            temp_name = output.name
        os.replace(temp_name, folder / 'manifest.json')

    def _files(self, game_id: str, data: dict):
        folder = self.folder(game_id)
        return [name for name in data.get('files', []) if isinstance(name, str)
                and re.fullmatch(r'(?:store-\d{2}(?:-[a-f0-9]{10})?|user-\d{2})\.(?:jpg|jpeg|png|webp)', name)
                and (folder / name).is_file()]

    def _manual(self, game_id: str):
        folder = self.folder(game_id)
        return sorted(f.name for f in folder.glob('user-*') if
                      re.fullmatch(r'user-\d{2}\.(?:jpg|jpeg|png|webp)', f.name) and f.is_file())

    def status(self, game_id: str, title: str, hint: str = '', schedule=True):
        identity = normalize(search_title(title)) + '|' + normalize(search_title(hint))
        with self.lock:
            data = self.manifest(game_id)
            same_title = data.get('identity') == identity
            manual = self._manual(game_id)
            stored = self._files(game_id, data) if same_title else []
            files = list(dict.fromkeys(manual + stored))
            running = game_id in self.jobs
            ttl = 1800 if data.get('partial') else (7 * 86400 if data.get('status') == 'found' else 86400)
            if data.get('status') == 'error': ttl = 1800
            stale = (not same_title or time.time() - float(data.get('checked', 0)) > ttl)
            should_schedule = schedule and stale and not running
            if running: state = 'loading'
            elif files: state = 'ready'
            elif not same_title or not data: state = 'loading' if should_schedule else 'unavailable'
            else: state = data.get('status', 'unavailable')
            response = {'status': state, 'count': len(files), 'indexes': list(range(len(files))),
                        'source': data.get('source', '') if same_title else '',
                        'reason': data.get('reason', '') if same_title else '',
                        'refreshing': bool(running or should_schedule), 'partial': bool(data.get('partial', False)) if same_title else False,
                        'trailer': data.get('trailer', {}) if same_title else {},
                        'generation': int(data.get('checked', 0)) if same_title else 0}
        if should_schedule:
            self.refresh(game_id, title, hint)
        return response

    def refresh(self, game_id: str, title: str, hint: str = '', force=False) -> bool:
        with self.lock:
            if game_id in self.jobs:
                if force: self.pending[game_id] = (title, hint)
                return bool(force)
            data = self.manifest(game_id)
            identity = normalize(search_title(title)) + '|' + normalize(search_title(hint))
            ttl = 1800 if data.get('status') == 'error' or data.get('partial') else (86400 if data.get('status') != 'found' else 7 * 86400)
            if not force and data.get('identity') == identity and time.time() - float(data.get('checked', 0)) < ttl:
                return False
            self.jobs.add(game_id)
        t = threading.Thread(target=self._worker, args=(game_id, title, hint, identity),
                             name='ElmosScreenshot-' + hashlib.md5(game_id.encode('utf8')).hexdigest()[:6], daemon=True)
        t.start()
        return True

    def _worker(self, game_id, title, hint, identity):
        previous = self.manifest(game_id)
        same_title = previous.get('identity') == identity
        previous_files = self._files(game_id, previous) if same_title else []
        try:
            resolved = self.resolver(title, hint)
            urls = resolved.get('urls', []) if resolved.get('status') == 'found' else []
            folder = self.folder(game_id)
            folder.mkdir(parents=True, exist_ok=True)
            files = []
            failed = 0
            for i, url in enumerate(urls[:MAX_SHOTS]):
                while self.pause_while_playing():
                    time.sleep(1)
                try:
                    raw = self.downloader(url)
                    ext = image_kind(raw)
                    if not ext: raise ValueError('Unsupported image bytes')
                    # Versioned names keep the image cache honest after refresh.
                    # A failed slot retains its previous valid file only if the
                    # game identity is unchanged. Different editions never mix.
                    tag = hashlib.sha256(raw).hexdigest()[:10]
                    name = f'store-{i:02d}-{tag}{ext}'
                    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as tmp:
                        tmp.write(raw)
                        pathname = tmp.name
                    os.replace(pathname, folder / name)
                    files.append(name)
                except Exception:
                    failed += 1
                    # A failed network attempt cannot erase working media for
                    # the SAME confirmed title. Do not reuse another title's art.
                    if i < len(previous_files): files.append(previous_files[i])
            if not files and previous_files and not urls:
                files = previous_files
            trailer = resolved.get('trailer', {})
            if trailer and not trusted_trailer(trailer.get('url', '')):
                trailer = {}
            if not trailer and same_title:
                trailer = previous.get('trailer', {})
            outcome = 'found' if files else 'unavailable'
            self._write(game_id, {'identity': identity, 'checked': time.time(),
                                  'status': outcome, 'reason': resolved.get('reason','') if not files else '',
                                  'source': 'Steam Store' if files or trailer else '',
                                  'steamAppId': resolved.get('appId'), 'files': files,
                                  'trailer': trailer, 'partial': bool(failed)})
        except Exception:
            if same_title and (previous_files or previous.get('trailer')):
                previous['checked'] = time.time()
                previous['partial'] = True
                self._write(game_id, previous)
            else:
                self._write(game_id, {'identity': identity, 'checked': time.time(),
                                      'status': 'error', 'reason': 'Could not reach the media source.',
                                      'files': [], 'trailer': {}})
        finally:
            with self.lock:
                self.jobs.discard(game_id)
                pending = self.pending.pop(game_id, None)
            if pending:
                self.refresh(game_id, *pending, force=True)

    def image(self, game_id: str, title: str, hint: str, index: int) -> Path | None:
        """Only permit images in the current matched gallery manifest."""
        view = self.status(game_id, title, hint, schedule=False)
        if index < 0 or index >= view['count']:
            return None
        data = self.manifest(game_id)
        identity = normalize(search_title(title)) + '|' + normalize(search_title(hint))
        files = list(dict.fromkeys(self._manual(game_id) +
                                   (self._files(game_id, data) if data.get('identity') == identity else [])))
        target = self.folder(game_id) / files[index]
        return target if target.is_file() else None

    def import_images(self, game_id: str, paths: list[str]) -> dict:
        folder = self.folder(game_id)
        folder.mkdir(parents=True, exist_ok=True)
        added = 0
        for raw_path in paths[:12]:
            p = Path(raw_path)
            if not p.is_file() or p.suffix.casefold() not in ('.jpg', '.jpeg', '.png', '.webp'):
                continue
            if p.stat().st_size > MAX_IMAGE_SIZE:
                continue
            raw = p.read_bytes()
            ext = image_kind(raw)
            if not ext: continue
            index = 0
            while index < 99 and any((folder / f'user-{index:02d}{e}').exists() for e in ('.jpg','.jpeg','.png','.webp')):
                index += 1
            if index >= 99: break
            destination = folder / f'user-{index:02d}{ext}'
            # Snapshot; never edit the original image.
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as tmp:
                tmp.write(raw)
                pathname = tmp.name
            os.replace(pathname, destination)
            added += 1
        return {'added': added, 'totalManual': len(self._manual(game_id))}

    def batch_refresh(self, games, force=False):
        with self.lock:
            if self._batch: return {'running': True, **self._batch_progress}
            self._batch = True
            self._batch_progress = {'running': True, 'done': 0, 'total': len(games)}
        def batch():
            try:
                for g in games:
                    while self.pause_while_playing():
                        time.sleep(1)
                    self.refresh(g['id'], g['name'], g.get('localMatch', ''), force=force)
                    # Limit concurrent network traffic; refresh is async by design.
                    while True:
                        with self.lock:
                            busy = g['id'] in self.jobs
                        if not busy: break
                        time.sleep(.4)
                    with self.lock: self._batch_progress['done'] += 1
                    time.sleep(.3)
            finally:
                with self.lock:
                    self._batch = False
                    self._batch_progress['running'] = False
        threading.Thread(target=batch, name='ElmosGalleryBatch', daemon=True).start()
        return dict(self._batch_progress)

    def batch_status(self):
        with self.lock: return dict(self._batch_progress)
