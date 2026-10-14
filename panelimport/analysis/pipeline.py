"""Panel identification: ODB++ job + settings + user decisions -> :class:`PanelAnalysis`.

Modes:

* ``panel`` — the panel step has STEP-REPEAT blocks; circuits are read from them.
* ``flattened`` — no STEP-REPEAT, designators repeat: circuits are reconstructed from
  the repeated designators (``analysis.grouping``) and fitted transforms.
* ``single-board`` — no STEP-REPEAT and every designator appears once: the user
  confirms and enters the circuit grid.  The mode is never chosen silently.

Frames: the *board frame* is the board step's own coordinate system (for a flattened
panel: circuit 1 where it sits in the panel step).  The *panel frame* is the panel
step's coordinate system shifted so the panel origin (setting ``panel_origin``) is 0,0.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
from shapely.geometry import Polygon

from panelimport.analysis import grouping
from panelimport.analysis.edits import apply_edits
from panelimport.analysis.checks import (
    CircuitGeometry,
    ExpectedCopy,
    PartToCheck,
    crosscheck,
    duplicate_designators,
    orientation_checks,
    paste_check,
)
from panelimport.analysis.fiducials import (
    MAX_PANEL_FIDUCIALS,
    FiducialCandidate,
    classify,
    feature_candidates,
    feature_name,
    make_regions,
    matches_pattern,
    merge,
    transform_candidate,
)
from panelimport.analysis.layers import pad_set
from panelimport.analysis.result import (
    CircuitInfo,
    LayerDraw,
    PanelAnalysis,
    PanelPartInfo,
    PlacementInfo,
    StepInstanceInfo,
    compose_rotation,
)
from panelimport.analysis.roles import LAYER_ROLES, detect_layer_roles, detect_steps
from panelimport.analysis.step_repeat import Instance, expand
from panelimport.analysis.transforms import (
    Transform,
    ccw_from_odb,
    derive_grid,
    fit_rigid,
    norm_angle,
    number_circuits,
)
from panelimport.io.bom import Bom
from panelimport.io.odb.components import OdbComponent
from panelimport.io.odb.eda import Package
from panelimport.io.odb.job import OdbJob
from panelimport.model.issues import Issue, Severity, error, info, sort_issues, warning
from panelimport.model.panel import Decisions, EditFrame, Numbering, PanelProject
from panelimport.settings import CORNERS, ORDERS, PANEL_ORIGINS, REFERENCE_KINDS, Settings

__all__ = ["analyze", "decisions_from_project", "with_changes", "PanelAnalysis", "LayerDraw"]


# ====================================================================== helpers
def _missing(rel: str) -> Issue:
    return error("missing_file", f"Missing required file {rel}", file=rel, subject=rel)


def _step_components(job: OdbJob, step: str) -> list[tuple[str, OdbComponent]]:
    out = []
    for side, layer in sorted(job.component_layers().items(), key=lambda kv: kv[0] != "top"):
        cf = job.components(step, layer.name)
        if cf is not None:
            out.extend((side, c) for c in cf.components)
    return out


def _package(job: OdbJob, step: str, comp: OdbComponent) -> Package | None:
    eda = job.eda(step)
    if eda is None or not (0 <= comp.pkg_ref < len(eda.packages)):
        return None
    return eda.packages[comp.pkg_ref]


def component_transform(comp: OdbComponent, pkg: Package | None) -> Transform:
    """Package frame -> step frame for a component (rotate clockwise, then mirror).

    For mirrored parts the order is checked against the toeprints: if mirroring before
    rotating matches the TOP records better, that order is used for the body outline.
    """
    base = Transform.odb_placement(comp.x, comp.y, comp.rotation, comp.mirror)
    if not comp.mirror or pkg is None or not comp.toeprints or not pkg.pins:
        return base
    alt = Transform.translation(comp.x, comp.y) @ Transform.rotation_cw(comp.rotation) @ Transform.mirror_x()

    def err(t: Transform) -> float:
        total = 0.0
        for tp in comp.toeprints:
            if 0 <= tp.pin_num < len(pkg.pins):
                pin = pkg.pins[tp.pin_num]
                x, y = t.apply(pin.x, pin.y)
                total += math.hypot(x - tp.x, y - tp.y)
        return total

    return alt if err(alt) + 1e-9 < err(base) else base


def _bbox(points) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _circuit_shape(tf: Transform, outline: list[tuple[float, float]]):
    pts = [tf.apply(x, y) for x, y in outline]
    x0, y0, x1, y1 = _bbox(outline)
    center = tf.apply((x0 + x1) / 2, (y0 + y1) / 2)
    bx0, by0, bx1, by1 = _bbox(pts)
    return pts, center, (bx1 - bx0, by1 - by0)


def _panel_part(job: OdbJob, side: str, comp: OdbComponent, tf: Transform, flip: bool, step: str) -> PanelPartInfo:
    x, y = tf.apply(comp.x, comp.y)
    if flip:
        side = "bottom" if side == "top" else "top"
    rot = compose_rotation(ccw_from_odb(comp.rotation), tf)
    pkg = _package(job, step, comp)
    return PanelPartInfo(
        comp.name,
        comp.part_name,
        pkg.name if pkg else "",
        side,
        x,
        y,
        rot,
        norm_angle(-rot),
        step,
        attributes=comp.all_attributes(),
    )


def _placements(job: OdbJob, step: str, comps: list[tuple[str, OdbComponent]]) -> list[PlacementInfo]:
    out = []
    for side, comp in comps:
        pkg = _package(job, step, comp)
        tf = component_transform(comp, pkg)
        body = []
        if pkg is not None:
            for shape in pkg.outlines:
                for poly in shape.polygons():
                    body.append([tf.apply(x, y) for x, y in poly])
        out.append(
            PlacementInfo(
                designator=comp.name,
                part_name=comp.part_name,
                package=pkg.name if pkg else "",
                layer=side,
                x=comp.x,
                y=comp.y,
                rotation_raw=comp.rotation,
                rotation=ccw_from_odb(comp.rotation),
                mirror=comp.mirror,
                attributes=comp.all_attributes(),
                toeprints=[(t.x, t.y) for t in comp.toeprints],
                body=body,
                written=comp.name,
            )
        )
    return out


def _package_issues(job: OdbJob, step: str, comps: list[tuple[str, OdbComponent]]) -> list[Issue]:
    if not comps:
        return []
    eda = job.eda(step)
    if eda is None:
        return [_missing(f"steps/{step}/eda/data")]
    bad = [c.name for _s, c in comps if not (0 <= c.pkg_ref < len(eda.packages))]
    if not bad:
        return []
    return [
        warning(
            "unknown_package",
            f"{len(bad)} component(s) reference a package missing from eda/data: "
            f"{', '.join(bad[:8])}{'…' if len(bad) > 8 else ''}",
            subject=f"{step}:packages",
        )
    ]


@dataclass
class _ModeContext:
    """What a mode step leaves for the steps that run after the component edits."""

    step: str  # the step the placements (and their paste) come from
    scope: str  # names that step in messages
    copies: list[tuple[int, str, grouping.Copy]] | None = None  # flattened: every copy, by circuit
    # Flattened: numbering -> (that numbering's board frame -> this one, its reference point).
    frame_of: Callable[[str, str], tuple[Transform, tuple[float, float]]] | None = None


def _removed(decisions: Decisions, level: str | None = None) -> set[str]:
    """Designators the user removed (at ``level``, or at either level)."""
    return {
        e.designator
        for e in decisions.component_edits
        if e.removed and not e.added and (level is None or e.level == level)
    }


# ====================================================================== pipeline
def analyze(
    job: OdbJob,
    settings: Settings | None = None,
    decisions: Decisions | None = None,
    *,
    bom: Bom | None = None,
    panel_job: OdbJob | None = None,
) -> PanelAnalysis:
    """Identify the panel.  ``panel_job`` is an optional panel export for single-board mode."""
    settings = settings or Settings()
    decisions = decisions or Decisions()
    a = PanelAnalysis(job=job, settings=settings, decisions=decisions, bom=bom, panel_job=panel_job)
    issues: list[Issue] = []

    first = decisions.numbering_first or settings.circuit1_corner
    order = decisions.numbering_order or settings.numbering_order
    a.numbering = Numbering(first if first in CORNERS else "lower-left", order if order in ORDERS else "row-major")
    ref_kind = decisions.circuit_reference or settings.circuit_reference
    if ref_kind not in REFERENCE_KINDS:
        ref_kind = "profile-lower-left"

    # ------------------------------------------------------------- roles
    det = detect_steps(job)
    a.detection = det
    roles, notes = detect_layer_roles(job.matrix)
    for role, layer in decisions.layer_roles.items():
        if role not in LAYER_ROLES:
            continue
        if layer:
            roles[role] = layer
        else:
            roles.pop(role, None)
    for role, layer in list(roles.items()):
        ml = job.matrix.layer(layer)
        if ml is None:
            issues.append(error("unknown_layer", f"Layer '{layer}' set as {role} is not in the matrix", subject=role))
            roles.pop(role)
        else:
            roles[role] = ml.name
    a.layer_roles = roles
    for note in notes:
        issues.append(info("layer_roles", note, subject=note))

    def canonical(name: str | None) -> str | None:
        if not name:
            return None
        ms = job.matrix.step(name)
        if ms is None:
            issues.append(error("unknown_step", f"Step '{name}' is not in the matrix", subject=name))
            return None
        return ms.name

    panel_step = canonical(decisions.panel_step) or det.panel_step
    board_step = canonical(decisions.board_step) or det.board_step
    if det.ambiguous and decisions.panel_step is None:
        issues.append(
            error(
                "ambiguous_steps",
                f"{det.reason or 'Step roles are ambiguous'}. Choose the panel and board steps in the import dialog.",
                subject="steps",
            )
        )
    a.panel_step, a.board_step = panel_step, board_step
    if panel_step is None:
        issues.append(error("no_panel_step", "No step to analyse", subject="steps"))
        return _finish(a, issues)

    # ------------------------------------------------------------- panel step
    hdr = job.stephdr(panel_step)
    if hdr is None:
        issues.append(_missing(f"steps/{panel_step}/stephdr"))
    prof = job.profile(panel_step)
    if prof is None and not job.source.exists(f"steps/{panel_step}/profile"):
        issues.append(_missing(f"steps/{panel_step}/profile"))
    ox, oy = (prof.extent[0], prof.extent[1]) if prof is not None and settings.panel_origin == "profile-lower-left" else (0.0, 0.0)
    a.panel_origin = (ox, oy)
    to_panel = Transform.translation(-ox, -oy)
    if prof is not None:
        a.panel_outline = [to_panel.apply(x, y) for x, y in prof.outline]

    instances: list[Instance] = []
    if hdr is not None and hdr.repeats:
        instances, exp_issues = expand(job, panel_step, settings.step_repeat_anchor)
        issues.extend(exp_issues)

    if instances:
        board_instances = [i for i in instances if board_step and i.step.lower() == board_step.lower()]
        if not board_instances:
            issues.append(
                error(
                    "no_board_instances",
                    f"The STEP-REPEAT blocks of '{panel_step}' place no step with components"
                    + (f" (board step '{board_step}')" if board_step else ""),
                    subject="steps",
                )
            )
            return _finish(a, issues)
        a.mode = "panel"
        ctx = _step_repeat_mode(a, issues, panel_step, board_step, instances, board_instances, to_panel, ref_kind)
    else:
        comps = _step_components(job, panel_step)
        if not comps:
            issues.append(error("no_components", f"Step '{panel_step}' has no components", subject=panel_step))
            return _finish(a, issues)
        copies = grouping.make_copies(comps, settings.copy_suffix_regex)
        groups = grouping.group_copies(copies)
        n = grouping.copy_count(groups)
        a.copy_count = n
        if n <= 1:
            a.mode = "single-board"
            a.suggested_suffix = grouping.suggest_suffix([c.designator for c in copies])
            ctx = _single_board_mode(a, issues, panel_step, comps, to_panel, ref_kind)
        else:
            a.mode = "flattened"
            issues.append(
                info(
                    "flattened_panel",
                    f"No STEP-REPEAT in '{panel_step}': circuits reconstructed from repeated designators "
                    f"({n} copies each)",
                    subject=panel_step,
                )
            )
            ctx = _flattened_mode(a, issues, panel_step, groups, n, to_panel, ref_kind)

    _part_numbers(a, issues)
    board_map, panel_map = _edit_maps(a, ctx)
    apply_edits(a, issues, board_map, panel_map, _package_lookup(a, ctx))
    _paste_checks(a, issues, ctx)
    _common_checks(a, issues)
    _fiducials(a, issues)
    _bom_check(a, issues)
    return _finish(a, issues)


def _finish(a: PanelAnalysis, issues: list[Issue]) -> PanelAnalysis:
    if not a.component_edits and a.decisions.component_edits:
        # The analysis stopped before the edits were applied: keep them for the next edit.
        a.component_edits = list(a.decisions.component_edits)
    seen = set()
    unique = []
    for i in issues + list(a.job.issues) + a.job.units_issues():
        k = (i.severity, i.key, i.message)
        if k not in seen:
            seen.add(k)
            unique.append(i)
    a.issues = sort_issues(unique)
    acks = {ack.key for ack in a.decisions.acknowledged}
    a.acknowledged = {i.key for i in a.issues if i.severity is not Severity.ERROR and i.key in acks}
    return a


# ---------------------------------------------------------------------- shared steps
def _reference_point(
    a: PanelAnalysis, issues: list[Issue], ref_kind: str, board_step: str | None
) -> None:
    hdr = a.job.stephdr(board_step) if board_step else None
    if ref_kind == "board-origin" and board_step:
        a.reference_kind, a.reference_board = ref_kind, (0.0, 0.0)
        return
    if ref_kind == "board-datum" and hdr is not None:
        a.reference_kind, a.reference_board = ref_kind, hdr.datum
        return
    if ref_kind != "profile-lower-left":
        issues.append(
            warning(
                "reference_fallback",
                f"Circuit reference '{ref_kind}' needs a board step; using the lower-left of the board outline",
                subject="reference",
            )
        )
    x0, y0, _x1, _y1 = _bbox(a.board_outline)
    a.reference_kind = "profile-lower-left" if board_step else "outline-lower-left"
    a.reference_board = (x0, y0)


def _relative(a: PanelAnalysis, circuits: list[CircuitInfo]) -> None:
    """Offsets, rotation and mirror of every circuit relative to circuit 1."""
    t1_inv = circuits[0].transform.inverse()
    rx, ry = a.reference_board
    p1 = circuits[0].transform.apply(rx, ry)
    for c in circuits:
        rel = c.transform @ t1_inv
        c.rotation, c.mirror = rel.rotation, rel.mirrored
        p = c.transform.apply(rx, ry)
        c.dx, c.dy = p[0] - p1[0], p[1] - p1[1]
    a.circuits = circuits


def _number(a: PanelAnalysis, raw: list[CircuitInfo]) -> list[CircuitInfo]:
    order = number_circuits([c.center for c in raw], [c.size for c in raw], a.numbering.first, a.numbering.order)
    out = [raw[i] for i in order]
    for k, c in enumerate(out, start=1):
        c.index = k
    return out


def _paste(
    a: PanelAnalysis,
    issues: list[Issue],
    step: str,
    placements: list[PlacementInfo],
    to_panel: Transform,
    scope: str,
    circuits: list[int | None] | None = None,
) -> None:
    paste = {}
    for side in ("top", "bottom"):
        layer = a.layer_roles.get(f"paste_{side}")
        ff = a.job.features(step, layer) if layer else None
        paste[side] = pad_set(ff) if ff is not None else None
        has_parts = any(p.layer == side for p in placements)
        if layer and ff is None and has_parts:
            issues.append(
                warning(
                    "missing_layer",
                    f"Step '{step}' has no features for the {side} paste layer '{layer}'; paste checks skipped",
                    subject=f"{step}:{layer}",
                )
            )
        if not layer and has_parts:
            issues.append(
                warning(
                    "no_paste_layer",
                    f"No {side} paste layer identified; paste checks skipped for {side}-side parts",
                    subject=side,
                )
            )
    parts = []
    for k, p in enumerate(placements):
        body = _bbox([q for poly in p.body for q in poly]) if p.body else None
        parts.append(
            PartToCheck(
                designator=p.designator,
                side=p.layer,
                x=p.x,
                y=p.y,
                toeprints=p.toeprints,
                body=body,
                circuit=circuits[k] if circuits else None,
                location=to_panel.apply(p.x, p.y),
            )
        )
    results, found = paste_check(parts, paste, a.settings.tolerances, scope)
    for p, r in zip(placements, results):
        p.paste = r
    # A part added by hand with no paste under it is more likely misplaced than
    # through-hole: a warning, not the usual note.
    added = {p.designator for p in a.placements if p.state == "added"}
    for issue in [i for i in found if i.code == "no_paste" and i.designator in added]:
        found.remove(issue)
        if any(i.code == "added_no_paste" and i.designator == issue.designator for i in issues):
            continue
        issues.append(
            warning(
                "added_no_paste",
                f"No paste under {issue.designator} (added by hand); check its position, side and package",
                designator=issue.designator,
                location=issue.location,
            )
        )
    # One no-paste line per designator, listing the circuits, instead of one per copy.
    no_paste: dict[str, list[Issue]] = {}
    for issue in found:
        if issue.code == "no_paste" and issue.circuit is not None:
            no_paste.setdefault(issue.designator or "", []).append(issue)
        else:
            issues.append(issue)
    for name, items in no_paste.items():
        circuits_list = sorted(i.circuit for i in items if i.circuit is not None)
        first = items[0]
        issues.append(
            info(
                "no_paste",
                f"No paste near {name} in circuit{'s' if len(circuits_list) > 1 else ''} "
                f"{', '.join(map(str, circuits_list))}; likely a through-hole part",
                designator=name,
                location=first.location,
                data={"circuits": circuits_list},
            )
        )


def _part_numbers(a: PanelAnalysis, issues: list[Issue]) -> None:
    mapping = a.decisions.part_number_attribute
    if mapping is None:
        mapping = a.settings.part_number_attribute
    a.part_number_attribute = mapping or ""
    keys = set()
    for p in [*a.placements, *a.panel_parts]:
        keys.update(p.attributes)
        p.part_number = p.attributes.get(mapping, "") if mapping else ""
    a.attribute_keys = sorted(keys)
    if mapping and a.placements and mapping not in keys:
        issues.append(
            warning("part_number_attribute", f"No component carries the part-number attribute '{mapping}'", subject=mapping)
        )


# ---------------------------------------------------------------------- component edits
def _reference_xy(a: PanelAnalysis, kind: str) -> tuple[float, float] | None:
    """Where reference ``kind`` sits in the board frame (None when it does not exist)."""
    if kind in ("profile-lower-left", "outline-lower-left"):
        if not a.board_outline:
            return None
        x0, y0, _x1, _y1 = _bbox(a.board_outline)
        return x0, y0
    if kind == "board-origin" and a.board_step:
        return 0.0, 0.0
    if kind == "board-datum" and a.board_step:
        hdr = a.job.stephdr(a.board_step)
        return hdr.datum if hdr is not None else None
    return None


def _panel_origin_xy(a: PanelAnalysis, kind: str) -> tuple[float, float]:
    """Where panel origin ``kind`` sits in panel-step coordinates."""
    if kind == "profile-lower-left" and a.panel_step:
        prof = a.job.profile(a.panel_step)
        if prof is not None:
            return prof.extent[0], prof.extent[1]
    return 0.0, 0.0


def _edit_maps(a: PanelAnalysis, ctx: _ModeContext | None) -> tuple[Transform | None, Transform | None]:
    """How to carry edit coordinates from the frame they were entered in into this one:
    (circuit-relative map, panel-frame map); None where the frames cannot be related."""
    frame = a.decisions.edit_frame
    current = a.edit_frame
    if frame is None or frame == current or not a.decisions.component_edits:
        return Transform(), Transform()
    board: Transform | None = None
    rx, ry = a.reference_board
    if (frame.mode == "flattened") != (current.mode == "flattened"):
        board = None  # board frames of different kinds
    elif current.mode != "flattened":
        ref = _reference_xy(a, frame.reference)  # the board frame is the board step's own
        if ref is not None:
            board = Transform.translation(ref[0] - rx, ref[1] - ry)
    elif (frame.first, frame.order) == (current.first, current.order):
        board = Transform()  # same circuit 1, and the reference is always its outline's corner
    elif ctx is not None and ctx.frame_of is not None and frame.first in CORNERS and frame.order in ORDERS:
        to_board, ref = ctx.frame_of(frame.first, frame.order)
        board = Transform.translation(-rx, -ry) @ to_board @ Transform.translation(*ref)
    panel: Transform | None = None
    if frame.panel_origin == current.panel_origin:
        panel = Transform()
    elif frame.panel_origin in PANEL_ORIGINS and current.panel_origin in PANEL_ORIGINS:
        ox, oy = _panel_origin_xy(a, frame.panel_origin)
        panel = Transform.translation(ox - a.panel_origin[0], oy - a.panel_origin[1])
    return board, panel


def _package_lookup(a: PanelAnalysis, ctx: _ModeContext | None):
    """Packages by name for parts added by hand: the placements' step first, then the panel's."""
    cache: dict[tuple[str, str], Package | None] = {}

    def lookup(level: str, name: str) -> Package | None:
        steps = [ctx.step if ctx else None, a.panel_step]
        if level == "panel":
            steps.reverse()
        for step in steps:
            if not step:
                continue
            key = (step.lower(), name.lower())
            if key not in cache:
                eda = a.job.eda(step)
                cache[key] = next((p for p in eda.packages if p.name.lower() == name.lower()), None) if eda else None
            if cache[key] is not None:
                return cache[key]
        return None

    return lookup


def _carried(p: PlacementInfo, tf: Transform) -> PlacementInfo:
    """A placement moved by ``tf`` (circuit 1 -> another circuit of a flattened panel)."""
    x, y = tf.apply(p.x, p.y)
    return PlacementInfo(
        designator=p.designator,
        part_name=p.part_name,
        package=p.package,
        layer=p.layer,
        x=x,
        y=y,
        rotation_raw=p.rotation_raw,
        rotation=compose_rotation(p.rotation, tf),
        mirror=p.mirror,
        attributes=p.attributes,
        toeprints=[tf.apply(tx, ty) for tx, ty in p.toeprints],
        body=[[tf.apply(bx, by) for bx, by in poly] for poly in p.body],
    )


def _paste_checks(a: PanelAnalysis, issues: list[Issue], ctx: _ModeContext | None) -> None:
    """Centroid-on-paste checks of what is placed, after the component edits."""
    if ctx is None or not a.circuits:
        return
    if ctx.copies is None:
        _paste(a, issues, ctx.step, a.placements, a.circuits[0].transform, ctx.scope)
        return
    # Flattened: every copy where it is in the panel step, reported per circuit.  Parts the
    # user moved or added are carried from circuit 1 into every circuit by its fit.
    to_step = Transform.translation(*a.panel_origin)
    active = {p.designator: p for p in a.placements}
    keep = [(k, base, cp) for k, base, cp in ctx.copies if base in active and not active[base].moved]
    checked = _placements(a.job, ctx.step, [(cp.side, cp.comp) for _k, _b, cp in keep])
    circuits = [k for k, _b, _cp in keep]
    for p, (_k, base, _cp) in zip(checked, keep):
        p.designator = base
    for p in a.placements:
        if p.moved:
            for c in a.circuits:
                checked.append(_carried(p, to_step @ c.transform))
                circuits.append(c.index)
    _paste(a, issues, ctx.step, checked, to_step.inverse(), ctx.scope, circuits)
    result_of = {(p.designator, k): p.paste for p, k in zip(checked, circuits)}
    for p in a.placements:
        p.paste = result_of.get((p.designator, 1))


# ---------------------------------------------------------------------- step-repeat
def _step_repeat_mode(
    a: PanelAnalysis,
    issues: list[Issue],
    panel_step: str,
    board_step: str,
    instances: list[Instance],
    board_instances: list[Instance],
    to_panel: Transform,
    ref_kind: str,
) -> _ModeContext:
    job = a.job
    removed = _removed(a.decisions, "board")
    board_prof = job.profile(board_step)
    if board_prof is None:
        issues.append(_missing(f"steps/{board_step}/profile"))
    board_comps = _step_components(job, board_step)
    if not board_comps:
        issues.append(error("no_components", f"Board step '{board_step}' has no components", subject=board_step))
    if board_prof is not None:
        a.board_outline = list(board_prof.outline)
    elif board_comps:
        x0, y0, x1, y1 = _bbox([(c.x, c.y) for _s, c in board_comps])
        a.board_outline = _rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
    else:
        a.board_outline = _rect(0, 0, 1, 1)
    _reference_point(a, issues, ref_kind, board_step)

    raw = []
    for inst in board_instances:
        tf = to_panel @ inst.transform
        pts, center, size = _circuit_shape(tf, a.board_outline)
        raw.append(CircuitInfo(0, tf, "step-repeat", None, inst.flip, outline=pts, center=center, size=size, label=inst.label))
    _relative(a, _number(a, raw))
    a.grid_source = "step-repeat"

    a.placements = _placements(job, board_step, board_comps)
    issues.extend(_package_issues(job, board_step, board_comps))
    issues.extend(duplicate_designators([p.designator for p in a.placements if p.designator not in removed]))

    # Panel-level parts: the panel step's own components (minus flattened copies of the
    # board) and the components of intermediate (sub-panel) steps.
    board_by_name = {p.designator: p for p in a.placements}
    copies_by_name: dict[str, list[tuple[float, float, float, str]]] = {}
    panel_parts: list[PanelPartInfo] = []
    for cp in grouping.make_copies(_step_components(job, panel_step), a.settings.copy_suffix_regex):
        b = board_by_name.get(cp.base)
        if b is not None and b.part_name == cp.comp.part_name:
            x, y = to_panel.apply(cp.x, cp.y)
            copies_by_name.setdefault(cp.base, []).append((x, y, cp.comp.rotation, cp.designator))
        else:
            panel_parts.append(_panel_part(job, cp.side, cp.comp, to_panel, False, panel_step))
    for inst in instances:
        if inst.step.lower() != board_step.lower():
            for side, comp in _step_components(job, inst.step):
                panel_parts.append(_panel_part(job, side, comp, to_panel @ inst.transform, inst.flip, inst.step))
    a.panel_parts = panel_parts

    n_copies = sum(len(v) for v in copies_by_name.values())
    if n_copies:
        expected = []
        for name in removed:  # parts that are not placed are not compared
            copies_by_name.pop(name, None)
        for p in a.placements:
            if p.designator in removed:
                continue
            for c in a.circuits:
                x, y = c.transform.apply(p.x, p.y)
                rot = None if c.transform.mirrored else norm_angle(p.rotation_raw - c.transform.rotation)
                expected.append(ExpectedCopy(p.designator, c.index, x, y, rot))
        issues.append(
            info(
                "flattened_copies",
                f"The panel step also contains {n_copies} flattened copies of board components; "
                "they were compared with the STEP-REPEAT expansion",
                subject=panel_step,
            )
        )
        report_missing = len(copies_by_name) >= 0.5 * max(len(set(board_by_name) - removed), 1)
        issues.extend(crosscheck(expected, copies_by_name, a.settings.tolerances, report_missing))

    circuit_of = {c.label: c.index for c in a.circuits}
    a.instances = [StepInstanceInfo(job, panel_step, to_panel)]
    for inst in instances:
        is_board = inst.step.lower() == board_step.lower()
        a.instances.append(
            StepInstanceInfo(job, inst.step, to_panel @ inst.transform, circuit_of.get(inst.label) if is_board else None, inst.flip)
        )
    return _ModeContext(board_step, f"board step '{board_step}'")


# ---------------------------------------------------------------------- flattened
def _flattened_mode(
    a: PanelAnalysis,
    issues: list[Issue],
    panel_step: str,
    groups: dict[str, list[grouping.Copy]],
    n: int,
    to_panel: Transform,
    ref_kind: str,
) -> _ModeContext:
    job = a.job
    tol = a.settings.tolerances
    removed_board = _removed(a.decisions, "board")
    removed_any = _removed(a.decisions)
    prof = job.profile(panel_step)
    outline_layer = a.layer_roles.get("outline")
    outline_ff = job.features(panel_step, outline_layer) if outline_layer else None
    polys = grouping.closed_outlines(outline_ff, prof.islands[1:] if prof else [])
    if prof is not None:
        panel_area = Polygon(prof.outline).area
        polys = [p for p in polys if p.area < 0.9 * panel_area]
    assignment = grouping.assign_by_outline(groups, n, polys) or grouping.assign_by_sorting(groups, n)
    complete = sorted(b for b, g in groups.items() if len(g) == n)
    if assignment.method == "sorted":
        issues.append(
            info(
                "copies_sorted",
                "No closed board outline found for every circuit; copies were assigned to circuits by "
                "sorting each designator's copies by Y, then X",
                subject=panel_step,
            )
        )

    # Number the circuits by where their copies (or outlines) are.
    boxes = [grouping.cluster_extent(cl, ol) for cl, ol in zip(assignment.clusters, assignment.outlines)]
    centers = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes]
    sizes = [(b[2] - b[0], b[3] - b[1]) for b in boxes]
    order = number_circuits(centers, sizes, a.numbering.first, a.numbering.order)
    clusters = [assignment.clusters[i] for i in order]
    outlines = [assignment.outlines[i] for i in order]

    # Board frame = circuit 1 where it sits in the panel step; fit circuit 1 -> circuit k.
    # Parts the user removed do not count (unless too few would be left).
    fitted = [b for b in complete if b not in removed_board]
    if len(fitted) < 3:
        fitted = complete
    src = grouping.positions(clusters[0], fitted)
    fits = [fit_rigid(src, grouping.positions(cl, fitted), tol.fit_residual) for cl in clusters]
    for k, fit in enumerate(fits[1:], start=2):
        if fit.max_residual > tol.fit_residual:
            worst = fitted[int(np.argmax(fit.residuals))]
            issues.append(
                error(
                    "fit_residual",
                    f"Circuit {k} does not match circuit 1 as a rigid copy: residual up to "
                    f"{fit.max_residual:.4f} mm (worst {worst})",
                    circuit=k,
                    designator=worst,
                    data={"residual": fit.max_residual},
                )
            )
    if outlines[0] is not None:
        a.board_outline = list(outlines[0].exterior.coords)[:-1]
    else:
        x0, y0, x1, y1 = grouping.cluster_extent(clusters[0], None)
        a.board_outline = _rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        issues.append(
            warning(
                "reference_fallback",
                "No board outline found for circuit 1; its outline and reference point come from the "
                "bounding box of its components (+1 mm)",
                subject="reference",
            )
        )
    _reference_point(a, issues, ref_kind, None)

    circuits = []
    for k, (cluster, fit) in enumerate(zip(clusters, fits), start=1):
        tf = to_panel @ fit.transform
        pts, center, size = _circuit_shape(tf, a.board_outline)
        positions = {}
        for base, cp in cluster.items():
            x, y = to_panel.apply(cp.x, cp.y)
            positions[base] = (x, y, cp.comp.rotation, cp.side)
        circuits.append(
            CircuitInfo(
                k,
                tf,
                "fitted",
                residual=fit.max_residual,
                outline=pts,
                center=center,
                size=size,
                label=f"copy group {order[k - 1] + 1}",
                positions=positions,
            )
        )
    _relative(a, circuits)
    a.grid_source = "fitted"

    # Copies whose count is not N: locate them and report missing / extra / outside.
    region1 = grouping.region_of(clusters[0], outlines[0])
    fit_tfs = [f.transform for f in fits]
    confirmed = set(a.decisions.panel_level)
    panel_parts: list[PanelPartInfo] = []
    stray: dict[int, dict[str, grouping.Copy]] = {}
    for base, group in sorted(groups.items()):
        if len(group) == n and base not in confirmed:
            continue
        located = [(cp, grouping.locate_copy(cp, fit_tfs, region1, outlines)) for cp in group]
        if base in confirmed:
            panel_parts.extend(_panel_part(job, cp.side, cp.comp, to_panel, False, panel_step) for cp, _k in located)
            continue
        per_circuit = Counter(k for _cp, k in located if k is not None)
        outside = [cp for cp, k in located if k is None]
        missing = [k for k in range(1, n + 1) if per_circuit.get(k, 0) == 0]
        extra = sorted(k for k, m in per_circuit.items() if m > 1)
        panel_parts.extend(_panel_part(job, cp.side, cp.comp, to_panel, False, panel_step) for cp in outside)
        for cp, k in located:
            if k is not None:
                stray.setdefault(k, {}).setdefault(base, cp)
                if positions_k := circuits[k - 1].positions:
                    positions_k.setdefault(base, (*to_panel.apply(cp.x, cp.y), cp.comp.rotation, cp.side))
        if base in removed_any:
            continue  # not placed: its copy count does not matter
        copies_text = f"{len(group)} cop{'y' if len(group) == 1 else 'ies'}"
        inside = [(cp, k) for cp, k in located if k is not None]
        if not inside:
            message = (
                f"{base}: {copies_text}, all outside the circuits (expected {n}, one per circuit). "
                "A panel-level part? Confirm it as panel-level or fix the export."
            )
            circuit = None
            loc = to_panel.apply(group[0].x, group[0].y)
        else:
            detail = []
            if missing:
                detail.append(f"missing in circuit{'s' if len(missing) > 1 else ''} {', '.join(map(str, missing))}")
            if extra:
                detail.append(f"extra copy in circuit{'s' if len(extra) > 1 else ''} {', '.join(map(str, extra))}")
            if outside:
                detail.append(f"{len(outside)} outside every circuit")
            message = (
                f"{base}: {copies_text}, expected {n} — {'; '.join(detail) or 'count differs'}. "
                "Fix the export or confirm it as panel-level."
            )
            circuit = (missing or extra or [None])[0]
            if missing:
                cp, k = inside[0]
                x1, y1 = fit_tfs[k - 1].inverse().apply(cp.x, cp.y)
                loc = to_panel.apply(*fit_tfs[missing[0] - 1].apply(x1, y1))
            else:
                loc = to_panel.apply(inside[0][0].x, inside[0][0].y)
        issues.append(
            error(
                "copy_count",
                message,
                designator=base,
                circuit=circuit,
                location=loc,
                data={"count": len(group), "expected": n, "missing": missing, "extra": extra, "outside": len(outside)},
            )
        )
    a.panel_parts = panel_parts

    # Placements: circuit 1's copies, including not-N designators found inside circuit 1.
    members = dict(clusters[0])
    for base, cp in stray.get(1, {}).items():
        members.setdefault(base, cp)
    ordered = sorted(members.items())
    a.placements = _placements(job, panel_step, [(cp.side, cp.comp) for _b, cp in ordered])
    for p, (base, _cp) in zip(a.placements, ordered):
        p.designator = base
    issues.extend(_package_issues(job, panel_step, [(cp.side, cp.comp) for _b, cp in ordered]))
    for k, cluster in enumerate(clusters, start=1):
        names = [cp.base for cp in cluster.values()]
        names += [cp.base for b, cp in stray.get(k, {}).items() if b not in cluster]
        issues.extend(duplicate_designators([b for b in names if b not in removed_board], circuit=k))

    a.instances = [StepInstanceInfo(job, panel_step, to_panel)]

    def frame_of(first: str, order_: str) -> tuple[Transform, tuple[float, float]]:
        """Another numbering's board frame (its circuit 1's copy) -> this one, and the
        reference point (lower-left of that copy's outline) in its own frame."""
        i = number_circuits(centers, sizes, first, order_)[0]
        to_copy = fits[order.index(i)].transform  # this board frame -> copy i
        if assignment.outlines[i] is not None:
            x0, y0, _x1, _y1 = _bbox(list(assignment.outlines[i].exterior.coords)[:-1])
        else:
            x0, y0, _x1, _y1 = grouping.cluster_extent(assignment.clusters[i], None)
            x0, y0 = x0 - 1, y0 - 1
        return to_copy.inverse(), (x0, y0)

    # Paste is checked after the edits, on every copy in the panel step.
    entries = [(k, base, cp) for k, cl in enumerate(clusters, start=1) for base, cp in sorted(cl.items())]
    return _ModeContext(panel_step, f"panel step '{panel_step}'", entries, frame_of)


# ---------------------------------------------------------------------- single board
def _single_board_mode(
    a: PanelAnalysis,
    issues: list[Issue],
    board_step: str,
    comps: list[tuple[str, OdbComponent]],
    to_panel: Transform,
    ref_kind: str,
) -> _ModeContext:
    job = a.job
    a.board_step = board_step
    ctx = _ModeContext(board_step, f"board step '{board_step}'")
    setup = a.decisions.single_board
    prof = job.profile(board_step)
    if prof is not None:
        a.board_outline = list(prof.outline)
    else:
        x0, y0, x1, y1 = _bbox([(c.x, c.y) for _s, c in comps])
        a.board_outline = _rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
    _reference_point(a, issues, ref_kind, board_step)
    a.placements = _placements(job, board_step, comps)
    issues.extend(_package_issues(job, board_step, comps))
    removed = _removed(a.decisions, "board")
    issues.extend(duplicate_designators([p.designator for p in a.placements if p.designator not in removed]))
    a.grid_source = "manual"

    if setup is None:
        hint = ""
        if a.suggested_suffix:
            hint = (
                f" The designators look like suffixed copies (pattern {a.suggested_suffix!r}); if this is a "
                "flattened panel, set the copy-suffix setting instead."
            )
        issues.append(
            error(
                "single_board",
                "This export is a single board: no STEP-REPEAT and every designator appears once. "
                "Confirm single-board mode and enter the circuit grid." + hint,
                subject=board_step,
            )
        )
        pts, center, size = _circuit_shape(to_panel, a.board_outline)
        a.circuits = [CircuitInfo(1, to_panel, "manual", outline=pts, center=center, size=size, label="board")]
        a.instances = [StepInstanceInfo(job, board_step, to_panel, 1)]
        return ctx

    issues.append(info("single_board", "Single-board mode confirmed; circuits come from the entered grid", subject=board_step))
    raw = []
    for k, (dx, dy) in enumerate(setup.offsets_list()):
        tf = Transform.translation(setup.origin_x + dx, setup.origin_y + dy)
        pts, center, size = _circuit_shape(tf, a.board_outline)
        raw.append(CircuitInfo(k, tf, "manual", outline=pts, center=center, size=size, label=f"entry {k + 1}"))
    _relative(a, _number(a, raw))
    a.panel_origin = (0.0, 0.0)
    a.instances = [StepInstanceInfo(job, board_step, c.transform, c.index) for c in a.circuits]
    panel_outline = None
    if setup.panel_outline:
        panel_outline = [(float(p[0]), float(p[1])) for p in setup.panel_outline]
    elif setup.panel_width > 0 and setup.panel_height > 0:
        panel_outline = _rect(0, 0, setup.panel_width, setup.panel_height)
    pj = a.panel_job
    if pj is not None:
        pstep = detect_steps(pj).panel_step
        if pstep:
            pprof = pj.profile(pstep)
            if panel_outline is None and pprof is not None:
                panel_outline = list(pprof.outline)
            a.instances.append(StepInstanceInfo(pj, pstep, Transform()))
    if panel_outline is None:
        x0, y0, x1, y1 = _bbox([q for c in a.circuits for q in c.outline])
        panel_outline = _rect(min(0.0, x0), min(0.0, y0), x1, y1)
        issues.append(warning("panel_outline", "No panel outline entered; showing the circuits' extent", subject="panel"))
    a.panel_outline = panel_outline
    return ctx


# ---------------------------------------------------------------------- common checks
def _common_checks(a: PanelAnalysis, issues: list[Issue]) -> None:
    if not a.circuits:
        return
    tol = a.settings.tolerances
    if a.mode != "single-board" or a.decisions.single_board is not None:
        geoms = [CircuitGeometry(c.index, c.transform, c.rotation, c.mirror, c.center) for c in a.circuits]
        issues.extend(orientation_checks(geoms, tol))
    a.grid = g = derive_grid([c.center for c in a.circuits], [c.size for c in a.circuits], tol.grid)
    if len(a.circuits) > 1 and not g.uniform:
        n = len(a.circuits)
        if n != g.cols * g.rows or len(set(zip(g.col_of, g.row_of))) != n:
            text = f"The {n} circuits do not fill a {g.cols} × {g.rows} grid"
        else:
            text = (
                f"The circuits do not form a uniform {g.cols} × {g.rows} grid "
                f"(deviation up to {g.max_deviation:.4f} mm)"
            )
        issues.append(warning("nonuniform_grid", text, subject="grid", data={"deviation": g.max_deviation}))


def _bom_check(a: PanelAnalysis, issues: list[Issue]) -> None:
    if a.bom is None:
        return
    placed = {p.designator for p in a.placements} | {p.designator for p in a.panel_parts}
    removed = {p.designator: p for p in [*a.removed_placements, *a.removed_panel_parts]}
    bom = set(a.bom.designators)
    for name in sorted(bom - placed):
        part = removed.get(name)
        if part is None:
            issues.append(warning("bom_not_in_odb", f"{name} is in the BOM but not in the ODB++ export", designator=name))
        elif part.edit is not None and part.edit.reason == "not-populated":
            issues.append(
                warning("bom_removed", f"{name} is in the BOM but was removed as not populated", designator=name)
            )
    states = {p.designator: p.state for p in a.placements}
    for name in sorted(set(states) - bom):
        where = "was added by hand" if states[name] == "added" else "is in the ODB++ export"
        issues.append(warning("bom_not_in_bom", f"{name} {where} but is not in the BOM", designator=name))


# ---------------------------------------------------------------------- fiducials
def _fiducials(a: PanelAnalysis, issues: list[Issue]) -> None:
    fs = a.settings.fiducials
    regions = make_regions([(c.index, c.outline) for c in a.circuits])
    cands: list[FiducialCandidate] = []

    def add_classified(name, x, y, side, source, diameter=None, designator=None, note=""):
        level, circuit = classify(x, y, regions)
        cands.append(
            FiducialCandidate(name, x, y, side, level, [source], circuit, diameter, designator, [note] if note else [])
        )

    # Removed parts count: a fiducial component that is not placed is still a fiducial.
    for p in [*a.panel_parts, *a.removed_panel_parts]:
        if matches_pattern(p.designator, fs.patterns) or (p.package and matches_pattern(p.package, fs.patterns)):
            add_classified(p.designator, p.x, p.y, p.layer, "component", designator=p.designator)
    for p in [*a.placements, *a.removed_placements]:
        if matches_pattern(p.designator, fs.patterns) or (p.package and matches_pattern(p.package, fs.patterns)):
            for c in a.circuits:
                x, y, _r = a.circuit_position(p, c)
                cands.append(
                    FiducialCandidate(f"{p.designator}#{c.index}", x, y, p.layer, "circuit", ["component"], c.index, None, p.designator)
                )

    found: dict[tuple[int, str], list] = {}
    for inst in a.instances:
        key = (id(inst.job), inst.step.lower())
        if key not in found:
            roles = a.layer_roles if inst.job is a.job else detect_layer_roles(inst.job.matrix)[0]
            found[key] = feature_candidates(inst.job, inst.step, roles, fs)
        for lc in found[key]:
            x, y, side = transform_candidate(lc, inst.transform, inst.flip)
            notes = [lc.note] if lc.note else []
            if inst.circuit is not None:
                cands.append(FiducialCandidate(feature_name(x, y), x, y, side, "circuit", [lc.source], inst.circuit, lc.diameter, None, notes))
            else:
                add_classified(feature_name(x, y), x, y, side, lc.source, lc.diameter, note=lc.note)

    setup = a.decisions.single_board
    if a.mode == "single-board" and setup is not None:
        for f in setup.fiducials:
            cands.append(FiducialCandidate(f.name, f.x, f.y, f.layer, "panel", ["manual"], None, f.diameter))

    merged = merge(cands, a.settings.tolerances.fiducial_merge)
    a.fiducial_candidates = merged
    selectable = {c.name: c for c in merged if c.selectable}
    wanted = list(a.decisions.fiducials)
    if a.mode == "single-board" and setup is not None:
        for f in setup.fiducials:
            if f.name not in wanted:
                wanted.append(f.name)
    chosen: list[FiducialCandidate] = []
    for name in wanted:
        c = selectable.get(name)
        if c is None:
            issues.append(
                warning("fiducial_missing", f"Selected fiducial {name} is no longer a panel fiducial candidate", subject=name)
            )
        elif len(chosen) >= MAX_PANEL_FIDUCIALS:
            issues.append(
                error("fiducial_count", f"At most {MAX_PANEL_FIDUCIALS} panel fiducials can be selected", subject="fiducials")
            )
            break
        else:
            chosen.append(c)
    a.fiducials = chosen
    if a.circuits and not selectable:
        issues.append(info("no_fiducials", "No panel fiducial candidates found", subject="fiducials"))


# ---------------------------------------------------------------------- decisions
def decisions_from_project(project: PanelProject) -> Decisions:
    """The user decisions stored in a project file, to re-apply on reopen."""
    return Decisions(
        panel_step=project.source.panel_step,
        board_step=project.source.board_step,
        layer_roles=dict(project.layer_roles),
        numbering_first=project.numbering.first,
        numbering_order=project.numbering.order,
        circuit_reference=project.circuit_reference.kind if project.circuit_reference.kind in REFERENCE_KINDS else None,
        part_number_attribute=project.part_number_attribute,
        fiducials=[f.name for f in project.fiducials if f.source != "manual"],
        acknowledged=list(project.acknowledged_warnings),
        panel_level=list(project.panel_level_designators),
        single_board=project.single_board,
        component_edits=list(project.component_edits),
        edit_frame=EditFrame(
            mode=project.mode,
            reference=project.circuit_reference.kind,
            first=project.numbering.first,
            order=project.numbering.order,
            panel_origin=project.panel.origin.kind,
        ),
        confirmed=True,
    )


#: Edits that do not change the identified panel keep an existing confirmation.
NON_STRUCTURAL = frozenset(
    {"fiducials", "part_number_attribute", "acknowledged", "bom_path", "component_edits", "edit_frame"}
)


def with_changes(decisions: Decisions, **changes) -> Decisions:
    """A copy of the decisions with ``changes``; structural edits reset the confirmation."""
    if "confirmed" not in changes and not set(changes) <= NON_STRUCTURAL:
        changes["confirmed"] = False
    return replace(decisions, **changes)
