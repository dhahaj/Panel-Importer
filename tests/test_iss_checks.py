"""Checks before writing ISS: each one fires on a synthetic case; errors stop the write."""

from __future__ import annotations

import pytest

from panelimport.iss.checks import prepare
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import IssWriteError, write_iss
from panelimport.model.issues import Severity, error
from panelimport.model.panel import PanelPart
from tests.synthetic.projects import make_project


def issues(project, settings: IssSettings | None = None, **kw):
    return prepare(project, settings or IssSettings(), pwb_id="T", **kw)


def codes(prepared, severity: Severity | None = None) -> list[str]:
    return [i.code for i in prepared.issues if severity is None or i.severity is severity]


def assert_refused(prepared, tmp_path) -> None:
    assert not prepared.can_write
    with pytest.raises(IssWriteError):
        write_iss(prepared, tmp_path / "out.iss")
    assert not (tmp_path / "out.iss").exists()


def test_clean_project_has_no_issues(tmp_path):
    prepared = issues(make_project())
    assert prepared.issues == [] and prepared.can_write
    assert write_iss(prepared, tmp_path / "out.iss").exists()


def test_project_invalid(tmp_path):
    project = make_project()
    project.circuits = []
    prepared = issues(project)
    assert codes(prepared) == ["project_invalid"] and prepared.layout is None
    assert_refused(prepared, tmp_path)
    prepared = issues(make_project(), confirmed=False)
    assert codes(prepared) == ["project_invalid"] and "not confirmed" in prepared.issues[0].message
    project = make_project()
    project.circuit_outline = []
    assert codes(issues(project)) == ["project_invalid"]


def test_no_fiducials_counts_the_placements_layer(tmp_path):
    # Three fiducials, but only one on the bottom layer the parts are on.
    project = make_project(layer="bottom", fiducials=[(2, 2, "top"), (98, 2, "top"), (2, 68, "bottom")])
    prepared = issues(project)
    assert "no_fiducials" in codes(prepared, Severity.ERROR)
    assert "2 on the other layer" in next(i.message for i in prepared.issues if i.code == "no_fiducials")
    assert_refused(prepared, tmp_path)


def test_too_many_fiducials(tmp_path):
    project = make_project(fiducials=[(2, 2, "top"), (98, 2, "top"), (2, 68, "top"), (98, 68, "top")])
    prepared = issues(project)
    assert codes(prepared) == ["too_many_fiducials"]
    assert_refused(prepared, tmp_path)


def test_only_the_sides_fiducials_are_written():
    project = make_project(
        layer="bottom", fiducials=[(2, 2, "top"), (98, 2, "bottom"), (2, 68, "bottom"), (98, 68, "bottom"), (50, 2, "top")]
    )
    prepared = issues(project)
    assert "too_many_fiducials" not in codes(prepared)  # 3 on the bottom layer
    assert [f.name for f in prepared.layout.program.fiducials] == ["FID2", "FID3", "FID4"]
    assert prepared.layout.other_layer_fiducials == ["FID1", "FID5"]


def test_mixed_sides(tmp_path):
    project = make_project()
    project.placements[1].layer = "bottom"
    prepared = issues(project)
    assert "mixed_sides" in codes(prepared, Severity.ERROR)
    assert prepared.issues[0].data == {"top": 3, "bottom": 1}
    assert_refused(prepared, tmp_path)


def test_bottom_angles_unverified_warns():
    prepared = issues(make_project(layer="bottom"))
    assert codes(prepared) == ["bottom_angles_unverified"] and prepared.can_write
    assert "180° − θ" in prepared.issues[0].message
    prepared = issues(make_project(layer="bottom"), IssSettings(bottom_flip="front-back"))
    assert "−θ" in prepared.issues[0].message


def test_mirrored_circuit(tmp_path):
    project = make_project()
    project.circuits[1].mirror = True
    prepared = issues(project)
    assert [(i.code, i.circuit) for i in prepared.errors] == [("mirrored_circuit", 2)]
    assert_refused(prepared, tmp_path)
    project = make_project(ref=(45.0, 5.0), ref_mirror=True, circuits=[(0, 0, 0)])
    assert [(i.code, i.circuit) for i in issues(project).errors] == [("mirrored_circuit", 1)]


def test_rotated_circuit_warns():
    # Circuit 2's reference at (130, 30), turned 90°: its parts span x 80..130, y 30..70.
    project = make_project(width=150, height=150, ref=(20, 20), circuits=[(0, 0, 0), (110.0, 10.0, 90.0)])
    prepared = issues(project)
    assert [(i.code, i.circuit, i.severity) for i in prepared.issues] == [("rotated_circuit", 2, Severity.WARNING)]
    assert prepared.can_write


def test_part_number_fallback_and_missing_name(tmp_path):
    project = make_project()
    project.placements[0].part_number = ""
    prepared = issues(project)
    assert [(i.code, i.designator) for i in prepared.issues] == [("no_part_number", "R1")]
    assert prepared.layout.program.placements[0].component == "NAME-R1"
    project.placements[0].part_name = "  "
    prepared = issues(project)
    assert [(i.code, i.designator) for i in prepared.errors] == [("no_component_name", "R1")]
    assert_refused(prepared, tmp_path)


def test_component_name_chars():
    project = make_project()
    project.placements[0].part_number = "RES 1K/0603"
    project.placements[3].part_number = "RES 1K/0603"  # reported once per name
    prepared = issues(project)
    assert [(i.code, i.severity) for i in prepared.issues] == [("component_name_chars", Severity.WARNING)]
    assert "' /'" in prepared.issues[0].message


def test_duplicate_designator(tmp_path):
    project = make_project()
    project.placements[1].designator = "R1"
    prepared = issues(project)
    assert [(i.code, i.designator) for i in prepared.errors] == [("duplicate_designator", "R1")]
    assert_refused(prepared, tmp_path)


def test_panel_parts_skipped():
    parts = [
        PanelPart(designator="FID9", x=50, y=2),  # fiducial pattern: not reported
        PanelPart(designator="X1", x=2.01, y=2.0),  # on a selected fiducial: not reported
        PanelPart(designator="J9", x=60, y=60, part_number="CONN"),
    ]
    prepared = issues(make_project(panel_parts=parts))
    assert codes(prepared) == ["panel_parts_skipped"] and prepared.can_write
    assert prepared.issues[0].data == {"designators": ["J9"]}


def test_outside_circuit_warns():
    project = make_project(parts=[("R1", 41.0, 20.0, 0, "P-1"), ("R2", 40.0, 50.0, 0, "P-1")])  # R2 on the corner
    prepared = issues(project)
    assert [(i.code, i.designator, i.severity) for i in prepared.issues] == [("outside_circuit", "R1", Severity.WARNING)]


def test_outside_panel(tmp_path):
    # Circuit 2's copy of R1 lands at x = 5 + 45 + 52 = 102 on a 100 mm panel.
    project = make_project(parts=[("R1", 52.0, 20.0, 0, "P-1")])
    prepared = issues(project)
    assert [(i.code, i.circuit) for i in prepared.errors] == [("outside_panel", 2)]
    assert prepared.errors[0].location == pytest.approx((102.0, 25.0))
    assert_refused(prepared, tmp_path)
    project = make_project(fiducials=[(2, 2, "top"), (98, 2, "top"), (2, 71, "top")])
    assert [(i.code, i.subject) for i in issues(project).errors] == [("outside_panel", "FID3")]


def test_no_placements(tmp_path):
    project = make_project(parts=[])
    prepared = issues(project)
    assert codes(prepared) == ["no_placements"]
    assert_refused(prepared, tmp_path)


def test_source_changed_warns():
    changed = error("source_changed", "The source export Panel.zip has changed", subject="source")
    prepared = issues(make_project(), source_issue=changed)
    assert [(i.code, i.severity) for i in prepared.issues] == [("source_changed", Severity.WARNING)]
    assert prepared.can_write


def test_setting_dependent_errors(tmp_path):
    grid = make_project(circuits=[(0, 0, 0), (45.0, 0, 0)])
    assert issues(grid, IssSettings(circuit_layout="matrix")).issues == []  # 2 × 1 is a grid
    offset = make_project(circuits=[(0, 0, 0), (45.0, 0.3, 0)])  # not in one row
    assert codes(issues(offset, IssSettings(circuit_layout="matrix"))) == ["matrix_layout"]
    project = make_project(width=150, circuits=[(0, 0, 0), (45.0, 0, 0), (100.0, 0, 0)])  # uneven pitch
    prepared = issues(project, IssSettings(circuit_layout="matrix"))
    assert codes(prepared) == ["matrix_layout"]
    assert_refused(prepared, tmp_path)
