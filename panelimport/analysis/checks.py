"""Checks run after the panel structure is known.  Each finding is an :class:`Issue`.

| Check                                             | Default        | Severity |
| ------------------------------------------------- | -------------- | -------- |
| Step-repeat expansion vs flattened copies         | 0.01 mm        | Error    |
| Circuit rotated or mirrored relative to circuit 1 | 0.05°          | Warning  |
| Non-uniform grid                                  | 0.01 mm        | Warning  |
| Centroid not on its pads (paste cluster centre)   | 0.25 mm        | Warning  |
| Centroid pattern shifted against paste            | median > 0.1   | Error    |
| No paste near a part (likely through-hole)        |                | Info     |
| Duplicate designator inside one circuit           | exact          | Error    |
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from panelimport.analysis.layers import PadSet
from panelimport.analysis.transforms import Transform, angle_diff
from panelimport.model.issues import Issue, error, info, warning
from panelimport.settings import Tolerances


# ---------------------------------------------------------------- paste
@dataclass
class PartToCheck:
    designator: str
    side: str  # "top" | "bottom"
    x: float  # same frame as the paste pads
    y: float
    toeprints: list[tuple[float, float]]
    body: tuple[float, float, float, float] | None  # bounding box in the same frame
    circuit: int | None = None
    location: tuple[float, float] | None = None  # panel frame, for zooming


@dataclass
class PasteResult:
    status: str  # "ok" | "off" | "no-paste" | "no-layer"
    offset: tuple[float, float] | None = None
    pads: int = 0

    @property
    def distance(self) -> float | None:
        return math.hypot(*self.offset) if self.offset else None

    def describe(self) -> str:
        if self.status == "no-layer":
            return "no paste layer"
        if self.status == "no-paste":
            return "no paste"
        d = self.distance or 0.0
        return f"{'OK' if self.status == 'ok' else 'OFF'} {d:.3f} mm"


def match_pads(part: PartToCheck, pads: PadSet, radius: float) -> list[int]:
    """Paste pads belonging to a part: the pad under (or nearest to) each toeprint."""
    found: set[int] = set()
    if part.toeprints:
        for tx, ty in part.toeprints:
            hits = pads.index.containing(tx, ty)
            if hits:
                found.add(min(hits, key=lambda i: math.hypot(*(pads.centres[i] - (tx, ty)))))
                continue
            near = pads.index.within(tx, ty, radius)
            if near:
                found.add(near[0])
        return sorted(found)
    if part.body is not None:
        x0, y0, x1, y1 = part.body
        for i in pads.index.overlapping(x0, y0, x1, y1):
            cx, cy = pads.centres[i]
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                found.add(i)
        return sorted(found)
    return pads.index.within(part.x, part.y, radius)


def paste_check(
    parts: list[PartToCheck],
    paste: dict[str, PadSet | None],
    tol: Tolerances,
    scope: str,
) -> tuple[list[PasteResult], list[Issue]]:
    """Centroid-on-pads per part, plus the per-side pattern shift.

    ``scope`` names what was checked (e.g. "board step 'pcb'") for the messages.
    """
    results: list[PasteResult] = []
    issues: list[Issue] = []
    offsets: dict[str, list[tuple[float, float]]] = {"top": [], "bottom": []}
    for part in parts:
        pads = paste.get(part.side)
        if pads is None:
            results.append(PasteResult("no-layer"))
            continue
        idx = match_pads(part, pads, tol.pad_match_radius)
        if not idx:
            results.append(PasteResult("no-paste"))
            issues.append(
                info(
                    "no_paste",
                    f"No paste near {part.designator} ({part.side}); likely a through-hole part",
                    designator=part.designator,
                    circuit=part.circuit,
                    location=part.location,
                )
            )
            continue
        c = pads.centres[idx]
        off = (part.x - (c[:, 0].min() + c[:, 0].max()) / 2, part.y - (c[:, 1].min() + c[:, 1].max()) / 2)
        offsets[part.side].append(off)
        off_pads = math.hypot(*off) > tol.centroid_on_pads
        results.append(PasteResult("off" if off_pads else "ok", off, len(idx)))

    # A whole side shifted by one vector is one error, not a warning per part.
    shifts: dict[str, tuple[float, float]] = {}
    for side, offs in offsets.items():
        if len(offs) < 3:
            continue
        arr = np.array(offs)
        mx, my = float(np.median(arr[:, 0])), float(np.median(arr[:, 1]))
        shift = math.hypot(mx, my)
        if shift > tol.pattern_shift:
            shifts[side] = (mx, my)
            explained = sum(1 for o in offs if math.hypot(o[0] - mx, o[1] - my) <= tol.centroid_on_pads)
            issues.append(
                error(
                    "pattern_shift",
                    f"The {side}-side centroids in {scope} are shifted against the paste layer by "
                    f"ΔX {mx:+.3f}, ΔY {my:+.3f} mm ({shift:.3f} mm, median over {len(offs)} parts; "
                    f"{explained} parts follow this shift)",
                    subject=f"{scope}:{side}",
                    data={"dx": mx, "dy": my, "distance": shift, "parts": len(offs), "side": side},
                )
            )

    for part, res in zip(parts, results):
        if res.status != "off" or res.offset is None:
            continue
        shift = shifts.get(part.side)
        if shift and math.hypot(res.offset[0] - shift[0], res.offset[1] - shift[1]) <= tol.centroid_on_pads:
            continue  # explained by the pattern shift reported above
        dist = math.hypot(*res.offset)
        issues.append(
            warning(
                "centroid_off_pads",
                f"Centroid of {part.designator} is {dist:.3f} mm from the centre of its paste pads "
                f"(ΔX {res.offset[0]:+.3f}, ΔY {res.offset[1]:+.3f} mm)",
                designator=part.designator,
                circuit=part.circuit,
                location=part.location,
                data={"dx": res.offset[0], "dy": res.offset[1], "distance": dist},
            )
        )
    return results, issues


# ---------------------------------------------------------------- duplicates
def duplicate_designators(names: list[str], circuit: int | None = None) -> list[Issue]:
    counts = Counter(names)
    return [
        error(
            "duplicate_designator",
            f"Designator {name} appears {n} times in {'circuit ' + str(circuit) if circuit else 'the board'}",
            designator=name,
            circuit=circuit,
        )
        for name, n in sorted(counts.items())
        if n > 1
    ]


# ---------------------------------------------------------------- circuits
@dataclass
class CircuitGeometry:
    index: int
    transform: Transform  # board frame -> panel frame
    rel_rotation: float = 0.0
    rel_mirror: bool = False
    center: tuple[float, float] = (0.0, 0.0)
    extra: dict = field(default_factory=dict)


def orientation_checks(circuits: list[CircuitGeometry], tol: Tolerances) -> list[Issue]:
    issues = []
    for c in circuits[1:]:
        if c.rel_mirror:
            issues.append(
                warning(
                    "circuit_mirrored",
                    f"Circuit {c.index} is mirrored relative to circuit 1",
                    circuit=c.index,
                    location=c.center,
                )
            )
        if angle_diff(c.rel_rotation, 0.0) > tol.rotation:
            issues.append(
                warning(
                    "circuit_rotated",
                    f"Circuit {c.index} is rotated {c.rel_rotation:.3f}° (CCW) relative to circuit 1",
                    circuit=c.index,
                    location=c.center,
                    data={"rotation": c.rel_rotation},
                )
            )
    if circuits:
        c1 = circuits[0]
        rot = c1.transform.rotation
        if c1.transform.mirrored:
            issues.append(
                warning(
                    "circuit_mirrored",
                    "Circuit 1 is mirrored on the panel; placements are in the board's own frame",
                    circuit=1,
                    location=c1.center,
                )
            )
        if angle_diff(rot, 0.0) > tol.rotation:
            issues.append(
                warning(
                    "circuit_rotated",
                    f"Circuit 1 is rotated {rot:.3f}° (CCW) on the panel; placements are in the board's own frame",
                    circuit=1,
                    location=c1.center,
                    data={"rotation": rot},
                )
            )
    return issues


# ---------------------------------------------------------------- cross-check
@dataclass
class ExpectedCopy:
    designator: str
    circuit: int
    x: float
    y: float
    rotation_raw: float | None  # ODB++ clockwise rotation expected, None when mirrored


def crosscheck(
    expected: list[ExpectedCopy],
    copies: dict[str, list[tuple[float, float, float, str]]],
    tol: Tolerances,
    report_missing: bool,
) -> list[Issue]:
    """Compare flattened copies in the panel step with the expanded step-repeat.

    ``copies`` maps a designator to its copies (x, y, rotation_raw, written name) in the
    panel frame; ``expected`` lists where the step-repeat puts every board component.
    """
    issues: list[Issue] = []
    by_name: dict[str, list[ExpectedCopy]] = {}
    for e in expected:
        by_name.setdefault(e.designator, []).append(e)
    for name, exps in sorted(by_name.items()):
        found = list(copies.get(name, []))
        if not found and not report_missing:
            continue
        used: set[int] = set()
        for e in exps:
            best = None
            for k, (x, y, _rot, _w) in enumerate(found):
                if k in used:
                    continue
                d = math.hypot(x - e.x, y - e.y)
                if best is None or d < best[0]:
                    best = (d, k)
            if best is None or best[0] > max(tol.crosscheck * 50, 1.0):
                issues.append(
                    error(
                        "crosscheck_missing",
                        f"No flattened copy of {name} in the panel step for circuit {e.circuit} "
                        f"(expected at {e.x:.3f}, {e.y:.3f})",
                        designator=name,
                        circuit=e.circuit,
                        location=(e.x, e.y),
                    )
                )
                continue
            d, k = best
            used.add(k)
            x, y, rot, written = found[k]
            if d > tol.crosscheck:
                issues.append(
                    error(
                        "crosscheck_mismatch",
                        f"Flattened copy {written} is {d:.4f} mm from where the step-repeat puts {name} in "
                        f"circuit {e.circuit}",
                        designator=name,
                        circuit=e.circuit,
                        location=(x, y),
                        data={"distance": d},
                    )
                )
            elif e.rotation_raw is not None and angle_diff(rot, e.rotation_raw) > tol.rotation:
                issues.append(
                    error(
                        "crosscheck_mismatch",
                        f"Flattened copy {written} is rotated {rot:.3f}° but the step-repeat gives "
                        f"{e.rotation_raw:.3f}° (ODB++ clockwise) in circuit {e.circuit}",
                        designator=name,
                        circuit=e.circuit,
                        location=(x, y),
                    )
                )
        for k, (x, y, _rot, written) in enumerate(found):
            if k not in used:
                issues.append(
                    error(
                        "crosscheck_extra",
                        f"Flattened copy {written} at ({x:.3f}, {y:.3f}) matches no step-repeat instance",
                        designator=name,
                        location=(x, y),
                        subject=f"{written}@{x:.3f},{y:.3f}",
                    )
                )
    return issues
