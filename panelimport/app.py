"""GUI entry point: ``panelimport-gui [ODB++ export or .panel.json]``."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from panelimport.model.serialize import SerializationError
from panelimport.settings import Settings

# packaging/pcb.ico; the Windows build (packaging/panelimport.spec) copies it to sys._MEIPASS.
ICON = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1] / "packaging"), "pcb.ico")


def dark_palette() -> QPalette:
    p = QPalette()
    base, window, text = QColor("#1f2329"), QColor("#2a2f36"), QColor("#e6edf3")
    p.setColor(QPalette.Window, window)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, window)
    p.setColor(QPalette.ToolTipBase, QColor("#30363d"))
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, window)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.Highlight, QColor("#2f81f7"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.PlaceholderText, QColor("#8b949e"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#6e7681"))
    return p


def create_app(argv: list[str] | None = None) -> QApplication:
    QCoreApplication.setOrganizationName("Detex")
    QCoreApplication.setApplicationName("Panel Importer")
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setWindowIcon(QIcon(str(ICON)))
    return app


def smoke_test(path: str | None) -> int:
    """Start the GUI, optionally analyse ``path``, and exit (used to check frozen builds)."""
    from PySide6.QtCore import QSettings, QTemporaryDir

    from panelimport.gui.main_window import MainWindow

    if QApplication.windowIcon().isNull():  # pcb.ico missing from the build
        return 4
    tmp = QTemporaryDir()
    win = MainWindow(Settings(), QSettings(tmp.filePath("smoke.ini"), QSettings.IniFormat))
    win.show()
    QApplication.processEvents()
    if path:
        from panelimport.io.odb import OdbJob
        from panelimport.model.panel import Decisions

        win.open_job(OdbJob(path), Decisions())
        QApplication.processEvents()
        if win.analysis is None or not win.analysis.circuits:
            win.controller.undo_stack.setClean()
            dispose(win)
            return 3
    win.controller.undo_stack.setClean()
    dispose(win)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_app(argv)
    if "--smoke-test" in argv:
        rest = [a for a in argv[argv.index("--smoke-test") + 1 :] if not a.startswith("-")]
        return smoke_test(rest[0] if rest else None)
    from panelimport.gui.main_window import MainWindow

    try:
        settings = Settings.load()
        problem = None
    except (SerializationError, ValueError, OSError) as exc:
        settings, problem = Settings(), str(exc)
    win = MainWindow(settings)
    win.show()
    if problem:
        QMessageBox.warning(win, "Settings", f"Your settings file could not be read; using defaults.\n\n{problem}")
    paths = [a for a in argv[1:] if not a.startswith("-")]
    if paths:
        win.open_path(paths[0])
    code = app.exec()
    # Delete the window while the QApplication still exists.
    dispose(win)
    return code


def dispose(widget) -> None:
    """Delete a Qt widget now (not at interpreter exit, after the QApplication)."""
    from PySide6.QtCore import QCoreApplication, QEvent

    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    sys.exit(main())
