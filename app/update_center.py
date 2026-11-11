"""Elmos World release updater. Only GitHub release installers with SHA-256 sidecars."""
from __future__ import annotations
import hashlib, json, os, re, subprocess, sys, tempfile, threading, urllib.request
from pathlib import Path
from urllib.parse import urlparse

VERSION = '3.1.1'
ASSET_PREFIX = 'ElmosWorld_Setup_'
DEFAULT_REPOSITORY = 'davidstapleton2308/elmos-world'
CFG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ElmosWorld' / 'update_center.json'
LOCK = threading.Lock()


def config():
    try:
        return json.loads(CFG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'repository': DEFAULT_REPOSITORY}


def configure(repo):
    repo = str(repo).strip().removeprefix('https://github.com/').strip('/')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or '..' in repo:
        raise ValueError('Enter a GitHub repository as owner/repository.')
    CFG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CFG.with_suffix('.tmp')
    tmp.write_text(json.dumps({'repository': repo}, indent=2), encoding='utf-8')
    os.replace(tmp, CFG)
    return repo


def ver_tuple(s):
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(s))
    return tuple(map(int, m.groups())) if m else None


def request(url, *, api=False):
    if urlparse(url).scheme != 'https':
        raise ValueError('Updates require HTTPS.')
    headers = {'User-Agent': 'ElmosWorld-UpdateCenter/3.1.1', 'Accept': 'application/vnd.github+json' if api else 'application/octet-stream'}
    return urllib.request.Request(url, headers=headers)


def latest():
    repo = config().get('repository') or DEFAULT_REPOSITORY
    if not repo:
        return {'configured': False, 'current': VERSION, 'message': 'Set your GitHub owner/repository to enable updates.'}
    url = 'https://api.github.com/repos/' + repo + '/releases/latest'
    try:
        with urllib.request.urlopen(request(url, api=True), timeout=12) as response:
            obj = json.load(response)
    except Exception as exc:
        raise RuntimeError('Could not check GitHub Releases: ' + str(exc)) from exc
    version = str(obj.get('tag_name', '')).removeprefix('v')
    current, remote = ver_tuple(VERSION), ver_tuple(version)
    if not remote or not current:
        raise RuntimeError('Latest release must have a vMAJOR.MINOR.PATCH tag.')
    newer = remote > current
    filename = ASSET_PREFIX + version + '.exe'
    assets = {x.get('name'): x for x in obj.get('assets', [])}
    installer, checksum = assets.get(filename), assets.get(filename + '.sha256')
    ready = bool(installer and checksum)
    return {'configured': True, 'repository': repo, 'current': VERSION,
            'latest': version, 'available': newer, 'installable': newer and ready,
            'notes': str(obj.get('body') or '')[:2500], 'releaseUrl': str(obj.get('html_url') or ''),
            'message': ('New version ready' if ready else 'Release is missing its installer or SHA-256 checksum') if newer else 'You are up to date',
            # Installers are resolved only from this verified latest release response.
            '_installer': installer.get('browser_download_url') if installer else None,
            '_checksum': checksum.get('browser_download_url') if checksum else None}


def _download(url, target, limit):
    if urlparse(url).hostname != 'github.com':
        raise RuntimeError('Release asset URL must originate from github.com')
    # GitHub release assets legitimately redirect to release-assets.githubusercontent.com.
    with urllib.request.urlopen(request(url), timeout=45) as response, open(target, 'wb') as dst:
        host = urlparse(response.geturl()).hostname or ''
        if host not in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise RuntimeError('Untrusted download redirect host: ' + host)
        size = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk: break
            size += len(chunk)
            if size > limit: raise RuntimeError('Update asset exceeds download limit.')
            dst.write(chunk)
    if not size: raise RuntimeError('Empty download')


def prepare():
    with LOCK:
        release = latest()
        if not release.get('installable'): raise RuntimeError(release.get('message', 'No valid update available.'))
        version = release['latest']
        name = ASSET_PREFIX + version + '.exe'
        directory = Path(tempfile.mkdtemp(prefix='elmos-update-'))
        installer = directory / name
        checksum_file = directory / (name + '.sha256')
        try:
            _download(release['_checksum'], checksum_file, 10240)
            content = checksum_file.read_text(encoding='utf-8').strip()
            match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?' + re.escape(name), content)
            if not match: raise RuntimeError('Malformed release checksum file.')
            _download(release['_installer'], installer, 800 * 1024 * 1024)
            digest = hashlib.file_digest(installer.open('rb'), 'sha256').hexdigest()
            if digest.lower() != match.group(1).lower(): raise RuntimeError('Installer SHA-256 mismatch! Update cancelled.')
            return installer
        except BaseException:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)
            raise


def launch_helper(installer, parent_pid):
    """Start an independent Windows PowerShell installer worker in the temp folder."""
    if not getattr(sys, 'frozen', False) or sys.platform != 'win32':
        raise RuntimeError('Automatic installation requires the installed Windows desktop executable.')
    installer = Path(installer)
    if not installer.is_file(): raise RuntimeError('Missing verified installer.')
    # This script lives OUTSIDE the installed application so Windows can replace
    # ElmosWorld.exe and its DLLs without locking the binaries used by the updater.
    helper = installer.parent / 'apply_update.ps1'
    app_exe = str(Path(sys.executable).resolve())
    # Values are supplied as arguments, never interpolated into PowerShell source.
    helper.write_text(r'''param([string]$Installer, [int]$ParentId, [string]$AppExe)
$ErrorActionPreference = 'Stop'
try {
  $p = Get-Process -Id $ParentId -ErrorAction Stop
  if (-not $p.WaitForExit(120000)) { exit 3 }
} catch [System.ArgumentException] { exit 3 }
catch [Microsoft.PowerShell.Commands.ProcessCommandException] { exit 3 }
Start-Sleep -Milliseconds 700
$log = Join-Path (Split-Path -Parent $Installer) 'installer.log'
$process = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS',('/LOG="' + $log + '"')) -Wait -PassThru
if ($process.ExitCode -ne 0) { exit $process.ExitCode }
if (Test-Path -LiteralPath $AppExe) { Start-Process -FilePath $AppExe }
''', encoding='utf-8')
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                      '-File', str(helper), '-Installer', str(installer), '-ParentId', str(parent_pid),
                      '-AppExe', app_exe], close_fds=True, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
