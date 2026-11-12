"""Panels that repeat more than one design: each circuit places its own design's parts.

The panel (``tests/synthetic/panel_types.mixed_job``) holds two copies of a main board and
two of a smaller design that shares the designator U1, one of them turned 90°.  Every
position is worked out by hand in ``MIXED``.
"""

from __future__ import annotations

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.analysis.transforms import angle_diff
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.reader import read_iss_bytes
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import encode, render
from panelimport.model.panel import Acknowledgement, ComponentEdit, Decisions
from panelimport.model.project_file import load_project, save_project
from panelimport.session import Session
from panelimport.settings import Settings
from tests.synthetic.panel_types import FIDS, MIXED, MIXED_SIZE, mixed_job
from tests.synthetic.projects import machine_angle


def _analyze(tmp_path, side: str = "top", **decisions):
    src = mixed_job(side).write_folder(tmp_path / side)
    return analyze(
        OdbJob(src),
        Settings(part_number_attribute="PART_NUMBER"),
        Decisions(fiducials=list(FIDS), confirmed=True, **decisions),
    )


def _positions(a) -> dict[str, tuple[float, float, float]]:
    """Every placement of every circuit, named like the flattened program."""
    got = {}
    for p in a.placements:
        for c in a.circuits_of(p):
            x, y, r = a.circuit_position(p, c)
            got[f"{p.designator.split('/', 1)[1]}_{c.index}"] = (round(x, 6), round(y, 6), round(r, 6) % 360)
    return got


def program_of(project, settings: IssSettings):
    prepared = prepare(project, settings, pwb_id="T")
    assert prepared.can_write, [i.format() for i in prepared.errors]
    return prepared, read_iss_bytes(encode(render(prepared.layout, settings)))


# -------------------------------------------------------------------- Phase 1
def test_both_designs_found(tmp_path):
    a = _analyze(tmp_path)
    assert a.mode == "panel" and not a.errors, [i.format() for i in a.errors]
    assert a.board_step is None
    assert [d.step for d in a.designs] == ["MAIN", "AUX"]
    assert [c.design for c in a.circuits] == ["MAIN", "MAIN", "AUX", "AUX"]
    assert sorted(p.designator for p in a.placements) == ["AUX/R1", "AUX/U1", "MAIN/C1", "MAIN/U1"]
    assert {p.design for p in a.placements} == {"MAIN", "AUX"}
    assert sorted(p.designator for p in a.panel_parts) == FIDS
    assert _positions(a) == MIXED
    assert any(i.code == "mixed_designs" for i in a.issues)


def test_project_keeps_each_design_frame(tmp_path):
    """Placements are relative to their own design's reference point (the lower-left of its
    profile): main (−8, −6), aux (−2, −1).  Circuit offsets are those points' positions
    relative to circuit 1's: main at (3, 3) and (63, 3); aux at (147, 13), and turned at
    (150, 50) + (−3, −2) turned clockwise = (148, 53)."""
    project = _analyze(tmp_path).to_project()
    assert [(d.name, d.board_x, d.board_y) for d in project.designs] == [("MAIN", -8.0, -6.0), ("AUX", -2.0, -1.0)]
    assert [len(d.outline) for d in project.designs] == [4, 4]
    ref = project.circuit_reference
    assert (ref.x, ref.y, ref.board_x, ref.board_y) == (3.0, 3.0, -8.0, -6.0)
    assert [(c.index, c.design, c.dx, c.dy, c.rotation) for c in project.circuits] == [
        (1, "MAIN", 0.0, 0.0, 0.0),
        (2, "MAIN", 60.0, 0.0, 0.0),
        (3, "AUX", 144.0, 10.0, 0.0),
        (4, "AUX", 145.0, 50.0, 270.0),
    ]
    assert {p.designator: (p.design, p.x, p.y) for p in project.placements} == {
        "MAIN/U1": ("MAIN", 15.0, 18.0),
        "MAIN/C1": ("MAIN", 25.0, 10.0),
        "AUX/U1": ("AUX", 5.0, 5.0),
        "AUX/R1": ("AUX", 10.0, 3.0),
    }
    path = save_project(project, tmp_path / "mixed.panel.json")
    assert load_project(path) == project


def test_one_design_chosen_keeps_the_others_off_the_circuits(tmp_path):
    """Choosing a board step is the way back to one design: the other design's parts are
    then placed once each, at panel level, as before."""
    a = _analyze(tmp_path, panel_step="PANEL", board_step="MAIN")
    assert a.board_step == "MAIN" and not a.designs
    assert len(a.circuits) == 2 and {c.design for c in a.circuits} == {""}
    assert sorted(p.designator for p in a.placements) == ["C1", "U1"]
    assert sorted(p.designator for p in a.panel_parts) == sorted([*FIDS, "R1", "R1", "U1", "U1"])


def test_edits_name_their_design(tmp_path):
    """An added part goes into its own design's circuits only: C9 at (12, 8) from aux's
    reference is (10, 7) on aux, (9, 6) from its datum: (159, 21) at 0° in circuit 3 and
    (150, 50) + (6, −9) = (156, 41) at 270° in circuit 4."""
    added = ComponentEdit(
        "AUX/C9", added=True, part_name="CAP", part_number="D-2", package="C0603", layer="top", x=12.0, y=8.0, rotation=0.0
    )
    removed = ComponentEdit("MAIN/C1", removed=True, reason="not-populated")
    a = _analyze(tmp_path, component_edits=[added, removed])
    assert not a.errors, [i.format() for i in a.errors]
    expected = {k: v for k, v in MIXED.items() if not k.startswith("C1_")}
    expected.update({"C9_3": (159.0, 21.0, 0.0), "C9_4": (156.0, 41.0, 270.0)})
    assert _positions(a) == expected


def test_added_part_without_its_design_is_refused(tmp_path):
    edit = ComponentEdit("C9", added=True, package="C0603", layer="top", x=12.0, y=8.0, rotation=0.0)
    a = _analyze(tmp_path, component_edits=[edit])
    assert [i.code for i in a.errors] == ["edit_invalid"]
    assert "MAIN/C9 or AUX/C9" in a.errors[0].message


def _saved(tmp_path):
    src = mixed_job().write_tgz(tmp_path / "Mixed.tgz")
    s = Session()
    s.open_source(src)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings])
    s.update(confirmed=True)
    s.update(fiducials=list(FIDS), part_number_attribute="PART_NUMBER")
    path = tmp_path / "Mixed.panel.json"
    return s, src, path, s.save(path)


def test_reopen_finds_the_same_designs(tmp_path):
    """The project stores no board step, so reopening detects both designs again."""
    _s, _src, path, saved = _saved(tmp_path)
    assert saved.source.board_step is None and saved.version == 4
    s2 = Session()
    result = s2.open_project(path)
    assert result.source_issue is None and result.differences == []
    assert s2.analysis.confirmed and s2.analysis.to_project(path) == saved


def test_missing_source_shows_each_design_in_its_circuits(tmp_path):
    s, src, path, _saved_project = _saved(tmp_path)
    src.unlink()
    s2 = Session()
    assert s2.open_project(path).source_issue.code == "source_missing"
    snap = s2.analysis
    assert [d.step for d in snap.designs] == ["MAIN", "AUX"]
    assert _positions(snap) == _positions(s.analysis)
    for live, shown in zip(s.analysis.circuits, snap.circuits):
        assert shown.design == live.design
        key = lambda pts: sorted((round(x, 4), round(y, 4)) for x, y in pts)  # noqa: E731
        assert key(shown.outline) == key(live.outline)


# -------------------------------------------------------------------- Phase 2
def test_mixed_panel_flattened_by_hand(tmp_path):
    """Top side, 200 × 80 landscape: the program frame is the panel frame."""
    prepared, prog = program_of(_analyze(tmp_path).to_project(), IssSettings())
    assert prepared.layout.output == "flatten"
    assert prepared.layout.output_reason == "2 designs: MAIN in circuits 1, 2; AUX in circuits 3, 4"
    assert {p.designator: (p.x, p.y, p.angle) for p in prog.placements} == MIXED
    assert sorted(c.name for c in prog.components) == ["D-1", "D-2", "D-3", "D-5"]


def test_mixed_bottom_panel_flattened_by_hand(tmp_path):
    """The same panel with its parts on the bottom, turned over left-right: x → 200 − x,
    θ → 180° − θ."""
    project = _analyze(tmp_path, "bottom").to_project()
    prepared, prog = program_of(project, IssSettings())
    m = prepared.layout.machine
    assert (m.side, m.flip, m.rotation) == ("bottom", "left-right", 0)
    got = {p.designator: p for p in prog.placements}
    assert set(got) == set(MIXED)
    for name, (x, y, angle) in MIXED.items():
        assert (got[name].x, got[name].y) == (MIXED_SIZE[0] - x, y), name
        assert angle_diff(got[name].angle, machine_angle(angle, "left-right", 0)) <= 1e-3, name


@pytest.mark.parametrize("output", ["circuits", "auto"])
def test_mixed_panel_is_never_written_per_circuit(tmp_path, output):
    project = _analyze(tmp_path).to_project()
    prepared = prepare(project, IssSettings(circuit_output=output), pwb_id="T")
    if output == "auto":
        assert prepared.can_write and prepared.layout.output == "flatten"
        return
    assert not prepared.can_write
    assert "mixed_designs" in [i.code for i in prepared.errors]
