"""Circuit-instance transform math, checked against coordinates worked out by hand.

A STEP-REPEAT copy turns its step clockwise about the step's datum, mirrors X when
MIRROR is set (after rotating), then moves the datum to (X + i·DX, Y + j·DY).  Nested
copies compose.  Phase 2 then applies the machine transform (bottom flip, panel
rotation, shift) after the circuit's own transform.
"""

from __future__ import annotations

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.analysis.step_repeat import expand, local_transform
from panelimport.io.odb import OdbJob
from panelimport.io.odb.stephdr import StepRepeat
from panelimport.iss.mapping import circuit_transforms, direction_angle, machine_transform
from panelimport.iss.settings import IssSettings
from panelimport.model.panel import Decisions
from panelimport.settings import Settings
from tests.synthetic.odbgen import Job
from tests.synthetic.projects import make_project

DATUM = (4.0, 3.0)
POINT = (10.0, 5.0)  # (6, 2) from the datum


def rep(angle: float = 0.0, mirror: bool = False, flip: bool = False) -> StepRepeat:
    return StepRepeat("pcb", 100.0, 50.0, 30.0, 40.0, 3, 2, angle, flip, mirror, 1)


@pytest.mark.parametrize(
    ("angle", "mirror", "expected"),
    [
        (0, False, (106.0, 52.0)),  # (6, 2)
        (90, False, (102.0, 44.0)),  # clockwise: (6, 2) → (2, −6)
        (180, False, (94.0, 48.0)),  # (−6, −2)
        (270, False, (98.0, 56.0)),  # (−2, 6)
        (0, True, (94.0, 52.0)),  # mirror X: (−6, 2)
        (90, True, (98.0, 44.0)),  # rotate first (2, −6), then mirror (−2, −6)
    ],
)
def test_rotation_about_the_datum(angle, mirror, expected):
    tf = local_transform(rep(angle, mirror), 0, 0, DATUM)
    assert tf.apply(*POINT) == pytest.approx(expected)
    assert tf.apply(*DATUM) == pytest.approx((100.0, 50.0))  # the datum lands on X, Y
    assert tf.mirrored is mirror


def test_flip_mirrors_like_mirror_and_both_cancel():
    assert local_transform(rep(90, flip=True), 0, 0, DATUM).apply(*POINT) == pytest.approx((98.0, 44.0))
    assert local_transform(rep(90, mirror=True, flip=True), 0, 0, DATUM).apply(*POINT) == pytest.approx((102.0, 44.0))


def test_repeat_steps_in_the_parent_frame():
    """DX/DY move the datum in the parent frame, whatever the copy's angle."""
    tf = local_transform(rep(90), 2, 1, DATUM)
    assert tf.apply(*POINT) == pytest.approx((162.0, 84.0))  # (102, 44) + (2·30, 1·40)


def _nested_job() -> Job:
    job = Job()
    job.step("pcb", 50.0, 36.5, x0=-8.0, y0=-6.0, datum=DATUM).component("U1", "SOIC8", *POINT, part="IC")
    sub = job.step("sub", 60.0, 40.0)
    sub.step_repeat("pcb", 5.0, 0.0, 20.0, 0.0, 2, 1)
    panel = job.step("panel", 200.0, 200.0)
    panel.step_repeat("sub", 10.0, 60.0, 0.0, 0.0, 1, 1, angle=90)
    return job


def test_nested_copies_compose(tmp_path):
    """pcb in sub: (10, 5) → (6, 2) from the datum → (11, 2) and (31, 2) in sub.  sub turned
    90° clockwise about its datum (0, 0) and placed at (10, 60): (x, y) → (10 + y, 60 − x)."""
    job = OdbJob(_nested_job().write_folder(tmp_path))
    instances, issues = expand(job, "panel")
    assert [i.code for i in issues] == ["datum_origin_differ"]  # pcb's datum is not its origin
    boards = [i for i in instances if i.step.lower() == "pcb"]
    assert [i.transform.apply(*POINT) for i in boards] == [pytest.approx((12.0, 49.0)), pytest.approx((12.0, 29.0))]
    paths = [tuple((s.lower(), b, x, y) for s, b, x, y in i.path) for i in boards]
    assert paths == [(("panel", 0, 0, 0), ("sub", 0, 0, 0)), (("panel", 0, 0, 0), ("sub", 0, 1, 0))]
    assert all(i.transform.rotation == pytest.approx(270.0) for i in boards)  # 90° clockwise


# -------------------------------------------------------------------- Phase 1, irregular copies
def _irregular_job() -> Job:
    """One board, four copies at uneven offsets and 0/90/180/270° (clockwise, ODB++)."""
    job = Job()
    b = job.step("pcb", 50.0, 36.5, x0=-8.0, y0=-6.0, datum=DATUM)
    b.component("U1", "SOIC8", 7.0, 12.0, rot=0, part="IC")  # (3, 9) from the datum
    b.component("C1", "C0603", 17.0, 4.0, rot=90, part="CAP")  # (13, 1) from the datum
    panel = job.step("panel", 230.0, 70.0)
    panel.step_repeat("pcb", 15.0, 12.0, 0.0, 0.0, 1, 1)
    panel.step_repeat("pcb", 75.0, 50.0, 0.0, 0.0, 1, 1, angle=90)
    panel.step_repeat("pcb", 160.0, 45.0, 0.0, 0.0, 1, 1, angle=180)
    panel.step_repeat("pcb", 215.0, 20.0, 0.0, 0.0, 1, 1, angle=270)
    for i, (x, y) in enumerate([(2.5, 2.5), (227.5, 2.5), (2.5, 67.5)], start=1):
        panel.component(f"FID{i}", "FID1MM", x, y, part="FIDUCIAL")
    return job


# (x, y, CCW rotation) per copy, by hand: (3, 9) and (13, 1) turned clockwise, plus X, Y.
IRREGULAR_U1 = {(18.0, 21.0, 0.0), (84.0, 47.0, 270.0), (157.0, 36.0, 180.0), (206.0, 23.0, 90.0)}
IRREGULAR_C1 = {(28.0, 13.0, 270.0), (76.0, 37.0, 180.0), (147.0, 44.0, 90.0), (214.0, 33.0, 0.0)}


def test_irregular_rotated_copies_land_where_computed_by_hand(tmp_path):
    a = analyze(OdbJob(_irregular_job().write_folder(tmp_path)), Settings(), Decisions())
    assert a.mode == "panel" and len(a.circuits) == 4
    parts = {p.designator: p for p in a.placements}

    def where(name):
        return {tuple(round(v, 6) for v in a.circuit_position(parts[name], c)) for c in a.circuits}

    assert where("U1") == IRREGULAR_U1
    assert where("C1") == IRREGULAR_C1
    assert sorted(round(c.rotation) for c in a.circuits) == [0, 90, 180, 270]
    assert not any(c.mirror for c in a.circuits)


# -------------------------------------------------------------------- Phase 2, bottom side
def test_bottom_rotated_circuit_composition_by_hand():
    """Panel 150 × 150, circuit 1's reference at (20, 20), circuit 2 at +(100, 100) turned 90°
    CCW; R1 at (10, 20) in the circuit, 30°, bottom side, turned over left-right, no rotation.

    Circuit 1: (30, 40), 30° → flip x → 150 − x: (120, 40), 180° − 30° = 150°.
    Circuit 2: (10, 20) turned 90° → (−20, 10) + (120, 120) = (100, 130), 120° → (50, 130), 60°."""
    project = make_project(
        width=150, height=150, ref=(20.0, 20.0), circuits=[(0, 0, 0), (100.0, 100.0, 90.0)], layer="bottom", parts=[("R1", 10.0, 20.0, 30.0, "P")]
    )
    m = machine_transform(project, IssSettings(panel_rotation=0))
    assert (m.flip, m.rotation) == ("left-right", 0)
    frames = [m.transform @ t for t in circuit_transforms(project)]
    assert frames[0].apply(10.0, 20.0) == pytest.approx((120.0, 40.0))
    assert frames[1].apply(10.0, 20.0) == pytest.approx((50.0, 130.0))
    assert direction_angle(frames[0], 30.0) == pytest.approx(150.0)
    assert direction_angle(frames[1], 30.0) == pytest.approx(60.0)


def test_bottom_rotated_circuit_with_panel_rotation_by_hand():
    """The same panel turned over left-right, then 90° CCW: (x, y) → (150 − y, 150 − x)... after
    the flip (150 − x, y), turning 90° CCW gives (−y, 150 − x), shifted by +150 in X.

    Circuit 1: (30, 40) → (110, 120), 150° + 90° = 240°.
    Circuit 2: (100, 130) → (20, 50), 60° + 90° = 150°."""
    project = make_project(
        width=150, height=150, ref=(20.0, 20.0), circuits=[(0, 0, 0), (100.0, 100.0, 90.0)], layer="bottom", parts=[("R1", 10.0, 20.0, 30.0, "P")]
    )
    m = machine_transform(project, IssSettings(panel_rotation=90))
    frames = [m.transform @ t for t in circuit_transforms(project)]
    assert frames[0].apply(10.0, 20.0) == pytest.approx((110.0, 120.0))
    assert frames[1].apply(10.0, 20.0) == pytest.approx((20.0, 50.0))
    assert direction_angle(frames[0], 30.0) == pytest.approx(240.0)
    assert direction_angle(frames[1], 30.0) == pytest.approx(150.0)
