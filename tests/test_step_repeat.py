"""Panel structure read from STEP-REPEAT (primary path)."""

import pytest

from panelimport.io.odb import OdbJob
from panelimport.settings import Settings
from tests.conftest import codes, issues_of, run, write
from tests.synthetic.odbgen import sr_panel

TOL = 0.01


@pytest.mark.parametrize("units", ["MM", "INCH"])
@pytest.mark.parametrize("compressed", [False, True])
def test_uniform_panel(tmp_path, units, compressed):
    a = run(sr_panel(units=units, compress_members=compressed), tmp_path)
    assert a.mode == "panel"
    assert a.summary == "6 circuits, 3 × 2, pitch 52.000 × 38.500 mm, from STEP-REPEAT"
    assert (a.grid.cols, a.grid.rows) == (3, 2)
    assert a.grid.pitch_x == pytest.approx(52.0, abs=TOL)
    assert a.grid.pitch_y == pytest.approx(38.5, abs=TOL)
    assert a.grid.uniform
    offsets = [(round(c.dx, 3), round(c.dy, 3)) for c in a.circuits]
    assert offsets == [(0, 0), (52, 0), (104, 0), (0, 38.5), (52, 38.5), (104, 38.5)]
    assert not a.errors and not a.warnings
    assert a.can_confirm() == (True, "")


def test_placements_match_board_step(tmp_path):
    """Every circuit-relative placement matches the board step's component data."""
    path = write(sr_panel(n_parts=40), tmp_path)
    from panelimport.analysis.pipeline import analyze

    job = OdbJob(path)
    a = analyze(job, Settings())
    project = a.to_project()
    board = {
        c.name: c
        for layer in ("comp_+_top", "comp_+_bot")
        for c in job.components("pcb", layer).components
    }
    assert len(project.placements) == len(board) == 40
    rx, ry = project.circuit_reference.board_x, project.circuit_reference.board_y
    for p in project.placements:
        c = board[p.designator]
        assert p.x == pytest.approx(c.x - rx, abs=TOL)
        assert p.y == pytest.approx(c.y - ry, abs=TOL)
        assert p.rotation_raw == pytest.approx(c.rotation)
        assert p.rotation == pytest.approx((360 - c.rotation) % 360)
        assert p.layer == ("bottom" if c.mirror else "top")
    c1 = next(p for p in project.placements if p.designator == "C1")
    assert c1.package == "C0603" and c1.part_name == "CAP-100N"
    assert c1.attributes["PART_NUMBER"] == "D-1001"


def test_reference_point_and_panel_frame(tmp_path):
    a = run(sr_panel(), tmp_path)
    p = a.to_project()
    assert p.circuit_reference.kind == "profile-lower-left"
    assert (p.circuit_reference.x, p.circuit_reference.y) == (5.0, 5.0)
    assert p.panel.outline[0] == [0.0, 0.0]
    assert (p.panel.width, p.panel.height) == (164.0, 85.0)


def test_board_origin_reference(tmp_path):
    a = run(sr_panel(), tmp_path, settings=Settings(circuit_reference="board-origin"))
    assert a.reference_kind == "board-origin"


def test_multiple_blocks_uniform(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 3, 1)
    pan.step_repeat("pcb", 5, 43.5, 52, 0, 3, 1)
    a = run(job, tmp_path)
    assert a.summary == "6 circuits, 3 × 2, pitch 52.000 × 38.500 mm, from STEP-REPEAT"
    assert "nonuniform_grid" not in codes(a)


def test_multiple_blocks_non_uniform(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 3, 1)
    pan.step_repeat("pcb", 5.7, 43.5, 52, 0, 3, 1)
    a = run(job, tmp_path)
    (issue,) = issues_of(a, "nonuniform_grid")
    assert issue.severity.value == "warning"
    assert a.summary.endswith("non-uniform")


def test_nested_repeat(tmp_path):
    job = sr_panel()
    sub = job.step("sub", 104, 36.5)
    sub.step_repeat("pcb", 0, 0, 52, 0, 2, 1)
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("sub", 5, 5, 0, 38.5, 1, 2)
    pan.step_repeat("pcb", 109, 5, 0, 38.5, 1, 2)
    a = run(job, tmp_path)
    assert a.board_step.lower() == "pcb"
    assert sorted((round(c.dx, 3), round(c.dy, 3)) for c in a.circuits) == sorted(
        [(0, 0), (52, 0), (104, 0), (0, 38.5), (52, 38.5), (104, 38.5)]
    )
    assert a.grid.uniform and not a.errors


def test_rotated_instance_flagged(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 3, 1)
    # Second row rotated 180° about the datum: datum placed at the far corner.
    pan.step_repeat("pcb", 55, 80, 52, 0, 3, 1, angle=180)
    a = run(job, tmp_path)
    rotated = issues_of(a, "circuit_rotated")
    assert sorted(i.circuit for i in rotated) == [4, 5, 6]
    assert all(i.severity.value == "warning" for i in rotated)
    assert a.grid.uniform  # same footprint grid, only rotated
    c4 = a.circuits[3]
    assert c4.rotation == pytest.approx(180)
    # A component lands where 180° rotation about the instance puts it.
    u1 = next(p for p in a.placements if p.designator == "U1")
    x, y, rot = a.circuit_position(u1, c4)
    assert (x, y) == pytest.approx((55 - 15, 80 - 18))
    assert rot == pytest.approx(180)


def test_mirrored_instance_flagged(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 2, 1)
    pan.step_repeat("pcb", 159, 5, 0, 0, 1, 1, mirror=True)
    a = run(job, tmp_path)
    (issue,) = issues_of(a, "circuit_mirrored")
    assert issue.circuit == 3 and a.circuits[2].mirror


def test_flipped_instance_flagged(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 2, 1)
    pan.step_repeat("pcb", 159, 5, 0, 0, 1, 1, flip=True)
    a = run(job, tmp_path)
    assert "step_flipped" in codes(a)
    assert a.circuits[2].flip


def test_datum_anchor_setting(tmp_path):
    job = sr_panel()
    job.steps["pcb"].datum = (10.0, 5.0)
    path = write(job, tmp_path)
    from panelimport.analysis.pipeline import analyze

    a_datum = analyze(OdbJob(path), Settings(step_repeat_anchor="datum"))
    a_origin = analyze(OdbJob(path), Settings(step_repeat_anchor="origin"))
    assert "datum_origin_differ" in codes(a_datum)
    # Datum anchoring shifts the boards by the datum relative to origin anchoring.
    x_d, y_d = a_datum.circuits[0].transform.apply(0, 0)
    x_o, y_o = a_origin.circuits[0].transform.apply(0, 0)
    assert (x_o - x_d, y_o - y_d) == pytest.approx((10.0, 5.0))


def test_crosscheck_consistent_and_inconsistent(tmp_path):
    job = sr_panel()
    job.flatten("panel", keep_repeats=True)
    a = run(job, tmp_path / "a")
    assert "flattened_copies" in codes(a)
    assert not [c for c in codes(a) if c.startswith("crosscheck")]
    assert [p.designator for p in a.panel_parts] == ["FID1", "FID2", "FID3"]

    job = sr_panel()
    job.flatten("panel", keep_repeats=True)
    pan = job.steps["panel"]
    [c for c in pan.components if c.name == "R1"][3].x += 0.05
    pan.components.remove([c for c in pan.components if c.name == "C1"][5])
    a = run(job, tmp_path / "b")
    (mismatch,) = issues_of(a, "crosscheck_mismatch")
    assert (mismatch.designator, mismatch.circuit) == ("R1", 4)
    (missing,) = issues_of(a, "crosscheck_missing")
    assert (missing.designator, missing.circuit) == ("C1", 6)


def test_panel_parts_and_fiducials(tmp_path):
    a = run(sr_panel(), tmp_path)
    panel_fids = [f for f in a.fiducial_candidates if f.selectable]
    assert [f.name for f in panel_fids] == ["FID1", "FID2", "FID3"]
    assert all("component" in f.sources and "copper" in f.sources for f in panel_fids)


def test_duplicate_designator(tmp_path):
    job = sr_panel()
    job.steps["pcb"].component("R1", "R0402", 45, 5)
    a = run(job, tmp_path)
    (dup,) = issues_of(a, "duplicate_designator")
    assert dup.designator == "R1" and dup.severity.value == "error"


def test_ambiguous_board_steps(tmp_path):
    job = sr_panel()
    other = job.step("pcb2", 20, 20)
    other.component("X1", "R0402", 5, 5)
    job.steps["panel"].step_repeat("pcb2", 0, 90, 0, 0, 1, 1)
    a = run(job, tmp_path)
    assert "ambiguous_steps" in codes(a)
    b = run(job, tmp_path / "b", panel_step="panel", board_step="pcb")
    assert "ambiguous_steps" not in codes(b)
