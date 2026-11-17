"""Conservative Windows DS4Windows companion: preserve user's existing controller stack.

The user may use classic ViGEmBus or a custom VIIPER USB backend. Elmos World
never changes their profile, installs a kernel driver, stops a pre-existing
instance, or assumes those backends are interchangeable.
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
import io
import os
import subprocess
import threading
import sys
from pathlib import Path

_lock = threading.RLock()
_owned = None
_owned_exe = None
_last_error = ''

def _running_named(name):
    """Return current process IDs, without touching unrelated processes."""
    if os.name != 'nt':
        return []
    try:
        data = subprocess.run(['tasklist.exe','/FI',f'IMAGENAME eq {name}',
                               '/FO','CSV','/NH'],capture_output=True,text=True,
                              timeout=4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        matches=[]
        for row in csv.reader(io.StringIO(data.stdout)):
            if len(row)>=2 and row[0].strip().lower()==name.lower():
                try: matches.append(int(row[1]))
                except ValueError: pass
        return matches
    except (OSError,subprocess.SubprocessError):
        return []

def _candidates():
    home=Path.home()
    env_local=Path(os.environ.get('LOCALAPPDATA',str(home/'AppData'/'Local')))
    env_program=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))
    env_roaming=Path(os.environ.get('APPDATA',str(home/'AppData'/'Roaming')))
    paths=[
        Path(r'C:\Gaming\Controller-Test\DS4Windows\DS4Windows.exe'),
        env_program/'DS4Windows'/'DS4Windows.exe',
        env_local/'Programs'/'DS4Windows'/'DS4Windows.exe',
        env_local/'DS4Windows'/'DS4Windows.exe',
        env_roaming/'DS4Windows'/'DS4Windows.exe',
    ]
    # Preserve already-working external install before any managed download.
    paths += [
        env_local/'ElmosWorld'/'ElmosInput'/'DS4Windows'/'DS4Windows.exe',
        env_local/'ElmosWorld'/'ElmosInput'/'DS4Windows'/'DS4Windows'/'DS4Windows.exe',
    ]
    # Archive layouts can contain a nested x64 subdirectory.
    paths += [Path(r'C:\Gaming\Controller-Test\DS4Windows')/sub/'DS4Windows.exe'
              for sub in ('DS4Windows','DS4Windows_3.3.3_x64')]
    return paths


# Archive is the verified ds4windowsapp GitHub Ryochan7 release asset. Its
# GitHub asset SHA-256 matches the historical Chocolatey 3.3.3 checksum.
ARCHIVE_URL = ('https://github.com/ds4windowsapp/DS4Windows/releases/download/'
               'ryochan7/ds4windows-3-3-3.zip')
ARCHIVE_SHA256 = 'cf5619bcb51b82e4e1765276e9f67fb1e2d23dff968a653657acf35bafff8bf4'
MAX_ARCHIVE_BYTES = 12_000_000
MAX_EXTRACT_BYTES = 110_000_000

def managed_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'ElmosWorld' / 'ElmosInput'

def install_missing_user_component():
    """Download missing verified DS4Windows without an extra Elmos prompt.

    Never installs/modifies ViGEmBus, VIIPER, HidHide, USB/IP or other kernel
    drivers. Those may require Windows elevation and verified installers.
    Existing controller executables, settings and mappers are left intact.
    """
    root = managed_root()
    target = root / 'DS4Windows'
    if existing_executable():
        return {'installed':False, 'reason':'existing installation preserved'}
    root.mkdir(parents=True, exist_ok=True)
    fd = None
    archive = None
    staging = None
    try:
        fd, archive = tempfile.mkstemp(prefix='elmos-ds4-',suffix='.zip',dir=str(root))
        digest = hashlib.sha256()
        length = 0
        with os.fdopen(fd, 'wb') as output:
            fd = None
            with urllib.request.urlopen(ARCHIVE_URL, timeout=18) as source:
                while True:
                    block=source.read(131072)
                    if not block: break
                    length += len(block)
                    if length > MAX_ARCHIVE_BYTES:
                        raise ValueError('Controller archive exceeds safe size')
                    output.write(block)
                    digest.update(block)
        if digest.hexdigest().lower() != ARCHIVE_SHA256:
            raise ValueError('Controller archive SHA-256 mismatch; refused to install')
        staging = Path(tempfile.mkdtemp(prefix='elmos-stage-',dir=str(root)))
        with zipfile.ZipFile(archive) as z:
            entries=z.infolist()
            if len(entries)>1500 or sum(max(0,e.file_size) for e in entries)>MAX_EXTRACT_BYTES:
                raise ValueError('Unexpected archive size')
            for entry in entries:
                name=entry.filename.replace('\\','/')
                pieces=[x for x in name.split('/') if x]
                typebits=(entry.external_attr >> 16) & 0o170000
                if (not pieces or name.startswith('/') or ':' in name
                    or any(x in ('.','..') for x in pieces) or typebits==0o120000):
                    raise ValueError('Unsafe archive entry')
                dest=staging.joinpath(*pieces)
                if entry.is_dir():
                    dest.mkdir(parents=True,exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(entry) as src, dest.open('wb') as dst:
                        shutil.copyfileobj(src,dst)
        executables=list(staging.rglob('DS4Windows.exe'))
        if len(executables)!=1:
            raise ValueError('Verified archive does not contain one DS4Windows.exe')
        if target.exists():
            return {'installed':False,'reason':'existing managed files preserved'}
        staging.rename(target)
        staging=None
        return {'installed':True,'reason':'Verified classic DS4Windows 3.3.3 installed'}
    finally:
        if fd is not None:
            os.close(fd)
        if archive:
            try: os.unlink(archive)
            except OSError: pass
        if staging:
            shutil.rmtree(staging,ignore_errors=True)

def bundled_executable():
    """Controller runtime shipped with the *Elmos World* release.

    This is an embedded distribution payload, not a separately downloaded
    installer. Windows may still require a one-time signed USB/IP driver setup.
    """
    roots = [Path(__file__).resolve().parent / 'ElmosInput']
    if getattr(sys, 'frozen', False):
        roots.append(Path(sys.executable).resolve().parent / '_internal' / 'ElmosInput')
    for root in roots:
        if root.is_dir():
            matches = [p for p in root.rglob('DS4Windows.exe') if p.is_file()]
            if len(matches) == 1:
                return matches[0]
    return None

def existing_executable():
    shipped = bundled_executable()
    if shipped:
        return shipped
    for p in _candidates():
        if p.is_file():
            return p
    # Verified archives may contain a versioned subfolder.
    managed=managed_root()/'DS4Windows'
    if managed.exists():
        matches=[p for p in managed.rglob('DS4Windows.exe') if p.is_file()]
        if len(matches)==1:
            return matches[0]
    return None

def status():
    with _lock:
        current=_owned
        owned=bool(current and current.poll() is None)
        exe=existing_executable()
        running=bool(_running_named('DS4Windows.exe'))
        viiper=bool(_running_named('viiper.exe'))
        return {'available':os.name=='nt',
                'running':running or owned,'startedByElmos':owned,
                'exeFound':bool(exe),'viiperRunning':viiper,
                'backend':'bundled VIIPER runtime' if bundled_executable() else 'existing installation, unchanged',
                'message':_last_error if _last_error else (
                   'Existing VIIPER virtual-controller backend detected; untouched' if viiper and not running
                   else 'Using existing DS4Windows; no duplicate launched' if running and not owned
                   else 'Elmos World started your existing DS4Windows installation' if owned
                   else 'DS4Windows found; ready for Elmos to open it' if exe
                   else 'DS4Windows was not located in standard folders. Existing controller drivers were not modified.'
                )}

def start_existing():
    global _owned, _owned_exe, _last_error
    if os.name!='nt' or os.environ.get('ELMOS_INPUT_DISABLE_SETUP')=='1':
        return status()
    with _lock:
        if _owned and _owned.poll() is None:
            return status()
        if _running_named('DS4Windows.exe') or _running_named('viiper.exe'):
            # VIIPER is a separate backend, not a request to launch a
            # possibly incompatible classic ViGEmBus mapper alongside it.
            _last_error=''
            return status()
        exe=existing_executable()
        if not exe:
            # Never download a controller application or elevate a driver
            # implicitly just because the player opened Elmos World.
            _last_error='No bundled controller runtime was found; existing controller devices are unchanged.'
            return status()
        shipped=bundled_executable()
        if shipped is None:
            # An installed external mapper may already have its driver.
            # Do not install the retired ViGEmBus during a routine game launch.
            _last_error=''
        else:
            # The matching VIIPER backend/USB-IP driver payload accompanies
            # the shipped runtime. First-time driver setup is explicitly
            # handled by upstream Windows setup; it cannot bypass UAC.
            _last_error=''
        # Start the preserved classic mapper only after its virtual output bus is ready.
        try:
            _owned=subprocess.Popen([str(exe)],cwd=str(exe.parent),
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            _owned_exe=exe
            _last_error=''
        except (OSError,ValueError) as exc:
            _last_error='Could not start existing DS4Windows: '+str(exc)[:180]
    return status()

def stop_owned(game_active=False):
    """Stop only the process created by this launcher, preserving other apps."""
    global _owned, _owned_exe
    with _lock:
        proc=_owned
        if not proc:
            return {'stopped':False,'reason':'not owned'}
        if proc.poll() is not None:
            _owned=None;_owned_exe=None
            return {'stopped':False,'reason':'already exited'}
        if game_active:
            # Games launched independently may still need this output device.
            return {'stopped':False,'reason':'game in progress'}
        try:
            # Ask its top-level window to close; never forcefully terminate a
            # third-party driver/service or a pre-existing DS4Windows process.
            _close_owned_window(proc.pid)
            try:proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                # Avoid an orphan only if this is exactly the child we launched.
                proc.terminate()
                try:proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired: pass
        except (OSError,ValueError):
            pass
        _owned=None;_owned_exe=None
        return {'stopped':proc.poll() is not None,'reason':'Elmos-owned DS4Windows closed'}

def _close_owned_window(pid):
    if os.name != 'nt':return
    import ctypes
    from ctypes import wintypes
    user32=ctypes.windll.user32
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @callback_type
    def scan(hwnd,_):
        current=wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(current))
        if current.value==pid:
            user32.PostMessageW(hwnd,0x0010,0,0) # WM_CLOSE
        return True
    user32.EnumWindows(scan,0)
