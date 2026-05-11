# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

project_root = Path(os.getcwd()).resolve()

datas = [
    (str(project_root / "assets"), "assets"),
]

a = Analysis(
    ["PyGUI/main.py"],
    pathex=[str(project_root), str(project_root / "PyGUI")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Stalcraft-Waypoint-Editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / "assets" / "app.ico"),
)
