"""Component sizes: from the export (package body outline, ``.comp_height``), edited in
Phase 1, saved with the project and written to ISS as one size per component."""

from __future__ import annotations

import json

import pytest

from panelimport.analysis import edits as E
from panelimport.analysis.pipeline import analyze
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.reader import read_program
from panelimport.iss.report import format_report
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import write_iss
from panelimport.model.panel import Acknowledgement, ComponentEdit, Decisions
from panelimport.model.project_file import load_project
from panelimport.session import Session
from tests.conftest import write
from tests.synthetic.odbgen import sr_panel
from tests.synthetic.projects import make_project


def _job(tmp_path, units: str = "MM") -> OdbJob:
    job = sr_panel(units=units, n_parts=5)
    job.steps["pcb"].components[1].attrs[".comp_height"] = 0.55  # C1, in mm
    return OdbJob(write(job, tmp_path))


def _size(part) -> tuple[float, float, float]:
    return (round(part.width, 4), round(part.length, 4), round(part.height, 4))


def _sized(project, **sizes):
    """``project`` with these placements' sizes: designator=(width, length, height)."""
    for p in project.placements:
        if p.designator in sizes:
            p.width, p.length, p.height = sizes[p.designator]
    return project


def _written(prepared) -> dict[str, tuple[float, float, float]]:
    return {c.name: (c.width, c.length, c.height) for c in prepared.layout.program.components}


# ---------------------------------------------------------------- Phase 1
@pytest.mark.parametrize("units", ["MM", "INCH"])
def test_sizes_come_from_the_package_body_and_comp_height(tmp_path, units):
    a = analyze(_job(tmp_path, units))
    sizes = {p.designator: _size(p) for p in a.placements}
    assert sizes["C1"] == (1.6, 0.8, 0.55)  # C0603 body (pads left out); .comp_height in the file's units
    assert sizes["U1"] == (5.31, 3.9, 0.0)  # SOIC8 body; no .comp_height: unknown
    assert sizes["C2"] == (1.6, 0.8, 0.0)  # bottom side: the package's own frame, not mirrored
    fid = next(p for p in a.panel_parts if p.designator == "FID1")
    assert _size(fid) == (2.0, 2.0, 0.0)
    c1 = next(p for p in a.to_project().placements if p.designator == "C1")
    assert (c1.width, c1.length, c1.height) == pytest.approx((1.6, 0.8, 0.55), abs=1e-4)


def test_size_edit(tmp_path):
    job = _job(tmp_path)
    a = analyze(job)
    c1 = E.find_part(a, "board", "C1")
    e = E.edit_from_values(a, "board", "C1", {**E.shown_values(a, c1), "width": 1.6, "height": 0.9})
    assert (e.width, e.length, e.height) == (None, None, 0.9)  # only what differs from the export
    assert E.describe_edit(e) == "changes size"
    b = analyze(job, None, Decisions(component_edits=[e], edit_frame=a.edit_frame))
    c1 = E.find_part(b, "board", "C1")
    assert c1.state == "edited" and _size(c1) == (1.6, 0.8, 0.9) and c1.export == {"height": 0.55}
    assert E.status_text(c1) == "edited: size"
    assert E.shown_values(b, c1, export=True)["height"] == 0.55
    assert E.edit_from_values(b, "board", "C1", {**E.shown_values(b, c1), "height": 0.55}) is None  # back to the export
    p = next(p for p in b.to_project().placements if p.designator == "C1")
    assert p.height == 0.9
    # 0 sets a dimension to unknown.
    unknown = E.edit_from_values(a, "board", "C1", {**E.shown_values(a, E.find_part(a, "board", "C1")), "height": 0.0})
    assert unknown.height == 0.0
    c1 = E.find_part(analyze(job, None, Decisions(component_edits=[unknown], edit_frame=a.edit_frame)), "board", "C1")
    assert c1.height == 0.0 and c1.export == {"height": 0.55}


def test_added_part_size_from_its_package_or_as_entered(tmp_path):
    job = _job(tmp_path)
    a = analyze(job)
    values = {"package": "C0603", "layer": "top", "x": 20.0, "y": 20.0, "rotation": 0.0}
    add = E.added_edit("board", "C9", {**values, "width": 0.0, "height": 0.0})
    assert (add.width, add.length, add.height) == (None, None, None)  # unknown is not stored
    b = analyze(job, None, Decisions(component_edits=[add], edit_frame=a.edit_frame))
    assert _size(E.find_part(b, "board", "C9")) == (1.6, 0.8, 0.0)
    add = E.added_edit("board", "C9", {**values, "width": 2.0, "height": 1.1})
    b = analyze(job, None, Decisions(component_edits=[add], edit_frame=a.edit_frame))
    assert _size(E.find_part(b, "board", "C9")) == (2.0, 0.8, 1.1)
    panel = E.added_edit("panel", "FID9", {"package": "FID1MM", "layer": "top", "x": 80.0, "y": 2.5, "rotation": 0.0})
    b = analyze(job, None, Decisions(component_edits=[panel], edit_frame=a.edit_frame))
    assert _size(E.find_part(b, "panel", "FID9")) == (2.0, 2.0, 0.0)


def test_sizes_are_saved_and_older_projects_reopen_unchanged(tmp_path):
    s = Session()
    s.open_job(_job(tmp_path))
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    path = tmp_path / "p.panel.json"
    s.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    c1 = next(p for p in data["placements"] if p["designator"] == "C1")
    assert (data["version"], c1["width"], c1["length"], c1["height"]) == (3, 1.6, 0.8, 0.55)
    reopened = Session().open_project(path)
    assert reopened.differences == [] and reopened.project == s.saved_project

    # A version 2 file has no sizes: the re-analysis finds them, which is no difference.
    data["version"] = 2
    for key in ("placements", "panel_parts"):
        for part in data[key]:
            for f in ("width", "length", "height"):
                del part[f]
    path.write_text(json.dumps(data), encoding="utf-8")
    s2 = Session()
    reopened = s2.open_project(path)
    assert reopened.project.version == 2 and reopened.differences == []
    assert s2.analysis.confirmed and _size(E.find_part(s2.analysis, "board", "C1")) == (1.6, 0.8, 0.55)
    # Written straight from the old file, every size is 0, and the report says why.
    codes = [i.code for i in prepare(load_project(path), IssSettings(), pwb_id="P").issues]
    assert "component_size_old_project" in codes and "component_size_unknown" not in codes


# ---------------------------------------------------------------- ISS
def test_one_size_per_component_written_and_read_back(tmp_path):
    project = _sized(make_project(), U1=(9.0177, 9.0177, 1.2))
    prepared = prepare(project, IssSettings(), pwb_id="T")
    assert prepared.issues == []
    expected = {
        "107522-31-1001": (1.6, 0.8, 0.55),  # R1 and R2
        "107523-3156-1003": (1.6, 0.8, 0.55),
        "109826": (9.0177, 9.0177, 1.2),
    }
    assert _written(prepared) == expected
    out = write_iss(prepared, tmp_path / "t.iss")
    assert '<componentSize witdh="9.0177" length="9.0177" height="1.2" />' in out.read_text(encoding="utf-8-sig")
    assert {c.name: (c.width, c.length, c.height) for c in read_program(out).components} == expected
    assert "Components: 3; every size known" in format_report(prepared)
    report = format_report(prepared, verbose=True)
    assert "component              width    length    height" in report and "109826" in report.split("component  ")[-1]
    zero = prepare(project, IssSettings(component_size="zero"), pwb_id="T")
    assert zero.issues == [] and set(_written(zero).values()) == {(0.0, 0.0, 0.0)}
    assert "sizes written as 0 (component_size=zero)" in format_report(zero)


def test_unknown_sizes_are_reported():
    project = _sized(make_project(), C1=(0.0, 0.0, 0.0), U1=(9.0, 9.0, 0.0))
    prepared = prepare(project, IssSettings(), pwb_id="T")
    (issue,) = prepared.issues
    assert issue.code == "component_size_unknown" and issue.is_warning and prepared.can_write
    assert issue.data == {"components": {"107523-3156-1003": ["width", "length", "height"], "109826": ["height"]}}
    assert "2 component(s) have an unknown size, written as 0: 107523-3156-1003 (width, length, height)" in issue.message
    assert "Components: 3; sizes: 1 complete, 2 with unknowns" in format_report(prepared)


def test_placements_of_one_component_that_disagree():
    # R1 and R2 are both 107522-31-1001; R2's height is unknown, which is no disagreement.
    project = _sized(make_project(), R2=(2.0, 0.8, 0.0))
    prepared = prepare(project, IssSettings(), pwb_id="T")
    (issue,) = prepared.issues
    assert (issue.code, issue.subject, issue.designator) == ("component_size_differs", "107522-31-1001", "R1")
    assert "different width (R1 1.6 × 0.8 × 0.55; R2 2 × 0.8 × 0); written 1.6 × 0.8 × 0.55" in issue.message
    assert _written(prepared)["107522-31-1001"] == (1.6, 0.8, 0.55)  # the first placement's
    # An edit is deliberate: it sets the size of the whole component, without a warning.
    project.component_edits = [ComponentEdit("R2", width=2.0)]
    prepared = prepare(project, IssSettings(), pwb_id="T")
    assert prepared.issues == [] and _written(prepared)["107522-31-1001"] == (2.0, 0.8, 0.55)


def test_a_quarter_turn_angle_offset_swaps_width_and_length():
    def size(layer: str = "top", **settings) -> tuple[float, float, float]:
        project = _sized(make_project(layer=layer), U1=(5.0, 3.0, 1.0))
        return _written(prepare(project, IssSettings(**settings), pwb_id="T"))["109826"]

    assert size() == size(angle_offset=180.0) == size(bottom_angle_offset=90.0) == (5.0, 3.0, 1.0)
    assert size(angle_offset=90.0) == size(angle_offset=-90.0) == size(angle_offset=270.0) == (3.0, 5.0, 1.0)
    assert size("bottom", bottom_angle_offset=90.0) == (3.0, 5.0, 1.0)
    assert size("bottom", bottom_angle_offset=90.0, angle_offset=90.0) == (5.0, 3.0, 1.0)
    assert size(angle_offset=45.0) == (5.0, 3.0, 1.0)  # not a quarter turn: left as it is
