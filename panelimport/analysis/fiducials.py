"""Fiducial candidates.

Sources, strongest first:

* ``component`` — a panel-level component whose designator or package matches a
  fiducial pattern (``FID*`` by default, configurable);
* ``attribute`` — a copper pad carrying ``.pad_usage`` = ``g_fiducial``/``l_fiducial``
  or a ``.fiducial_name`` attribute;
* ``copper`` — an isolated round copper pad with a larger solder-mask opening, no
  paste and no drill hole (a through-hole pin routed on other layers looks isolated).

Candidates inside a circuit are circuit-level fiducials (shown, not selectable); the
rest are panel fiducials, of which the user confirms up to three.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass, field

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from panelimport.analysis.layers import CopperGeometry, copper_geometry, pad_set
from panelimport.analysis.transforms import Transform
from panelimport.io.odb.attributes import resolve_attributes
from panelimport.io.odb.job import OdbJob
from panelimport.settings import FiducialSettings

SOURCE_ORDER = ("component", "attribute", "copper", "manual")
MAX_PANEL_FIDUCIALS = 3


@dataclass
class FiducialCandidate:
    name: str
    x: float  # panel frame, mm
    y: float
    side: str
    level: str  # "panel" | "circuit"
    sources: list[str]
    circuit: int | None = None
    diameter: float | None = None
    designator: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def selectable(self) -> bool:
        return self.level == "panel"

    @property
    def source(self) -> str:
        return min(self.sources, key=SOURCE_ORDER.index)


@dataclass
class LocalCandidate:
    x: float  # step frame
    y: float
    side: str
    source: str
    diameter: float | None
    note: str = ""


def matches_pattern(value: str, patterns: list[str]) -> bool:
    v = value.upper()
    return any(fnmatch.fnmatchcase(v, p.upper()) for p in patterns if p)


def drill_geometry(job: OdbJob, step: str) -> list[CopperGeometry]:
    """The holes and slots of every board drill layer of one step."""
    out = []
    for layer in job.matrix.layers:
        if layer.is_board and layer.type == "DRILL":
            ff = job.features(step, layer.name)
            if ff is not None:
                out.append(copper_geometry(ff))
    return out


def feature_candidates(job: OdbJob, step: str, roles: dict[str, str], fs: FiducialSettings) -> list[LocalCandidate]:
    """Attribute-marked and isolated round copper pads of one step (step frame)."""
    out: list[LocalCandidate] = []
    holes = drill_geometry(job, step)
    for side in ("top", "bottom"):
        copper_name = roles.get(f"copper_{side}")
        if not copper_name:
            continue
        copper_ff = job.features(step, copper_name)
        if copper_ff is None:
            continue
        mask_name = roles.get(f"mask_{side}")
        paste_name = roles.get(f"paste_{side}")
        mask = pad_set(job.features(step, mask_name) if mask_name else None)
        paste = pad_set(job.features(step, paste_name) if paste_name else None)
        cg = copper_geometry(copper_ff)
        pads = cg.pads
        for i in range(len(pads)):
            x, y = (float(v) for v in pads.centres[i])
            d = float(pads.round_d[i]) if not math.isnan(pads.round_d[i]) else None
            raw = pads.attrs[i]
            if raw:
                attrs = resolve_attributes(raw, copper_ff.attr_names, copper_ff.attr_texts, job.attr_defs)
                usage = attrs.get(".pad_usage", "")
                if usage in ("g_fiducial", "l_fiducial") or ".fiducial_name" in attrs:
                    note = usage or f".fiducial_name={attrs.get('.fiducial_name')}"
                    out.append(LocalCandidate(x, y, side, "attribute", d, note))
                    continue
            if d is None or not (fs.min_diameter <= d <= fs.max_diameter):
                continue
            opening = [
                k for k in mask.index.within(x, y, 0.01) if mask.min_size[k] >= d + fs.mask_margin
            ]
            if not opening:
                continue
            r = d / 2
            if paste.index.overlapping(x - r, y - r, x + r, y + r):
                continue
            if not all(h.clear_of(x, y, r) for h in holes):
                continue
            if not cg.clear_of(x, y, r + fs.clearance, ignore_pad=i):
                continue
            out.append(LocalCandidate(x, y, side, "copper", d))
    return out


def classify(
    x: float, y: float, circuit_regions: list[tuple[int, object]]
) -> tuple[str, int | None]:
    pt = Point(x, y)
    for index, region in circuit_regions:
        if region.contains(pt):
            return "circuit", index
    return "panel", None


def merge(cands: list[FiducialCandidate], tolerance: float) -> list[FiducialCandidate]:
    out: list[FiducialCandidate] = []
    for c in sorted(cands, key=lambda c: SOURCE_ORDER.index(c.source)):
        for m in out:
            if m.side == c.side and m.level == c.level and math.hypot(m.x - c.x, m.y - c.y) <= tolerance:
                for s in c.sources:
                    if s not in m.sources:
                        m.sources.append(s)
                m.diameter = m.diameter or c.diameter
                m.notes.extend(n for n in c.notes if n not in m.notes)
                break
        else:
            out.append(c)
    return sorted(out, key=lambda c: (c.level != "panel", c.circuit or 0, c.name))


def feature_name(x: float, y: float) -> str:
    return f"F({x:.3f},{y:.3f})"


def make_regions(circuit_outlines: list[tuple[int, list[tuple[float, float]]]]):
    regions = []
    for index, pts in circuit_outlines:
        if len(pts) >= 3:
            regions.append((index, prep(Polygon(pts).buffer(1e-6))))
    return regions


def transform_candidate(
    lc: LocalCandidate, tf: Transform, flip: bool
) -> tuple[float, float, str]:
    x, y = tf.apply(lc.x, lc.y)
    side = lc.side
    if flip:
        side = "bottom" if side == "top" else "top"
    return x, y, side
