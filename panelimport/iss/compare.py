"""Compare two placement programs (ISS or ``.x21``) part by part in panel coordinates.

Each program is turned into panel-absolute positions with its own P
(P = (panel width − pwbLayoutOffset.x, −pwbLayoutOffset.y)), so programs that put P
in different places, or number their circuits differently, still compare.  Circuits
are matched by where their parts are on the panel.

Positions match within a tolerance (0.01 mm by default); angles are reported, not
judged.  This answers "did JaNets change anything?" and "does Phase 2 match the
program that ran?".
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from panelimport.analysis.transforms import norm_angle
from panelimport.iss.mapping import Program

DEFAULT_TOLERANCE = 0.01  # mm
#: Smaller position changes are below what a program stores (4 decimals).
RESOLUTION = 0.00005  # mm
ANGLE_RESOLUTION = 0.0005  # degrees


# -------------------------------------------------------------------- panel-absolute geometry
@dataclass
class PanelPlacement:
    designator: str
    circuit: int  # allocation number in this program (1-based)
    component: str
    x: float
    y: float
    angle: float  # CCW in the program panel frame
    skip: bool = False


@dataclass
class PanelCircuit:
    number: int
    origin: tuple[float, float]  # this circuit's P
    angle: float
    outline: list[tuple[float, float]]  # 4 corners, panel frame


@dataclass
class PanelGeometry:
    program: Program
    origin: tuple[float, float]
    circuits: list[PanelCircuit]
    placements: list[PanelPlacement]
    fiducials: list[tuple[str, float, float]]


def _rot(angle: float, x: float, y: float) -> tuple[float, float]:
    if not angle:
        return x, y
    t = math.radians(angle)
    c, s = math.cos(t), math.sin(t)
    return c * x - s * y, s * x + c * y


def panel_geometry(program: Program, angle_direction: str = "ccw") -> PanelGeometry:
    """Panel-absolute positions in the program's own panel frame (lower-left 0,0).

    Allocation angles rotate a circuit about its allocation point; ``angle_direction``
    says how the program's angles turn (``cw`` programs are negated)."""
    sign = -1.0 if angle_direction == "cw" else 1.0
    px, py = program.origin
    cw, ch = program.circuit_width, program.circuit_height
    lx, ly = program.circuit_layout_offset
    circuits = []
    placements = []
    for c in program.circuits:
        a = sign * c.angle
        ox, oy = px + c.x, py + c.y
        corners = [(lx, ly), (lx + cw, ly), (lx + cw, ly + ch), (lx, ly + ch)]
        outline = [(ox + dx, oy + dy) for dx, dy in (_rot(a, x, y) for x, y in corners)]
        circuits.append(PanelCircuit(c.number, (ox, oy), norm_angle(a), outline))
        for p in program.placements:
            if p.circuit_id not in ("A", ""):
                continue
            dx, dy = _rot(a, p.x, p.y)
            placements.append(
                PanelPlacement(p.designator, c.number, p.component, ox + dx, oy + dy, norm_angle(sign * p.angle + a), p.skip)
            )
    fiducials = [(f.name, px + f.x, py + f.y) for f in program.fiducials]
    return PanelGeometry(program, (px, py), circuits, placements, fiducials)


# -------------------------------------------------------------------- comparison
@dataclass
class PartRow:
    designator: str
    circuit_a: int
    circuit_b: int
    component_a: str
    component_b: str
    a: tuple[float, float, float]  # x, y, angle
    b: tuple[float, float, float]
    skip_a: bool = False
    skip_b: bool = False

    @property
    def dx(self) -> float:
        return self.b[0] - self.a[0]

    @property
    def dy(self) -> float:
        return self.b[1] - self.a[1]

    @property
    def distance(self) -> float:
        return math.hypot(self.dx, self.dy)

    @property
    def dangle(self) -> float:
        """B − A, in (−180, 180]."""
        d = norm_angle(self.b[2] - self.a[2])
        return d - 360.0 if d > 180.0 else d

    @property
    def moved(self) -> bool:
        """Any position change a program can store (4 decimals)."""
        return abs(self.dx) > RESOLUTION or abs(self.dy) > RESOLUTION

    @property
    def rotated(self) -> bool:
        return abs(self.dangle) > ANGLE_RESOLUTION

    @property
    def differs(self) -> bool:
        return self.moved or self.rotated or self.component_a != self.component_b or self.skip_a != self.skip_b


@dataclass
class CircuitPair:
    a: int
    b: int
    dx: float  # median part offset B − A
    dy: float
    dangle: float  # allocation angle B − A
    parts: int  # common parts compared
    outside: int  # of which beyond the tolerance


@dataclass
class FiducialPair:
    name_a: str
    name_b: str
    a: tuple[float, float]
    b: tuple[float, float]

    @property
    def distance(self) -> float:
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])


@dataclass
class Comparison:
    a: Program
    b: Program
    tolerance: float
    rows: list[PartRow] = field(default_factory=list)
    only_a: list[str] = field(default_factory=list)  # designators
    only_b: list[str] = field(default_factory=list)
    circuits: list[CircuitPair] = field(default_factory=list)
    circuits_only_a: list[int] = field(default_factory=list)
    circuits_only_b: list[int] = field(default_factory=list)
    fiducials: list[FiducialPair] = field(default_factory=list)
    fiducials_only_a: list[str] = field(default_factory=list)
    fiducials_only_b: list[str] = field(default_factory=list)
    components_only_a: list[str] = field(default_factory=list)
    components_only_b: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------- derived
    @property
    def changed(self) -> list[PartRow]:
        """Rows with any difference (position at the programs' resolution, angle, component, skip)."""
        return [r for r in self.rows if r.differs]

    @property
    def changed_designators(self) -> list[str]:
        return sorted({r.designator for r in self.changed}, key=_natural)

    @property
    def position_changed(self) -> list[PartRow]:
        return [r for r in self.rows if r.distance > self.tolerance]

    def angle_pattern(self) -> str:
        """Whether angle differences are one constant offset or vary per part."""
        per_part: dict[str, set[float]] = {}
        for r in self.rows:
            per_part.setdefault(r.designator, set()).add(round(r.dangle, 3))
        deltas = Counter(d for ds in per_part.values() for d in ds)
        if not deltas:
            return "no common parts"
        if set(deltas) == {0.0}:
            return "all angles equal"
        if len(deltas) == 1:
            return f"constant offset {next(iter(deltas)):+g}°"
        changed = sum(1 for ds in per_part.values() if ds != {0.0})
        return f"vary per part ({changed} of {len(per_part)} parts differ; offsets {', '.join(f'{d:+g}°' for d in sorted(deltas))})"

    def summary(self) -> str:
        n_parts = len({r.designator for r in self.rows})
        pos = len({r.designator for r in self.position_changed})
        small = len({r.designator for r in self.rows if r.moved} - {r.designator for r in self.position_changed})
        ang = len({r.designator for r in self.rows if r.rotated})
        comp = len({r.designator for r in self.rows if r.component_a != r.component_b})
        bits = [
            f"{n_parts} common parts × {len(self.circuits)} circuits",
            f"{len(self.changed_designators)} changed",
            f"{pos} moved > {self.tolerance:g} mm",
        ]
        if small:
            bits.append(f"{small} moved ≤ {self.tolerance:g} mm")
        bits.append(f"{ang} rotated")
        if comp:
            bits.append(f"{comp} with another component")
        if self.a.circuit_layout != self.b.circuit_layout:
            bits.append(f"layout {self.a.circuit_layout} → {self.b.circuit_layout}")
        if self.components_only_a or self.components_only_b:
            bits.append(f"components: {len(self.components_only_a)} only in A, {len(self.components_only_b)} only in B")
        if self.only_a or self.only_b:
            bits.append(f"parts: {len(self.only_a)} only in A, {len(self.only_b)} only in B")
        if self.circuits_only_a or self.circuits_only_b or len(self.a.circuits) != len(self.b.circuits):
            bits.append(f"circuits {len(self.a.circuits)} vs {len(self.b.circuits)}")
        far = [f for f in self.fiducials if f.distance > self.tolerance]
        if far or self.fiducials_only_a or self.fiducials_only_b:
            bits.append(f"fiducials: {len(far)} moved, {len(self.fiducials_only_a)} only in A, {len(self.fiducials_only_b)} only in B")
        if self.panel_differs():
            bits.append("panel size differs")
        if self.clamp_differs():
            bits.append("clamp offset differs")
        same = not (self.changed or self.only_a or self.only_b or far or self.panel_differs() or self.clamp_differs())
        return ("Same placements" if same else "Different") + ": " + ", ".join(bits)

    def panel_differs(self) -> bool:
        return abs(self.a.width - self.b.width) > self.tolerance or abs(self.a.height - self.b.height) > self.tolerance

    def clamp_differs(self) -> bool:
        ca, cb = self.a.clamp_offset, self.b.clamp_offset
        if ca is None or cb is None:
            return ca is not cb
        return abs(ca - cb) > self.tolerance


def compare_programs(
    a: Program, b: Program, tolerance: float = DEFAULT_TOLERANCE, angle_direction: str = "ccw"
) -> Comparison:
    ga, gb = panel_geometry(a, angle_direction), panel_geometry(b, angle_direction)
    cmp = Comparison(a, b, tolerance)

    names_a = [p.designator for p in a.placements]
    names_b = [p.designator for p in b.placements]
    common = set(names_a) & set(names_b)
    cmp.only_a = sorted(set(names_a) - common, key=_natural)
    cmp.only_b = sorted(set(names_b) - common, key=_natural)

    by_a = _index(ga.placements)
    by_b = _index(gb.placements)
    pairs = _match_circuits(ga, gb, by_a, by_b, common)
    for ca, cb in pairs:
        rows = []
        for d in sorted(common, key=_natural):
            pa, pb = by_a.get((ca, d)), by_b.get((cb, d))
            if pa is None or pb is None:
                continue
            rows.append(
                PartRow(d, ca, cb, pa.component, pb.component, (pa.x, pa.y, pa.angle), (pb.x, pb.y, pb.angle), pa.skip, pb.skip)
            )
        cmp.rows += rows
        circ_a = next(c for c in ga.circuits if c.number == ca)
        circ_b = next(c for c in gb.circuits if c.number == cb)
        if rows:
            dx = _median([r.dx for r in rows])
            dy = _median([r.dy for r in rows])
        else:
            dx = circ_b.outline[0][0] - circ_a.outline[0][0]
            dy = circ_b.outline[0][1] - circ_a.outline[0][1]
        da = norm_angle(circ_b.angle - circ_a.angle)
        cmp.circuits.append(
            CircuitPair(ca, cb, dx, dy, da - 360.0 if da > 180.0 else da, len(rows), sum(1 for r in rows if r.distance > tolerance))
        )
    matched_a = {p[0] for p in pairs}
    matched_b = {p[1] for p in pairs}
    cmp.circuits_only_a = [c.number for c in ga.circuits if c.number not in matched_a]
    cmp.circuits_only_b = [c.number for c in gb.circuits if c.number not in matched_b]

    fa = list(ga.fiducials)
    fb = list(gb.fiducials)
    for i, j in _greedy([[math.hypot(x2 - x1, y2 - y1) for _n2, x2, y2 in fb] for _n1, x1, y1 in fa]):
        cmp.fiducials.append(FiducialPair(fa[i][0], fb[j][0], (fa[i][1], fa[i][2]), (fb[j][1], fb[j][2])))
    used_a = {f.name_a for f in cmp.fiducials}
    used_b = {f.name_b for f in cmp.fiducials}
    cmp.fiducials_only_a = [n for n, _x, _y in fa if n not in used_a]
    cmp.fiducials_only_b = [n for n, _x, _y in fb if n not in used_b]

    comps_a = {c.name for c in a.components}
    comps_b = {c.name for c in b.components}
    cmp.components_only_a = sorted(comps_a - comps_b, key=_natural)
    cmp.components_only_b = sorted(comps_b - comps_a, key=_natural)
    return cmp


def _index(placements: list[PanelPlacement]) -> dict[tuple[int, str], PanelPlacement]:
    out: dict[tuple[int, str], PanelPlacement] = {}
    for p in placements:
        out.setdefault((p.circuit, p.designator), p)
    return out


def _anchor(geom: PanelGeometry, by: dict, number: int, common: set[str]) -> tuple[float, float]:
    """Where a circuit is: the mean of its common parts, else its outline centre."""
    pts = [(by[(number, d)].x, by[(number, d)].y) for d in common if (number, d) in by]
    if not pts:
        c = next(c for c in geom.circuits if c.number == number)
        pts = c.outline
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _match_circuits(ga, gb, by_a, by_b, common) -> list[tuple[int, int]]:
    anchors_a = [(c.number, _anchor(ga, by_a, c.number, common)) for c in ga.circuits]
    anchors_b = [(c.number, _anchor(gb, by_b, c.number, common)) for c in gb.circuits]
    dist = [[math.hypot(pb[0] - pa[0], pb[1] - pa[1]) for _nb, pb in anchors_b] for _na, pa in anchors_a]
    pairs = [(anchors_a[i][0], anchors_b[j][0]) for i, j in _greedy(dist)]
    return sorted(pairs)


def _greedy(dist: list[list[float]]) -> list[tuple[int, int]]:
    """Nearest pairs first, each item used once."""
    cand = sorted((d, i, j) for i, row in enumerate(dist) for j, d in enumerate(row))
    used_i, used_j, out = set(), set(), []
    for _d, i, j in cand:
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        out.append((i, j))
    return sorted(out)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _natural(text: str) -> tuple:
    import re

    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text))


# -------------------------------------------------------------------- report
def format_comparison(cmp: Comparison, *, all_rows: bool = False, name_a: str = "A", name_b: str = "B") -> str:
    a, b = cmp.a, cmp.b
    lines = [
        f"A: {name_a} ({a.kind}, {len(a.placements)} placements, {len(a.circuits)} circuits, {a.circuit_layout})",
        f"B: {name_b} ({b.kind}, {len(b.placements)} placements, {len(b.circuits)} circuits, {b.circuit_layout})",
        "",
        f"Panel:   A {a.width:.4f} × {a.height:.4f}   B {b.width:.4f} × {b.height:.4f}"
        + ("   (differs)" if cmp.panel_differs() else ""),
        f"Clamp:   A {_opt(a.clamp_offset)}   B {_opt(b.clamp_offset)}" + ("   (differs)" if cmp.clamp_differs() else ""),
        f"P:       A ({_f4(a.origin[0])}, {_f4(a.origin[1])})   B ({_f4(b.origin[0])}, {_f4(b.origin[1])})",
    ]
    for key in sorted(set(a.counts) | set(b.counts)):
        ca, cb = a.counts.get(key), b.counts.get(key)
        lines.append(f"Header {key}: A {_count(ca)}   B {_count(cb)}")
    if a.circuit_layout != b.circuit_layout:
        lines.append(f"Circuit layout: A {a.circuit_layout} → B {b.circuit_layout}")
    lines.append("")
    lines.append(f"Circuits: A {len(a.circuits)}, B {len(b.circuits)} (matched by position)")
    lines.append("  A#   B#       ΔX        ΔY     Δangle  parts  > tol")
    for c in cmp.circuits:
        lines.append(f"  {c.a:<4} {c.b:<4} {c.dx:9.4f} {c.dy:9.4f} {c.dangle:9.3f}  {c.parts:5}  {c.outside:5}")
    if cmp.circuits_only_a:
        lines.append(f"  only in A: {', '.join(map(str, cmp.circuits_only_a))}")
    if cmp.circuits_only_b:
        lines.append(f"  only in B: {', '.join(map(str, cmp.circuits_only_b))}")
    lines.append("")
    lines.append("Fiducials (matched by position):")
    for f in cmp.fiducials:
        flag = "" if f.distance <= cmp.tolerance else "   > tol"
        lines.append(
            f"  {f.name_a:<12} {f.name_b:<12} A ({f.a[0]:.4f}, {f.a[1]:.4f})  ΔX {f.b[0] - f.a[0]:+.4f}  ΔY {f.b[1] - f.a[1]:+.4f}{flag}"
        )
    if cmp.fiducials_only_a:
        lines.append(f"  only in A: {', '.join(cmp.fiducials_only_a)}")
    if cmp.fiducials_only_b:
        lines.append(f"  only in B: {', '.join(cmp.fiducials_only_b)}")
    lines.append("")
    rows = cmp.rows if all_rows else cmp.changed
    title = "Parts" if all_rows else "Parts that differ (position, angle, component or skip; * = moved more than the tolerance)"
    lines.append(f"{title}: {len(rows)} of {len(cmp.rows)} rows")
    if rows:
        lines.append("  designator   A#   B#        X(A)       Y(A)       ΔX        ΔY    angle A  angle B   Δangle  component")
        for r in rows:
            comp = r.component_a if r.component_a == r.component_b else f"{r.component_a} → {r.component_b}"
            skip = "" if r.skip_a == r.skip_b else f"  skip {r.skip_a}→{r.skip_b}"
            star = "*" if r.distance > cmp.tolerance else " "
            lines.append(
                f" {star}{r.designator:<12} {r.circuit_a:<4} {r.circuit_b:<4} {r.a[0]:10.4f} {r.a[1]:10.4f} {r.dx:+9.4f} {r.dy:+9.4f}"
                f"  {r.a[2]:7.2f}  {r.b[2]:7.2f}  {r.dangle:+7.2f}  {comp}{skip}"
            )
    if cmp.only_a:
        lines.append(f"Only in A ({len(cmp.only_a)}): {', '.join(cmp.only_a)}")
    if cmp.only_b:
        lines.append(f"Only in B ({len(cmp.only_b)}): {', '.join(cmp.only_b)}")
    if cmp.components_only_a:
        lines.append(f"Components only in A: {', '.join(repr(c) for c in cmp.components_only_a)}")
    if cmp.components_only_b:
        lines.append(f"Components only in B: {', '.join(repr(c) for c in cmp.components_only_b)}")
    lines.append(f"Angles: {cmp.angle_pattern()}")
    for label, prog in (("A", a), ("B", b)):
        for note in prog.notes:
            lines.append(f"Note ({label}): {note}")
    lines.append("")
    lines.append(cmp.summary())
    return "\n".join(lines)


def _f4(v: float) -> str:
    return f"{round(v, 4) + 0.0:.4f}"  # + 0.0: never "-0.0000"


def _opt(v: float | None) -> str:
    return "-" if v is None else f"{v:g}"


def _count(c: tuple[int, int] | None) -> str:
    return "-" if c is None else f"{c[1]}/{c[0]}"
