"""Component edits on top of the export: remove, change or add components.

Edits are user decisions (:class:`~panelimport.model.panel.ComponentEdit` in
``Decisions.component_edits``).  The analysis converts them into its own frame
(:func:`convert`), applies them to the placements and panel parts (:func:`apply_edits`)
and flags edits that no longer fit the export.  The export itself is never changed.

Also here, free of Qt so the GUI and the tests share them: the edit-list operations
(remove, restore, revert, set), the values shown for a part, and the removal suggestions
(through-hole, not populated, mechanical, not in the BOM).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from shapely.geometry import Point, Polygon

from panelimport.analysis.fiducials import matches_pattern
from panelimport.analysis.result import (
    PanelAnalysis,
    PanelPartInfo,
    PlacementInfo,
    angle6,
    compose_rotation,
    r6,
)
from panelimport.analysis.transforms import Transform, angle_diff, norm_angle
from panelimport.io.odb.eda import Package
from panelimport.model.issues import Issue, error, warning
from panelimport.model.panel import EDIT_FIELDS, SIZE_FIELDS, ComponentEdit

Key = tuple[str, str]  # (level, designator)
Part = PlacementInfo | PanelPartInfo

LEVELS = ("board", "panel")
TEXT_FIELDS = ("part_name", "part_number", "package")
POSE_FIELDS = ("layer", "x", "y", "rotation")
FIELD_LABELS = {
    "part_name": "part name",
    "part_number": "part number",
    "package": "package",
    "layer": "side",
    "x": "X",
    "y": "Y",
    "rotation": "rotation",
    "width": "width",
    "length": "length",
    "height": "height",
}
REASON_LABELS = {
    "through-hole": "through-hole",
    "not-populated": "not populated (DNP)",
    "mechanical": "mechanical / fiducial",
    "other": "other",
}
EPS = 5e-7  # mm and degrees: below the project's 1e-6 rounding

PackageLookup = Callable[[str, str], Package | None]  # (level, package name) -> package


# ====================================================================== frames
def is_identity(tf: Transform) -> bool:
    return (tf.a, tf.b, tf.c, tf.d, tf.tx, tf.ty) == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def has_position(e: ComponentEdit) -> bool:
    return e.x is not None or e.y is not None or e.rotation is not None


def convert(
    edits: Iterable[ComponentEdit], board: Transform | None, panel: Transform | None
) -> tuple[list[ComponentEdit], list[ComponentEdit]]:
    """The edits in the analysis's frame.

    ``board`` and ``panel`` map circuit-relative and panel coordinates from the frame the
    edits were entered in.  None means the two frames cannot be related: those edits are
    kept unchanged and also returned in the second list.
    """
    out, stuck = [], []
    for e in edits:
        tf = board if e.level == "board" else panel
        if not has_position(e) or (tf is not None and is_identity(tf)):
            out.append(e)
        elif tf is None:
            out.append(e)
            stuck.append(e)
        else:
            changes: dict[str, float] = {}
            if e.x is not None and e.y is not None:
                x, y = tf.apply(e.x, e.y)
                changes.update(x=r6(x), y=r6(y))
            if e.rotation is not None:
                changes["rotation"] = angle6(compose_rotation(e.rotation, tf))
            out.append(replace(e, **changes))
    return out, stuck


# ====================================================================== applying
def pose(x: float, y: float, rotation: float, bottom: bool) -> Transform:
    """Package frame -> board frame for a part at (x, y), CCW ``rotation``, on ``bottom``
    (ODB++ order: rotate, then mirror)."""
    t = Transform.rotation_ccw(rotation)
    if bottom:
        t = Transform.mirror_x() @ t
    return Transform.translation(x, y) @ t


def apply_edits(
    a: PanelAnalysis,
    issues: list[Issue],
    board_map: Transform | None,
    panel_map: Transform | None,
    package_of: PackageLookup,
) -> None:
    """Convert the decisions' edits into ``a``'s frame and apply them to its parts."""
    converted, stuck = convert(a.decisions.component_edits, board_map, panel_map)
    edits = _unique(converted, issues)
    a.component_edits = sorted(edits, key=sort_key)
    if stuck:
        names = ", ".join(e.designator for e in stuck[:8]) + ("…" if len(stuck) > 8 else "")
        frame = a.decisions.edit_frame
        issues.append(
            warning(
                "edit_frame",
                f"The positions of {len(stuck)} edited component(s) were entered for a different panel "
                f"structure ({frame.mode if frame else '?'} mode, panel origin "
                f"{frame.panel_origin if frame else '?'}) and are used unchanged; check them: {names}",
                subject="component_edits",
            )
        )
    if not edits:
        return
    ref = a.reference_board
    targets: dict[str, dict[str, list[Part]]] = {"board": {}, "panel": {}}
    for p in a.placements:
        targets["board"].setdefault(p.designator, []).append(p)
    for p in a.panel_parts:
        targets["panel"].setdefault(p.designator, []).append(p)
    added: dict[str, list[Part]] = {"board": [], "panel": []}
    for e in a.component_edits:
        origin = ref if e.level == "board" else (0.0, 0.0)
        problem = _invalid(e)
        if problem:
            issues.append(
                error(
                    "edit_invalid",
                    f"{e.designator or '(no designator)'}: {problem}",
                    designator=e.designator or None,
                    subject=f"{e.level}:{e.designator}",
                )
            )
            continue
        existing = targets[e.level].get(e.designator)
        if e.added:
            if existing:
                issues.append(
                    error(
                        "edit_conflict",
                        f"{e.designator} was added by hand but the export now has a {e.level}-level "
                        f"{e.designator}; edit or delete the added one",
                        designator=e.designator,
                        subject=f"{e.level}:{e.designator}",
                    )
                )
                continue
            part = _added(e, origin, package_of)
            added[e.level].append(part)
            targets[e.level][e.designator] = [part]
            continue
        if not existing:
            issues.append(
                warning(
                    "edit_orphan",
                    f"{e.designator}: the {e.level}-level edit ({describe_edit(e)}) matches no component "
                    "in the export",
                    designator=e.designator,
                    subject=f"{e.level}:{e.designator}",
                )
            )
            continue
        for part in existing:
            _override(part, e, origin)
    for level, parts in (("board", a.placements), ("panel", a.panel_parts)):
        removed = [p for p in parts if p.state == "removed"]
        kept = [p for p in parts if p.state != "removed"] + sorted(added[level], key=lambda p: p.designator)
        if level == "board":
            a.placements, a.removed_placements = kept, removed
        else:
            a.panel_parts, a.removed_panel_parts = kept, removed
    # Flattened panels draw unedited parts where each copy really is; moved parts follow
    # the circuit transforms instead.
    moved = {p.designator for p in a.placements if p.moved}
    for c in a.circuits:
        if c.positions:
            for name in moved:
                c.positions.pop(name, None)
    _outline_checks(a, issues)


def _unique(edits: list[ComponentEdit], issues: list[Issue]) -> list[ComponentEdit]:
    seen: dict[Key, ComponentEdit] = {}
    for e in edits:
        if e.key in seen:
            issues.append(
                error(
                    "edit_invalid",
                    f"{e.designator}: more than one {e.level}-level edit; the first is used",
                    designator=e.designator,
                    subject=f"{e.level}:{e.designator}:duplicate",
                )
            )
            continue
        seen[e.key] = e
    return list(seen.values())


def _invalid(e: ComponentEdit) -> str:
    if not e.designator.strip():
        return "an edit needs a designator"
    if (e.x is None) != (e.y is None):
        return "a position edit needs both X and Y"
    if e.added and (e.x is None or e.layer is None or e.rotation is None):
        return "an added component needs a side, X, Y and a rotation"
    if e.added and e.removed:
        return "an added component cannot also be removed"
    return ""


def _override(p: Part, e: ComponentEdit, origin: tuple[float, float]) -> None:
    """Apply an edit to an export part (x/y of ``e`` are relative to ``origin``)."""
    export: dict[str, object] = {}
    for f in TEXT_FIELDS:
        value = getattr(e, f)
        if value is not None and value != getattr(p, f):
            export[f] = getattr(p, f)
            setattr(p, f, value)
    x, y = (e.x + origin[0], e.y + origin[1]) if e.x is not None and e.y is not None else (p.x, p.y)
    rotation = norm_angle(e.rotation) if e.rotation is not None else p.rotation
    layer = e.layer or p.layer
    if abs(x - p.x) > EPS or abs(y - p.y) > EPS:
        export["x"], export["y"] = p.x, p.y
    if angle_diff(rotation, p.rotation) > EPS:
        export["rotation"] = p.rotation
    if layer != p.layer:
        export["layer"] = p.layer
    if any(k in export for k in POSE_FIELDS):
        _repose(p, x, y, rotation, layer)
    for f in SIZE_FIELDS:
        value = getattr(e, f)
        if value is not None and abs(value - getattr(p, f)) > EPS:
            export[f] = getattr(p, f)
            setattr(p, f, value)
    p.export = export
    p.edit = e
    p.state = "removed" if e.removed else ("edited" if export else "")


def _repose(p: Part, x: float, y: float, rotation: float, layer: str) -> None:
    """Correct where the part is placed.  Its pins and body stay where the PCB has them, so
    the paste check compares the corrected centroid with the part's own pads."""
    if isinstance(p, PlacementInfo):
        p.mirror = layer == "bottom"
    p.x, p.y, p.rotation, p.layer = x, y, rotation, layer
    p.rotation_raw = norm_angle(-rotation)


def _added(e: ComponentEdit, origin: tuple[float, float], package_of: PackageLookup) -> Part:
    x, y = e.x + origin[0], e.y + origin[1]
    rotation = norm_angle(e.rotation or 0.0)
    layer = e.layer or "top"
    # A package of the same name in the export gives the added part its body size, and
    # (board level) pins and a body, so it is drawn and paste-checked like the others.
    pkg = package_of(e.level, e.package) if e.package else None
    size = _added_size(e, pkg)
    if e.level == "panel":
        return PanelPartInfo(
            designator=e.designator,
            part_name=e.part_name or "",
            package=e.package or "",
            layer=layer,
            x=x,
            y=y,
            rotation=rotation,
            rotation_raw=norm_angle(-rotation),
            step="",
            part_number=e.part_number or "",
            state="added",
            edit=e,
            **size,
        )
    p = PlacementInfo(
        designator=e.designator,
        part_name=e.part_name or "",
        package=e.package or "",
        layer=layer,
        x=x,
        y=y,
        rotation_raw=norm_angle(-rotation),
        rotation=rotation,
        mirror=layer == "bottom",
        attributes={},
        part_number=e.part_number or "",
        written=e.designator,
        state="added",
        edit=e,
        **size,
    )
    if pkg is not None:
        tf = pose(x, y, rotation, layer == "bottom")
        p.toeprints = [tf.apply(pin.x, pin.y) for pin in pkg.pins]
        p.body = [[tf.apply(px, py) for px, py in poly] for shape in pkg.outlines for poly in shape.polygons()]
    return p


def _added_size(e: ComponentEdit, pkg: Package | None) -> dict[str, float]:
    """An added part's size: what the edit gives, else (width, length) the package body's."""
    body = (pkg.body_size if pkg is not None else None) or (0.0, 0.0)
    known = {"width": body[0], "length": body[1], "height": 0.0}
    return {f: getattr(e, f) or known[f] for f in SIZE_FIELDS}


def _outline_checks(a: PanelAnalysis, issues: list[Issue]) -> None:
    """Parts the user added or moved must lie on the board (or the panel)."""
    board = Polygon(a.board_outline).buffer(1e-6) if len(a.board_outline) >= 3 else None
    panel = Polygon(a.panel_outline).buffer(1e-6) if len(a.panel_outline) >= 3 else None
    rx, ry = a.reference_board
    c1 = a.circuits[0].transform if a.circuits else Transform()
    for p in a.placements:
        moved = p.state == "added" or "x" in p.export
        if moved and board is not None and not board.contains(Point(p.x, p.y)):
            issues.append(
                warning(
                    "outside_outline",
                    f"{p.designator} ({'added' if p.state == 'added' else 'moved'} by hand) is outside the board "
                    f"outline at X {p.x - rx:.3f}, Y {p.y - ry:.3f} (circuit-relative)",
                    designator=p.designator,
                    location=c1.apply(p.x, p.y),
                    subject="board",
                )
            )
    for p in a.panel_parts:
        moved = p.state == "added" or "x" in p.export
        if moved and panel is not None and not panel.contains(Point(p.x, p.y)):
            issues.append(
                warning(
                    "outside_outline",
                    f"{p.designator} ({'added' if p.state == 'added' else 'moved'} by hand) is outside the panel "
                    f"outline at X {p.x:.3f}, Y {p.y:.3f}",
                    designator=p.designator,
                    location=(p.x, p.y),
                    subject="panel",
                )
            )


# ====================================================================== describing
def sort_key(e: ComponentEdit) -> tuple:
    return (e.level, natural_key(e.designator))


def natural_key(text: str) -> tuple:
    """C2 before C10."""
    out: list = []
    num = ""
    for ch in text:
        if ch.isdigit():
            num += ch
            continue
        if num:
            out.append((1, int(num), ""))
            num = ""
        out.append((2, 0, ch.lower()))
    if num:
        out.append((1, int(num), ""))
    return tuple(out)


def changed_labels(fields: Iterable[str]) -> list[str]:
    """What changed, in words: X and Y are the "position", the size fields the "size"."""
    out: list[str] = []
    for f in fields:
        label = "position" if f in ("x", "y") else ("size" if f in SIZE_FIELDS else FIELD_LABELS[f])
        if label not in out:
            out.append(label)
    return out


def describe_edit(e: ComponentEdit) -> str:
    if e.added:
        return "added"
    parts = []
    if e.removed:
        parts.append("removed" + (f": {REASON_LABELS.get(e.reason, e.reason)}" if e.reason else ""))
    changed = changed_labels(f for f in EDIT_FIELDS if getattr(e, f) is not None)
    if changed:
        parts.append("changes " + ", ".join(changed))
    return "; ".join(parts) or "no change"


def status_text(part: Part) -> str:
    """What the components table shows in its Status column."""
    e = part.edit
    note = f" — {e.note}" if e is not None and e.note else ""
    if part.state == "added":
        return "added" + note
    if part.state == "removed":
        reason = REASON_LABELS.get(e.reason, e.reason) if e is not None and e.reason else ""
        return "removed" + (f": {reason}" if reason else "") + note
    if part.state == "edited":
        return "edited: " + ", ".join(changed_labels(f for f in EDIT_FIELDS if f in part.export)) + note
    return ""


def edits_summary(edits: Iterable[ComponentEdit], limit: int = 8) -> str:
    """One line for reports: "2 removed (J1, C2), 1 added (U99), 1 edited (C1)"."""
    groups: dict[str, list[str]] = {"removed": [], "added": [], "edited": []}
    for e in sorted(edits, key=sort_key):
        name = e.designator + (" (panel)" if e.level == "panel" else "")
        if e.added:
            groups["added"].append(name)
        elif e.removed:
            groups["removed"].append(name + (f" {e.reason}" if e.reason else ""))
        elif e.overrides:
            groups["edited"].append(name)
    out = []
    for kind, names in groups.items():
        if names:
            shown = ", ".join(names[:limit]) + (", …" if len(names) > limit else "")
            out.append(f"{len(names)} {kind} ({shown})")
    return "; ".join(out)


def level_of(part: Part) -> str:
    return "board" if isinstance(part, PlacementInfo) else "panel"


def all_parts(a: PanelAnalysis) -> list[tuple[str, Part]]:
    """Every component of the analysis with its level, removed ones included."""
    return (
        [("board", p) for p in a.placements]
        + [("board", p) for p in a.removed_placements]
        + [("panel", p) for p in a.panel_parts]
        + [("panel", p) for p in a.removed_panel_parts]
    )


def find_part(a: PanelAnalysis, level: str, designator: str) -> Part | None:
    for lv, p in all_parts(a):
        if lv == level and p.designator == designator:
            return p
    return None


def shown_values(a: PanelAnalysis, part: Part, *, export: bool = False) -> dict[str, object]:
    """The values the GUI shows for a part (x/y circuit-relative for board-level parts).
    With ``export``, the export's values before any edit."""
    values = {f: getattr(part, f) for f in EDIT_FIELDS}
    if export:
        values.update(part.export)
    if isinstance(part, PlacementInfo):
        rx, ry = a.reference_board
        values["x"] = values["x"] - rx
        values["y"] = values["y"] - ry
    return values


def edit_from_values(
    a: PanelAnalysis, level: str, designator: str, values: dict[str, object], note: str | None = None
) -> ComponentEdit | None:
    """The edit that makes an export component show ``values`` (as :func:`shown_values`
    gives them); fields equal to the export's are left out.  None when nothing is left.
    ``note`` None keeps the existing edit's note.  Keeps an existing removal."""
    part = find_part(a, level, designator)
    if part is None:
        raise KeyError((level, designator))
    old = part.edit
    if old is not None and old.added:
        return added_edit(level, designator, {**shown_values(a, part), **values}, old.note if note is None else note)
    export = shown_values(a, part, export=True)
    changes: dict[str, object] = {}
    for f in TEXT_FIELDS + ("layer",):
        v = values.get(f)
        if v is not None and v != export[f]:
            changes[f] = v
    vx, vy = values.get("x"), values.get("y")
    if vx is not None and vy is not None and (abs(vx - export["x"]) > EPS or abs(vy - export["y"]) > EPS):
        changes["x"], changes["y"] = r6(vx), r6(vy)
    rot = values.get("rotation")
    if rot is not None and angle_diff(rot, export["rotation"]) > EPS:
        changes["rotation"] = angle6(rot)
    for f in SIZE_FIELDS:
        v = values.get(f)
        if v is not None and abs(v - export[f]) > EPS:
            changes[f] = r6(v)
    removed = old is not None and old.removed
    note = (old.note if old is not None else "") if note is None else note
    if not changes and not removed:
        return None
    return ComponentEdit(
        designator=designator,
        level=level,
        removed=removed,
        reason=old.reason if removed else "",
        note=note,
        **changes,
    )


def added_edit(level: str, designator: str, values: dict[str, object], note: str = "") -> ComponentEdit:
    return ComponentEdit(
        designator=designator.strip(),
        level=level,
        added=True,
        note=note,
        part_name=str(values.get("part_name") or ""),
        part_number=str(values.get("part_number") or ""),
        package=str(values.get("package") or ""),
        layer=values.get("layer") or "top",
        x=r6(values.get("x") or 0.0),
        y=r6(values.get("y") or 0.0),
        rotation=angle6(values.get("rotation") or 0.0),
        # 0 (unknown) is left unset: the package body, if the export has it, gives the size.
        **{f: r6(values[f]) for f in SIZE_FIELDS if values.get(f)},
    )


# ====================================================================== list operations
def edit_for(edits: Iterable[ComponentEdit], key: Key) -> ComponentEdit | None:
    return next((e for e in edits if e.key == key), None)


def set_edits(edits: Iterable[ComponentEdit], new: Iterable[ComponentEdit], drop: Iterable[Key] = ()) -> list[ComponentEdit]:
    """``edits`` with the entries for ``new``'s keys replaced and ``drop`` removed, sorted."""
    new = list(new)
    gone = {e.key for e in new} | set(drop)
    return sorted([e for e in edits if e.key not in gone] + new, key=sort_key)


def remove_parts(edits: Iterable[ComponentEdit], keys: Iterable[Key], reason: str, note: str = "") -> list[ComponentEdit]:
    """Mark components removed.  A removed component that was added by hand is deleted."""
    edits = list(edits)
    new, drop = [], []
    for key in keys:
        e = edit_for(edits, key)
        if e is not None and e.added:
            drop.append(key)
        elif e is not None:
            new.append(replace(e, removed=True, reason=reason, note=note or e.note))
        else:
            new.append(ComponentEdit(designator=key[1], level=key[0], removed=True, reason=reason, note=note))
    return set_edits(edits, new, drop)


def restore_parts(edits: Iterable[ComponentEdit], keys: Iterable[Key]) -> list[ComponentEdit]:
    """Undo removals; changes made before the removal stay."""
    edits = list(edits)
    new, drop = [], []
    for key in keys:
        e = edit_for(edits, key)
        if e is None or not e.removed:
            continue
        kept = replace(e, removed=False, reason="")
        if kept.overrides:
            new.append(kept)
        else:
            drop.append(key)
    return set_edits(edits, new, drop)


def revert_parts(edits: Iterable[ComponentEdit], keys: Iterable[Key]) -> list[ComponentEdit]:
    """Back to the export: drops every edit of these components except additions."""
    edits = list(edits)
    drop = [k for k in keys if (e := edit_for(edits, k)) is not None and not e.added]
    return set_edits(edits, [], drop)


# ====================================================================== suggestions
SUGGESTIONS = {
    "through-hole": "Through-hole parts",
    "not-populated": "Not-populated parts (DNP)",
    "mechanical": "Fiducials and mechanical parts",
    "not-in-bom": "Parts not in the BOM",
}
#: The removal reason each suggestion proposes.
SUGGESTED_REASON = {
    "through-hole": "through-hole",
    "not-populated": "not-populated",
    "mechanical": "mechanical",
    "not-in-bom": "not-populated",
}
DNP_VALUES = {
    "dnp", "dnf", "dni", "nf", "no pop", "nopop", "no stuff", "nostuff", "not fitted", "not populated",
    "not placed", "do not populate", "do not place", "do not fit", "do not mount",
}  # fmt: skip
DNP_KEYS = {"no_pop", "nopop", "dnp", "dnf", "dni", "not_fitted", "notfitted", "not fitted"}
TRUE_VALUES = {"yes", "y", "true", "1", "x", "on"}


@dataclass(frozen=True)
class Suggestion:
    level: str
    designator: str
    why: str

    @property
    def key(self) -> Key:
        return (self.level, self.designator)


def dnp_marker(attributes: dict[str, str]) -> str | None:
    """Why the attributes say "not populated", or None."""
    for key, value in attributes.items():
        name = key.lower().lstrip(".").removeprefix("prp.").removeprefix("bom.")
        v = str(value).strip().lower()
        if name in DNP_KEYS and v in TRUE_VALUES:
            return f"{key} = {value}"
        if name == "fitted" and v in ("no", "n", "false", "0"):
            return f"{key} = {value}"
        if v in DNP_VALUES:
            return f"{key} = {value}"
    return None


def suggest_removals(a: PanelAnalysis) -> dict[str, list[Suggestion]]:
    """Components that are probably not machine-placed, by kind (see :data:`SUGGESTIONS`).
    Only suggestions: the user reviews the list before anything is removed."""
    out: dict[str, list[Suggestion]] = {k: [] for k in SUGGESTIONS}
    patterns = a.settings.fiducials.patterns
    bom = set(a.bom.designators) if a.bom is not None else None
    parts = [("board", p) for p in a.placements] + [("panel", p) for p in a.panel_parts]
    # "No pins" only means something when the export gives the other parts their pins.
    with_pins = sum(1 for p in a.placements if p.toeprints)
    pins_known = with_pins > len(a.placements) / 2
    for level, p in parts:
        if p.state == "added":
            continue
        fiducial = matches_pattern(p.designator, patterns) or bool(p.package and matches_pattern(p.package, patterns))
        if fiducial:
            out["mechanical"].append(Suggestion(level, p.designator, "fiducial (designator or package matches the fiducial pattern)"))
        elif level == "board" and pins_known and not p.toeprints:
            out["mechanical"].append(Suggestion(level, p.designator, "no pins"))
        mount = str(p.attributes.get(".comp_mount_type", "")).lower()
        if mount in ("thmt", "pressfit"):
            out["through-hole"].append(Suggestion(level, p.designator, f".comp_mount_type = {mount}"))
        elif not fiducial and isinstance(p, PlacementInfo) and p.paste is not None and p.paste.status == "no-paste":
            out["through-hole"].append(Suggestion(level, p.designator, "no paste on its pads"))
        marker = dnp_marker(p.attributes)
        if marker:
            out["not-populated"].append(Suggestion(level, p.designator, marker))
        if bom is not None and level == "board" and p.designator not in bom:
            out["not-in-bom"].append(Suggestion(level, p.designator, "not in the BOM"))
    for items in out.values():
        items.sort(key=lambda s: (s.level, natural_key(s.designator)))
    return out
