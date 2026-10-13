"""2D transforms, rigid fitting and grid derivation.

Conventions (ODB++ spec, "Rotation and Mirroring"): ODB++ angles are clockwise,
mirroring negates X, and when both apply the feature is rotated first, then mirrored.
Angles reported to the user and stored in the project are counter-clockwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def norm_angle(deg: float) -> float:
    """Normalise to [0, 360), snapping values within 1e-7 of a full turn to 0."""
    a = deg % 360.0
    if a > 360.0 - 1e-7 or a < 1e-7:
        return 0.0
    return a


def angle_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two angles in degrees."""
    d = abs(norm_angle(a) - norm_angle(b)) % 360.0
    return min(d, 360.0 - d)


def ccw_from_odb(rot_cw: float) -> float:
    """ODB++ clockwise rotation -> counter-clockwise rotation (both in degrees)."""
    return norm_angle(-rot_cw)


@dataclass(frozen=True)
class Transform:
    """``x' = a*x + b*y + tx``, ``y' = c*x + d*y + ty``."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    # ---------------------------------------------------------------- builders
    @staticmethod
    def identity() -> "Transform":
        return Transform()

    @staticmethod
    def translation(tx: float, ty: float) -> "Transform":
        return Transform(tx=tx, ty=ty)

    @staticmethod
    def rotation_cw(deg: float) -> "Transform":
        t = math.radians(deg)
        c, s = math.cos(t), math.sin(t)
        return Transform(c, s, -s, c)

    @staticmethod
    def rotation_ccw(deg: float) -> "Transform":
        return Transform.rotation_cw(-deg)

    @staticmethod
    def mirror_x() -> "Transform":
        return Transform(a=-1.0)

    @staticmethod
    def odb_placement(x: float, y: float, rot_cw: float, mirror: bool) -> "Transform":
        """Place local coordinates at (x, y): rotate clockwise, then mirror X, then translate."""
        t = Transform.rotation_cw(rot_cw)
        if mirror:
            t = Transform.mirror_x() @ t
        return Transform.translation(x, y) @ t

    # ---------------------------------------------------------------- algebra
    def __matmul__(self, o: "Transform") -> "Transform":
        """Composition: ``(self @ o)(p) == self(o(p))``."""
        return Transform(
            self.a * o.a + self.b * o.c,
            self.a * o.b + self.b * o.d,
            self.c * o.a + self.d * o.c,
            self.c * o.b + self.d * o.d,
            self.a * o.tx + self.b * o.ty + self.tx,
            self.c * o.tx + self.d * o.ty + self.ty,
        )

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.b * y + self.tx, self.c * x + self.d * y + self.ty

    def apply_many(self, pts: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts, dtype=float).reshape(-1, 2)
        m = np.array([[self.a, self.b], [self.c, self.d]])
        return pts @ m.T + np.array([self.tx, self.ty])

    def inverse(self) -> "Transform":
        det = self.det
        if abs(det) < 1e-15:
            raise ZeroDivisionError("singular transform")
        a, b, c, d = self.d / det, -self.b / det, -self.c / det, self.a / det
        return Transform(a, b, c, d, -(a * self.tx + b * self.ty), -(c * self.tx + d * self.ty))

    # ---------------------------------------------------------------- properties
    @property
    def det(self) -> float:
        return self.a * self.d - self.b * self.c

    @property
    def mirrored(self) -> bool:
        return self.det < 0

    @property
    def rotation(self) -> float:
        """Counter-clockwise rotation applied after the (optional) X mirror, degrees."""
        if self.mirrored:
            return norm_angle(math.degrees(math.atan2(-self.c, -self.a)))
        return norm_angle(math.degrees(math.atan2(self.c, self.a)))

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return self.a, self.b, self.c, self.d, self.tx, self.ty


# -------------------------------------------------------------------- rigid fit
@dataclass
class RigidFit:
    transform: Transform
    residuals: np.ndarray  # per point, mm

    @property
    def max_residual(self) -> float:
        return float(self.residuals.max()) if len(self.residuals) else 0.0


def _kabsch(src: np.ndarray, dst: np.ndarray, proper: bool) -> Transform:
    cs = src.mean(axis=0)
    cd = dst.mean(axis=0)
    h = (src - cs).T @ (dst - cd)
    u, _s, vt = np.linalg.svd(h)
    sign = 1.0 if proper else -1.0
    corr = np.diag([1.0, sign * np.sign(np.linalg.det(vt.T @ u.T)) or 1.0])
    r = vt.T @ corr @ u.T
    t = cd - r @ cs
    return Transform(r[0, 0], r[0, 1], r[1, 0], r[1, 1], t[0], t[1])


def fit_rigid(src: np.ndarray, dst: np.ndarray, tolerance: float = 0.01) -> RigidFit:
    """Least-squares rigid transform mapping ``src`` onto ``dst`` (2D Kabsch).

    A mirrored solution is used only when the proper rotation does not fit within
    ``tolerance`` and the mirrored one fits better (needs three or more points).
    """
    src = np.asarray(src, dtype=float).reshape(-1, 2)
    dst = np.asarray(dst, dtype=float).reshape(-1, 2)
    if len(src) == 0:
        return RigidFit(Transform(), np.zeros(0))
    if len(src) == 1:
        t = Transform.translation(*(dst[0] - src[0]))
        return RigidFit(t, np.zeros(1))
    proper = _kabsch(src, dst, proper=True)
    res = np.linalg.norm(proper.apply_many(src) - dst, axis=1)
    if res.max() <= tolerance or len(src) < 3:
        return RigidFit(proper, res)
    improper = _kabsch(src, dst, proper=False)
    res_m = np.linalg.norm(improper.apply_many(src) - dst, axis=1)
    if res_m.max() < res.max():
        return RigidFit(improper, res_m)
    return RigidFit(proper, res)


# -------------------------------------------------------------------- clustering
def cluster_1d(values: list[float], gap: float) -> list[int]:
    """Cluster index per value; values closer than ``gap`` to their neighbour share a cluster.

    Clusters are numbered in ascending value order.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0] * len(values)
    cluster = -1
    prev = None
    for i in order:
        v = values[i]
        if prev is None or v - prev > gap:
            cluster += 1
        out[i] = cluster
        prev = v
    return out


@dataclass
class GridInfo:
    cols: int
    rows: int
    pitch_x: float
    pitch_y: float
    uniform: bool
    max_deviation: float  # mm from the ideal grid
    col_of: list[int]
    row_of: list[int]


def derive_grid(
    points: list[tuple[float, float]], sizes: list[tuple[float, float]], tolerance: float
) -> GridInfo:
    """Columns, rows and pitch of circuit positions, and whether they form a uniform grid.

    ``points`` are comparable positions of each circuit (e.g. the transformed centre of
    the board profile); ``sizes`` their extents, used to group rows and columns.
    """
    n = len(points)
    if n == 0:
        return GridInfo(0, 0, 0.0, 0.0, True, 0.0, [], [])
    widths = sorted(s[0] for s in sizes) or [1.0]
    heights = sorted(s[1] for s in sizes) or [1.0]
    col_gap = max(widths[len(widths) // 2] * 0.5, tolerance * 10)
    row_gap = max(heights[len(heights) // 2] * 0.5, tolerance * 10)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    col_of = cluster_1d(xs, col_gap)
    row_of = cluster_1d(ys, row_gap)
    cols = max(col_of) + 1
    rows = max(row_of) + 1

    def means(values: list[float], idx: list[int], k: int) -> list[float]:
        return [float(np.mean([v for v, i in zip(values, idx) if i == c])) for c in range(k)]

    col_x = means(xs, col_of, cols)
    row_y = means(ys, row_of, rows)
    pitch_x = float(np.median(np.diff(col_x))) if cols > 1 else 0.0
    pitch_y = float(np.median(np.diff(row_y))) if rows > 1 else 0.0

    # Fit an ideal grid through the points (least squares origin) and measure deviation.
    x0 = float(np.mean([x - c * pitch_x for x, c in zip(xs, col_of)]))
    y0 = float(np.mean([y - r * pitch_y for y, r in zip(ys, row_of)]))
    dev = max(
        math.hypot(x - (x0 + c * pitch_x), y - (y0 + r * pitch_y))
        for x, y, c, r in zip(xs, ys, col_of, row_of)
    )
    cells = set(zip(col_of, row_of))
    uniform = dev <= tolerance and len(cells) == n == cols * rows
    return GridInfo(cols, rows, pitch_x, pitch_y, uniform, dev, col_of, row_of)


def number_circuits(
    points: list[tuple[float, float]],
    sizes: list[tuple[float, float]],
    first: str,
    order: str,
) -> list[int]:
    """Return input indices in circuit order (element 0 is circuit 1).

    ``first`` is the corner of circuit 1; ``order`` is ``row-major``, ``serpentine``,
    ``column-major`` or ``column-serpentine``.
    """
    n = len(points)
    if n == 0:
        return []
    grid = derive_grid(points, sizes, tolerance=0.0)
    flip_rows = first.startswith("upper")
    flip_cols = first.endswith("right")
    rows = [(grid.rows - 1 - r) if flip_rows else r for r in grid.row_of]
    cols = [(grid.cols - 1 - c) if flip_cols else c for c in grid.col_of]
    xs = [(-p[0] if flip_cols else p[0]) for p in points]
    ys = [(-p[1] if flip_rows else p[1]) for p in points]

    def key(i: int) -> tuple:
        if order in ("row-major", "serpentine"):
            col_key = xs[i]
            if order == "serpentine" and rows[i] % 2 == 1:
                col_key = -col_key
            return rows[i], col_key, ys[i]
        row_key = ys[i]
        if order == "column-serpentine" and cols[i] % 2 == 1:
            row_key = -row_key
        return cols[i], row_key, xs[i]

    return sorted(range(n), key=key)
