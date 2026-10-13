"""Single-board fallback: never chosen silently, grid entered by the user."""

import pytest

from panelimport.model.panel import Fiducial, SingleBoardSetup
from panelimport.session import Session
from tests.conftest import codes, issues_of, run
from tests.synthetic.odbgen import Job, populate_board, sr_panel


def single_board_job():
    job = Job(name="single")
    board = job.step("pcb", 50, 36.5)
    board.component("U1", "SOIC8", 15, 18)
    board.component("C1", "C0603", 25, 10, rot=90)
    populate_board(board, 10, seed=5)
    return job


def test_single_board_needs_confirmation(tmp_path):
    a = run(single_board_job(), tmp_path)
    assert a.mode == "single-board"
    (issue,) = issues_of(a, "single_board")
    assert issue.severity.value == "error"
    assert a.can_confirm() == (False, "Single-board mode is not confirmed")
    assert a.summary.startswith("Single board")


def test_single_board_grid(tmp_path):
    setup = SingleBoardSetup(
        cols=3,
        rows=2,
        pitch_x=52,
        pitch_y=38.5,
        origin_x=5,
        origin_y=5,
        panel_width=164,
        panel_height=85,
        fiducials=[Fiducial("FID1", 2.5, 2.5, "manual"), Fiducial("FID2", 161.5, 2.5, "manual")],
    )
    a = run(single_board_job(), tmp_path, single_board=setup)
    assert a.summary == "6 circuits, 3 × 2, pitch 52.000 × 38.500 mm, from manual entry"
    assert [(c.dx, c.dy) for c in a.circuits][:3] == [(0, 0), (52, 0), (104, 0)]
    assert a.circuits[0].transform.apply(0, 0) == (5, 5)
    assert [f.name for f in a.fiducials] == ["FID1", "FID2"]
    assert a.can_confirm() == (True, "")
    project = a.to_project()
    assert project.mode == "single-board" and project.grid.source == "manual"
    assert project.single_board == setup


def test_single_board_offset_table(tmp_path):
    setup = SingleBoardSetup(offsets=[[0, 0], [60, 0], [0, 45]], origin_x=3, origin_y=4)
    a = run(single_board_job(), tmp_path, single_board=setup)
    assert len(a.circuits) == 3
    assert "panel_outline" in codes(a)  # no outline entered: warned, not guessed silently
    assert "nonuniform_grid" in codes(a)


def test_single_board_with_panel_export(tmp_path):
    panel_src = sr_panel().write_folder(tmp_path / "panel")
    src = single_board_job().write_folder(tmp_path / "board")
    s = Session()
    s.open_source(src)
    setup = SingleBoardSetup(cols=3, rows=2, pitch_x=52, pitch_y=38.5, origin_x=5, origin_y=5, panel_source=str(panel_src))
    a = s.update(single_board=setup)
    assert a.panel_outline and max(x for x, _y in a.panel_outline) == pytest.approx(164)
    assert {"FID1", "FID2", "FID3"} <= {f.name for f in a.fiducial_candidates if f.selectable} or any(
        f.selectable for f in a.fiducial_candidates
    )
    draws = a.layer_draws()
    assert any(d.job is s.panel_job for d in draws)
