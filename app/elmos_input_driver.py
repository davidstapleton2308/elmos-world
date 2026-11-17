"""Conditional installation of the exact classic ViGEmBus 1.22.0 driver.

The vendor's signed machine-wide driver requires Windows elevation. We can
automatically download/verify and launch setup, but cannot bypass Windows UAC.
No VIIPER/USB-IP/HidHide driver changes are made here.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request

VIGEM_URL='https://github.com/nefarius/ViGEmBus/releases/download/v1.22.0/ViGEmBus_1.22.0_x64_x86_arm64.exe'
VIGEM_SHA256='89220a7865076b342892f98865f3499fb7c4cfd673159e89d352c360fd014c6a'
VIGEM_MAX_SIZE=8_000_000

def is_installed():
    """Only a registered Windows kernel service proves ViGEmBus is installed.

    A stale Apps & Features/uninstall registry key is NOT evidence of a working
    bus; the previous implementation could skip setup for a broken installation.
    """
    if os.name != 'nt':
        return False
    hidden=getattr(subprocess,'CREATE_NO_WINDOW',0)
    try:
        p=subprocess.run(['sc.exe','query','ViGEmBus'], capture_output=True,
                         text=True,timeout=5,creationflags=hidden)
        return p.returncode == 0 and 'SERVICE_NAME:' in p.stdout.upper() and 'VIGEMBUS' in p.stdout.upper()
    except (OSError,subprocess.SubprocessError):
        return False


def managed_driver_file():
    local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))
    return local/'ElmosWorld'/'ElmosInput'/'installers'/'ViGEmBus_1.22.0_x64_x86_arm64.exe'

def download_verified():
    """Download once from official publisher, and verify Microsoft manifest SHA."""
    target=managed_driver_file()
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==VIGEM_SHA256:
        return target
    temp=target.with_suffix('.partial')
    digest=hashlib.sha256()
    size=0
    try:
        with urllib.request.urlopen(VIGEM_URL,timeout=20) as source, temp.open('wb') as out:
            while True:
                chunk=source.read(131072)
                if not chunk:break
                size+=len(chunk)
                if size>VIGEM_MAX_SIZE:
                    raise ValueError('ViGEmBus installer exceeded expected size')
                digest.update(chunk);out.write(chunk)
        if digest.hexdigest()!=VIGEM_SHA256:
            raise ValueError('ViGEmBus installer checksum mismatch; refusing to execute')
        temp.replace(target)
        return target
    finally:
        try:temp.unlink(missing_ok=True)
        except OSError:pass

def install_if_missing():
    """Start verified setup; Windows itself handles any necessary UAC approval."""
    if os.name!='nt':return {'status':'unavailable'}
    if is_installed():return {'status':'already-installed'}
    installer=download_verified()
    # The published Winget switches perform a quiet driver setup. They do not
    # suppress Windows UAC or force a reboot, and should never be treated as
    # proof installation succeeded until the driver re-check passes.
    switches='/exenoui /qn /norestart'
    hidden=getattr(subprocess,'CREATE_NO_WINDOW',0)
    # Start-Process -Verb RunAs invokes the normal Windows elevation consent.
    # No separate Elmos confirmation is required; no credentials are collected.
    quoted=str(installer).replace("'","''")
    command=(
        f"$p=Start-Process -FilePath '{quoted}' -ArgumentList '{switches}' "
        f"-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
    )
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive',
                          '-Command',command],capture_output=True,text=True,
                         timeout=180,creationflags=hidden)
    except subprocess.TimeoutExpired:
        return {'status':'timeout','message':'Driver setup did not complete'}
    except OSError as exc:
        return {'status':'error','message':str(exc)[:170]}
    if p.returncode not in (0,3010):
        return {'status':'not-installed','message':
                'Windows driver setup was cancelled or failed; no other driver was changed'}
    if is_installed():
        return {'status':'installed','rebootSuggested':p.returncode==3010}
    return {'status':'reboot-pending','rebootSuggested':True}
