"""Checks before an ISS program is written.

Errors stop the write; warnings go in the report (and the GUI shows both before
saving).  Issues reuse :mod:`panelimport.model.issues`, so the CLI and the GUI format
them exactly as Phase 1 does.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from panelimport.iss.mapping import IssLayout, build_layout, circuit_transforms, panel_outline, placement_sides
from panelimport.iss.settings import IssSettings
from panelimport.model.issues import Issue, error, sort_issues, warning
from panelimport.model.panel import PanelProject

#: Characters JaNets is known to accept in a component name.
_NAME_OK = re.compile(r"^[A-Za-z0-9._-]+$")
#: Positions within this of an outline count as on it (rounding in the project file).
EDGE_TOL = 1e-4


@dataclass
class Prepared:
    """A project mapped into the ISS frame, with everything the checks found."""

    project: PanelProject
    settings: IssSettings
    layout: IssLayout | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.is_error]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.is_warning]

    @property
    def can_write(self) -> bool:
        return self.layout is not None and not self.errors


def prepare(
    project: PanelProject,
    settings: IssSettings,
    *,
    pwb_id: str = "",
    confirmed: bool = True,
    source_issue: Issue | None = None,
) -> Prepared:
    """Map ``project`` and run every check.  ``pwb_id`` is used when the setting is empty."""
    issues: list[Issue] = []
    structural = _structure(project, confirmed)
    issues += structural
    if structural:
        return Prepared(project, settings, None, sort_issues(issues))
    layout = build_layout(project, settings, settings.pwb_id or pwb_id)
    issues += check_project(project, settings, layout)
    if source_issue is not None and source_issue.code == "source_changed":
        issues.append(
            warning(
                "source_changed",
                source_issue.message + "; the program is written from the saved project",
                subject="source",
                data=source_issue.data,
            )
        )
    return Prepared(project, settings, layout, sort_issues(issues))


def _structure(project: PanelProject, confirmed: bool) -> list[Issue]:
    """project_invalid: what a confirmed, saved project always has."""
    problems = []
    if not confirmed:
        problems.append("the panel is not confirmed")
    if not project.circuits:
        problems.append("it has no circuits")
    elif [c.index for c in project.circuits] != list(range(1, len(project.circuits) + 1)):
        problems.append("its circuits are not numbered 1..N")
    if not (project.panel.width > 0 and project.panel.height > 0):
        problems.append("it has no panel outline")
    if len(project.circuit_outline) < 3:
        problems.append("it has no circuit outline")
    if project.mode == "single-board" and project.single_board is None:
        problems.append("its single-board setup is missing")
    if not problems:
        return []
    return [error("project_invalid", "Not a confirmed panel project: " + "; ".join(problems), subject="project")]


def check_project(project: PanelProject, settings: IssSettings, layout: IssLayout) -> list[Issue]:
    issues: list[Issue] = []
    side = layout.machine.side
    sides = placement_sides(project)

    # ------------------------------------------------------------ sides and placements
    if not project.placements:
        issues.append(error("no_placements", "Nothing to place: the project has no placements", subject="placements"))
    if len(sides) > 1:
        counts = Counter(p.layer for p in project.placements)
        issues.append(
            error(
                "mixed_sides",
                f"Placements on both layers (top {counts['top']}, bottom {counts['bottom']}); "
                "a program places one side only. Remove the other side's parts in Phase 1",
                subject="sides",
                data=dict(counts),
            )
        )
    elif side == "bottom":
        issues.append(
            warning(
                "bottom_angles_unverified",
                "Bottom-layer program: angles are mirrored with the panel "
                f"({'180° − θ' if layout.machine.flip == 'left-right' else '−θ'}) and turned "
                f"{layout.machine.rotation}°, a mapping not yet verified on the machine; check rotations in JaNets",
                subject="bottom",
            )
        )

    # ------------------------------------------------------------ fiducials
    on_side = [f for f in project.fiducials if f.layer == side]
    if len(on_side) < 2:
        other = f" ({len(layout.other_layer_fiducials)} on the other layer)" if layout.other_layer_fiducials else ""
        issues.append(
            error(
                "no_fiducials",
                f"{len(on_side)} fiducial(s) on the {side} layer{other}; at least 2 are needed. Pick them in Phase 1",
                subject="fiducials",
            )
        )
    elif len(on_side) > 3:
        issues.append(
            error("too_many_fiducials", f"{len(on_side)} fiducials on the {side} layer; an ISS program takes at most 3", subject="fiducials")
        )

    # ------------------------------------------------------------ circuits
    ref = project.circuit_reference
    if ref.mirror:
        issues.append(error("mirrored_circuit", "Circuit 1 is mirrored on the panel", circuit=1, subject="circuit"))
    for c in project.circuits:
        if c.mirror:
            issues.append(error("mirrored_circuit", f"Circuit {c.index} is mirrored relative to circuit 1", circuit=c.index))
    for number, c in zip(layout.circuit_numbers, layout.program.circuits):
        if c.angle:
            issues.append(
                warning(
                    "rotated_circuit",
                    f"Circuit {number} is written with allocation angle {c.angle:g}°; rotated allocations have never "
                    "been tested in JaNets",
                    circuit=number,
                )
            )
    if settings.circuit_layout == "matrix" and layout.matrix is None:
        issues.append(
            error(
                "matrix_layout",
                "circuit_layout=matrix needs a full, uniform, unrotated grid of circuits; use nonmatrix",
                subject="layout",
            )
        )
    if settings.component_size == "body":
        issues.append(
            error(
                "component_size_body",
                "component_size=body needs package body sizes, which the project file does not carry; use zero",
                subject="component_size",
            )
        )

    # ------------------------------------------------------------ component names
    for p in project.placements:
        if not (p.part_number or "").strip():
            if (p.part_name or "").strip():
                issues.append(
                    warning("no_part_number", f"No part number; the part name '{p.part_name}' is used as the component name", designator=p.designator)
                )
            else:
                issues.append(error("no_component_name", "No part number and no part name: no component name", designator=p.designator))
    seen = set()
    for pl in layout.program.placements:
        name = pl.component
        if name and name not in seen:
            seen.add(name)
            if not _NAME_OK.match(name):
                bad = "".join(sorted({ch for ch in name if not _NAME_OK.match(ch)}))
                issues.append(
                    warning(
                        "component_name_chars",
                        f"Component name '{name}' has characters outside A-Z a-z 0-9 - _ . ({bad!r})",
                        designator=pl.designator,
                        subject=name,
                    )
                )
    for d, n in Counter(p.designator for p in project.placements).items():
        if n > 1:
            issues.append(error("duplicate_designator", f"Designator {d} appears {n} times in circuit 1", designator=d))

    # ------------------------------------------------------------ panel-level parts
    if layout.skipped_panel_parts:
        names = ", ".join(layout.skipped_panel_parts)
        issues.append(
            warning(
                "panel_parts_skipped",
                f"Panel-level parts that are not fiducials are left out (placed once, no circuit for them): {names}",
                subject="panel_parts",
                data={"designators": list(layout.skipped_panel_parts)},
            )
        )

    issues += _outline_checks(project)
    return issues


def _outline_checks(project: PanelProject) -> list[Issue]:
    issues: list[Issue] = []
    if len(project.circuit_outline) >= 3:
        circuit = prep(Polygon(project.circuit_outline).buffer(EDGE_TOL))
        for p in project.placements:
            if not circuit.contains(Point(p.x, p.y)):
                issues.append(
                    warning("outside_circuit", f"Placement at ({p.x:.3f}, {p.y:.3f}) is outside the circuit outline", designator=p.designator)
                )
    panel = prep(Polygon(panel_outline(project)).buffer(EDGE_TOL))
    frames = circuit_transforms(project)
    for p in project.placements:
        for c, tf in zip(project.circuits, frames):
            x, y = tf.apply(p.x, p.y)
            if not panel.contains(Point(x, y)):
                issues.append(
                    error(
                        "outside_panel",
                        f"Placement at panel ({x:.3f}, {y:.3f}) is outside the panel outline",
                        designator=p.designator,
                        circuit=c.index,
                        location=(x, y),
                    )
                )
    for f in project.fiducials:
        if not panel.contains(Point(f.x, f.y)):
            issues.append(
                error(
                    "outside_panel",
                    f"Fiducial {f.name} at ({f.x:.3f}, {f.y:.3f}) is outside the panel outline",
                    subject=f.name,
                    location=(f.x, f.y),
                )
            )
    return issues
