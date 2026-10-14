from __future__ import annotations

import os
from pathlib import Path

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.io.odb import OdbJob
from panelimport.model.panel import Decisions
from panelimport.settings import Settings

# Keep tests away from the user's real settings file.
os.environ.setdefault("PANELIMPORT_SETTINGS", str(Path(__file__).parent / "_no_such_settings.json"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def write(job, tmp_path: Path, kind: str = "folder") -> Path:
    if kind == "folder":
        return job.write_folder(tmp_path)
    if kind == "tgz":
        return job.write_tgz(tmp_path / f"{job.name}.tgz")
    if kind == "zip":
        return job.write_zip(tmp_path / f"{job.name}.zip")
    raise ValueError(kind)


def run(job, tmp_path: Path, settings: Settings | None = None, kind: str = "folder", **decisions):
    path = write(job, tmp_path, kind)
    return analyze(OdbJob(path), settings or Settings(), Decisions(**decisions))


def codes(analysis) -> list[str]:
    return [i.code for i in analysis.issues]


def issues_of(analysis, code: str):
    return [i for i in analysis.issues if i.code == code]


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELIMPORT_SETTINGS", str(tmp_path / "settings.json"))


# ---------------------------------------------------------------- GUI (PySide6 imported lazily)
@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from panelimport.app import create_app

    return create_app([])


@pytest.fixture
def boxes(monkeypatch):
    """Record message boxes instead of blocking on them."""
    from PySide6.QtWidgets import QMessageBox

    seen = []

    def make(kind, answer=QMessageBox.Yes):
        def box(parent, title, text, *args, **kwargs):
            seen.append((kind, title, text))
            return answer

        return box

    monkeypatch.setattr(QMessageBox, "warning", make("warning", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", make("information", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", make("question"))
    return seen


@pytest.fixture
def window(app, tmp_path, boxes):
    from PySide6.QtCore import QSettings

    from panelimport.app import dispose
    from panelimport.gui.main_window import MainWindow

    w = MainWindow(Settings(), QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat))
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    yield w
    w.controller.undo_stack.setClean()
    dispose(w)


def open_panel(window, tmp_path: Path, app, job=None) -> Path:
    """Write a synthetic panel (default: 20 parts) and open it in the window."""
    from tests.synthetic.odbgen import sr_panel

    job = job or sr_panel(n_parts=20)
    src = job.write_tgz(tmp_path / "Panel_ODB.tgz")
    window.open_job(OdbJob(src), Decisions())
    app.processEvents()
    return src

