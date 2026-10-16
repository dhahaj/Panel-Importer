"""Project -> ISS frame: pure math, no XML.

Every ISS program has one origin **P**.  JaNets, CircuitCAM and issgen all use

    placement on panel   = P + allocation[k] + placementPosition      (allocation angle 0)
    circuit k outline LL = P + allocation[k] + circuitLayoutOffset
    pwbLayoutOffset      = panel lower-right corner - P
    fiducial on panel    = P + markPosition
    clampOffset.y        = panel height / 2

with P in different places.  Rotation and flipping are not special-cased: everything is
computed in panel-absolute coordinates from the project, then one *machine transform*
is applied for the side being written (the bottom flip, if any, then the panel
rotation, then a shift that puts the transformed panel's lower-left corner at 0,0).
The ISS values are derived from the transformed geometry:

* P is circuit 1's transformed reference point, moved to the lower-left of circuit 1's
  transformed outline (with the default ``profile-lower-left`` reference, P *is* that
  corner; with another reference, P keeps the reference's offset from the outline's
  lower-left corner, turned with the circuit, so an untransformed panel has P at the
  reference point and ``circuitLayoutOffset`` = the outline's lower-left).
* Each allocation is the change in a circuit's P (the same circuit-frame point placed
  by that circuit), and its angle the circuit's rotation relative to circuit 1.
* Each placement position is the transformed position in circuit 1 minus P.

Angles follow the geometry: a part's angle is the direction of its rotated X axis, so
a left-right flip maps θ to 180° − θ and a front-back flip maps θ to −θ.

Component sizes are in the part's own frame (``witdh`` along its X axis at angle 0), so
the panel's flip and rotation do not change them; an angle offset of ±90° does.
"""

from __future__ import annotations

import fnmatch
import math
import re
from dataclasses import dataclass, field

from panelimport.analysis.transforms import Transform, norm_angle
from panelimport.iss.settings import IssSettings
from panelimport.model.panel import SIZE_FIELDS, PanelProject

#: Decimals JaNets stores (``.x21`` shows ``41.7830``); every written number is rounded to it.
DECIMALS = 4


def r4(v: float) -> float:
    out = round(float(v), DECIMALS)
    return 0.0 if out == 0 else out


def angle4(v: float) -> float:
    """An angle rounded to 4 decimals and kept in [0, 360)."""
    return r4(norm_angle(r4(norm_angle(v))))


# -------------------------------------------------------------------- program model
@dataclass
class ProgramCircuit:
    """One circuit (allocation).  x/y are relative to P; angle is CCW in the program."""

    number: int
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0


@dataclass
class ProgramPlacement:
    """One placement of the base circuit: placementPosition (relative to P) and angle."""

    designator: str
    component: str
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    circuit_id: str = "A"
    skip: bool = False  # the program says not to place it
    layer: str = ""  # known for generated programs only


@dataclass
class ProgramComponent:
    name: str
    comment: str = ""
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0


@dataclass
class SizeConflict:
    """Placements of one component that know different sizes for it."""

    component: str
    fields: list[str]  # the size fields whose known values differ
    sizes: list[tuple[str, tuple[float, float, float]]]  # (designator, (width, length, height)), one per size


@dataclass
class ProgramFiducial:
    name: str
    x: float  # markPosition, relative to P
    y: float


@dataclass
class Program:
    """What a placement program says, read from ISS or ``.x21``, or generated.

    Coordinates are as written in the program: allocations, placement positions and
    mark positions are relative to P, and P = (width − pwbLayoutOffset.x,
    −pwbLayoutOffset.y) in the program's panel frame (lower-left corner at 0,0).
    """

    kind: str = "iss"  # "iss" | "x21" | "generated"
    path: str = ""
    pwb_id: str = ""
    width: float = 0.0
    height: float = 0.0
    circuit_width: float = 0.0
    circuit_height: float = 0.0
    circuit_layout: str = "NONMATRIX"  # as written: NONMATRIX | MATRIX | SINGLE | ...
    circuits: list[ProgramCircuit] = field(default_factory=list)
    pwb_layout_offset: tuple[float, float] = (0.0, 0.0)
    circuit_layout_offset: tuple[float, float] = (0.0, 0.0)
    clamp_offset: float | None = None
    placements: list[ProgramPlacement] = field(default_factory=list)
    components: list[ProgramComponent] = field(default_factory=list)
    fiducials: list[ProgramFiducial] = field(default_factory=list)
    # Header completeness, e.g. {"component": (35, 34)} from HdCompo[total comp].
    counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    # Structure that was not understood (reported, never fatal).
    notes: list[str] = field(default_factory=list)

    @property
    def origin(self) -> tuple[float, float]:
        """P in the program's panel frame."""
        return (self.width - self.pwb_layout_offset[0], -self.pwb_layout_offset[1])


# -------------------------------------------------------------------- transforms
def rigid(rotation: float, mirror: bool) -> Transform:
    """Mirror X (optional), then rotate CCW: the project's circuit convention."""
    t = Transform.rotation_ccw(rotation)
    return t @ Transform.mirror_x() if mirror else t


def rotation90(deg: int) -> Transform:
    """Exact CCW rotation by a multiple of 90°."""
    a, b, c, d = {0: (1, 0, 0, 1), 90: (0, -1, 1, 0), 180: (-1, 0, 0, -1), 270: (0, 1, -1, 0)}[deg % 360]
    return Transform(float(a), float(b), float(c), float(d))


def linear(t: Transform) -> Transform:
    return Transform(t.a, t.b, t.c, t.d)


def direction_angle(t: Transform, theta: float) -> float:
    """CCW angle of a part rotated ``theta`` once ``t`` is applied: the direction of its X axis."""
    rad = math.radians(theta)
    cx, sx = math.cos(rad), math.sin(rad)
    return norm_angle(math.degrees(math.atan2(t.c * cx + t.d * sx, t.a * cx + t.b * sx)))


def circuit_transforms(project: PanelProject) -> list[Transform]:
    """Circuit-relative coordinates -> project panel frame, one per circuit (project order)."""
    ref = project.circuit_reference
    t1 = Transform.translation(ref.x, ref.y) @ rigid(ref.rotation, ref.mirror)
    out = []
    for c in project.circuits:
        rel = (
            Transform.translation(ref.x + c.dx, ref.y + c.dy)
            @ rigid(c.rotation, c.mirror)
            @ Transform.translation(-ref.x, -ref.y)
        )
        out.append(rel @ t1)
    return out


def panel_outline(project: PanelProject) -> list[tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in project.panel.outline]
    if len(pts) >= 3:
        return pts
    w, h = project.panel.width, project.panel.height
    return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]


def bbox(points) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def placement_sides(project: PanelProject) -> set[str]:
    return {p.layer for p in project.placements}


def panel_side(project: PanelProject) -> str:
    """'top', 'bottom', or 'mixed' (placements on both layers; refused by the checks)."""
    sides = placement_sides(project)
    if sides == {"bottom"}:
        return "bottom"
    if len(sides) > 1:
        return "mixed"
    return "top"


@dataclass(frozen=True)
class MachineTransform:
    """Project panel frame -> program panel frame (lower-left corner at 0,0)."""

    side: str  # "top" | "bottom"
    flip: str | None  # None | "left-right" | "front-back"
    rotation: int  # CCW degrees, applied after the flip
    transform: Transform
    width: float  # program panel
    height: float

    def point(self, x: float, y: float) -> tuple[float, float]:
        return self.transform.apply(x, y)

    def angle(self, theta: float) -> float:
        return direction_angle(self.transform, theta)

    def describe(self) -> str:
        flip = f"{self.flip} flip, then " if self.flip else ""
        return f"{self.side} layer: {flip}rotated {self.rotation}° CCW"


def machine_transform(project: PanelProject, settings: IssSettings, side: str | None = None) -> MachineTransform:
    side = side or panel_side(project)
    outline = panel_outline(project)
    x0, y0, x1, y1 = bbox(outline)
    flip = settings.bottom_flip if side == "bottom" else None
    t = Transform.identity()
    if flip == "left-right":
        t = Transform(a=-1.0, tx=x0 + x1)
    elif flip == "front-back":
        t = Transform(d=-1.0, ty=y0 + y1)
    if settings.panel_rotation == "auto":
        rotation = 90 if (y1 - y0) > (x1 - x0) + 1e-6 else 0
    else:
        rotation = int(settings.panel_rotation) % 360
    t = rotation90(rotation) @ t
    mx0, my0, mx1, my1 = bbox([t.apply(x, y) for x, y in outline])
    t = Transform.translation(-mx0, -my0) @ t
    return MachineTransform(
        side="bottom" if side == "bottom" else "top",
        flip=flip,
        rotation=rotation,
        transform=t,
        width=mx1 - mx0,
        height=my1 - my0,
    )


# -------------------------------------------------------------------- layout
@dataclass
class IssLayout:
    """The program to write plus how it was derived (for the report, checks and preview)."""

    program: Program
    machine: MachineTransform
    # P in the program panel frame, and the same point in circuit 1's own frame.
    origin: tuple[float, float] = (0.0, 0.0)
    origin_circuit: tuple[float, float] = (0.0, 0.0)
    # Circuit-frame -> program-frame transform per circuit (project order).
    circuit_frames: list[Transform] = field(default_factory=list)
    # Circuit numbers of the project, in program order (allocation index + 1).
    circuit_numbers: list[int] = field(default_factory=list)
    # Fiducials left out because they are on the other layer.
    other_layer_fiducials: list[str] = field(default_factory=list)
    # Panel-level parts that are not fiducials (not placed).
    skipped_panel_parts: list[str] = field(default_factory=list)
    # Placements whose component name fell back to the part name.
    part_name_fallbacks: list[str] = field(default_factory=list)
    # Components whose placements know different sizes (component_size=body).
    size_conflicts: list[SizeConflict] = field(default_factory=list)
    # Uniform grid for MATRIX output: (nx, ny, pitch_x, pitch_y), or None.
    matrix: tuple[int, int, float, float] | None = None


_PLAIN_NAME = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


def component_name(p) -> str:
    return (p.part_number or "").strip() or (p.part_name or "").strip()


def component_comment(p, attributes: list[str]) -> str:
    for key in attributes:
        value = (p.attributes.get(key) or "").strip()
        if value:
            return value
    return (p.part_name or "").strip()


def mark_name(name: str, index: int) -> str:
    """The project's fiducial name when it is a plain identifier, else F1, F2, ..."""
    return name if _PLAIN_NAME.match(name or "") else f"F{index}"


def is_fiducial_part(project: PanelProject, part, tol: float = 0.05) -> bool:
    names = {f.name for f in project.fiducials}
    if part.designator in names:
        return True
    patterns = project.settings.fiducials.patterns
    if any(fnmatch.fnmatch(part.designator.upper(), pat.upper()) for pat in patterns):
        return True
    return any(math.hypot(part.x - f.x, part.y - f.y) <= tol for f in project.fiducials)


def build_layout(project: PanelProject, settings: IssSettings, pwb_id: str = "") -> IssLayout:
    """Map a project into the ISS frame.  Never raises for content problems: the checks
    report them, and the layout is built from whatever can be mapped."""
    side = panel_side(project)
    machine = machine_transform(project, settings, side)
    m = machine.transform
    frames = [m @ c for c in circuit_transforms(project)]
    if not frames:
        frames = [m @ Transform.translation(project.circuit_reference.x, project.circuit_reference.y)]
    g1 = frames[0]
    l1 = linear(g1)

    # P: circuit 1's transformed reference point, moved to the lower-left of its transformed outline.
    outline = [(float(p[0]), float(p[1])) for p in project.circuit_outline] or [(0.0, 0.0)]
    ox, oy, _, _ = bbox(outline)
    t_outline = [g1.apply(x, y) for x, y in outline]
    lx, ly, ux, uy = bbox(t_outline)
    off = l1.apply(ox, oy)
    origin = (r4(lx - off[0]), r4(ly - off[1]))
    q = g1.inverse().apply(*origin)  # the same point in circuit 1's frame

    circuits = []
    for k, g in enumerate(frames, start=1):
        pk = g.apply(*q)
        rel = linear(g) @ l1.inverse()
        angle = direction_angle(rel, 0.0) if not rel.mirrored else 0.0
        if settings.angle_direction == "cw":
            angle = -angle
        circuits.append(ProgramCircuit(k, r4(pk[0] - origin[0]), r4(pk[1] - origin[1]), angle4(angle)))
    circuits[0] = ProgramCircuit(1, 0.0, 0.0, circuits[0].angle)

    placements: list[ProgramPlacement] = []
    components: dict[str, ProgramComponent] = {}
    members: dict[str, list] = {}  # component name -> its placements
    fallbacks = []
    for p in project.placements:
        name = component_name(p)
        if not (p.part_number or "").strip() and name:
            fallbacks.append(p.designator)
        x, y = g1.apply(p.x, p.y)
        angle = direction_angle(g1, p.rotation)
        if machine.side == "bottom":
            angle += settings.bottom_angle_offset
        if settings.angle_direction == "cw":
            angle = -angle
        angle += settings.angle_offset
        placements.append(
            ProgramPlacement(p.designator, name, r4(x - origin[0]), r4(y - origin[1]), angle4(angle), layer=p.layer)
        )
        if name and name not in components:
            components[name] = ProgramComponent(name, component_comment(p, settings.comment_attributes))
        if name:
            members.setdefault(name, []).append(p)
    conflicts = []
    if settings.component_size == "body":
        edited = size_edits(project)
        offset = settings.angle_offset + (settings.bottom_angle_offset if machine.side == "bottom" else 0.0)
        for name, comp in components.items():
            size, conflict = component_size(name, members[name], edited)
            if quarter_turned(offset):
                size = (size[1], size[0], size[2])
            comp.width, comp.length, comp.height = size
            if conflict is not None:
                conflicts.append(conflict)

    fiducials = []
    other = []
    for f in project.fiducials:
        if f.layer != machine.side:
            other.append(f.name)
            continue
        x, y = m.apply(f.x, f.y)
        fiducials.append(ProgramFiducial(mark_name(f.name, len(fiducials) + 1), r4(x - origin[0]), r4(y - origin[1])))

    width, height = r4(machine.width), r4(machine.height)
    clamp = height / 2 if settings.clamp_offset_y == "auto" else float(settings.clamp_offset_y)
    program = Program(
        kind="generated",
        pwb_id=pwb_id,
        width=width,
        height=height,
        circuit_width=r4(ux - lx),
        circuit_height=r4(uy - ly),
        circuit_layout="MATRIX" if settings.circuit_layout == "matrix" else "NONMATRIX",
        circuits=circuits,
        pwb_layout_offset=(r4(width - origin[0]), r4(-origin[1])),
        circuit_layout_offset=(r4(lx - origin[0]), r4(ly - origin[1])),
        clamp_offset=r4(clamp),
        placements=placements,
        components=list(components.values()),
        fiducials=fiducials,
    )
    layout = IssLayout(
        program=program,
        machine=machine,
        origin=origin,
        origin_circuit=q,
        circuit_frames=frames,
        circuit_numbers=[c.index for c in project.circuits] or [1],
        other_layer_fiducials=other,
        skipped_panel_parts=[p.designator for p in project.panel_parts if not is_fiducial_part(project, p)],
        part_name_fallbacks=fallbacks,
        size_conflicts=conflicts,
    )
    grid = uniform_grid(circuits)
    if grid is not None:
        nx, ny, px, py, x0, y0 = grid
        layout.matrix = (nx, ny, px, py)
        if settings.circuit_layout == "matrix":
            _rebase_matrix(layout, x0, y0)
    return layout


def size_edits(project: PanelProject) -> dict[str, set[str]]:
    """The size fields a Phase 1 edit set, by board-level designator."""
    out: dict[str, set[str]] = {}
    for e in project.component_edits:
        if e.level == "board":
            fields = {f for f in SIZE_FIELDS if getattr(e, f) is not None}
            if fields:
                out[e.designator] = fields
    return out


def component_size(
    name: str, placements: list, edited: dict[str, set[str]]
) -> tuple[tuple[float, float, float], SizeConflict | None]:
    """One size for a component from its placements.  Per dimension: what an edit set
    (edits are deliberate and override the export for the whole component), else what
    the export says; 0 when none knows it.  Known values that differ within that choice
    are a conflict, and the first placement's is used."""
    size: list[float] = []
    differ = []
    for f in SIZE_FIELDS:
        pool = [p for p in placements if f in edited.get(p.designator, ())] or placements
        known = [r4(getattr(p, f)) for p in pool if getattr(p, f) > 0]
        size.append(known[0] if known else 0.0)
        if len(set(known)) > 1:
            differ.append(f)
    if not differ:
        return (size[0], size[1], size[2]), None
    distinct: dict[tuple[float, float, float], str] = {}
    for p in placements:
        distinct.setdefault((r4(p.width), r4(p.length), r4(p.height)), p.designator)
    return (size[0], size[1], size[2]), SizeConflict(name, differ, [(d, s) for s, d in distinct.items()])


def quarter_turned(offset: float) -> bool:
    """Whether an angle offset turns the parts by an odd multiple of 90° (their X and Y swap)."""
    quarters = round(offset / 90.0)
    return abs(offset - quarters * 90.0) < 1e-6 and quarters % 2 == 1


def _rebase_matrix(layout: IssLayout, dx: float, dy: float) -> None:
    """MATRIX output: move P to the grid's lower-left circuit and list the circuits in
    JaNets' grid order.  Panel positions do not change; circuit numbering does (a MATRIX
    block has none of its own)."""
    prog = layout.program
    nx, ny, px, py = layout.matrix
    old = list(layout.circuit_numbers)
    cells = {(round((c.x - dx) / px) if px else 0, round((c.y - dy) / py) if py else 0): i for i, c in enumerate(prog.circuits)}
    layout.circuit_numbers = [old[cells[(i, j)]] for j in range(ny) for i in range(nx)]
    frames = list(layout.circuit_frames)
    layout.circuit_frames = [frames[cells[(i, j)]] for j in range(ny) for i in range(nx)]
    layout.origin = (r4(layout.origin[0] + dx), r4(layout.origin[1] + dy))
    layout.origin_circuit = layout.circuit_frames[0].inverse().apply(*layout.origin)
    prog.circuits = matrix_circuits(nx, ny, px, py)
    # Placement positions and circuitLayoutOffset are relative to each circuit's own P,
    # so they do not change; marks are relative to the program's P.
    for f in prog.fiducials:
        f.x, f.y = r4(f.x - dx), r4(f.y - dy)
    prog.pwb_layout_offset = (r4(prog.width - layout.origin[0]), r4(-layout.origin[1]))


def uniform_grid(circuits: list[ProgramCircuit], tol: float = 1e-3) -> tuple[int, int, float, float, float, float] | None:
    """(nx, ny, pitch_x, pitch_y, x0, y0) when the allocations are a full, uniform,
    unrotated grid whose lower-left allocation is (x0, y0); else None."""
    if not circuits or any(c.angle for c in circuits):
        return None
    xs = _levels([c.x for c in circuits], tol)
    ys = _levels([c.y for c in circuits], tol)
    nx, ny = len(xs), len(ys)
    if nx * ny != len(circuits):
        return None
    px = xs[1] - xs[0] if nx > 1 else 0.0
    py = ys[1] - ys[0] if ny > 1 else 0.0
    if any(abs((xs[i + 1] - xs[i]) - px) > tol for i in range(nx - 1)):
        return None
    if any(abs((ys[j + 1] - ys[j]) - py) > tol for j in range(ny - 1)):
        return None
    cells = {(round((c.x - xs[0]) / px) if px else 0, round((c.y - ys[0]) / py) if py else 0) for c in circuits}
    if len(cells) != len(circuits):
        return None
    return nx, ny, r4(px), r4(py), xs[0], ys[0]


def _levels(values: list[float], tol: float) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def matrix_circuits(nx: int, ny: int, px: float, py: float) -> list[ProgramCircuit]:
    """The allocations a MATRIX block stands for, in JaNets' order (along X first)."""
    return [ProgramCircuit(j * nx + i + 1, r4(i * px), r4(j * py), 0.0) for j in range(ny) for i in range(nx)]
