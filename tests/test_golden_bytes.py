"""Golden ISS bytes: the programs written for step-and-repeat panels must not change.

Every case is rendered with a fixed ``lastEdit`` and compared byte for byte with
``tests/fixtures/golden/<case>.iss``.  The files were written by the code before
non-grid panels were supported; set ``PANELIMPORT_REGEN_GOLDEN=1`` to rewrite them
(only when a change to grid output is intended and reviewed).

Cases: projects built from the model (Phase 2 only) and synthetic ODB++ exports run
through Phase 1 (STEP-REPEAT grids, several blocks, nested sub-panels, every copy
rotated, a flattened export, single-board entry), plus the real ER panel.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import encode, render
from panelimport.model.panel import Decisions, Fiducial, SingleBoardSetup
from panelimport.session import Session
from panelimport.settings import CORNERS, REFERENCE_KINDS, Settings
from tests.synthetic.odbgen import Job
from tests.synthetic.projects import make_project

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 5, 9, 30, tzinfo=timezone(timedelta(hours=-6)))
REGEN = os.environ.get("PANELIMPORT_REGEN_GOLDEN") == "1"


# -------------------------------------------------------------------- model projects
GRID = [(5.0, 5.0), (50.0, 5.0), (5.0, 60.0), (50.0, 60.0)]
OUTLINES = {
    "profile-lower-left": (0.0, 0.0, 40.0, 50.0),
    "board-origin": (-12.0, -7.0, 28.0, 43.0),
    "board-datum": (-40.0, -50.0, 0.0, 0.0),
}
FIRST = {"lower-left": 0, "lower-right": 1, "upper-left": 2, "upper-right": 3}


def _reference_case(kind: str, first: str):
    ox, oy, _, _ = OUTLINES[kind]
    order = [FIRST[first]] + [i for i in range(4) if i != FIRST[first]]
    lls = [GRID[i] for i in order]
    ref = (lls[0][0] - ox, lls[0][1] - oy)
    circuits = [(x - lls[0][0], y - lls[0][1], 0.0) for x, y in lls]
    parts = [("R1", ox + 10.0, oy + 20.0, 30.0, "P-1"), ("C1", ox + 35.5, oy + 2.25, 90.0, "P-2")]
    return make_project(width=100, height=120, ref=ref, kind=kind, outline=OUTLINES[kind], circuits=circuits, parts=parts)


def _two_circuits_bottom(width: float, height: float, circuits, outline):
    return make_project(
        width=width,
        height=height,
        circuits=circuits,
        outline=outline,
        layer="bottom",
        parts=[("R1", 10.0, 20.0, 30.0, "P-1")],
        fiducials=[(2.0, 2.0, "bottom"), (width - 2.0, 2.0, "bottom"), (2.0, height - 2.0, "bottom")],
    )


def _model_cases() -> dict:
    cases = {}
    for kind in REFERENCE_KINDS:
        for first in CORNERS:
            cases[f"model_ref_{kind}_{first}"] = lambda k=kind, f=first: (_reference_case(k, f), IssSettings(panel_rotation=0))
    non_uniform = [(0.0, 0.0, 0.0), (45.123, 0.2, 0.0), (0.05, 55.5, 0.0), (44.9, 55.31, 0.0), (90.0007, 1.0, 0.0)]
    cases["model_non_uniform"] = lambda: (make_project(width=150, height=120, circuits=non_uniform), IssSettings())
    for rot in (0, 90, 180, 270):
        cases[f"model_panel_rotation_{rot}"] = lambda r=rot: (make_project(), IssSettings(panel_rotation=r))
    for rot in (90, 30, 270):
        cases[f"model_rotated_circuit1_{rot}"] = lambda r=rot: (
            make_project(width=200, height=200, ref=(80.0, 60.0), ref_rotation=float(r), circuits=[(0, 0, 0), (0, 70.0, 0)]),
            IssSettings(panel_rotation=0),
        )
    for flip in ("left-right", "front-back"):
        for rot in (0, 90, 180, 270, "auto"):
            cases[f"model_bottom_{flip}_{rot}"] = lambda f=flip, r=rot: (
                make_project(layer="bottom"),
                IssSettings(bottom_flip=f, panel_rotation=r),
            )
    for flip in (None, "left-right", "front-back"):
        cases[f"model_portrait_auto_{flip or 'top'}"] = lambda f=flip: (
            make_project(
                width=70, height=100, circuits=[(0, 0, 0), (0, 52.0, 0)], layer="top" if f is None else "bottom", outline=(0, 0, 50, 40)
            ),
            IssSettings(bottom_flip=f or "left-right"),
        )
    grid = [(0, 0, 0), (45.0, 0, 0), (0, 55.0, 0), (45.0, 55.0, 0)]
    cases["model_matrix_bottom"] = lambda: (
        make_project(width=100, height=120, circuits=grid, layer="bottom"),
        IssSettings(circuit_layout="matrix"),
    )
    cases["model_by_hand_left_right"] = lambda: (
        _two_circuits_bottom(100, 70, [(0, 0, 0), (45.0, 0, 0)], (0, 0, 40, 50)),
        IssSettings(),
    )
    cases["model_by_hand_front_back"] = lambda: (
        _two_circuits_bottom(100, 70, [(0, 0, 0), (45.0, 0, 0)], (0, 0, 40, 50)),
        IssSettings(bottom_flip="front-back"),
    )
    cases["model_by_hand_portrait"] = lambda: (
        _two_circuits_bottom(70, 100, [(0, 0, 0), (0, 52.0, 0)], (0, 0, 50, 40)),
        IssSettings(),
    )
    cases["model_angle_settings"] = lambda: (
        make_project(),
        IssSettings(angle_direction="cw", angle_offset=10, header_completion="total", component_size="zero"),
    )
    return cases


# -------------------------------------------------------------------- synthetic ODB++
def board(job: Job, side: str = "top", name: str = "pcb"):
    """A 50 × 36.5 board whose profile, origin and datum all differ, three parts on one side."""
    b = job.step(name, 50.0, 36.5, x0=-8.0, y0=-6.0, datum=(4.0, 3.0))
    b.component("U1", "SOIC8", 7.0, 12.0, rot=0, side=side, part="IC-555", props={"PART_NUMBER": "D-1"})
    b.component("C1", "C0603", 17.0, 4.0, rot=90, side=side, part="CAP", props={"PART_NUMBER": "D-2"})
    b.component("R1", "R0402", 22.0, 19.0, rot=45, side=side, part="RES", props={"PART_NUMBER": "D-3"})
    return b


def fiducials(step, width: float, height: float, side: str = "top") -> None:
    for i, (x, y) in enumerate([(2.5, 2.5), (width - 2.5, 2.5), (2.5, height - 2.5)], start=1):
        step.component(f"FID{i}", "FID1MM", x, y, side=side, part="FIDUCIAL")


SETTINGS = Settings(part_number_attribute="PART_NUMBER")
FIDS = ["FID1", "FID2", "FID3"]


def _grid_job(side: str = "top") -> Job:
    job = Job()
    board(job, side)
    panel = job.step("panel", 164.0, 85.0)
    panel.step_repeat("pcb", 17.0, 14.0, 52.0, 38.5, 3, 2)
    fiducials(panel, 164.0, 85.0, side)
    return job


def _two_blocks_job() -> Job:
    job = Job()
    board(job)
    panel = job.step("panel", 200.0, 90.0)
    panel.step_repeat("pcb", 17.0, 14.0, 52.0, 0.0, 2, 1)
    panel.step_repeat("pcb", 17.0, 55.0, 60.0, 0.0, 3, 1)
    fiducials(panel, 200.0, 90.0)
    return job


def _nested_job() -> Job:
    job = Job()
    board(job)
    sub = job.step("sub", 104.0, 38.5)
    sub.step_repeat("pcb", 12.0, 9.0, 52.0, 0.0, 2, 1)
    panel = job.step("panel", 220.0, 90.0)
    panel.step_repeat("sub", 5.0, 5.0, 0.0, 40.0, 1, 2)
    panel.step_repeat("pcb", 121.0, 14.0, 0.0, 40.0, 1, 2)
    fiducials(panel, 220.0, 90.0)
    return job


def _all_rotated_job() -> Job:
    """Every copy turned 90°: circuit 1 is rotated on the panel, no circuit relative to it."""
    job = Job()
    board(job)
    panel = job.step("panel", 170.0, 70.0)
    panel.step_repeat("pcb", 50.0, 45.0, 42.0, 0.0, 3, 1, angle=90)
    fiducials(panel, 170.0, 70.0)
    return job


def _flattened_job() -> Job:
    job = _grid_job()
    job.flatten("panel")
    return job


def _single_board_job() -> Job:
    job = Job(name="single")
    board(job)
    return job


def _odb_cases() -> dict:
    cases = {}
    for kind in REFERENCE_KINDS:
        for first in CORNERS:
            cases[f"odb_grid_{kind}_{first}"] = lambda tmp, k=kind, f=first: (
                _grid_job(),
                dict(numbering_first=f, circuit_reference=k),
                IssSettings(),
            )
    for flip in ("left-right", "front-back"):
        cases[f"odb_grid_bottom_{flip}"] = lambda tmp, f=flip: (_grid_job("bottom"), {}, IssSettings(bottom_flip=f, panel_rotation=90))
    cases["odb_grid_matrix"] = lambda tmp: (_grid_job(), {}, IssSettings(circuit_layout="matrix"))
    cases["odb_two_blocks_non_uniform"] = lambda tmp: (_two_blocks_job(), {}, IssSettings())
    cases["odb_nested"] = lambda tmp: (_nested_job(), {}, IssSettings())
    cases["odb_all_rotated_90"] = lambda tmp: (_all_rotated_job(), {}, IssSettings())
    cases["odb_flattened"] = lambda tmp: (_flattened_job(), dict(panel_step="panel", panel_level=list(FIDS)), IssSettings())
    setup = SingleBoardSetup(
        cols=3,
        rows=2,
        pitch_x=52,
        pitch_y=38.5,
        origin_x=17,
        origin_y=14,
        panel_width=164,
        panel_height=85,
        fiducials=[Fiducial("FID1", 2.5, 2.5, "manual"), Fiducial("FID2", 161.5, 2.5, "manual"), Fiducial("FID3", 2.5, 82.5, "manual")],
    )
    cases["odb_single_board"] = lambda tmp: (_single_board_job(), dict(single_board=setup, fiducials=[]), IssSettings())
    return cases


MODEL_CASES = _model_cases()
ODB_CASES = _odb_cases()


def _program_bytes(project, settings: IssSettings, pwb_id: str = "T") -> bytes:
    prepared = prepare(project, settings, pwb_id=pwb_id)
    assert prepared.can_write, [i.format() for i in prepared.errors]
    return encode(render(prepared.layout, settings, NOW))


def _check(name: str, data: bytes) -> None:
    path = GOLDEN / f"{name}.iss"
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    assert path.exists(), f"missing golden {path.name}; run with PANELIMPORT_REGEN_GOLDEN=1 to create it"
    assert data == path.read_bytes(), f"{path.name} changed"


@pytest.mark.parametrize("name", sorted(MODEL_CASES))
def test_model_golden(name):
    project, settings = MODEL_CASES[name]()
    _check(name, _program_bytes(project, settings))


@pytest.mark.parametrize("name", sorted(ODB_CASES))
def test_odb_golden(name, tmp_path):
    job, decisions, iss_settings = ODB_CASES[name](tmp_path)
    src = job.write_folder(tmp_path)
    decisions.setdefault("fiducials", list(FIDS))
    a = analyze(OdbJob(src), SETTINGS, Decisions(confirmed=True, **decisions))
    assert a.mode in ("panel", "flattened", "single-board"), a.mode
    project = a.to_project()
    _check(name, _program_bytes(project, iss_settings))


ER_FILES = [FIXTURES / "Panel.zip", FIXTURES / "Panel.panel.json"]
PILOT_FIDUCIALS = ["F(176.275,12.703)", "F(6.351,12.703)", "F(176.275,243.307)"]


@pytest.mark.skipif(not all(p.exists() for p in ER_FILES), reason="ER panel files not present")
def test_er_golden(tmp_path):
    shutil.copy(FIXTURES / "Panel.zip", tmp_path / "Panel.zip")
    data = json.loads((FIXTURES / "Panel.panel.json").read_text(encoding="utf-8"))
    data["source"]["path"] = "Panel.zip"
    (tmp_path / "Panel.panel.json").write_text(json.dumps(data), encoding="utf-8")
    session = Session()
    reopened = session.open_project(tmp_path / "Panel.panel.json")
    assert reopened.source_issue is None and reopened.differences == []
    session.update(fiducials=PILOT_FIDUCIALS)
    project = session.analysis.to_project(tmp_path / "Panel.panel.json")
    _check("er_panel", _program_bytes(project, IssSettings(), pwb_id="Panel"))
