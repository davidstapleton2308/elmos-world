# -*- mode: python ; coding: utf-8 -*-
"""Windows standalone onedir build. Run with: python -m PyInstaller build/ElmosWorld.spec"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
APP = ROOT / 'app'
LAB = ROOT / 'controller-lab'
ASSETS = [
    'index.html', 'app.css', 'app.js', 'apply_update.ps1', 'brand_emblem.svg', 'graphite_weave.svg',
    'elmos_world.ico', 'grove.ico', 'premium_23.css', 'premium_24.css',
    'premium_25.css', 'premium_26.css', 'premium_27.css', 'premium_28.css',
    'premium_30.css', 'premium_31.css',
]
datas = [(str(APP / f), '.') for f in ASSETS]
for preset_file in (APP / 'presets').rglob('*'):
    if preset_file.is_file():
        datas.append((str(preset_file), str(preset_file.relative_to(APP).parent)))
binaries = []
hiddenimports = [
    'server', 'update_center', 'backend', 'controller_runtime', 'store_inventory', 'rom_identity', 'game_media', 'game_descriptions', 'game_discovery',
    'game_uninstall', 'geforce_library', 'steam_core', 'provider_adapters',
    'controller_input', 'native_game_menu', 'smart_discovery', 'game_metadata', 'tkinter', 'tkinter.filedialog',
    'webview.platforms.winforms', 'webview.platforms.edgechromium',
    'pygame._sdl2.controller', 'clr',
    'elmos_controller_lab.lab', 'elmos_controller_lab.bridge',
    'elmos_controller_lab.prerequisites',
    'elmos_controller_lab.healthy_lease', 'elmos_controller_lab.mapping',
    'elmos_controller_lab.actions', 'elmos_controller_lab.model',
    'elmos_controller_lab.sdl_source', 'elmos_controller_lab.sony_hid',
    'elmos_controller_lab.sony_reports', 'elmos_controller_lab.store',
    'elmos_controller_lab.gui', 'elmos_controller_lab.api_probe',
    'elmos_controller_lab.browser_probe',
]
# These libraries load important components dynamically on Windows. Bundle
# their data files and native extensions rather than depending on local Python.
for package in ('webview', 'pygame', 'pythonnet', 'clr_loader'):
    pkg_data, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_data
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

analysis = Analysis(
    [str(APP / 'launcher_entry.py')],
    pathex=[str(APP), str(LAB)],
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
