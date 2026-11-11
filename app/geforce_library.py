"""Opt-in GeForce NOW shortcut library.

No NVIDIA credentials, account scraping, or unsupported private API calls.
The official Windows app provides per-game desktop shortcuts; those are imported
by the user and launched unchanged. A shortcut is never executed during import.
"""
from pathlib import Path
from urllib.parse import urlsplit
import configparser
import hashlib
import os
import re
import sys

SHORTCUT_TYPES = {'.lnk', '.url'}

def clean_shortcut_title(path):
    value = Path(path).stem
    value = re.sub(r'(?i)\s*[-–—|:]?\s*(?:nvidia\s*)?geforce\s*now\s*$', '', value)
    value = re.sub(r'(?i)\s*\(geforce now\)\s*$', '', value)
    return ' '.join(value.replace('_', ' ').split())[:140] or 'Cloud Game'

def check_shortcut(path):
    """Only existing user-selected Windows shortcuts; no arbitrary EXEs/scripts."""
    entry = Path(str(path)).expanduser()
    if entry.suffix.lower() not in SHORTCUT_TYPES or not entry.is_file():
        raise ValueError('Select an existing GeForce NOW .lnk or .url shortcut.')
    if entry.is_symlink() or (sys.platform == 'win32' and bool(getattr(entry.stat(),'st_file_attributes',0) & 0x400)):
        raise ValueError('Linked/reparse-point shortcut paths are not supported.')
    if entry.suffix.lower() == '.url':
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(entry, encoding='utf-8-sig')
        url = parser.get('InternetShortcut', 'URL', fallback='')
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or (parsed.hostname or '').lower() != 'play.geforcenow.com':
            raise ValueError('Internet shortcuts must point directly to play.geforcenow.com.')
    return entry.resolve()

def import_shortcut(collection, path, title=None):
    file = check_shortcut(path)
    key = 'gfn:' + hashlib.sha256(str(file).casefold().encode('utf8')).hexdigest()[:24]
    existing = collection.get(key)
    name = ' '.join(str(title or clean_shortcut_title(file)).split())[:140]
    if not name:
        raise ValueError('Cloud game name is required.')
    collection[key] = {'name':name, 'shortcut':str(file), 'steamId':(existing or {}).get('steamId')}
    return key

def launch_shortcut(record):
    path = check_shortcut(record['shortcut'])
    if sys.platform != 'win32':
        return {'ok':True, 'dryRun':True, 'name':record['name']}
    # Windows Shell follows the user-created shortcut; no command substitution,
    # injected arguments, or conversion to a local game launch.
    os.startfile(str(path))
    return {'ok':True,'name':record['name']}

def desktop_candidates():
    """Read-only, optional discovery of shortcuts created by NVIDIA.

    Import remains explicitly user-approved after the candidates are displayed.
    Windows Script Host resolves LNK targets without launching them.
    """
    if sys.platform != 'win32':
        return []
    import subprocess, json, base64
    script = r'''
$ErrorActionPreference='SilentlyContinue'
$dirs=@([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('CommonDesktopDirectory'))
$od=Join-Path $env:USERPROFILE 'OneDrive\Desktop'
if(Test-Path -LiteralPath $od){$dirs+= $od}
$wsh=New-Object -ComObject WScript.Shell
$found=@()
foreach($dir in ($dirs | Select-Object -Unique)){
 if(!(Test-Path -LiteralPath $dir)){continue}
 foreach($f in (Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -eq '.lnk' -or $_.Extension -eq '.url'})){
  if($f.Extension -eq '.lnk'){
   $s=$wsh.CreateShortcut($f.FullName)
   $target=($s.TargetPath+' '+$s.Arguments)
   if($target -match '(?i)GeForceNOW|GeForce\s*NOW|play\.geforcenow\.com'){
    $found+=@{path=$f.FullName;name=$f.BaseName}
   }
  } else {
   $content=Get-Content -LiteralPath $f.FullName -Raw
   if($content -match '(?i)https://play\.geforcenow\.com/'){$found+=@{path=$f.FullName;name=$f.BaseName}}
  }
 }
}
ConvertTo-Json -InputObject @($found) -Compress -Depth 3
'''
    try:
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        output = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                                capture_output=True, text=True, timeout=12, check=True)
        raw=json.loads(output.stdout.strip() or '[]')
        return [{'path':str(x['path']), 'name':clean_shortcut_title(x['name'])}
                for x in raw if isinstance(x,dict) and x.get('path')][:100]
    except (OSError, ValueError, subprocess.SubprocessError, KeyError):
        return []
