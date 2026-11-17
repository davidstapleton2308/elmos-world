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
import time
from pathlib import Path

_lock = threading.RLock()
_owned = None
_owned_exe = None
_last_error = ''
_setup_phase = 'idle'

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

def existing_executable():
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

def _log(message):
    try:
        path=managed_root().parent/'logs'/'controller-setup.log'
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as output:
            output.write(time.strftime('%Y-%m-%d %H:%M:%S')+' '+message+'\n')
    except OSError:
        pass

def _command(exe, action):
    """Issue classic DS4Windows IPC command without a console or WM_CLOSE."""
    startup=subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow=0
    return subprocess.Popen([str(exe),'-command',action],cwd=str(Path(exe).parent),
              startupinfo=startup,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def _connect_default_profile(proc, exe):
    """Once DS4 is running, start input and select the existing Default profile.

    Never replace a player's existing XML profile or generate fake profile data.
    """
    for attempt in range(20):
        if proc.poll() is not None:
            _log('Controller app exited before it became ready')
            return
        if _running_named('DS4Windows.exe'):
            break
        time.sleep(0.25)
    time.sleep(1.25)
    if proc.poll() is not None:return
    try:
        _command(exe,'start').wait(timeout=3)
        _log('Requested DS4Windows controller start')
        paths=[
            managed_root()/'DS4Windows'/'Profiles'/'Default.xml',
            Path(exe).parent/'Profiles'/'Default.xml',
            Path(os.environ.get('APPDATA',str(Path.home())))/'DS4Windows'/'Profiles'/'Default.xml',
        ]
        if any(p.is_file() for p in paths):
            _command(exe,'LoadProfile.1.Default').wait(timeout=3)
            _log('Requested existing Default profile for controller 1')
        else:
            _log('Default.xml not found; preserving DS4Windows automatic profile selection')
    except (OSError,subprocess.SubprocessError) as exc:
        _log('Unable to request controller profile: '+str(exc)[:140])

def status():
    current=_owned
    owned=bool(current and current.poll() is None)
    exe=existing_executable()
    running=bool(_running_named('DS4Windows.exe'))
    viiper=bool(_running_named('viiper.exe'))
    return {'available':os.name=='nt',
            'running':running or owned,'startedByElmos':owned,
            'exeFound':bool(exe),'viiperRunning':viiper,
            'backend':'classic DS4Windows + ViGEmBus',
            'phase':_setup_phase,
            'message':_last_error if _last_error else (
               'Existing VIIPER virtual-controller backend detected; untouched' if viiper and not running
               else 'Using existing DS4Windows; no duplicate launched' if running and not owned
               else 'Elmos World started your existing DS4Windows installation' if owned
               else 'DS4Windows found; ready for Elmos to open it' if exe
               else 'DS4Windows was not located in standard folders. Existing controller drivers were not modified.'
            )}

def start_existing():
    global _owned, _owned_exe, _last_error, _setup_phase
    if os.name!='nt' or os.environ.get('ELMOS_INPUT_DISABLE_SETUP')=='1':
        return status()
    with _lock:
        if _owned and _owned.poll() is None:
            return status()
        # Check both dependencies independently on each startup and update.
        # Downloads are skipped when the proper files / driver are present.
        _setup_phase='checking'
        _log('Checking DS4Windows and ViGEmBus')
        exe=existing_executable()
        if not exe:
            _setup_phase='installing-ds4'
            try:
                install_missing_user_component()
                exe=existing_executable()
                _log('DS4Windows verified download completed')
            except (OSError,ValueError,zipfile.BadZipFile) as exc:
                _last_error='DS4Windows setup failed: '+str(exc)[:170]
                _setup_phase='error'
                _log(_last_error)
                return status()
        if not exe:
            _last_error='DS4Windows.exe was not found after extraction'
            _setup_phase='error'
            _log(_last_error)
            return status()
        from elmos_input_driver import install_if_missing
        try:
            _setup_phase='checking-driver'
            driver=install_if_missing()
        except (OSError,ValueError) as exc:
            _last_error='ViGEmBus setup failed: '+str(exc)[:170]
            _setup_phase='error'
            _log(_last_error)
            return status()
        if driver['status'] not in ('already-installed','installed'):
            _last_error='ViGEmBus not ready ('+driver['status']+'). '+driver.get('message','Restart Windows if required.')
            _setup_phase='restart-required' if driver['status']=='reboot-pending' else 'error'
            _log(_last_error)
            return status()
        _log('ViGEmBus setup status: '+driver['status'])
        if _running_named('DS4Windows.exe') or _running_named('viiper.exe'):
            _last_error=''
            _setup_phase='external-running'
            _log('Controller mapper already running; leaving external process untouched')
            return status()
        try:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 7
            _owned=subprocess.Popen([str(exe)],cwd=str(exe.parent),
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                        startupinfo=startup)
            _owned_exe=exe
            _setup_phase='starting-controller'
            _log('Started managed DS4Windows PID '+str(_owned.pid))
            threading.Thread(target=_hide_owned_main_window,
                             args=(_owned,), daemon=True,
                             name='Elmos DS4 UI minimizer').start()
            threading.Thread(target=_connect_default_profile,
                             args=(_owned,exe), daemon=True,
                             name='Elmos DS4 default profile').start()
            _last_error=''
            _setup_phase='running'
        except (OSError,ValueError) as exc:
            _last_error='Could not start DS4Windows: '+str(exc)[:170]
            _setup_phase='error'
            _log(_last_error)
    return status()

def _hide_owned_main_window(proc):
    """Hide only DS4Windows's main window; leave any first-run/setup dialogs.

    A GUI program can ignore STARTUPINFO's initial show preference, so check
    a few times as its main window initializes. No other app is touched.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32=ctypes.WinDLL('user32',use_last_error=True)
        fn=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        @fn
        def hide(hwnd,_):
            pid=wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value != proc.pid:
                return True
            length=user32.GetWindowTextLengthW(hwnd)
            if not length or length > 200:
                return True
            buf=ctypes.create_unicode_buffer(length+1)
            user32.GetWindowTextW(hwnd,buf,len(buf))
            if buf.value.strip().lower().startswith('ds4windows'):
                user32.ShowWindowAsync(hwnd,0)  # SW_HIDE, not WM_CLOSE
            return True
        for _ in range(25):
            if proc.poll() is not None:
                break
            user32.EnumWindows(hide,0)
            time.sleep(0.15)
    except (OSError,ValueError):
        pass


def stop_owned(game_active=False):
    """Shut down only the DS4Windows instance launched by Elmos World.

    Use DS4Windows's documented IPC shutdown command rather than WM_CLOSE,
    which can show a confirmation dialog. If IPC fails, terminate *only*
    our own child process; never stop an external DS4Windows instance.
    """
    global _owned, _owned_exe, _last_error
    with _lock:
        proc=_owned
        exe=_owned_exe
        if not proc:
            return {'stopped':False,'reason':'not owned'}
        if proc.poll() is not None:
            _owned=None;_owned_exe=None
            return {'stopped':True,'reason':'already exited'}
        if game_active:
            return {'stopped':False,'reason':'game in progress'}
        graceful=False
        try:
            if exe and Path(exe).is_file():
                cmd=_command(exe,'shutdown')
                try:cmd.wait(timeout=2.0)
                except subprocess.TimeoutExpired:pass
                try:
                    proc.wait(timeout=3.0)
                    graceful=True
                except subprocess.TimeoutExpired:
                    pass
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    _last_error='Managed DS4Windows did not exit after shutdown request'
        except (OSError,ValueError) as exc:
            _last_error='DS4Windows shutdown error: '+str(exc)[:160]
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except (OSError,subprocess.TimeoutExpired):
                    pass
        stopped=proc.poll() is not None
        _log('Managed DS4Windows stop: '+('success' if stopped else 'failed'))
        if stopped:
            _owned=None;_owned_exe=None
        return {'stopped':stopped,
                'reason':'graceful IPC shutdown' if graceful else
                         ('managed process terminated' if stopped else 'shutdown failed')}
