"""Detection of step roles (panel, board) and layer roles (paste, copper, mask, outline).

Steps: the step whose header contains STEP-REPEAT blocks (and which no other step
repeats) is the panel; the repeated step that carries components is the board.  A job
whose steps have no STEP-REPEAT at all is ambiguous when it has several steps.

Layers: from the matrix TYPE and the stack-up order (ROW).  Paste and mask layers
above the first copper layer are top-side, below the last copper layer bottom-side.
The v8 ``REF`` field links a paste/mask layer to its copper layer explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from panelimport.io.odb.job import OdbJob, polygon_area
from panelimport.io.odb.matrix import Matrix, MatrixLayer

LAYER_ROLES = (
    "paste_top",
    "paste_bottom",
    "copper_top",
    "copper_bottom",
    "mask_top",
    "mask_bottom",
    "outline",
)
ROLE_LABELS = {
    "paste_top": "Top paste",
    "paste_bottom": "Bottom paste",
    "copper_top": "Top copper",
    "copper_bottom": "Bottom copper",
    "mask_top": "Top mask",
    "mask_bottom": "Bottom mask",
    "outline": "Board outlines (flattened panels)",
}


def detect_layer_roles(matrix: Matrix) -> tuple[dict[str, str], list[str]]:
    """Return ``{role: layer name}`` and notes about ambiguous choices."""
    notes: list[str] = []
    board = [layer for layer in matrix.layers if layer.is_board]
    copper = [layer for layer in board if layer.is_copper]
    roles: dict[str, str] = {}
    if copper:
        roles["copper_top"] = copper[0].name
        if len(copper) > 1:
            roles["copper_bottom"] = copper[-1].name
    top_row = copper[0].row if copper else None
    bottom_row = copper[-1].row if len(copper) > 1 else None
    by_id = {layer.id: layer for layer in matrix.layers if layer.id}

    def side_of(layer: MatrixLayer) -> str | None:
        if layer.ref and layer.ref in by_id:
            ref = by_id[layer.ref]
            if copper and ref.key == copper[0].key:
                return "top"
            if len(copper) > 1 and ref.key == copper[-1].key:
                return "bottom"
        if top_row is not None and layer.row < top_row:
            return "top"
        if bottom_row is not None and layer.row > bottom_row:
            return "bottom"
        if top_row is None:
            low = layer.key
            if "top" in low:
                return "top"
            if "bot" in low:
                return "bottom"
        return None

    for kind, ltype in (("paste", "SOLDER_PASTE"), ("mask", "SOLDER_MASK")):
        found: dict[str, list[MatrixLayer]] = {"top": [], "bottom": []}
        for layer in board:
            if layer.type != ltype:
                continue
            side = side_of(layer)
            if side:
                found[side].append(layer)
            else:
                notes.append(f"{ltype} layer '{layer.name}' could not be assigned to a side")
        for side, layers in found.items():
            if not layers:
                continue
            # The layer nearest the copper is the one applied to it.
            pick = layers[-1] if side == "top" else layers[0]
            roles[f"{kind}_{side}"] = pick.name
            if len(layers) > 1:
                notes.append(
                    f"Several {side} {kind} layers ({', '.join(x.name for x in layers)}); using {pick.name}"
                )
    rout = [layer for layer in board if layer.type == "ROUT"]
    if rout:
        roles["outline"] = rout[0].name
    return roles, notes


@dataclass
class StepDetection:
    panel_step: str | None
    board_step: str | None
    has_repeats: bool
    ambiguous: bool = False
    reason: str = ""
    panel_candidates: list[str] = field(default_factory=list)
    board_candidates: list[str] = field(default_factory=list)
    instance_counts: dict[str, int] = field(default_factory=dict)  # step -> placed instances


def _canonical(job: OdbJob, name: str) -> str | None:
    step = job.matrix.step(name)
    return step.name if step else None


def leaf_counts(job: OdbJob, step: str, stack: tuple[str, ...] = ()) -> dict[str, int]:
    """How many times each leaf step is placed under ``step`` (recursively)."""
    hdr = job.stephdr(step)
    out: dict[str, int] = {}
    if hdr is None:
        return out
    for rep in hdr.repeats:
        child = _canonical(job, rep.name)
        if child is None or child.lower() in stack:
            continue
        child_hdr = job.stephdr(child)
        if child_hdr is not None and child_hdr.repeats:
            for leaf, n in leaf_counts(job, child, stack + (step.lower(),)).items():
                out[leaf] = out.get(leaf, 0) + n * rep.count
        else:
            out[child] = out.get(child, 0) + rep.count
    return out


def has_components(job: OdbJob, step: str) -> bool:
    for layer in job.component_layers().values():
        cf = job.components(step, layer.name)
        if cf is not None and cf.components:
            return True
    return False


def detect_steps(job: OdbJob) -> StepDetection:
    steps = job.step_names
    headers = {s: job.stephdr(s) for s in steps}
    referenced: set[str] = set()
    for hdr in headers.values():
        if hdr is not None:
            referenced.update(r.name.lower() for r in hdr.repeats)
    with_repeats = [s for s in steps if headers[s] is not None and headers[s].repeats]
    tops = [s for s in with_repeats if s.lower() not in referenced]

    if with_repeats:
        if not tops:
            return StepDetection(None, None, True, True, "STEP-REPEAT references form a cycle", with_repeats)
        counts = {s: sum(leaf_counts(job, s).values()) for s in tops}
        panel = max(tops, key=lambda s: (counts[s], -steps.index(s)))
        leaves = leaf_counts(job, panel)
        boards = [s for s in leaves if has_components(job, s)]
        board = max(boards, key=lambda s: leaves[s]) if boards else None
        ambiguous = len(tops) > 1 or len(boards) > 1
        reason = ""
        if len(tops) > 1:
            reason = f"Several steps contain STEP-REPEAT blocks: {', '.join(tops)}"
        elif len(boards) > 1:
            reason = f"The panel repeats several steps with components: {', '.join(boards)}"
        elif not boards:
            reason = "No repeated step contains components"
        return StepDetection(
            panel, board, True, ambiguous or not boards, reason, tops, boards or list(leaves), leaves
        )

    if len(steps) == 1:
        return StepDetection(steps[0], None, False, False, "", list(steps), [])
    # Several steps and no STEP-REPEAT: guess the largest step with components as the panel.
    def area(s: str) -> float:
        prof = job.profile(s)
        return polygon_area(prof.outline) if prof else 0.0

    candidates = [s for s in steps if has_components(job, s)] or list(steps)
    panel = max(candidates, key=area)
    return StepDetection(
        panel,
        None,
        False,
        True,
        f"Several steps ({', '.join(steps)}) and no STEP-REPEAT: choose the step to analyse",
        candidates,
        [],
    )
