"""Read-only opt-in GeForce NOW My Library cache scanner."""
from __future__ import annotations
import os, re
from pathlib import Path
from urllib.parse import urlsplit

GAME_ITEM = re.compile(r'"__typename"\s*:\s*"GameItem"')
TITLE = re.compile(r'"title"\s*:\s*"((?:\\.|[^"\\])*)"')
GAME_UUID = re.compile(r'"id"\s*:\s*"([a-fA-F0-9-]{36})"')
VARIANT = re.compile(
    r'"id"\s*:\s*"(\d+)"\s*,.*?"shortName"\s*:\s*"((?:\\.|[^"\\])*)"'
    r'.*?"appStore"\s*:\s*"((?:\\.|[^"\\])+)".*?"selected"\s*:\s*(true|false)',
    re.DOTALL)
ART = re.compile(r'"(HERO_IMAGE|TV_BANNER|BOX_ART|KEY_ART|STORE_IMAGE|SMALL_IMAGE|TILE|ICON|LOGO)"'
                 r'\s*:\s*"(https?://[^"\\]{8,1000})"', re.I)
STORE = {'UPLAY':'Ubisoft','STEAM':'Steam','EPIC':'Epic Games',
         'XBOX':'Xbox','MICROSOFT':'Xbox','BATTLENET':'Battle.net'}

def cache_root():
    return (Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
            / 'NVIDIA Corporation' / 'GeForceNOW' / 'CefCache' / 'Default'
            / 'Service Worker' / 'CacheStorage')

def _safe_art(url):
    p = urlsplit(url)
    host = (p.hostname or '').lower()
    return (url if p.scheme == 'https' and len(url) < 900 and not p.username
            and (host == 'nvidia.com' or host.endswith('.nvidia.com')
                 or host == 'nvidiagrid.net' or host.endswith('.nvidiagrid.net')
                 or host == 'geforcenow.com' or host.endswith('.geforcenow.com'))
            else '')

def _plain(value):
    return (value.replace(r'\"', '"').replace(r'\/', '/')
            .replace(r'\n', ' ').replace(r'\t', ' ').strip())

def extract_cached_games(data):
    """Selected game variants only; returns no credentials or cache contents."""
    text = data.decode('utf-8', errors='ignore') if isinstance(data, bytes) else str(data)
    if not GAME_ITEM.search(text):
        return {}
    games = {}
    for part in GAME_ITEM.split(text)[1:]:
        part = part[:2_000_000]
        vstart = part.find('"variants"')
        if vstart < 0:
            continue
        head = part[:vstart]
        title_match = TITLE.search(head)
        uuid_match = GAME_UUID.search(head)
        if not title_match:
            continue
        name = _plain(title_match.group(1))
        if not 2 <= len(name) <= 160:
            continue
        art = {}
        for key, url in ART.findall(part):
            value = _safe_art(url)
            if not value:
                continue
            if key.upper() in ('HERO_IMAGE', 'TV_BANNER'):
                art.setdefault('hero', value)
            elif key.upper() in ('BOX_ART', 'KEY_ART', 'STORE_IMAGE', 'TILE', 'SMALL_IMAGE'):
                art.setdefault('portrait', value)
        for match in VARIANT.finditer(part[vstart:]):
            variant, raw_short, raw_store, selected = match.groups()
            if selected != 'true':
                continue
            store = _plain(raw_store).upper()
            if len(store) > 64 or not re.fullmatch(r'[A-Z0-9_ -]+', store):
                continue
            games[variant] = {'name':name,'store':STORE.get(store,store.title()),
                              'variantId':variant,
                              'shortName':_plain(raw_short)[:140],
                              'parentGameId':uuid_match.group(1) if uuid_match else '',
                              'images':art}
    return games

def scan_cache(root=None, max_bytes=400_000_000):
    """Read public game metadata from local GFN CacheStorage. Never copy raw caches."""
    root = Path(root) if root is not None else cache_root()
    if not root.is_dir():
        return {'games':[], 'scanned':0,'message':
                'GeForce NOW library cache not found. Open My Library and scroll through your games.'}
    found, files_scanned, used = {}, 0, 0
    for folder, _, files in os.walk(root):
        for filename in files:
            path = Path(folder) / filename
            try:
                if path.is_symlink():
                    continue
                size = path.stat().st_size
                if size > 30_000_000 or used + size > max_bytes:
                    continue
                with path.open('rb') as stream:
                    content = stream.read(30_000_001)
                used += len(content)
                if b'GameItem' not in content:
                    continue
                entries = extract_cached_games(content)
                if entries:
                    files_scanned += 1
                    found.update(entries)
            except (OSError, UnicodeError, ValueError):
                continue
    games = sorted(found.values(),key=lambda x:(x['name'].casefold(),x['store'].casefold()))
    return {'games':games,'scanned':files_scanned,
            'message': f'{len(games)} selected GeForce NOW entries found in local cache.'
                       if games else 'No selected games cached. Open My Library, scroll it, and retry.'}
