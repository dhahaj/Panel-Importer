"""Phase 2 frame: project → ISS → reader → panel positions, and the bottom flip by hand.

The round trips compare against positions computed independently of
``panelimport.iss.mapping`` (plain geometry in ``tests/synthetic/projects.py``, or
Phase 1's own ``circuit_position``), so a mapping error cannot cancel itself out.
"""

from __future__ import annotations

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.analysis.transforms import angle_diff
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.compare import panel_geometry
from panelimport.iss.mapping import build_layout
from panelimport.iss.reader import read_iss_bytes
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import encode, render
from panelimport.model.panel import Decisions
from panelimport.settings import CORNERS, REFERENCE_KINDS, Settings
from tests.synthetic.odbgen import Job
from tests.synthetic.projects import machine_angle, machine_point, make_project, truth_position

TOL = 1e-4 + 1e-9  # mm per axis: two 4-decimal roundings (allocation + position)
ANGLE_TOL = 1e-3


def written(project, settings: IssSettings):
    prepared = prepare(project, settings, pwb_id="T")
    assert prepared.layout is not None, [i.format() for i in prepared.issues]
    return prepared, read_iss_bytes(encode(render(prepared.layout, settings)))


def assert_round_trip(project, settings: IssSettings, flip, rotation, truth=None) -> None:
    """Every part in every circuit, every fiducial and the panel size land where plain
    geometry puts them on the machine's panel, and back where the project has them."""
    prepared, program = written(project, settings)
    layout = prepared.layout
    assert (layout.machine.flip, layout.machine.rotation) == (flip, rotation)
    w, h = project.panel.width, project.panel.height
    size = (h, w) if rotation in (90, 270) else (w, h)
    assert (program.width, program.height) == pytest.approx(size, abs=TOL)
    assert program.clamp_offset == pytest.approx(size[1] / 2, abs=TOL)
    geom = panel_geometry(program)
    got = {(p.circuit, p.designator): p for p in geom.placements}
    undo = layout.machine.transform.inverse()
    truth = truth or (lambda k, p: truth_position(project, k, p))
    assert len(layout.circuit_numbers) == len(project.circuits)
    for prog_k, proj_k in enumerate(layout.circuit_numbers, start=1):
        for p in project.placements:
            x, y, a = truth(proj_k, p)
            mx, my = machine_point(x, y, w, h, flip, rotation)
            g = got[(prog_k, p.designator)]
            assert abs(g.x - mx) <= TOL and abs(g.y - my) <= TOL, (proj_k, p.designator, (g.x, g.y), (mx, my))
            assert angle_diff(g.angle, machine_angle(a, flip, rotation)) <= ANGLE_TOL, (proj_k, p.designator)
            ux, uy = undo.apply(g.x, g.y)  # undo the machine transform: back on the project's panel
            assert abs(ux - x) <= TOL and abs(uy - y) <= TOL
    side = layout.machine.side
    expected = sorted(machine_point(f.x, f.y, w, h, flip, rotation) for f in project.fiducials if f.layer == side)
    marks = sorted((x, y) for _n, x, y in geom.fiducials)
    assert len(marks) == len(expected)
    for (gx, gy), (ex, ey) in zip(marks, expected):
        assert abs(gx - ex) <= TOL and abs(gy - ey) <= TOL


# -------------------------------------------------------------------- synthetic projects
GRID = [(5.0, 5.0), (50.0, 5.0), (5.0, 60.0), (50.0, 60.0)]  # circuit outline lower-lefts, 2 × 2
OUTLINES = {  # circuit outline relative to the reference point, per reference kind
    "profile-lower-left": (0.0, 0.0, 40.0, 50.0),
    "board-origin": (-12.0, -7.0, 28.0, 43.0),
    "board-datum": (-40.0, -50.0, 0.0, 0.0),
}
FIRST = {"lower-left": 0, "lower-right": 1, "upper-left": 2, "upper-right": 3}


@pytest.mark.parametrize("rotation", [0, "auto"])
@pytest.mark.parametrize("first", CORNERS)
@pytest.mark.parametrize("kind", REFERENCE_KINDS)
def test_round_trip_reference_kinds_and_corners(kind, first, rotation):
    ox, oy, _, _ = OUTLINES[kind]
    order = [FIRST[first]] + [i for i in range(4) if i != FIRST[first]]
    lls = [GRID[i] for i in order]
    ref = (lls[0][0] - ox, lls[0][1] - oy)
    circuits = [(x - lls[0][0], y - lls[0][1], 0.0) for x, y in lls]
    parts = [("R1", ox + 10.0, oy + 20.0, 30.0, "P-1"), ("C1", ox + 35.5, oy + 2.25, 90.0, "P-2")]
    project = make_project(width=100, height=120, ref=ref, kind=kind, outline=OUTLINES[kind], circuits=circuits, parts=parts)
    assert_round_trip(project, IssSettings(panel_rotation=rotation), None, 90 if rotation == "auto" else 0)


def test_round_trip_non_uniform_grid():
    circuits = [(0.0, 0.0, 0.0), (45.123, 0.2, 0.0), (0.05, 55.5, 0.0), (44.9, 55.31, 0.0), (90.0007, 1.0, 0.0)]
    project = make_project(width=150, height=120, circuits=circuits)
    assert_round_trip(project, IssSettings(), None, 0)
    assert build_layout(project, IssSettings(), "T").matrix is None  # not a grid: NONMATRIX only


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_round_trip_panel_rotation(rotation):
    assert_round_trip(make_project(), IssSettings(panel_rotation=rotation), None, rotation)


@pytest.mark.parametrize("ref_rotation", [90.0, 30.0, 270.0])
def test_round_trip_rotated_circuit_1(ref_rotation):
    project = make_project(width=200, height=200, ref=(80.0, 60.0), ref_rotation=ref_rotation, circuits=[(0, 0, 0), (0, 70.0, 0)])
    assert_round_trip(project, IssSettings(panel_rotation=0), None, 0)
    prepared, program = written(project, IssSettings(panel_rotation=0))
    assert [c.angle for c in program.circuits] == [0.0, 0.0]  # circuit 1's rotation is in the positions
    assert not any(i.code == "rotated_circuit" for i in prepared.issues)


@pytest.mark.parametrize("flip", ["left-right", "front-back"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270, "auto"])
def test_round_trip_bottom(flip, rotation):
    project = make_project(layer="bottom")
    settings = IssSettings(bottom_flip=flip, panel_rotation=rotation)
    assert_round_trip(project, settings, flip, 0 if rotation == "auto" else rotation)  # 100 × 70: landscape


@pytest.mark.parametrize("flip", [None, "left-right", "front-back"])
def test_round_trip_bottom_portrait_auto(flip):
    layer = "top" if flip is None else "bottom"
    project = make_project(width=70, height=100, circuits=[(0, 0, 0), (0, 52.0, 0)], layer=layer, outline=(0, 0, 50, 40))
    assert_round_trip(project, IssSettings(bottom_flip=flip or "left-right"), flip, 90)


@pytest.mark.parametrize("layer", ["top", "bottom"])
@pytest.mark.parametrize("rotation", [90.0, 180.0])
def test_round_trip_rotated_allocation(layer, rotation):
    """A circuit rotated relative to circuit 1 turns about its allocation point."""
    project = make_project(width=150, height=150, ref=(20.0, 20.0), circuits=[(0, 0, 0), (100.0, 100.0, rotation)], layer=layer)
    flip = "left-right" if layer == "bottom" else None
    assert_round_trip(project, IssSettings(panel_rotation=0), flip, 0)
    prepared, program = written(project, IssSettings(panel_rotation=0))
    assert program.circuits[1].angle == (360.0 - rotation) % 360.0 if flip else rotation  # a mirror reverses turns
    assert [i.circuit for i in prepared.issues if i.code == "rotated_circuit"] == [2]


def test_round_trip_matrix_layout_rebases_p():
    """MATRIX lists circuits in grid order from the grid's lower-left, which on a turned
    bottom panel is not circuit 1; panel positions must not change."""
    circuits = [(0, 0, 0), (45.0, 0, 0), (0, 55.0, 0), (45.0, 55.0, 0)]
    project = make_project(width=100, height=120, circuits=circuits, layer="bottom")
    settings = IssSettings(circuit_layout="matrix")
    assert_round_trip(project, settings, "left-right", 90)
    prepared, program = written(project, settings)
    assert program.circuit_layout == "MATRIX" and prepared.layout.matrix == (2, 2, 55.0, 45.0)
    # (u, v) = (120 − y, 100 − x): circuit 4 lands lower-left, 2 lower-right, 3 upper-left, 1 upper-right.
    assert prepared.layout.circuit_numbers == [4, 2, 3, 1]
    assert [(c.x, c.y) for c in program.circuits] == [(0, 0), (55.0, 0), (0, 45.0), (55.0, 45.0)]


# -------------------------------------------------------------------- Phase 1 pipeline
def _pipeline_project(tmp_path, first: str, kind: str, side: str = "top"):
    """A 3 × 2 step-repeat panel whose board step has profile ≠ origin ≠ datum, through
    Phase 1's analysis.  Returns the project and Phase 1's own panel positions."""
    job = Job()
    board = job.step("pcb", 50.0, 36.5, x0=-8.0, y0=-6.0, datum=(4.0, 3.0))
    board.component("U1", "SOIC8", 7.0, 12.0, rot=0, side=side, part="IC-555", props={"PART_NUMBER": "D-1"})
    board.component("C1", "C0603", 17.0, 4.0, rot=90, side=side, part="CAP", props={"PART_NUMBER": "D-2"})
    board.component("R1", "R0402", 22.0, 19.0, rot=45, side=side, part="RES", props={"PART_NUMBER": "D-3"})
    panel = job.step("panel", 164.0, 85.0)
    panel.step_repeat("pcb", 17.0, 14.0, 52.0, 38.5, 3, 2)
    for i, (x, y) in enumerate([(2.5, 2.5), (161.5, 2.5), (2.5, 82.5)], start=1):
        panel.component(f"FID{i}", "FID1MM", x, y, side=side, part="FIDUCIAL")
    src = job.write_folder(tmp_path / f"{first}-{kind}-{side}")
    decisions = Decisions(
        numbering_first=first, circuit_reference=kind, fiducials=["FID1", "FID2", "FID3"], confirmed=True
    )
    a = analyze(OdbJob(src), Settings(part_number_attribute="PART_NUMBER"), decisions)
    project = a.to_project()
    assert len(project.circuits) == 6 and project.circuit_reference.kind == kind
    info = {p.designator: p for p in a.placements}
    circuits = {c.index: c for c in a.circuits}

    def truth(k, p):
        return a.circuit_position(info[p.designator], circuits[k])

    return project, truth


@pytest.mark.parametrize("first", CORNERS)
@pytest.mark.parametrize("kind", REFERENCE_KINDS)
def test_round_trip_through_phase1(tmp_path, first, kind):
    project, truth = _pipeline_project(tmp_path, first, kind)
    assert_round_trip(project, IssSettings(), None, 0, truth)


@pytest.mark.parametrize("flip", ["left-right", "front-back"])
def test_round_trip_through_phase1_bottom(tmp_path, flip):
    project, truth = _pipeline_project(tmp_path, "lower-left", "profile-lower-left", side="bottom")
    assert {p.layer for p in project.placements} == {"bottom"}
    assert_round_trip(project, IssSettings(bottom_flip=flip, panel_rotation=90), flip, 90, truth)


# -------------------------------------------------------------------- by hand
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


def _program(project, settings):
    prepared = prepare(project, settings, pwb_id="T")
    assert not prepared.errors, [i.format() for i in prepared.errors]
    return prepared.layout.program


def test_bottom_by_hand_left_right():
    """Panel 100 × 70, circuit 1 at (5, 5) (40 × 50), circuit 2 45 mm to its right; R1 at
    (10, 20) in the circuit, 30°.  Turned over left-right (x → 100 − x), not rotated:
    circuit 1 spans x 55..95, so P = (55, 5); R1 at panel (15, 25) → (85, 25), i.e.
    (30, 20) from P; circuit 2 lies to the left: allocation (−45, 0); 30° → 150°."""
    prog = _program(_two_circuits_bottom(100, 70, [(0, 0, 0), (45.0, 0, 0)], (0, 0, 40, 50)), IssSettings())
    assert (prog.width, prog.height, prog.clamp_offset) == (100, 70, 35)
    assert prog.pwb_layout_offset == (45, -5)  # lower-right (100, 0) − P (55, 5)
    assert prog.circuit_layout_offset == (0, 0)
    assert (prog.circuit_width, prog.circuit_height) == (40, 50)
    assert [(c.x, c.y, c.angle) for c in prog.circuits] == [(0, 0, 0), (-45, 0, 0)]
    r1 = prog.placements[0]
    assert (r1.x, r1.y, r1.angle) == (30, 20, 150)
    # Fiducials (2, 2), (98, 2), (2, 68) → (98, 2), (2, 2), (98, 68), minus P.
    assert [(f.x, f.y) for f in prog.fiducials] == [(43, -3), (-53, -3), (43, 63)]


def test_bottom_by_hand_front_back():
    """The same panel turned over front-back (y → 70 − y): circuit 1 spans y 15..65, so
    P = (5, 15); R1 → (15, 45), i.e. (10, 30) from P; circuit 2 stays to the right:
    allocation (+45, 0); 30° → −30° = 330°."""
    prog = _program(
        _two_circuits_bottom(100, 70, [(0, 0, 0), (45.0, 0, 0)], (0, 0, 40, 50)), IssSettings(bottom_flip="front-back")
    )
    assert (prog.width, prog.height, prog.clamp_offset) == (100, 70, 35)
    assert prog.pwb_layout_offset == (95, -15)
    assert [(c.x, c.y, c.angle) for c in prog.circuits] == [(0, 0, 0), (45, 0, 0)]
    r1 = prog.placements[0]
    assert (r1.x, r1.y, r1.angle) == (10, 30, 330)
    # (2, 2), (98, 2), (2, 68) → (2, 68), (98, 68), (2, 2), minus P.
    assert [(f.x, f.y) for f in prog.fiducials] == [(-3, 53), (93, 53), (-3, -13)]


def test_bottom_by_hand_left_right_then_auto_rotation():
    """Portrait panel 70 × 100 (circuits 50 × 40, circuit 2 52 mm above circuit 1):
    left-right flip, then 90° CCW, i.e. program (u, v) = (100 − y, 70 − x), the ER pilot's
    transform.  Circuit 1 (x 5..55, y 5..45) → u 55..95, v 15..65: P = (55, 15).
    R1 at (15, 25) → (75, 55) = P + (20, 40); circuit 2 (y 57..97) → u 3..43: allocation
    (−52, 0); 30° → 180° − 30° + 90° = 240°."""
    prog = _program(_two_circuits_bottom(70, 100, [(0, 0, 0), (0, 52.0, 0)], (0, 0, 50, 40)), IssSettings())
    assert (prog.width, prog.height, prog.clamp_offset) == (100, 70, 35)
    assert (prog.circuit_width, prog.circuit_height) == (40, 50)
    assert prog.pwb_layout_offset == (45, -15)
    assert [(c.x, c.y, c.angle) for c in prog.circuits] == [(0, 0, 0), (-52, 0, 0)]
    r1 = prog.placements[0]
    assert (r1.x, r1.y, r1.angle) == (20, 40, 240)
    # (2, 2) → (98, 68) → mark (43, 53)
    assert (prog.fiducials[0].x, prog.fiducials[0].y) == (43, 53)


# -------------------------------------------------------------------- angles and names
def test_angle_settings():
    project = make_project(parts=[("R1", 10.0, 20.0, 30.0, "P-1")])
    assert _program(project, IssSettings()).placements[0].angle == 30
    assert _program(project, IssSettings(angle_direction="cw")).placements[0].angle == 330
    assert _program(project, IssSettings(angle_offset=-45)).placements[0].angle == 345
    assert _program(project, IssSettings(angle_direction="cw", angle_offset=10)).placements[0].angle == 340
    bottom = make_project(parts=[("R1", 10.0, 20.0, 30.0, "P-1")], layer="bottom")
    assert _program(bottom, IssSettings(bottom_angle_offset=90)).placements[0].angle == 240  # 150 + 90
    assert _program(project, IssSettings(bottom_angle_offset=90)).placements[0].angle == 30  # top: not applied


def test_components_in_first_use_order_with_comments():
    parts = [("R1", 1, 1, 0, "B-2"), ("R2", 2, 2, 0, "A-1"), ("R3", 3, 3, 0, "B-2"), ("R4", 4, 4, 0, "")]
    project = make_project(parts=parts)
    project.placements[3].part_name = "FALLBACK"
    project.placements[1].attributes = {"Description": "from Description", "Comment": "later"}
    project.placements[0].attributes = {}
    project.placements[3].attributes = {}
    prog = _program(project, IssSettings())
    assert [c.name for c in prog.components] == ["B-2", "A-1", "FALLBACK"]
    assert [c.comment for c in prog.components] == ["NAME-R1", "from Description", "FALLBACK"]
    assert [p.component for p in prog.placements] == ["B-2", "A-1", "B-2", "FALLBACK"]
    prog = _program(project, IssSettings(comment_attributes=["Comment"]))
    assert prog.components[1].comment == "later"


def test_fiducial_names():
    project = make_project()
    project.fiducials[1].name = "F(6.351,12.703)"
    prog = _program(project, IssSettings())
    assert [f.name for f in prog.fiducials] == ["FID1", "F2", "FID3"]
