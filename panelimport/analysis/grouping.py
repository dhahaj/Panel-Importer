"""Flattened-panel fallback: identify circuits from repeated designators.

1. Group designators (strip a configured copy suffix, otherwise identical names); the
   most common copy count is N.
2. Assign each copy to a circuit: by the closed board outline containing it when the
   panel profile/outline layer provides N such outlines, otherwise by sorting each
   designator's copies by Y (within a tolerance), then X.
3. Fit a rigid transform from circuit 1 to every circuit (done by the pipeline once the
   circuits are numbered), then place the copies whose count is not N.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep

from panelimport.analysis.transforms import Transform
from panelimport.io.odb.components import OdbComponent
from panelimport.io.odb.features import FeatureFile, arc_points

ROW_TOLERANCE = 1.0  # mm: copies whose Y differs by less are in the same row
SUFFIX_CANDIDATES = (r"_(\d+)$", r"-(\d+)$", r"\.(\d+)$", r"\((\d+)\)$")


@dataclass
class Copy:
    designator: str
    base: str
    copy_no: int | None
    side: str
    x: float  # panel step coordinates (ODB++), mm
    y: float
    comp: OdbComponent
    circuit: int | None = None  # 0-based cluster index once assigned


def make_copies(comps: list[tuple[str, OdbComponent]], suffix_regex: str) -> list[Copy]:
    pattern = re.compile(suffix_regex) if suffix_regex else None
    out = []
    for side, comp in comps:
        base, copy_no = comp.name, None
        if pattern is not None:
            m = pattern.search(comp.name)
            if m and m.start() > 0:
                base = comp.name[: m.start()]
                try:
                    copy_no = int(m.group(1))
                except (IndexError, ValueError, TypeError):
                    copy_no = None
        out.append(Copy(comp.name, base, copy_no, side, comp.x, comp.y, comp))
    return out


def group_copies(copies: list[Copy]) -> dict[str, list[Copy]]:
    groups: dict[str, list[Copy]] = {}
    for c in copies:
        groups.setdefault(c.base, []).append(c)
    return groups


def copy_count(groups: dict[str, list[Copy]]) -> int:
    """The most common copy count (ties go to the larger count)."""
    counts = Counter(len(g) for g in groups.values())
    if not counts:
        return 0
    return max(counts, key=lambda n: (counts[n], n))


def suggest_suffix(names: list[str]) -> str | None:
    """A copy-suffix pattern under which unique names group into equal-sized groups."""
    for pattern in SUFFIX_CANDIDATES:
        rx = re.compile(pattern)
        bases = Counter()
        matched = 0
        for n in names:
            m = rx.search(n)
            if m and m.start() > 0:
                matched += 1
                bases[n[: m.start()]] += 1
        if matched < 0.8 * len(names) or not bases:
            continue
        counts = Counter(bases.values())
        n_common, freq = counts.most_common(1)[0]
        if n_common >= 2 and freq >= 0.8 * len(bases):
            return pattern
    return None


# ------------------------------------------------------------------ outlines
def closed_outlines(ff: FeatureFile | None, extra: list[list[tuple[float, float]]] = ()) -> list[Polygon]:
    """Closed contours drawn on an outline layer (lines, arcs, surfaces) plus ``extra``."""
    polys: list[Polygon] = []
    for pts in extra:
        if len(pts) >= 3:
            polys.append(Polygon(pts))
    if ff is not None:
        lines = []

        def snap(v: float) -> float:
            return round(v, 4)

        for ln in ff.lines:
            a, b = (snap(ln.x1), snap(ln.y1)), (snap(ln.x2), snap(ln.y2))
            if a != b:
                lines.append(LineString([a, b]))
        for arc in ff.arcs:
            pts = [(arc.x1, arc.y1)] + arc_points(arc.x1, arc.y1, arc.x2, arc.y2, arc.xc, arc.yc, arc.cw)
            pts = [(snap(x), snap(y)) for x, y in pts]
            lines.append(LineString(pts))
        if lines:
            polys.extend(polygonize(unary_union(lines)))
        for s in ff.surfaces:
            for c in s.contours:
                if c.island and len(c.points) >= 3:
                    polys.append(Polygon(c.points))
    out: list[Polygon] = []
    seen = set()
    for p in polys:
        if not p.is_valid or p.area <= 0:
            continue
        key = tuple(round(v, 2) for v in p.bounds)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


@dataclass
class Assignment:
    n: int
    clusters: list[dict[str, Copy]]  # per circuit: base -> copy (complete groups)
    method: str  # "outline" | "sorted"
    outlines: list[Polygon | None] = field(default_factory=list)


def assign_by_outline(groups: dict[str, list[Copy]], n: int, outlines: list[Polygon]) -> Assignment | None:
    if len(outlines) < n:
        return None
    prepared = [prep(p) for p in outlines]
    used: dict[int, dict[str, Copy]] = {}
    for base, copies in groups.items():
        if len(copies) != n:
            continue
        seen: set[int] = set()
        for c in copies:
            pt = Point(c.x, c.y)
            hits = [i for i, p in enumerate(prepared) if p.contains(pt)]
            if not hits:
                return None
            # The smallest containing outline is the board, not the panel around it.
            i = min(hits, key=lambda k: outlines[k].area)
            if i in seen:
                return None
            seen.add(i)
            used.setdefault(i, {})[base] = c
    if len(used) != n:
        return None
    keys = sorted(used)
    return Assignment(n, [used[k] for k in keys], "outline", [outlines[k] for k in keys])


def assign_by_sorting(groups: dict[str, list[Copy]], n: int) -> Assignment:
    clusters: list[dict[str, Copy]] = [dict() for _ in range(n)]
    for base, copies in groups.items():
        if len(copies) != n:
            continue
        ordered = sorted(copies, key=lambda c: c.y)
        rows: list[list[Copy]] = []
        for c in ordered:
            if rows and abs(c.y - rows[-1][-1].y) <= ROW_TOLERANCE:
                rows[-1].append(c)
            else:
                rows.append([c])
        flat = [c for row in rows for c in sorted(row, key=lambda c: c.x)]
        for k, c in enumerate(flat):
            clusters[k][base] = c
    return Assignment(n, clusters, "sorted", [None] * n)


def cluster_extent(cluster: dict[str, Copy], outline: Polygon | None) -> tuple[float, float, float, float]:
    if outline is not None:
        return outline.bounds
    xs = [c.x for c in cluster.values()]
    ys = [c.y for c in cluster.values()]
    return min(xs), min(ys), max(xs), max(ys)


def locate_copy(
    copy: Copy,
    transforms: list[Transform],
    region1: Polygon,
    outlines: list[Polygon | None],
) -> int | None:
    """1-based circuit containing the copy, by outline or by circuit 1's region mapped back."""
    pt = Point(copy.x, copy.y)
    for k, outline in enumerate(outlines):
        if outline is not None and outline.contains(pt):
            return k + 1
    if any(o is not None for o in outlines):
        return None
    for k, tf in enumerate(transforms):
        x1, y1 = tf.inverse().apply(copy.x, copy.y)
        if region1.contains(Point(x1, y1)):
            return k + 1
    return None


def region_of(cluster: dict[str, Copy], outline: Polygon | None, margin: float = 2.0) -> Polygon:
    if outline is not None:
        return outline
    xs = [c.x for c in cluster.values()]
    ys = [c.y for c in cluster.values()]
    return Polygon(
        [
            (min(xs) - margin, min(ys) - margin),
            (max(xs) + margin, min(ys) - margin),
            (max(xs) + margin, max(ys) + margin),
            (min(xs) - margin, max(ys) + margin),
        ]
    )


def positions(cluster: dict[str, Copy], bases: list[str]) -> np.ndarray:
    return np.array([[cluster[b].x, cluster[b].y] for b in bases], dtype=float).reshape(-1, 2)
