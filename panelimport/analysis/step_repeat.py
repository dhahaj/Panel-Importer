"""Expansion of STEP-REPEAT blocks into placed step instances.

For a block in a parent step, instance (i, j) maps child coordinates to the parent as

    p_parent = T(X + i*DX, Y + j*DY) · Mx? · R_cw(ANGLE) · T(-anchor) · p_child

where ``anchor`` is the child's datum (spec: X/Y place the datum of the nested step)
or its origin (setting ``step_repeat_anchor``), ``R_cw`` rotates clockwise and ``Mx``
negates X when MIRROR (or FLIP) is set: rotation first, then mirroring, as for every
ODB++ transform.  FLIP additionally swaps the step's top and bottom side.
Nested repeats compose recursively.  Instances are produced in the specification's
order: along X first, then Y, block by block.
"""

from __future__ import annotations

from dataclasses import dataclass

from panelimport.analysis.transforms import Transform
from panelimport.io.odb.job import OdbJob
from panelimport.io.odb.stephdr import StepRepeat
from panelimport.model.issues import Issue, error, warning


@dataclass(frozen=True)
class Instance:
    step: str
    transform: Transform  # child step coordinates -> panel step coordinates
    flip: bool  # top and bottom side swapped
    path: tuple[tuple[str, int, int, int], ...]  # (parent step, block, i, j) from the panel down
    repeat: StepRepeat

    @property
    def label(self) -> str:
        return " / ".join(f"{p}[{b}]({i},{j})" for p, b, i, j in self.path)


def local_transform(rep: StepRepeat, i: int, j: int, anchor: tuple[float, float]) -> Transform:
    t = Transform.rotation_cw(rep.angle) @ Transform.translation(-anchor[0], -anchor[1])
    if rep.mirror != rep.flip:
        t = Transform.mirror_x() @ t
    return Transform.translation(rep.x + i * rep.dx, rep.y + j * rep.dy) @ t


def expand(
    job: OdbJob, panel_step: str, anchor_mode: str = "datum"
) -> tuple[list[Instance], list[Issue]]:
    issues: list[Issue] = []
    out: list[Instance] = []
    reported: set[str] = set()

    def rec(step: str, parent: Transform, flip: bool, path: tuple, stack: tuple[str, ...]) -> None:
        hdr = job.stephdr(step)
        if hdr is None:
            return
        for bi, rep in enumerate(hdr.repeats):
            ms = job.matrix.step(rep.name)
            if ms is None:
                key = f"missing:{rep.name.lower()}"
                if key not in reported:
                    reported.add(key)
                    issues.append(
                        error(
                            "missing_step",
                            f"STEP-REPEAT in '{step}' names step '{rep.name}', which is not in the matrix",
                            file=hdr.path,
                            subject=rep.name,
                        )
                    )
                continue
            child = ms.name
            if child.lower() in stack:
                issues.append(
                    error(
                        "circular_repeat",
                        f"STEP-REPEAT of '{child}' inside '{step}' is circular",
                        file=hdr.path,
                        subject=child,
                    )
                )
                continue
            child_hdr = job.stephdr(child)
            if child_hdr is None:
                key = f"hdr:{child.lower()}"
                if key not in reported:
                    reported.add(key)
                    issues.append(
                        error(
                            "missing_file",
                            f"Missing required file steps/{child}/stephdr",
                            file=f"steps/{child}/stephdr",
                            subject=f"steps/{child}/stephdr",
                        )
                    )
                continue
            if anchor_mode == "origin":
                anchor = child_hdr.origin
            else:
                anchor = child_hdr.datum
            if child_hdr.datum != child_hdr.origin and f"anchor:{child.lower()}" not in reported:
                reported.add(f"anchor:{child.lower()}")
                issues.append(
                    warning(
                        "datum_origin_differ",
                        f"Step '{child}' has datum ({child_hdr.datum[0]:.4f}, {child_hdr.datum[1]:.4f}) and origin "
                        f"({child_hdr.origin[0]:.4f}, {child_hdr.origin[1]:.4f}); STEP-REPEAT X/Y are read as the "
                        f"{anchor_mode} position (setting step_repeat_anchor). Verify against the export.",
                        subject=child,
                    )
                )
            if rep.flip and f"flip:{step.lower()}:{bi}" not in reported:
                reported.add(f"flip:{step.lower()}:{bi}")
                issues.append(
                    warning(
                        "step_flipped",
                        f"STEP-REPEAT of '{child}' in '{step}' (line {rep.line}) is FLIPped: its top and bottom "
                        "sides are swapped on the panel",
                        file=hdr.path,
                        subject=f"{step}:{bi}",
                    )
                )
            for j in range(rep.ny):
                for i in range(rep.nx):
                    tf = parent @ local_transform(rep, i, j, anchor)
                    inst = Instance(child, tf, flip != rep.flip, path + ((step, bi, i, j),), rep)
                    out.append(inst)
                    rec(child, tf, inst.flip, inst.path, stack + (child.lower(),))

    rec(panel_step, Transform(), False, (), (panel_step.lower(),))
    return out, issues
