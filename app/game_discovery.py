"""Offline, read-only PC game folder recognition.

No execution, untrusted file parsing, account access, or network requests. Pure
heuristics are deliberately conservative when several viable EXEs remain.
"""
from __future__ import annotations
import os
import re
import difflib
from pathlib import Path

JUNK_ROOT = re.compile(r'^(?:voices?\d+|download(?:s)?[ _-]*\d*|new folder(?: \(\d+\))?|game(?:s)?[ _-]*\d*|release[ _-]*\d+|folder[ _-]*\d+)$', re.I)
DANGEROUS_NAMES = re.compile(r'(?:^|[\W_])(?:unins\d*|uninstall|setup|install(?:er)?|redist(?:ributable)?|vc[_-]?redist|vcredist|dxsetup|dxwebsetup|crashreport(?:er)?|crashhandler|updater|bootstrapper|eac|easyanticheat)(?:$|[\W_])', re.I)
DANGEROUS_PATH_COMPONENTS = {'_uninstall','_uninstallers','_commonredist','redistributables','redist','installerresources','prerequisites','prereqs','directx','vcredist','vc_redist','uninstall','installer','installers'}
# Download release folders frequently mix game titles with site credits and build
# numbers. Strip only bounded, recognizable suffixes; never erase arbitrary
# digits embedded in a real title (e.g. "Silent Hill 2", "7 Days to Die").
SOURCE_TAIL = re.compile(
    r'(?i)(?:[\s._-]+|^)(?:steam\s*[._-]?\s*rip(?:\s*[._-]?\s*com)?|'
    r'fitgirl(?:\s+repacks?)?|elamigos|dodi(?:\s+repacks?)?|repack|'
    r'gog(?:\s*[._-]?\s*games)?)\s*$',
)
VERSION_TAIL = re.compile(
    r'(?i)(?:[\s._-]+)v\s*\d+(?:[\s._-]+\d+){0,5}[a-z]?\s*$'
)


def clean_game_title(raw):
    """Return a display title, not a claim of verified product identity.

    No live file changes, network lookups or Steam shortcut modifications.
    Version stripping intentionally applies only to a trailing v-prefixed build.
    """
    title=str(raw or '').strip()
    if not title:return ''
    # Strip trailing site markers and v-prefixed build numbers in either order.
    for _ in range(5):
        old=title
        title=SOURCE_TAIL.sub('',title).strip(' ._-')
        title=VERSION_TAIL.sub('',title).strip(' ._-')
        if title==old:break
    # Replace separator punctuation only after recognizing the original suffixes.
    title=re.sub(r'(?<=[A-Za-z0-9])[._-](?=[A-Za-z0-9])',' ',title)
    title=' '.join(title.split())
    # Unambiguous abbreviation in a familiar title; do not rewrite other UEs.
    if title.casefold()=='control ue':title='Control Ultimate Edition'
    return title or str(raw or '').strip()


KNOWN_EXES = {
    '7 days to die':'7DaysToDie.exe','buckshot roulette':'Buckshot Roulette.exe',
    'control':'Control.exe','control ultimate edition':'Control.exe',
    'keep talking and nobody explodes':'ktane.exe','outer wilds':'OuterWilds.exe',
    'sekiro shadows die twice':'sekiro.exe','silent hill 2':'SHProto.exe',
    'the jackbox party pack 7':'The Jackbox Party Pack 7.exe',
    'assassins creed black flag resynced':'ACBlackFlag.exe',
    'assassins creed iv black flag':'ACBlackFlag.exe',
}

def words(value):
    value=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',str(value))
    value=re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])',' ',value)
    return ' '.join(re.findall(r'[a-z0-9]+',value.lower()))

def blocked_exe(path):
    p=Path(path)
    name=p.stem
    flat=name.lower().replace(' ','').replace('_','').replace('-','')
    if any(word in flat for word in ('installer','uninstall','vcredist','redistributable','crashreport','bootstrapper','updater','dxsetup','easyanticheat')):return True
    if DANGEROUS_NAMES.search(name):return True
    return any(part.lower() in DANGEROUS_PATH_COMPONENTS or part.lower().startswith('unins') for part in p.parts[:-1])

def inferred_title(folder):
    folder=Path(folder)
    try:
        direct=[p for p in folder.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith('.')]
        root_exe=any(p.is_file() and p.suffix.lower()=='.exe' and not blocked_exe(p) for p in folder.iterdir())
    except (PermissionError,OSError):direct=[];root_exe=False
    best=folder
    plausible=[p for p in direct if p.name.lower() not in DANGEROUS_PATH_COMPONENTS]
    if len(plausible)==1 and not root_exe and (JUNK_ROOT.fullmatch(folder.name.strip()) or len(words(plausible[0].name))>len(words(folder.name))+4):
        best=plausible[0]
    name=clean_game_title(best.name)
    return name or folder.name, ('inner-folder' if best!=folder else 'folder')

def candidates(folder, title=None):
    folder=Path(folder)
    title=title or inferred_title(folder)[0]
    tw=words(title); tset=set(tw.split())
    expected=KNOWN_EXES.get(tw,'').lower()
    entries=[]
    if not folder.is_dir():return []
    for dirpath,dirs,files in os.walk(folder,followlinks=False):
        depth=len(Path(dirpath).relative_to(folder).parts)
        dirs[:]=[d for d in dirs if depth<5 and not d.startswith('.') and d.lower() not in DANGEROUS_PATH_COMPONENTS]
        for filename in files:
            if not filename.lower().endswith('.exe'):continue
            path=Path(dirpath)/filename
            if blocked_exe(path):continue
            try:
                if path.is_symlink() or path.stat().st_size<55_000:continue
                size=path.stat().st_size
            except OSError:continue
            stem=words(path.stem)
            overlap=len(tset.intersection(stem.split()))/max(1,len(set(stem.split())))
            ratio=difflib.SequenceMatcher(None,tw,stem).ratio()
            # Matching title and recognized game binaries dominate file size.
            score=round(20*ratio+44*overlap+min(size/(1024*1024),120)*.14-depth*2.0,2)
            reasons=[]
            if overlap>.3:reasons.append('Executable name matches the game title')
            if path.name.lower()==expected:score+=95;reasons.append('Recognized game executable')
            if 'game' in stem.split():score+=4
            if size>15*1024*1024:reasons.append('Substantial executable file')
            entries.append({'path':str(path),'score':round(score,2),'sizeMB':round(size/(1024*1024),1),'reasons':reasons,'safeCandidate':True})
    return sorted(entries,key=lambda x:(-x['score'],x['path'].lower()))

def detect(folder,prior=None):
    folder=Path(folder)
    prior=prior or {}
    title,source=inferred_title(folder)
    opts=candidates(folder,title)
    chosen=prior.get('exe','')
    matched=next((o for o in opts if os.path.normcase(o['path']).casefold()==os.path.normcase(str(chosen)).casefold()),None)
    if not matched:
        chosen=opts[0]['path'] if opts else ''
    else:chosen=matched['path']
    if not opts:return {'name':title,'source':source,'exe':'','uncertain':True,'candidates':[],'confidence':'missing'}
    # One plausible EXE (even if its name is abbreviated) is more reliable
    # than the largest EXE in the folder, provided all installer binaries are rejected.
    if matched or len(opts)==1:confidence='high';uncertain=False
    elif opts[0]['score']-opts[1]['score']>=18:confidence='high';uncertain=False
    else:confidence='review';uncertain=True
    return {'name':title,'source':source,'exe':chosen,'uncertain':uncertain,'candidates':opts,'confidence':confidence}
