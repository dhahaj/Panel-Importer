"""Layer features as numpy arrays for the checks: pads, segments and surfaces."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.validation import make_valid

from panelimport.analysis.spatial import BoxIndex
from panelimport.io.odb.features import FeatureFile, arc_points
from panelimport.io.odb.symbols import rotate_extent


@dataclass
class PadSet:
    """Positive pads (and surface islands, treated as pads) of one layer, step frame."""

    centres: np.ndarray
    boxes: np.ndarray
    round_d: np.ndarray  # diameter for round pads, NaN otherwise
    min_size: np.ndarray  # smaller side of the bounding box
    is_surface: np.ndarray
    feature_index: list[int]
    attrs: list[str]
    index: BoxIndex = field(repr=False)

    def __len__(self) -> int:
        return len(self.centres)


def _pad_box(ff: FeatureFile, pad) -> tuple[float, float, float, float]:
    shape = ff.symbol(pad.sym)
    ex = shape.local_extent()
    if pad.rotation:
        ex = rotate_extent(ex, pad.rotation)
    if pad.mirror:
        ex = (-ex[2], ex[1], -ex[0], ex[3])
    return pad.x + ex[0], pad.y + ex[1], pad.x + ex[2], pad.y + ex[3]


def pad_set(ff: FeatureFile | None, include_surfaces: bool = True) -> PadSet:
    centres: list[tuple[float, float]] = []
    boxes: list[tuple[float, float, float, float]] = []
    round_d: list[float] = []
    min_size: list[float] = []
    is_surface: list[bool] = []
    feature_index: list[int] = []
    attrs: list[str] = []
    if ff is not None:
        for p in ff.pads:
            if not p.positive:
                continue
            box = _pad_box(ff, p)
            shape = ff.symbol(p.sym)
            centres.append((p.x, p.y))
            boxes.append(box)
            round_d.append(shape.width if shape.is_round else math.nan)
            min_size.append(min(box[2] - box[0], box[3] - box[1]))
            is_surface.append(False)
            feature_index.append(p.index)
            attrs.append(p.attrs)
        if include_surfaces:
            for s in ff.surfaces:
                if not s.positive:
                    continue
                for c in s.contours:
                    if not c.island or len(c.points) < 3:
                        continue
                    xs = [q[0] for q in c.points]
                    ys = [q[1] for q in c.points]
                    box = (min(xs), min(ys), max(xs), max(ys))
                    centres.append(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
                    boxes.append(box)
                    round_d.append(math.nan)
                    min_size.append(min(box[2] - box[0], box[3] - box[1]))
                    is_surface.append(True)
                    feature_index.append(s.index)
                    attrs.append(s.attrs)
    c = np.array(centres, dtype=float).reshape(-1, 2)
    b = np.array(boxes, dtype=float).reshape(-1, 4)
    sizes = (b[:, 2] - b[:, 0]) if len(b) else np.zeros(0)
    cell = float(np.clip(np.median(sizes) * 4 if len(sizes) else 2.0, 0.5, 10.0))
    return PadSet(
        centres=c,
        boxes=b,
        round_d=np.array(round_d, dtype=float),
        min_size=np.array(min_size, dtype=float),
        is_surface=np.array(is_surface, dtype=bool),
        feature_index=feature_index,
        attrs=attrs,
        index=BoxIndex(b, c, cell),
    )


@dataclass
class CopperGeometry:
    """Everything on a copper layer that can make a pad non-isolated."""

    pads: PadSet
    segments: np.ndarray  # (M, 4)
    half_width: np.ndarray  # (M,)
    surfaces: list[Polygon]
    surface_boxes: np.ndarray  # (S, 4)

    def clear_of(self, x: float, y: float, radius: float, ignore_pad: int | None = None) -> bool:
        """True if no copper other than ``ignore_pad`` comes within ``radius`` of (x, y)."""
        for i in self.pads.index.overlapping(x - radius, y - radius, x + radius, y + radius):
            if i == ignore_pad:
                continue
            bx0, by0, bx1, by1 = self.pads.boxes[i]
            dx = max(bx0 - x, 0.0, x - bx1)
            dy = max(by0 - y, 0.0, y - by1)
            if math.hypot(dx, dy) < radius:
                return False
        if len(self.segments):
            s = self.segments
            px, py = x, y
            vx = s[:, 2] - s[:, 0]
            vy = s[:, 3] - s[:, 1]
            wx = px - s[:, 0]
            wy = py - s[:, 1]
            ll = vx * vx + vy * vy
            t = np.where(ll > 0, np.clip((wx * vx + wy * vy) / np.where(ll > 0, ll, 1), 0, 1), 0)
            dist = np.hypot(s[:, 0] + t * vx - px, s[:, 1] + t * vy - py) - self.half_width
            if np.any(dist < radius):
                return False
        if self.surfaces:
            b = self.surface_boxes
            near = np.nonzero(
                (b[:, 0] <= x + radius) & (b[:, 2] >= x - radius) & (b[:, 1] <= y + radius) & (b[:, 3] >= y - radius)
            )[0]
            pt = Point(x, y)
            for i in near:
                if self.surfaces[i].distance(pt) < radius:
                    return False
        return True


def copper_geometry(ff: FeatureFile | None) -> CopperGeometry:
    pads = pad_set(ff, include_surfaces=False)
    segs: list[tuple[float, float, float, float]] = []
    half: list[float] = []
    polys: list[Polygon] = []
    if ff is not None:
        for ln in ff.lines:
            if ln.positive:
                segs.append((ln.x1, ln.y1, ln.x2, ln.y2))
                half.append(ff.symbol(ln.sym).width / 2)
        for a in ff.arcs:
            if not a.positive:
                continue
            w = ff.symbol(a.sym).width / 2
            prev = (a.x1, a.y1)
            for q in arc_points(a.x1, a.y1, a.x2, a.y2, a.xc, a.yc, a.cw, step_deg=10.0):
                segs.append((prev[0], prev[1], q[0], q[1]))
                half.append(w)
                prev = q
        for s in ff.surfaces:
            if not s.positive:
                continue
            shell = None
            holes = []
            for c in s.contours:
                if len(c.points) < 3:
                    continue
                if c.island:
                    if shell is not None:
                        polys.append(_poly(shell, holes))
                        holes = []
                    shell = c.points
                else:
                    holes.append(c.points)
            if shell is not None:
                polys.append(_poly(shell, holes))
    boxes = np.array([p.bounds for p in polys], dtype=float).reshape(-1, 4)
    return CopperGeometry(
        pads=pads,
        segments=np.array(segs, dtype=float).reshape(-1, 4),
        half_width=np.array(half, dtype=float),
        surfaces=polys,
        surface_boxes=boxes,
    )


def _poly(shell, holes) -> Polygon:
    poly = Polygon(shell, holes)
    if not poly.is_valid:
        fixed = make_valid(poly)
        if isinstance(fixed, Polygon):
            return fixed
        return Polygon(shell)
    return poly
