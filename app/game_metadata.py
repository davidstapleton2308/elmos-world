"""Bounded, offline identity evidence for game folders.

Contents are untrusted data; parse only small text manifests with standard
library and never execute binary programs, launch installers, or modify files.
Some game installers include misleading metadata. Multiple contradictory
product identities cause a review decision, not an automatic rename.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LIMIT = 128_000
TITLE_MIN = 3
TITLE_MAX = 125
BAD_TITLES = {'game', 'launcher', 'unknown', 'unity', 'unreal engine', 'application',
              'windows', 'steam', 'epic games', 'gog galaxy', 'install'}
ACF_NAME = re.compile(r'(?im)^\s*"name"\s*"((?:[^"\\]|\\.){3,170})"')
ACF_ID = re.compile(r'(?im)^\s*"appid"\s*"(\d{1,12})"')
GOG_FILE = re.compile(r'(?i)^goggame-(\d{1,20})\.info$')
ACF_FILE = re.compile(r'(?i)^appmanifest_(\d{1,12})\.acf$')


def clean_title(title):
    title = str(title or '').strip()
    title = ''.join(ch for ch in title if ch.isprintable() and ch not in '/\\<>|')
    title = ' '.join(title.split()).strip(' ._-')
    if (not TITLE_MIN <= len(title) <= TITLE_MAX or
        title.casefold() in BAD_TITLES or not any(ch.isalpha() for ch in title)):
        return ''
    return title


def _read(path):
    try:
        if not path.is_file() or path.stat().st_size > LIMIT:
            return ''
        return path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        return ''


def _gog_name(path):
    try:
        j = json.loads(_read(path))
        if not isinstance(j, dict):
            return ''
        return clean_title(j.get('name') or j.get('gameTitle') or j.get('title'))
    except (ValueError, TypeError):
        return ''


def _steam_name(path, expected_id):
    content = _read(path)
    mid = ACF_ID.search(content)
    label = ACF_NAME.search(content)
    if mid and mid.group(1) != expected_id:
        return ''
    if label:
        return clean_title(label.group(1).replace(r'\"','"'))
    return ''


def _epic_name(path):
    try:
        obj = json.loads(_read(path))
        if not isinstance(obj, dict):
            return ''
        if not obj.get('AppName') and not obj.get('CatalogItemId'):
            return ''
        return clean_title(obj.get('DisplayName'))
    except (ValueError, TypeError):
        return ''


def inspect_manifest_names(folder, files):
    """Return title, source, conflict state and evidence paths.

    A declared name is evidence, NOT proof of ownership or authenticity.
    The scanner must still verify a game binary and game engine/data files.
    """
    root = Path(folder)
    results = []
    for path in files:
        path = Path(path)
        # Never trust metadata from a random nested utility.
        if path.parent != root and path.parent.name.casefold() != '.egstore':
            continue
        suffix = path.suffix.casefold()
        source = ''
        title = ''
        m = GOG_FILE.fullmatch(path.name)
        a = ACF_FILE.fullmatch(path.name)
        if m:
            source = 'GOG product manifest'
            title = _gog_name(path)
        elif a:
            source = 'Steam appmanifest'
            title = _steam_name(path, a.group(1))
        elif suffix == '.item' and path.parent.name.casefold() == '.egstore':
            source = 'Epic installation manifest'
            title = _epic_name(path)
        if title:
            results.append({'title':title,'source':source,'path':str(path)})
    canonical = {' '.join(re.findall(r'[a-z0-9]+',v['title'].casefold())) for v in results}
    conflicting = len(canonical) > 1
    return {'title':results[0]['title'] if len(canonical)==1 and results else '',
            'source':results[0]['source'] if len(canonical)==1 and results else '',
            'conflict':conflicting,'evidence':results[:8]}
