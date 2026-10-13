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
