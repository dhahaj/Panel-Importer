"""Component edits: remove, change and add components on top of the export."""

import json
from dataclasses import replace

import pytest

from panelimport.analysis import edits as E
from panelimport.analysis.pipeline import analyze, with_changes
from panelimport.cli import main
from panelimport.io.bom import read_bom
from panelimport.io.odb import OdbJob
from panelimport.model.panel import Acknowledgement, ComponentEdit, Decisions
from panelimport.model.project_file import load_project, project_from_dict
from panelimport.session import Session
from panelimport.settings import Settings
from tests.conftest import codes, issues_of, write
from tests.synthetic.odbgen import sr_panel


def _job(tmp_path, job=None):
    return OdbJob(write(job or sr_panel(n_parts=5), tmp_path))


def _apply(job, edits, a=None, settings=None, **decisions):
    """Analyse ``job`` with ``edits`` entered in ``a``'s frame (default: a fresh analysis)."""
    settings = settings or Settings()
    a = a or analyze(job, settings, Decisions(**decisions))
    return analyze(job, settings, Decisions(component_edits=edits, edit_frame=a.edit_frame, **decisions))


def _moved(a, designator, **changes):
    part = E.find_part(a, "board", designator)
    return E.edit_from_values(a, "board", designator, {**E.shown_values(a, part), **changes})


def _panel_positions(a, designator):
    p = E.find_part(a, "board", designator)
    return sorted((round(x, 5), round(y, 5), round(r, 4)) for c in a.circuits for x, y, r in [a.circuit_position(p, c)])


# ---------------------------------------------------------------- remove
def test_removed_part_is_not_placed_and_not_checked(tmp_path):
    job = _job(tmp_path)
    a = analyze(job)
    assert "no_paste" in codes(a)  # J1 is through-hole
    suggested = E.suggest_removals(a)["through-hole"]
    assert [(s.designator, s.why) for s in suggested] == [("J1", "no paste on its pads")]
    b = _apply(job, E.remove_parts([], [("board", "J1")], "through-hole"), a)
    assert "J1" not in {p.designator for p in b.placements}
    assert [p.designator for p in b.removed_placements] == ["J1"]
    assert E.status_text(b.removed_placements[0]) == "removed: through-hole"
    assert "no_paste" not in codes(b)
    project = b.to_project()
    assert "J1" not in {p.designator for p in project.placements}
    assert [(e.designator, e.removed, e.reason) for e in project.component_edits] == [("J1", True, "through-hole")]


def test_removed_fiducial_component_is_still_a_fiducial(tmp_path):
    job = _job(tmp_path)
    b = _apply(job, E.remove_parts([], [("panel", "FID2")], "mechanical"))
    assert "FID2" not in {p.designator for p in b.panel_parts}
    assert "FID2" in {f.name for f in b.fiducial_candidates if f.selectable}


def test_restore_keeps_changes_and_revert_drops_them():
    edits = [ComponentEdit("C1", part_number="D-1")]
    edits = E.remove_parts(edits, [("board", "C1"), ("board", "J1")], "not-populated", "variant B")
    assert {e.designator: (e.removed, e.part_number) for e in edits} == {"C1": (True, "D-1"), "J1": (True, None)}
    edits = E.restore_parts(edits, [("board", "C1"), ("board", "J1")])
    assert edits == [ComponentEdit("C1", part_number="D-1", note="variant B")]
    assert E.revert_parts(edits, [("board", "C1")]) == []
    added = [E.added_edit("board", "U9", {"x": 1, "y": 2, "rotation": 0, "layer": "top"})]
    assert E.revert_parts(added, [("board", "U9")]) == added  # revert keeps additions…
    assert E.remove_parts(added, [("board", "U9")], "other") == []  # …removing deletes them


# ---------------------------------------------------------------- change
def test_edited_values_reach_the_project_and_the_paste_check(tmp_path):
    job = _job(tmp_path)
    a = analyze(job)
    edit = _moved(a, "C1", part_number="D-9999", package="0603", x=25.1, rotation=0.0)
    assert (edit.part_number, edit.package, edit.x, edit.y, edit.rotation, edit.part_name) == ("D-9999", "0603", 25.1, 10.0, 0.0, None)
    b = _apply(job, [edit], a)
    c1 = E.find_part(b, "board", "C1")
    assert c1.state == "edited" and c1.part_number == "D-9999" and c1.rotation == 0.0
    assert c1.export == {"part_number": "", "package": "C0603", "x": 25.0, "y": 10.0, "rotation": 270.0}
    assert E.shown_values(b, c1, export=True)["rotation"] == 270.0
    assert E.status_text(c1) == "edited: part number, package, position, rotation"
    assert c1.paste.status == "ok"  # 0.1 mm nudge: still on its pads
    p = next(p for p in b.to_project().placements if p.designator == "C1")
    assert (p.part_number, p.package, p.x, p.y, p.rotation, p.rotation_raw) == ("D-9999", "0603", 25.1, 10.0, 0.0, 0.0)

    far = _apply(job, [_moved(a, "C1", x=25.6)], a)
    (warn,) = issues_of(far, "centroid_off_pads")
    assert warn.designator == "C1" and "0.600 mm" in warn.message


def test_edit_equal_to_the_export_is_no_edit(tmp_path):
    a = analyze(_job(tmp_path))
    assert _moved(a, "C1") is None
    assert _moved(a, "C1", x=25.0000001) is None


def test_part_number_edit_beats_the_mapping(tmp_path):
    job = _job(tmp_path)
    a = analyze(job, Settings(), Decisions(part_number_attribute="PART_NUMBER"))
    assert E.find_part(a, "board", "C1").part_number == "D-1001"
    b = _apply(job, [ComponentEdit("C1", part_number="D-7")], a, part_number_attribute="PART_NUMBER")
    c1 = E.find_part(b, "board", "C1")
    assert c1.part_number == "D-7" and c1.export == {"part_number": "D-1001"}


def test_panel_parts_get_packages_and_part_numbers(tmp_path):
    job = sr_panel(n_parts=5)
    job.steps["panel"].components[0].props["PART_NUMBER"] = "FID-STD"
    a = analyze(_job(tmp_path, job), Settings(), Decisions(part_number_attribute="PART_NUMBER"))
    fid1 = next(p for p in a.panel_parts if p.designator == "FID1")
    assert (fid1.package, fid1.part_number) == ("FID1MM", "FID-STD")
    assert next(p for p in a.to_project().panel_parts if p.designator == "FID1").part_number == "FID-STD"


# ---------------------------------------------------------------- add
def _board_with_bare_pads():
    """U5's pads are on the board but the export has no U5 component."""
    job = sr_panel(n_parts=5)
    board = job.steps["pcb"]
    board.component("U5", "SOIC8", 40.0, 12.0, rot=90)
    board.components.pop()
    return job


def test_added_part_gets_package_pins_and_is_checked(tmp_path):
    job = _job(tmp_path, _board_with_bare_pads())
    a = analyze(job)
    add = E.added_edit("board", "U5", {"package": "SOIC8", "part_number": "IC-5", "layer": "top", "x": 40.0, "y": 12.0, "rotation": 270.0})
    b = _apply(job, [add], a)
    u5 = E.find_part(b, "board", "U5")
    assert u5.state == "added" and len(u5.toeprints) == 8 and u5.body
    assert u5.paste.status == "ok"
    assert not b.errors and not b.warnings
    p = next(p for p in b.to_project().placements if p.designator == "U5")
    assert (p.part_number, p.package, p.x, p.y, p.rotation, p.layer) == ("IC-5", "SOIC8", 40.0, 12.0, 270.0, "top")
    # Elsewhere there is no paste: an added part is more likely misplaced than through-hole.
    off = _apply(job, [E.added_edit("board", "U5", {"package": "SOIC8", "layer": "top", "x": 5.0, "y": 25.0, "rotation": 0})], a)
    (warn,) = issues_of(off, "added_no_paste")
    assert warn.severity.value == "warning"
    assert [i.designator for i in issues_of(off, "no_paste")] == ["J1"]  # U5 is not "through-hole"


def test_added_part_outside_the_board_and_duplicates(tmp_path):
    job = _job(tmp_path)
    a = analyze(job)
    outside = E.added_edit("board", "U9", {"x": 60.0, "y": 10.0, "rotation": 0, "layer": "top"})
    b = _apply(job, [outside], a)
    (warn,) = issues_of(b, "outside_outline")
    assert warn.designator == "U9" and "outside the board outline" in warn.message
    clash = E.added_edit("board", "C1", {"x": 1.0, "y": 1.0, "rotation": 0, "layer": "top"})
    c = _apply(job, [clash], a)
    assert [i.designator for i in issues_of(c, "edit_conflict")] == ["C1"]
    assert not c.can_confirm()[0]
    assert len([p for p in c.placements if p.designator == "C1"]) == 1


def test_added_panel_level_fiducial_can_be_picked(tmp_path):
    job = _job(tmp_path)
    add = E.added_edit("panel", "FID4", {"package": "FID1MM", "x": 161.5, "y": 82.5, "rotation": 0, "layer": "top"})
    b = _apply(job, [add])
    assert "FID4" in {p.designator for p in b.panel_parts}
    assert "FID4" in {f.name for f in b.fiducial_candidates if f.selectable}


def test_invalid_and_orphan_edits(tmp_path):
    job = _job(tmp_path)
    b = _apply(job, [ComponentEdit("X1", removed=True, reason="other"), ComponentEdit("U8", added=True)])
    (orphan,) = issues_of(b, "edit_orphan")
    assert orphan.designator == "X1" and orphan.severity.value == "warning"
    (invalid,) = issues_of(b, "edit_invalid")
    assert invalid.designator == "U8" and "needs a side, X, Y and a rotation" in invalid.message
    half = _apply(job, [ComponentEdit("C1", x=3.0)])
    assert "needs both X and Y" in issues_of(half, "edit_invalid")[0].message


# ---------------------------------------------------------------- frames
def test_reference_change_does_not_move_edited_parts(tmp_path):
    job = sr_panel(n_parts=5)
    job.steps["pcb"].datum = (2.0, 3.0)
    job = _job(tmp_path, job)
    a = analyze(job)
    edits = [_moved(a, "C1", x=26.0, rotation=45.0), E.added_edit("board", "U9", {"x": 20.0, "y": 20.0, "rotation": 10, "layer": "top"})]
    b = _apply(job, edits, a)
    c = analyze(job, Settings(), Decisions(component_edits=edits, edit_frame=a.edit_frame, circuit_reference="board-datum"))
    assert c.reference_kind == "board-datum"
    for name in ("C1", "U9"):
        assert _panel_positions(b, name) == _panel_positions(c, name)
    converted = {e.designator: (e.x, e.y, e.rotation) for e in c.component_edits}
    assert converted == {"C1": (24.0, 7.0, 45.0), "U9": (18.0, 17.0, 10.0)}
    project = c.to_project()
    placed = {p.designator: (p.x, p.y) for p in project.placements}
    assert placed["C1"] == (24.0, 7.0) and placed["U9"] == (18.0, 17.0)


def test_panel_origin_setting_does_not_move_panel_level_edits(tmp_path):
    job = sr_panel(n_parts=5)
    job.steps["panel"].profile = [(x - 10, y - 20) for x, y in job.steps["panel"].profile]
    job = _job(tmp_path, job)
    a = analyze(job)
    edits = [E.added_edit("panel", "LBL1", {"x": 50.0, "y": 2.0, "rotation": 0, "layer": "top"})]
    b = _apply(job, edits, a)
    other = Settings(panel_origin="odb-origin")
    c = analyze(job, other, Decisions(component_edits=edits, edit_frame=a.edit_frame))
    pb = next(p for p in b.panel_parts if p.designator == "LBL1")
    pc = next(p for p in c.panel_parts if p.designator == "LBL1")
    assert (pc.x - pb.x, pc.y - pb.y) == pytest.approx((-10.0, -20.0))  # same spot, other origin
    assert (c.component_edits[0].x, c.component_edits[0].y) == (40.0, -18.0)


def test_flattened_renumbering_keeps_edits_in_place(tmp_path):
    """Circuit 1 becomes a copy rotated 180°: edited and added parts stay where they were."""
    job = sr_panel(nx=2, ny=1, n_parts=12)
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 0, 0, 1, 1)
    pan.step_repeat("pcb", 107, 41.5, 0, 0, 1, 1, angle=180)
    job.flatten("panel")
    job = _job(tmp_path, job)
    base = {"panel_step": "panel", "panel_level": ["FID1", "FID2", "FID3"]}
    a = analyze(job, Settings(), Decisions(**base))
    assert a.mode == "flattened" and not a.errors
    edits = [_moved(a, "R1", x=31.0, rotation=90.0), E.added_edit("board", "U9", {"package": "SOIC8", "x": 15.0, "y": 18.0, "rotation": 0, "layer": "top"})]
    b = _apply(job, edits, a, **base)
    c = analyze(job, Settings(), Decisions(component_edits=edits, edit_frame=a.edit_frame, numbering_first="lower-right", **base))
    assert c.circuits[0].center[0] > c.circuits[1].center[0]  # circuit 1 is now the rotated copy
    for name in ("R1", "U9"):
        assert _panel_positions(b, name) == _panel_positions(c, name)
    # Saved in the new frame, they reproduce themselves.
    again = analyze(job, Settings(), Decisions(component_edits=c.component_edits, edit_frame=c.edit_frame, numbering_first="lower-right", **base))
    assert again.component_edits == c.component_edits


def test_unrelated_frames_are_flagged(tmp_path):
    job = _job(tmp_path)
    a = analyze(job)
    frame = replace(a.edit_frame, mode="flattened")
    b = analyze(job, Settings(), Decisions(component_edits=[_moved(a, "C1", x=25.2)], edit_frame=frame))
    (warn,) = issues_of(b, "edit_frame")
    assert "C1" in warn.message
    assert E.find_part(b, "board", "C1").x == pytest.approx(25.2)


# ---------------------------------------------------------------- flattened panels
def test_flattened_removal_skips_copy_count_and_fit(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    pan = job.steps["panel"]
    copies = [c for c in pan.components if c.name == "U1"]
    copies[4].x += 0.2  # circuit 5's U1 is off: fit residual error
    r1 = [c for c in pan.components if c.name == "R1"]
    pan.components.remove(r1[2])  # R1 missing in circuit 3: copy-count error
    job = _job(tmp_path, job)
    base = {"panel_step": "panel", "panel_level": ["FID1", "FID2", "FID3"]}
    a = analyze(job, Settings(), Decisions(**base))
    assert {"fit_residual", "copy_count"} <= set(codes(a))
    b = _apply(job, E.remove_parts([], [("board", "U1"), ("board", "R1")], "not-populated"), a, **base)
    assert not b.errors
    assert {p.designator for p in b.removed_placements} == {"U1", "R1"}


def test_flattened_edited_part_is_checked_in_every_circuit(tmp_path):
    job = sr_panel()
    job.flatten("panel")
    job = _job(tmp_path, job)
    base = {"panel_step": "panel", "panel_level": ["FID1", "FID2", "FID3"]}
    a = analyze(job, Settings(), Decisions(**base))
    b = _apply(job, [_moved(a, "C1", x=25.5)], a, **base)
    warns = issues_of(b, "centroid_off_pads")
    assert sorted(i.circuit for i in warns) == [1, 2, 3, 4, 5, 6]
    assert all(i.designator == "C1" for i in warns)


# ---------------------------------------------------------------- BOM and suggestions
def test_bom_and_removals(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_text('Comment,Designator\n100n,"C1, C2"\n10k,R1\n555,U1\nhdr,J1\n', encoding="utf-8")
    job = sr_panel(n_parts=5)
    job.steps["pcb"].component("R9", "R0402", 35.0, 15.0, part="RES-DNP")
    job = _job(tmp_path, job)
    parsed = read_bom(bom)
    a = analyze(job, Settings(), Decisions(), bom=parsed)
    assert [i.designator for i in issues_of(a, "bom_not_in_bom")] == ["R9"]
    assert [s.designator for s in E.suggest_removals(a)["not-in-bom"]] == ["R9"]
    edits = E.remove_parts([], [("board", "R9")], "not-populated")
    edits = E.remove_parts(edits, [("board", "J1")], "through-hole")
    b = analyze(job, Settings(), Decisions(component_edits=edits, edit_frame=a.edit_frame), bom=parsed)
    assert not issues_of(b, "bom_not_in_bom") and not issues_of(b, "bom_not_in_odb")
    # Removing a BOM part as "not populated" contradicts the BOM.
    edits = E.remove_parts(edits, [("board", "C1")], "not-populated")
    c = analyze(job, Settings(), Decisions(component_edits=edits, edit_frame=a.edit_frame), bom=parsed)
    assert [i.designator for i in issues_of(c, "bom_removed")] == ["C1"]


def test_suggestions_from_attributes(tmp_path):
    job = sr_panel(n_parts=5)
    board = job.steps["pcb"]
    board.component("J7", "C0603", 35.0, 15.0, attrs={".comp_mount_type": "thmt"})
    board.component("R8", "R0402", 35.0, 20.0, props={"DNP": "True"})
    board.component("R9", "R0402", 35.0, 6.0, attrs={".no_pop": True})
    board.component("C9", "C0603", 44.0, 6.0, props={"Comment": "Not Fitted"})
    a = analyze(_job(tmp_path, job))
    s = {k: {x.designator: x.why for x in v} for k, v in E.suggest_removals(a).items()}
    assert s["through-hole"] == {"J1": "no paste on its pads", "J7": ".comp_mount_type = thmt"}
    assert s["not-populated"] == {"R8": "DNP = True", "R9": ".no_pop = YES", "C9": "Comment = Not Fitted"}
    assert set(s["mechanical"]) == {"FID1", "FID2", "FID3"}
    assert s["not-in-bom"] == {}


# ---------------------------------------------------------------- project file
def _saved_with_edits(tmp_path):
    src = _board_with_bare_pads().write_tgz(tmp_path / "Panel_ODB.tgz")
    s = Session()
    s.open_source(src)
    a = s.analysis
    edits = E.remove_parts([], [("board", "J1"), ("panel", "FID3")], "through-hole", "hand soldered")
    edits = E.set_edits(edits, [_moved(a, "C1", part_number="D-1", x=25.05)])
    edits = E.set_edits(edits, [E.added_edit("board", "U5", {"package": "SOIC8", "layer": "top", "x": 40.0, "y": 12.0, "rotation": 270.0})])
    s.update(component_edits=edits, edit_frame=a.edit_frame)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings])
    s.update(confirmed=True)
    s.update(fiducials=["FID1", "FID2"])
    path = tmp_path / "Panel_ODB.panel.json"
    return s, s.save(path), path


def test_edits_save_and_reopen_identically(tmp_path):
    _s, saved, path = _saved_with_edits(tmp_path)
    data = json.loads(path.read_text())
    assert data["component_edits"] == [
        {"designator": "C1", "level": "board", "part_number": "D-1", "x": 25.05, "y": 10.0},
        {"designator": "J1", "level": "board", "removed": True, "reason": "through-hole", "note": "hand soldered"},
        {"designator": "U5", "level": "board", "added": True, "part_name": "", "part_number": "", "package": "SOIC8", "layer": "top", "x": 40.0, "y": 12.0, "rotation": 270.0},
        {"designator": "FID3", "level": "panel", "removed": True, "reason": "through-hole", "note": "hand soldered"},
    ]
    s2 = Session()
    result = s2.open_project(path)
    assert result.differences == [] and s2.analysis.confirmed
    assert s2.analysis.to_project(path) == saved
    first = path.read_text()
    s2.save(path)
    assert path.read_text() == first


def test_edits_keep_the_confirmation(tmp_path):
    s, _saved, _path = _saved_with_edits(tmp_path)
    d = with_changes(s.decisions, component_edits=E.remove_parts(s.decisions.component_edits, [("board", "R1")], "other"))
    assert d.confirmed
    assert not with_changes(s.decisions, numbering_first="upper-left").confirmed


def test_version_1_project_still_loads(tmp_path):
    _s, _saved, path = _saved_with_edits(tmp_path)
    data = json.loads(path.read_text())
    data["version"] = 1
    data.pop("component_edits")
    for p in data["panel_parts"]:
        p.pop("part_number")
    project = project_from_dict(data)
    assert project.version == 1 and project.component_edits == []


def test_verify_lists_the_edits(tmp_path, capsys):
    _s, _saved, path = _saved_with_edits(tmp_path)
    assert main(["verify", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Edits:   2 removed (J1 through-hole, FID3 (panel) through-hole); 1 added (U5); 1 edited (C1)" in out
    assert load_project(path).component_edits


def test_edits_survive_an_analysis_that_stops_early(tmp_path):
    job = _job(tmp_path)
    edits = E.remove_parts([], [("board", "J1")], "through-hole")
    a = analyze(job, Settings(), Decisions(component_edits=edits, board_step="panel"))
    assert "no_board_instances" in codes(a) and not a.placements
    assert a.component_edits == edits
