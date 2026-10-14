# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder build:
#   dist/PanelImporter/PanelImporter.exe   GUI (no console window)
#   dist/PanelImporter/panelimport.exe     command line: panelimport analyze <odb path>, panelimport iss <project>
# Both share the libraries in the same folder; it runs without Python or admin rights.
#
#   pyinstaller packaging/panelimport.spec --noconfirm

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Qt modules the program does not use; leaving them out keeps the folder small.
QT_UNUSED = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DRender", "PySide6.QtBluetooth", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtDesigner", "PySide6.QtGraphs", "PySide6.QtHelp",
    "PySide6.QtLocation", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtNetworkAuth",
    "PySide6.QtNfc", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtSerialBus", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",
    "PySide6.QtSql", "PySide6.QtStateMachine", "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtTest",
    "PySide6.QtTextToSpeech", "PySide6.QtUiTools", "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtXml",
]
OTHER_UNUSED = ["tkinter", "matplotlib", "pytest", "IPython", "PyInstaller"]

gui = Analysis(
    [os.path.join(SPECPATH, "gui_main.py")],
    pathex=[ROOT],
    excludes=QT_UNUSED + OTHER_UNUSED,
    noarchive=False,
)
cli = Analysis(
    [os.path.join(SPECPATH, "cli_main.py")],
    pathex=[ROOT],
    excludes=QT_UNUSED + OTHER_UNUSED + ["PySide6", "shiboken6"],
    noarchive=False,
)

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    [],
    exclude_binaries=True,
    name="PanelImporter",
    console=False,
    debug=False,
    strip=False,
    upx=False,
    icon="pcb.ico",
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="panelimport",
    console=True,
    debug=False,
    strip=False,
    upx=False,
    icon="pcb.ico",
)

coll = COLLECT(
    gui_exe,
    gui.binaries,
    gui.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    strip=False,
    upx=False,
    name="PanelImporter",
)
