"""The result of panel identification and its conversion to the project model."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from panelimport import __version__
from panelimport.analysis.checks import PasteResult
from panelimport.analysis.fiducials import FiducialCandidate
from panelimport.analysis.roles import StepDetection, detect_layer_roles
from panelimport.analysis.transforms import GridInfo, Transform, ccw_from_odb, norm_angle
from panelimport.io.bom import Bom
from panelimport.io.odb.job import OdbJob
from panelimport.model.issues import Issue, Severity
from panelimport.model.panel import (
    SIZE_FIELDS,
    Acknowledgement,
    Circuit,
    CircuitReference,
    ComponentEdit,
    Decisions,
    EditFrame,
    Fiducial,
    Grid,
    Numbering,
    PanelOrigin,
    PanelOutline,
    PanelPart,
    PanelProject,
    Placement,
    SourceInfo,
)
from panelimport.settings import Settings

ROUND = 6  # decimals kept in the project file (1 nm, 1 µ°)


def r6(v: float) -> float:
    out = round(float(v), ROUND)
    return 0.0 if out == 0 else out


def angle6(v: float) -> float:
    """An angle rounded like r6 and kept in [0, 360)."""
    return r6(norm_angle(r6(v)))


def normalize_outline(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Counter-clockwise, starting at the vertex nearest the lower-left corner."""
    if len(points) < 3:
        return list(points)
    area = sum(
        points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )
    pts = list(points) if area > 0 else list(reversed(points))
    x0 = min(p[0] for p in pts)
    y0 = min(p[1] for p in pts)
    start = min(range(len(pts)), key=lambda i: ((pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2, i))
    return pts[start:] + pts[:start]


def compose_rotation(theta_ccw: float, tf: Transform) -> float:
    """CCW rotation of a part rotated ``theta_ccw`` in a frame placed by ``tf``."""
    if tf.mirrored:
        return norm_angle(tf.rotation - theta_ccw)
    return norm_angle(tf.rotation + theta_ccw)


@dataclass
class CircuitInfo:
    index: int
    transform: Transform  # board frame -> panel frame
    source: str  # "step-repeat" | "fitted" | "manual"
    residual: float | None = None
    flip: bool = False
    rotation: float = 0.0  # CCW, relative to circuit 1
    mirror: bool = False  # relative to circuit 1
    dx: float = 0.0  # reference point offset from circuit 1, panel frame
    dy: float = 0.0
    outline: list[tuple[float, float]] = field(default_factory=list)  # panel frame
    center: tuple[float, float] = (0.0, 0.0)
    size: tuple[float, float] = (0.0, 0.0)
    label: str = ""
    # Flattened panels: where each copy actually is (designator -> x, y, rotation_raw, side).
    positions: dict[str, tuple[float, float, float, str]] | None = None


@dataclass
class PlacementInfo:
    designator: str
    part_name: str
    package: str
    layer: str  # "top" | "bottom"
    x: float  # board frame, mm
    y: float
    rotation_raw: float  # ODB++, clockwise
    rotation: float  # counter-clockwise
    mirror: bool
    attributes: dict[str, str]
    part_number: str = ""
    toeprints: list[tuple[float, float]] = field(default_factory=list)
    body: list[list[tuple[float, float]]] = field(default_factory=list)  # board frame
    width: float = 0.0  # body size, mm (see model.panel); 0 = unknown
    length: float = 0.0
    height: float = 0.0
    paste: PasteResult | None = None
    written: str = ""  # designator as written in the export
    state: str = ""  # "" as exported | "edited" | "added" | "removed"
    export: dict[str, object] = field(default_factory=dict)  # export values of the fields an edit changed
    edit: ComponentEdit | None = None

    @property
    def moved(self) -> bool:
        """Placed somewhere other than the export says (added, or position/rotation/side edited)."""
        return self.state == "added" or any(k in self.export for k in ("x", "y", "rotation", "layer"))


@dataclass
class PanelPartInfo:
    designator: str
    part_name: str
    package: str
    layer: str
    x: float  # panel frame
    y: float
    rotation: float  # CCW
    rotation_raw: float
    step: str
    part_number: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    width: float = 0.0  # as PlacementInfo
    length: float = 0.0
    height: float = 0.0
    state: str = ""  # as PlacementInfo.state
    export: dict[str, object] = field(default_factory=dict)
    edit: ComponentEdit | None = None


@dataclass
class StepInstanceInfo:
    """A step drawn on the panel: the panel itself, a sub-panel or a circuit."""

    job: OdbJob
    step: str
    transform: Transform  # step frame -> panel frame
    circuit: int | None = None
    flip: bool = False


@dataclass
class LayerDraw:
    role: str  # role on the panel (swapped for flipped instances)
    job: OdbJob
    step: str
    layer: str
    transform: Transform
    circuit: int | None = None


def _swap(role: str) -> str:
    if role.endswith("_top"):
        return role[:-4] + "_bottom"
    if role.endswith("_bottom"):
        return role[:-7] + "_top"
    return role


@dataclass
class PanelAnalysis:
    job: OdbJob
    settings: Settings
    decisions: Decisions
    mode: str = "unknown"  # "panel" | "flattened" | "single-board" | "unknown"
    detection: StepDetection | None = None
    panel_step: str | None = None
    board_step: str | None = None
    layer_roles: dict[str, str] = field(default_factory=dict)
    panel_origin: tuple[float, float] = (0.0, 0.0)  # in ODB++ panel-step coordinates
    panel_outline: list[tuple[float, float]] = field(default_factory=list)  # panel frame
    board_outline: list[tuple[float, float]] = field(default_factory=list)  # board frame
    reference_kind: str = ""
    reference_board: tuple[float, float] = (0.0, 0.0)
    circuits: list[CircuitInfo] = field(default_factory=list)
    grid: GridInfo | None = None
    grid_source: str = ""
    placements: list[PlacementInfo] = field(default_factory=list)  # what is placed per circuit
    panel_parts: list[PanelPartInfo] = field(default_factory=list)  # what is placed once
    removed_placements: list[PlacementInfo] = field(default_factory=list)  # removed by an edit
    removed_panel_parts: list[PanelPartInfo] = field(default_factory=list)
    component_edits: list[ComponentEdit] = field(default_factory=list)  # in this analysis's frame
    instances: list[StepInstanceInfo] = field(default_factory=list)
    fiducial_candidates: list[FiducialCandidate] = field(default_factory=list)
    fiducials: list[FiducialCandidate] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    acknowledged: set = field(default_factory=set)
    numbering: Numbering = field(default_factory=Numbering)
    part_number_attribute: str = ""
    attribute_keys: list[str] = field(default_factory=list)
    suggested_suffix: str | None = None
    copy_count: int = 0
    bom: Bom | None = None
    panel_job: OdbJob | None = None

    # ------------------------------------------------------------------ status
    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    def is_acknowledged(self, issue: Issue) -> bool:
        return issue.key in self.acknowledged

    @property
    def unacknowledged_warnings(self) -> list[Issue]:
        return [i for i in self.warnings if not self.is_acknowledged(i)]

    def can_confirm(self) -> tuple[bool, str]:
        if not self.circuits:
            return False, "No circuits identified"
        if self.mode == "single-board" and self.decisions.single_board is None:
            return False, "Single-board mode is not confirmed"
        if self.errors:
            n = len(self.errors)
            return False, f"{n} error{'s' if n != 1 else ''} must be fixed first"
        if self.unacknowledged_warnings:
            n = len(self.unacknowledged_warnings)
            return False, f"{n} warning{'s' if n != 1 else ''} must be acknowledged first"
        return True, ""

    @property
    def confirmed(self) -> bool:
        return self.decisions.confirmed and self.can_confirm()[0]

    def issue_counts(self) -> dict[str, int]:
        out = {"error": 0, "warning": 0, "info": 0}
        for i in self.issues:
            out[i.severity.value] += 1
        return out

    # ------------------------------------------------------------------ summary
    @property
    def summary(self) -> str:
        n = len(self.circuits)
        if self.mode == "single-board" and self.decisions.single_board is None:
            return "Single board (no STEP-REPEAT, every designator once): confirm single-board mode"
        if n == 0 or self.grid is None:
            return "No circuits identified"
        g = self.grid
        source = {
            "step-repeat": "from STEP-REPEAT",
            "fitted": "from repeated designators",
            "manual": "from manual entry",
        }.get(self.grid_source, self.grid_source)
        text = (
            f"{n} circuit{'s' if n != 1 else ''}, {g.cols} × {g.rows}, "
            f"pitch {g.pitch_x:.3f} × {g.pitch_y:.3f} mm, {source}"
        )
        if not g.uniform and n > 1:
            text += ", non-uniform"
        return text

    @property
    def edit_frame(self) -> EditFrame:
        """The frame this analysis expresses component-edit coordinates in."""
        manual = self.mode == "single-board" and self.decisions.single_board is not None
        return EditFrame(
            mode=self.mode,
            reference=self.reference_kind,
            first=self.numbering.first,
            order=self.numbering.order,
            panel_origin="manual" if manual else self.settings.panel_origin,
        )

    # ------------------------------------------------------------------ geometry
    def layer_draws(self) -> list[LayerDraw]:
        draws = []
        role_cache: dict[int, dict[str, str]] = {}
        for inst in self.instances:
            if inst.job is self.job:
                roles = self.layer_roles
            else:
                roles = role_cache.setdefault(id(inst.job), detect_layer_roles(inst.job.matrix)[0])
            for role, layer in roles.items():
                if role == "outline":
                    continue
                draws.append(
                    LayerDraw(_swap(role) if inst.flip else role, inst.job, inst.step, layer, inst.transform, inst.circuit)
                )
        return draws

    def circuit_position(self, p: PlacementInfo, circuit: CircuitInfo) -> tuple[float, float, float]:
        """Panel-frame position and CCW rotation of a placement in a circuit."""
        if circuit.positions is not None:
            hit = circuit.positions.get(p.designator)
            if hit is not None:
                return hit[0], hit[1], ccw_from_odb(hit[2])
        x, y = circuit.transform.apply(p.x, p.y)
        return x, y, compose_rotation(p.rotation, circuit.transform)

    @cached_property
    def _regions(self) -> list:
        return [(c, prep(Polygon(c.outline).buffer(1e-6))) for c in self.circuits if len(c.outline) >= 3]

    @cached_property
    def _inverses(self) -> dict[int, Transform]:
        return {c.index: c.transform.inverse() for c in self.circuits}

    def circuit_relative(self, x: float, y: float) -> tuple[int, float, float] | None:
        """Circuit number and circuit-relative coordinates of a panel-frame point."""
        pt = Point(x, y)
        for c, region in self._regions:
            if region.contains(pt):
                bx, by = self._inverses[c.index].apply(x, y)
                return c.index, bx - self.reference_board[0], by - self.reference_board[1]
        return None

    # ------------------------------------------------------------------ project
    def to_project(self, project_path: str | os.PathLike | None = None) -> PanelProject:
        ref_x, ref_y = self.reference_board
        c1 = self.circuits[0] if self.circuits else None
        ref_panel = c1.transform.apply(ref_x, ref_y) if c1 else (0.0, 0.0)
        xs = [p[0] for p in self.panel_outline] or [0.0]
        ys = [p[1] for p in self.panel_outline] or [0.0]
        g = self.grid
        src_path = str(self.job.path)
        if project_path is not None:
            src_path = relative_source_path(self.job.path, Path(project_path))
        origin_kind = "manual" if self.mode == "single-board" else self.settings.panel_origin
        return PanelProject(
            generator=f"panelimport {__version__}",
            source=SourceInfo(
                kind="odb++",
                path=src_path,
                sha256=self.job.sha256,
                panel_step=self.panel_step,
                board_step=self.board_step,
                container=self.job.source.kind,
            ),
            mode=self.mode,
            panel=PanelOutline(
                width=r6(max(xs) - min(xs)),
                height=r6(max(ys) - min(ys)),
                outline=[[r6(x), r6(y)] for x, y in normalize_outline(self.panel_outline)],
                origin=PanelOrigin(kind=origin_kind, odb_x=r6(self.panel_origin[0]), odb_y=r6(self.panel_origin[1])),
            ),
            grid=Grid(
                cols=g.cols if g else 0,
                rows=g.rows if g else 0,
                pitch_x=r6(g.pitch_x) if g else 0.0,
                pitch_y=r6(g.pitch_y) if g else 0.0,
                uniform=bool(g.uniform) if g else True,
                source=self.grid_source,
            ),
            numbering=Numbering(self.numbering.first, self.numbering.order),
            circuit_reference=CircuitReference(
                kind=self.reference_kind,
                x=r6(ref_panel[0]),
                y=r6(ref_panel[1]),
                board_x=r6(ref_x),
                board_y=r6(ref_y),
                rotation=r6(c1.transform.rotation) if c1 else 0.0,
                mirror=bool(c1.transform.mirrored) if c1 else False,
            ),
            circuit_outline=[[r6(x - ref_x), r6(y - ref_y)] for x, y in normalize_outline(self.board_outline)],
            circuits=[
                Circuit(
                    index=c.index,
                    dx=r6(c.dx),
                    dy=r6(c.dy),
                    rotation=r6(c.rotation),
                    mirror=c.mirror,
                    source=c.source,
                    residual=None if c.residual is None else r6(c.residual),
                )
                for c in self.circuits
            ],
            part_number_attribute=self.part_number_attribute,
            placements=[
                Placement(
                    designator=p.designator,
                    part_name=p.part_name,
                    part_number=p.part_number,
                    package=p.package,
                    layer=p.layer,
                    x=r6(p.x - ref_x),
                    y=r6(p.y - ref_y),
                    rotation=r6(p.rotation),
                    rotation_raw=r6(p.rotation_raw),
                    attributes=dict(sorted(p.attributes.items())),
                    width=r6(p.width),
                    length=r6(p.length),
                    height=r6(p.height),
                )
                for p in self.placements
            ],
            panel_parts=[
                PanelPart(
                    designator=p.designator,
                    x=r6(p.x),
                    y=r6(p.y),
                    layer=p.layer,
                    part_name=p.part_name,
                    part_number=p.part_number,
                    package=p.package,
                    rotation=r6(p.rotation),
                    rotation_raw=r6(p.rotation_raw),
                    width=r6(p.width),
                    length=r6(p.length),
                    height=r6(p.height),
                )
                for p in self.panel_parts
            ],
            component_edits=[rounded_edit(e) for e in self.component_edits],
            fiducials=[
                Fiducial(
                    name=f.name,
                    x=r6(f.x),
                    y=r6(f.y),
                    source=f.source,
                    layer=f.side,
                    diameter=None if f.diameter is None else r6(f.diameter),
                )
                for f in self.fiducials
            ],
            acknowledged_warnings=sorted(
                {Acknowledgement.of(i) for i in self.issues if self.is_acknowledged(i)},
                key=lambda a: (a.code, a.designator or "", a.circuit or 0, a.subject or ""),
            ),
            layer_roles=dict(sorted(self.layer_roles.items())),
            panel_level_designators=sorted(self.decisions.panel_level),
            single_board=self.decisions.single_board,
            settings=self.settings,
        )


def rounded_edit(e: ComponentEdit) -> ComponentEdit:
    """An edit with its numbers rounded like the rest of the project."""
    return replace(
        e,
        x=None if e.x is None else r6(e.x),
        y=None if e.y is None else r6(e.y),
        rotation=None if e.rotation is None else angle6(e.rotation),
        **{f: r6(getattr(e, f)) for f in SIZE_FIELDS if getattr(e, f) is not None},
    )


def relative_source_path(source: str | os.PathLike, project: Path) -> str:
    """The source path relative to the project file's folder when possible."""
    try:
        return Path(os.path.relpath(Path(source).resolve(), Path(project).resolve().parent)).as_posix()
    except ValueError:  # different drives on Windows
        return str(Path(source).resolve())
