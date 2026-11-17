# -*- mode: python ; coding: utf-8 -*-
"""Windows standalone onedir build. Run with: python -m PyInstaller build/ElmosWorld.spec"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
APP = ROOT / 'app'
ASSETS = [
    'index.html', 'app.css', 'app.js', 'apply_update.ps1', 'brand_emblem.svg', 'graphite_weave.svg',
    'elmos_world.ico', 'grove.ico', 'premium_23.css', 'premium_24.css',
    'premium_25.css', 'premium_26.css', 'premium_27.css', 'premium_28.css',
    'premium_30.css', 'premium_31.css', 'premium_32.css', 'premium_33.css',
]
datas = [(str(APP / f), '.') for f in ASSETS]
# The native ViGEmBus kernel driver is signed and distributed by its publisher.
# Bundle its checksum-verified installer so restricted Wi-Fi cannot block setup.
datas.append((str(APP / 'drivers' / 'ViGEmBus_1.22.0_x64_x86_arm64.exe'), 'drivers'))
# Official pinned archived DS4Windows 3.3.3 portable mapper; no external runtime download.
datas.append((str(APP / 'engines' / 'ds4windows-3-3-3.zip'), 'engines'))
binaries = []
hiddenimports = [
    'server', 'update_center', 'backend', 'elmos_ds4_engine', 'gfn_cache_sync', 'elmos_native_input', 'elmos_input_driver', 'game_media', 'game_descriptions', 'game_discovery',
    'game_uninstall', 'geforce_library', 'gfn_artwork', 'steam_core', 'provider_adapters',
    'controller_input', 'native_game_menu', 'smart_discovery', 'game_metadata', 'tkinter', 'tkinter.filedialog',
    'webview.platforms.winforms', 'webview.platforms.edgechromium',
    'pygame._sdl2.controller', 'clr',
]
# These libraries load important components dynamically on Windows. Bundle
# their data files and native extensions rather than depending on local Python.
for package in ('webview', 'pygame', 'vgamepad', 'pythonnet', 'clr_loader'):
    pkg_data, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_data
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

analysis = Analysis(
    [str(APP / 'launcher_entry.py')],
    pathex=[str(APP)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    runtime_hooks=[str(ROOT / 'build' / 'pyi_stdio.py')],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name='ElmosWorld',
    icon=str(APP / 'elmos_world.ico'),
    version=str(ROOT / 'build' / 'version_file.txt'),
    console=False,
    upx=False,
)
coll = COLLECT(
    exe, analysis.binaries, analysis.datas,
    name='ElmosWorld',
    strip=False,
    upx=False,
)
