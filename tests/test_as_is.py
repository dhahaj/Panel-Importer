"""As-is mode: a panel without STEP-REPEAT placed as it is, the whole panel one circuit.

The panel (``tests/synthetic/panel_types.flat_job``) is one step with its parts placed
directly in it; every position is worked out by hand in ``FLAT``.
"""

from __future__ import annotations

from panelimport.analysis.pipeline import analyze, decisions_from_project
from panelimport.analysis.transforms import angle_diff
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.reader import read_iss_bytes
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import encode, render
from panelimport.model.panel import Acknowledgement, Decisions
from panelimport.session import Session
from panelimport.settings import Settings
from tests.synthetic.panel_types import FIDS, FLAT, FLAT_DUPLICATE, FLAT_SIZE, flat_job, irregular_job
from tests.synthetic.projects import machine_angle


def _analyze(tmp_path, side: str = "top", duplicate: bool = False, **decisions):
    src = flat_job(side, duplicate).write_folder(tmp_path / f"{side}{'-dup' if duplicate else ''}")
    decisions.setdefault("as_is", True)
    return analyze(
        OdbJob(src),
        Settings(part_number_attribute="PART_NUMBER"),
        Decisions(fiducials=list(FIDS), confirmed=True, **decisions),
    )


def _positions(a) -> dict[str, tuple[float, float, float]]:
    (c,) = a.circuits
    return {p.designator: tuple(round(v, 6) for v in a.circuit_position(p, c)) for p in a.placements}


def program_of(project, settings: IssSettings):
    prepared = prepare(project, settings, pwb_id="T")
    assert prepared.can_write, [i.format() for i in prepared.errors]
    return prepared, read_iss_bytes(encode(render(prepared.layout, settings)))


# -------------------------------------------------------------------- Phase 1
def test_flat_panel_asks_unless_as_is_is_chosen(tmp_path):
    a = _analyze(tmp_path, as_is=False)
    assert a.mode == "single-board" and [i.code for i in a.errors] == ["single_board"]


def test_whole_panel_is_one_circuit(tmp_path):
    a = _analyze(tmp_path)
    assert a.mode == "as-is" and not a.errors, [i.format() for i in a.errors]
    (c,) = a.circuits
    assert (c.index, c.dx, c.dy, c.rotation, c.mirror) == (1, 0.0, 0.0, 0.0, False)
    assert sorted((round(x, 6), round(y, 6)) for x, y in c.outline) == [(0, 0), (0, 60), (120, 0), (120, 60)]
    assert _positions(a) == FLAT
    # Fiducial components are panel parts and panel fiducials, never placements.
    assert sorted(p.designator for p in a.panel_parts) == FIDS
    assert [f.name for f in a.fiducials] == FIDS
    assert "as_is" in [i.code for i in a.issues]


def test_repeated_designators_are_numbered(tmp_path):
    a = _analyze(tmp_path, duplicate=True)
    assert not a.errors, [i.format() for i in a.errors]
    assert _positions(a) == FLAT_DUPLICATE
    assert {p.designator: p.written for p in a.placements}["U1_2"] == "U1"


def test_as_is_needs_a_panel_without_step_repeat(tmp_path):
    a = analyze(OdbJob(irregular_job().write_folder(tmp_path)), Settings(), Decisions(as_is=True))
    assert a.mode == "panel" and "as_is_ignored" in [i.code for i in a.warnings]


def test_reopen_keeps_as_is(tmp_path):
    src = flat_job().write_tgz(tmp_path / "Flat.tgz")
    s = Session()
    s.open_source(src, Decisions(as_is=True))
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings])
    s.update(confirmed=True)
    s.update(fiducials=list(FIDS), part_number_attribute="PART_NUMBER")
    path = tmp_path / "Flat.panel.json"
    saved = s.save(path)
    assert saved.mode == "as-is" and decisions_from_project(saved).as_is
    s2 = Session()
    result = s2.open_project(path)
    assert result.source_issue is None and result.differences == []
    assert s2.analysis.confirmed and s2.analysis.to_project(path) == saved


# -------------------------------------------------------------------- Phase 2
def test_written_as_one_circuit_by_hand(tmp_path):
    """Top side, 120 × 60 landscape: one allocation; P is the panel's lower-left corner, so
    each placement is its panel position under its own name."""
    prepared, prog = program_of(_analyze(tmp_path).to_project(), IssSettings())
    assert prepared.layout.output == "circuits" and prepared.layout.origin == (0.0, 0.0)
    assert [(c.number, c.x, c.y, c.angle) for c in prog.circuits] == [(1, 0, 0, 0)]
    assert (prog.circuit_width, prog.circuit_height) == FLAT_SIZE
    assert {p.designator: (p.x, p.y, p.angle) for p in prog.placements} == FLAT
    assert [(f.x, f.y) for f in prog.fiducials] == [(2.5, 2.5), (117.5, 2.5), (2.5, 57.5)]


def test_duplicates_written_by_hand(tmp_path):
    _prepared, prog = program_of(_analyze(tmp_path, duplicate=True).to_project(), IssSettings())
    assert {p.designator: (p.x, p.y, p.angle) for p in prog.placements} == FLAT_DUPLICATE


def test_bottom_written_by_hand(tmp_path):
    """Parts on the bottom, turned over left-right: x → 120 − x, θ → 180° − θ."""
    prepared, prog = program_of(_analyze(tmp_path, "bottom").to_project(), IssSettings())
    m = prepared.layout.machine
    assert (m.side, m.flip, m.rotation) == ("bottom", "left-right", 0)
    got = {p.designator: p for p in prog.placements}
    assert set(got) == set(FLAT)
    for name, (x, y, angle) in FLAT.items():
        assert (got[name].x, got[name].y) == (FLAT_SIZE[0] - x, y), name
        assert angle_diff(got[name].angle, machine_angle(angle, "left-right", 0)) <= 1e-3, name
