import math

import numpy as np
import pytest

from panelimport.analysis.transforms import (
    Transform,
    angle_diff,
    ccw_from_odb,
    derive_grid,
    fit_rigid,
    norm_angle,
    number_circuits,
)


def test_rotation_cw_is_clockwise():
    x, y = Transform.rotation_cw(90).apply(1, 0)
    assert (round(x, 9), round(y, 9)) == (0, -1)
    assert Transform.rotation_cw(90).rotation == pytest.approx(270)


def test_odb_placement_rotates_then_mirrors():
    t = Transform.odb_placement(10, 0, 90, mirror=True)
    # (1, 0) rotated 90° CW -> (0, -1); mirrored in X -> (0, -1); then + (10, 0)
    assert t.apply(1, 0) == pytest.approx((10, -1))
    assert t.apply(0, 1) == pytest.approx((9, 0))
    assert t.mirrored


def test_compose_and_inverse():
    a = Transform.translation(5, 2) @ Transform.rotation_cw(30) @ Transform.mirror_x()
    b = a.inverse()
    for p in [(0, 0), (1, 2), (-3, 7)]:
        assert (b @ a).apply(*p) == pytest.approx(p)


@pytest.mark.parametrize("deg", [0, 15, 90, 180, 270, 333.3])
@pytest.mark.parametrize("mirror", [False, True])
def test_rotation_property_roundtrip(deg, mirror):
    t = Transform.rotation_ccw(deg)
    if mirror:
        t = t @ Transform.mirror_x()
    assert t.mirrored is mirror
    assert angle_diff(t.rotation, deg) < 1e-9


def test_angle_helpers():
    assert norm_angle(-90) == 270
    assert norm_angle(359.99999999) == 0.0
    assert ccw_from_odb(90) == 270
    assert ccw_from_odb(0) == 0
    assert angle_diff(359, 1) == pytest.approx(2)


def test_fit_rigid_recovers_rotation_and_translation():
    rng = np.random.default_rng(1)
    src = rng.uniform(0, 50, size=(20, 2))
    truth = Transform.translation(100, -20) @ Transform.rotation_ccw(180)
    fit = fit_rigid(src, truth.apply_many(src))
    assert fit.max_residual < 1e-9
    assert fit.transform.rotation == pytest.approx(180)
    assert not fit.transform.mirrored


def test_fit_rigid_detects_mirror():
    rng = np.random.default_rng(2)
    src = rng.uniform(0, 50, size=(10, 2))
    truth = Transform.translation(7, 3) @ Transform.mirror_x()
    fit = fit_rigid(src, truth.apply_many(src))
    assert fit.transform.mirrored and fit.max_residual < 1e-9


def test_fit_rigid_reports_residual():
    src = np.array([[0, 0], [10, 0], [0, 10]], float)
    dst = src + [5, 5]
    dst[2] += [0.05, 0]
    fit = fit_rigid(src, dst, tolerance=0.01)
    assert fit.max_residual > 0.01


def _grid(nx, ny, dx, dy, jitter=None):
    pts = [(i * dx, j * dy) for j in range(ny) for i in range(nx)]
    if jitter:
        pts[jitter[0]] = (pts[jitter[0]][0] + jitter[1], pts[jitter[0]][1])
    return pts, [(dx * 0.9, dy * 0.9)] * len(pts)


def test_derive_grid_uniform_and_not():
    pts, sizes = _grid(3, 2, 52, 38.5)
    g = derive_grid(pts, sizes, 0.01)
    assert (g.cols, g.rows, g.uniform) == (3, 2, True)
    assert (g.pitch_x, g.pitch_y) == pytest.approx((52, 38.5))
    pts, sizes = _grid(3, 2, 52, 38.5, jitter=(4, 0.05))
    assert not derive_grid(pts, sizes, 0.01).uniform


@pytest.mark.parametrize(
    "first,order,expected",
    [
        ("lower-left", "row-major", [0, 1, 2, 3, 4, 5]),
        ("lower-left", "serpentine", [0, 1, 2, 5, 4, 3]),
        ("upper-left", "row-major", [3, 4, 5, 0, 1, 2]),
        ("lower-right", "row-major", [2, 1, 0, 5, 4, 3]),
        ("upper-right", "serpentine", [5, 4, 3, 0, 1, 2]),
        ("lower-left", "column-major", [0, 3, 1, 4, 2, 5]),
        ("lower-left", "column-serpentine", [0, 3, 4, 1, 2, 5]),
    ],
)
def test_numbering(first, order, expected):
    pts, sizes = _grid(3, 2, 52, 38.5)  # indices 0..2 bottom row, 3..5 top row
    assert number_circuits(pts, sizes, first, order) == expected


def test_numbering_shuffled_input():
    pts, sizes = _grid(3, 2, 52, 38.5)
    order = [4, 0, 5, 2, 1, 3]
    shuffled = [pts[i] for i in order]
    result = number_circuits(shuffled, sizes, "lower-left", "row-major")
    assert [order[i] for i in result] == [0, 1, 2, 3, 4, 5]
    assert math.isfinite(sum(p[0] for p in shuffled))
