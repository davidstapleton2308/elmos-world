# -*- mode: python ; coding: utf-8 -*-
"""One-file elevated helper used by Elmos World for virtual controller sessions."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
LAB = ROOT / "controller-lab"
datas = []
binaries = []
hiddenimports = [
    "elmos_controller_lab.lab", "elmos_controller_lab.bridge",
    "elmos_controller_lab.prerequisites",
    "elmos_controller_lab.healthy_lease", "elmos_controller_lab.mapping",
    "elmos_controller_lab.actions", "elmos_controller_lab.model",
    "elmos_controller_lab.sdl_source", "elmos_controller_lab.sony_hid",
    "elmos_controller_lab.sony_reports", "elmos_controller_lab.store",
    "elmos_controller_lab.gui", "elmos_controller_lab.api_probe",
    "elmos_controller_lab.browser_probe", "pygame._sdl2.controller",
]
for package in ("pygame", "hid"):
    try:
        pkg_data, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_data
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        if package == "pygame":
            raise

analysis = Analysis(
    [str(ROOT / "build" / "controller_runtime_entry.py")],
    pathex=[str(LAB)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    runtime_hooks=[str(ROOT / "build" / "pyi_stdio.py")],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, analysis.binaries, analysis.datas,
    [],
    name="ElmosControllerRuntime",
    console=False,
    upx=False,
)
