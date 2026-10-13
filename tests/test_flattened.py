"""Flattened-panel fallback: circuits from repeated designators."""

import pytest

from panelimport.settings import Settings
from tests.conftest import codes, issues_of, run
from tests.synthetic.odbgen import CompDef, sr_panel


def _comparable(project):
    return {
        "grid": (project.grid.cols, project.grid.rows, project.grid.pitch_x, project.grid.pitch_y, project.grid.uniform),
        "circuits": [(c.index, c.dx, c.dy, c.rotation, c.mirror) for c in project.circuits],
        "placements": sorted(
            (p.designator, p.x, p.y, p.rotation, p.rotation_raw, p.layer, p.package, p.part_name) for p in project.placements
        ),
        "panel": (project.panel.width, project.panel.height),
        "reference": (project.circuit_reference.x, project.circuit_reference.y),
    }


def test_flattened_twin_matches_step_repeat(tmp_path):
    """A flattened synthetic panel produces the same result as its step-repeat twin."""
    sr = run(sr_panel(n_parts=40), tmp_path / "sr")
    twin = sr_panel(n_parts=40)
    twin.flatten("panel")
    flat = run(twin, tmp_path / "flat", panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    assert sr.mode == "panel" and flat.mode == "flattened"
    assert _comparable(sr.to_project()) == _comparable(flat.to_project())
    assert [p.designator for p in flat.panel_parts] == ["FID1", "FID2", "FID3"]
    assert not flat.errors
    assert all(c.residual == pytest.approx(0, abs=1e-6) for c in flat.circuits)


def test_flattened_rotated_twin(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 3, 1)
    pan.step_repeat("pcb", 55, 80, 52, 0, 3, 1, angle=180)
    sr = run(job, tmp_path / "sr")
    job.flatten("panel")
    flat = run(job, tmp_path / "flat", panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    assert _comparable(sr.to_project())["circuits"] == _comparable(flat.to_project())["circuits"]
    assert sorted(i.circuit for i in issues_of(flat, "circuit_rotated")) == [4, 5, 6]


def test_outline_assignment_used_when_available(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    a = run(job, tmp_path, panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    assert "copies_sorted" not in codes(a)
    assert a.reference_kind == "outline-lower-left"


def test_sorted_assignment_without_outlines(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    job.steps["panel"].lines.pop("board_outline")
    a = run(job, tmp_path, panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    assert "copies_sorted" in codes(a)
    assert "reference_fallback" in codes(a)
    assert a.summary == "6 circuits, 3 × 2, pitch 52.000 × 38.500 mm, from repeated designators"


def test_suffixed_designators(tmp_path):
    job = sr_panel()
    job.flatten("panel", suffix="_{n}")
    plain = run(job, tmp_path / "a", panel_step="panel")
    assert plain.mode == "single-board"
    assert plain.suggested_suffix == r"_(\d+)$"
    a = run(job, tmp_path / "b", Settings(copy_suffix_regex=r"_(\d+)$"), panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    assert a.mode == "flattened" and len(a.circuits) == 6
    assert {p.designator for p in a.placements} >= {"U1", "C1", "R1"}
    assert not a.errors


def test_missing_and_extra_part_reported_with_designator_and_circuit(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    pan = job.steps["panel"]
    r1 = [c for c in pan.components if c.name == "R1"]
    pan.components.remove(r1[2])  # third copy: circuit 3
    c1 = [c for c in pan.components if c.name == "C1"][0]
    pan.components.append(CompDef("C1", "C0603", c1.x + 104 + 3, c1.y + 2, 90, "top", c1.part))
    a = run(job, tmp_path, panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    by_designator = {i.designator: i for i in issues_of(a, "copy_count")}
    assert by_designator["R1"].circuit == 3 and "missing in circuit 3" in by_designator["R1"].message
    assert by_designator["C1"].circuit == 3 and "extra copy in circuit 3" in by_designator["C1"].message
    assert all(i.severity.value == "error" for i in by_designator.values())
    assert not a.can_confirm()[0]


def test_panel_level_parts_need_confirmation(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    a = run(job, tmp_path / "a", panel_step="panel")
    fids = {i.designator for i in issues_of(a, "copy_count")}
    assert fids == {"FID1", "FID2", "FID3"}
    assert all("outside the circuits" in i.message for i in issues_of(a, "copy_count"))
    b = run(job, tmp_path / "b", panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    assert not issues_of(b, "copy_count")


def test_fit_residual_error(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    pan = job.steps["panel"]
    copies = [c for c in pan.components if c.name == "U1"]
    copies[4].x += 0.2  # circuit 5 no longer a rigid copy
    a = run(job, tmp_path, panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    (issue,) = issues_of(a, "fit_residual")
    assert issue.circuit == 5 and issue.designator == "U1"


def test_paste_checked_per_copy_with_circuits(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    a = run(job, tmp_path, panel_step="panel", panel_level=["FID1", "FID2", "FID3"])
    (no_paste,) = issues_of(a, "no_paste")
    assert no_paste.designator == "J1" and no_paste.data["circuits"] == [1, 2, 3, 4, 5, 6]
    assert all(p.paste is not None for p in a.placements)
