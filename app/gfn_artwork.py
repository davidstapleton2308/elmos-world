"""Find artwork suited to two different shapes: portrait game covers and wide hero scenes.

Uses public Steam Store metadata and, when the user configured its key in Settings,
SteamGridDB. Exact edition/title matches only. Never sends ownership, tokens,
NVIDIA cache, or game files to artwork providers.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request

IMAGE_HOSTS = ('steamstatic.com', 'steamgriddb.com', 'akamaihd.net')
ROMANS = {'ii': '2', 'iii': '3', 'iv': '4', 'vi': '6', 'v': '5'}


def normalized_title(title):
    title = unicodedata.normalize('NFKD', str(title or ''))
    title = title.replace('\u00ae', '').replace('\u2122', '').replace('\u00a9', '')
    title = title.replace('\u2019', "'").replace('\u2018', "'")
    title = title.casefold()
    title = re.sub(r'\b(?:remastered|definitive edition)\b', '', title) if False else title
    words = re.findall(r'[a-z0-9]+', title)
    return ' '.join(ROMANS.get(w, w) for w in words)


def safe_image(url):
    try:
        p = urllib.parse.urlsplit(str(url))
        host = (p.hostname or '').lower()
        if p.scheme != 'https' or p.username or p.password:
            return ''
        if not any(host == h or host.endswith('.' + h) for h in IMAGE_HOSTS):
            return ''
        if len(url) > 900 or not p.path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            return ''
        return url
    except (TypeError, ValueError):
        return ''


def get_json(url, key=''):
    headers = {'User-Agent': 'ElmosWorldCloudArt/1.0'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=7) as resp:
        return json.load(resp)


def steam_grid_match(title, key):
    """Use the same optional SteamGridDB key as the main library."""
    query = urllib.parse.quote(title, safe='')
    try:
        rows = get_json('https://www.steamgriddb.com/api/v2/search/autocomplete/' + query,
                        key).get('data', [])
        exact = [r for r in rows if normalized_title(r.get('name')) == normalized_title(title)]
        if len(exact) != 1:
            return {}
        gid = int(exact[0]['id'])
        if gid <= 0:
            return {}
        prefix = 'https://www.steamgriddb.com/api/v2/'
        out = {}
        for field, route in (
            ('portrait', 'grids/game/' + str(gid) + '?dimensions=600x900'),
            ('hero', 'heroes/game/' + str(gid)),
        ):
            try:
                doc = get_json(prefix + route, key)
                for row in doc.get('data', []):
                    url = safe_image(row.get('url', ''))
                    if url:
                        out[field] = url
                        break
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return out
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def steam_store_match(title):
    """Public exact title/edition match; only return generated image URL candidates."""
    try:
        term = urllib.parse.quote(title, safe='')
        doc = get_json('https://store.steampowered.com/api/storesearch/?term='
                       + term + '&l=english&cc=US')
        matches = [r for r in doc.get('items', [])
                   if normalized_title(r.get('name', '')) == normalized_title(title)]
        if len(matches) != 1:
            return {}
        app_id = int(matches[0]['id'])
        if app_id <= 0:
            return {}
        prefix = f'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/'
        return {'portrait': prefix + 'library_600x900.jpg',
                'hero': prefix + 'library_hero.jpg',
                'steamId': app_id}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def resolve_art(title, key=''):
    """Exact matches from optional artwork provider first; public Steam fallback."""
    title = ' '.join(str(title or '').split())[:140]
    if len(title) < 2 or not normalized_title(title):
        return {}
    if key:
        result = steam_grid_match(title, key)
        if result.get('portrait') and result.get('hero'):
            return result
        fallback = steam_store_match(title)
        if result:
            return {**fallback, **result}
        return fallback
    return steam_store_match(title)
