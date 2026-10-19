# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build recipe for GAMbit (one-folder build, used by the installer).
# Run via the Builder GUI, or:  python -m PyInstaller --noconfirm --clean GAMbit.spec

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("assets", "assets")],
    hiddenimports=["truststore", "qrcode", "cryptography"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml",
              "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GAMbit",
    icon="assets/gambit.ico",
    console=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="GAMbit",
    upx=False,
)
