# -*- mode: python ; coding: utf-8 -*-
"""Windows standalone onedir build. Run with: python -m PyInstaller build/ElmosWorld.spec"""
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
APP = ROOT / 'app'
ASSETS = [
    'index.html', 'app.css', 'app.js', 'brand_emblem.svg', 'graphite_weave.svg',
    'elmos_world.ico', 'grove.ico', 'premium_23.css', 'premium_24.css',
    'premium_25.css', 'premium_26.css', 'premium_27.css', 'premium_28.css',
    'premium_30.css', 'premium_31.css',
]
datas = [(str(APP / f), '.') for f in ASSETS]
binaries = []
hiddenimports = [
    'server', 'update_center', 'backend', 'game_media', 'game_descriptions', 'game_discovery',
    'game_uninstall', 'geforce_library', 'steam_core', 'provider_adapters',
    'controller_input', 'native_game_menu', 'elmos_input', 'vgamepad', 'tkinter', 'tkinter.filedialog',
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
    console=bool(os.environ.get('ELMOS_INPUT_DEBUG_CONSOLE')),
    upx=False,
)
coll = COLLECT(
    exe, analysis.binaries, analysis.datas,
    name='ElmosWorld',
    strip=False,
    upx=False,
)
