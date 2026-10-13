"""Rebuild a displayable :class:`PanelAnalysis` from a saved project alone.

Used when a project is reopened but its source export is missing: the saved model is
shown read-only (no layers, no re-analysis).
"""

from __future__ import annotations

from panelimport.analysis.fiducials import FiducialCandidate
from panelimport.analysis.result import CircuitInfo, PanelAnalysis, PanelPartInfo, PlacementInfo
from panelimport.analysis.transforms import GridInfo, Transform, norm_angle
from panelimport.model.issues import Issue
from panelimport.model.panel import Decisions, PanelProject


def _rigid(rotation: float, mirror: bool) -> Transform:
    t = Transform.rotation_ccw(rotation)
    return t @ Transform.mirror_x() if mirror else t


def snapshot_from_project(project: PanelProject, issues: list[Issue] | None = None) -> PanelAnalysis:
    ref = project.circuit_reference
    ref_board = (ref.board_x, ref.board_y)
    t1 = Transform.translation(ref.x, ref.y) @ _rigid(ref.rotation, ref.mirror) @ Transform.translation(-ref.board_x, -ref.board_y)
    board_outline = [(x + ref.board_x, y + ref.board_y) for x, y in project.circuit_outline]
    circuits = []
    for c in project.circuits:
        rel = (
            Transform.translation(ref.x + c.dx, ref.y + c.dy)
            @ _rigid(c.rotation, c.mirror)
            @ Transform.translation(-ref.x, -ref.y)
        )
        tf = rel @ t1
        outline = [tf.apply(x, y) for x, y in board_outline]
        xs = [p[0] for p in outline] or [0.0]
        ys = [p[1] for p in outline] or [0.0]
        circuits.append(
            CircuitInfo(
                index=c.index,
                transform=tf,
                source=c.source,
                residual=c.residual,
                rotation=c.rotation,
                mirror=c.mirror,
                dx=c.dx,
                dy=c.dy,
                outline=outline,
                center=((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2),
                size=(max(xs) - min(xs), max(ys) - min(ys)),
            )
        )
    decisions = Decisions(single_board=project.single_board, confirmed=True)
    a = PanelAnalysis(job=None, settings=project.settings, decisions=decisions)  # type: ignore[arg-type]
    a.mode = project.mode
    a.panel_step = project.source.panel_step
    a.board_step = project.source.board_step
    a.layer_roles = dict(project.layer_roles)
    a.panel_outline = [(p[0], p[1]) for p in project.panel.outline]
    a.board_outline = board_outline
    a.reference_kind = ref.kind
    a.reference_board = ref_board
    a.circuits = circuits
    g = project.grid
    a.grid = GridInfo(g.cols, g.rows, g.pitch_x, g.pitch_y, g.uniform, 0.0, [], [])
    a.grid_source = g.source
    a.numbering = project.numbering
    a.part_number_attribute = project.part_number_attribute
    a.placements = [
        PlacementInfo(
            designator=p.designator,
            part_name=p.part_name,
            package=p.package,
            layer=p.layer,
            x=p.x + ref.board_x,
            y=p.y + ref.board_y,
            rotation_raw=p.rotation_raw,
            rotation=p.rotation,
            mirror=p.layer == "bottom",
            attributes=dict(p.attributes),
            part_number=p.part_number,
            written=p.designator,
        )
        for p in project.placements
    ]
    a.attribute_keys = sorted({k for p in a.placements for k in p.attributes})
    a.panel_parts = [
        PanelPartInfo(p.designator, p.part_name, p.package, p.layer, p.x, p.y, p.rotation, norm_angle(p.rotation_raw), "")
        for p in project.panel_parts
    ]
    a.fiducial_candidates = [
        FiducialCandidate(f.name, f.x, f.y, f.layer, "panel", [f.source], None, f.diameter) for f in project.fiducials
    ]
    a.fiducials = list(a.fiducial_candidates)
    a.issues = list(issues or [])
    a.acknowledged = {ack.key for ack in project.acknowledged_warnings}
    return a
