"""Parser for ``steps/<step>/stephdr``: units, datum, origin and STEP-REPEAT arrays.

From the specification (v7 and 8.1): ``X``/``Y`` are the "start coordinate for placement
of the datum point of the nested step"; ``DX``/``DY`` the distance between datum points
when ``ANGLE`` = 0; repeats fill a row along X first, then step along Y.  ``ANGLE`` is
clockwise; ``MIRROR`` mirrors X; ``FLIP`` mirrors the step and reverses its layer order.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from panelimport.io.odb.common import Units, UnitsDirective, parse_units, unknown_field_issue, yes_no
from panelimport.io.odb.structured import parse_structured
from panelimport.model.issues import Issue, error

HEADER_FIELDS = frozenset(
    (
        "UNITS",
        "X_DATUM",
        "Y_DATUM",
        "X_ORIGIN",
        "Y_ORIGIN",
        "ID",
        "TOP_ACTIVE",
        "BOTTOM_ACTIVE",
        "RIGHT_ACTIVE",
        "LEFT_ACTIVE",
        "AFFECTING_BOM",
        "AFFECTING_BOM_CHANGED",
    )
)
REPEAT_FIELDS = frozenset(("NAME", "X", "Y", "DX", "DY", "NX", "NY", "ANGLE", "FLIP", "MIRROR"))


@dataclass
class StepRepeat:
    name: str
    x: float  # mm
    y: float
    dx: float
    dy: float
    nx: int
    ny: int
    angle: float  # degrees clockwise
    flip: bool
    mirror: bool
    line: int

    @property
    def count(self) -> int:
        return self.nx * self.ny


@dataclass
class StepHeader:
    path: str
    units: UnitsDirective
    datum: tuple[float, float] = (0.0, 0.0)
    origin: tuple[float, float] = (0.0, 0.0)
    repeats: list[StepRepeat] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)


def parse_stephdr(text: str, path: str, default_units: Units) -> tuple[StepHeader, list[Issue]]:
    doc = parse_structured(text)
    issues: list[Issue] = []
    hdr = StepHeader(path=path, units=UnitsDirective(default_units, False), fields=dict(doc.fields))

    for line_no, line, reason in doc.problems:
        issues.append(
            error("parse_error", f"line {line_no}: {reason}: {line.strip()[:60]!r}", file=path, subject=f"{path}:{line_no}")
        )

    units = default_units
    if "UNITS" in doc.fields:
        u = parse_units(doc.fields["UNITS"])
        if u is None:
            issues.append(
                error("unknown_units", f"Unrecognized units '{doc.fields['UNITS']}'", file=path, subject=f"{path}:units")
            )
        else:
            units = u
            hdr.units = UnitsDirective(u, True)
    s = units.coord_scale

    def num(fields: dict[str, str], key: str, default: float = 0.0) -> float:
        value = fields.get(key, "").strip()
        return float(value) if value else default

    try:
        hdr.datum = (num(doc.fields, "X_DATUM") * s, num(doc.fields, "Y_DATUM") * s)
        hdr.origin = (num(doc.fields, "X_ORIGIN") * s, num(doc.fields, "Y_ORIGIN") * s)
    except ValueError as exc:
        issues.append(error("parse_error", f"datum/origin: {exc}", file=path, subject=f"{path}:datum"))

    unknown_header = [
        k for k in doc.fields if k not in HEADER_FIELDS and not k.startswith("ONLINE_")
    ]
    if unknown_header:
        issues.append(unknown_field_issue(path, "step header", unknown_header, blocking=False))

    for block in doc.blocks:
        if block.name != "STEP-REPEAT":
            issues.append(
                error(
                    "unknown_record",
                    f"Unrecognized array '{block.name}' at line {block.line}",
                    file=path,
                    subject=f"{path}:{block.name}",
                )
            )
            continue
        f = block.fields
        unknown = [k for k in f if k not in REPEAT_FIELDS]
        if unknown:
            # Unknown placement fields could change where circuits are: block confirmation.
            issues.append(unknown_field_issue(path, "STEP-REPEAT", unknown, blocking=True))
        try:
            flip = yes_no(f.get("FLIP", "NO"))
            mirror = yes_no(f.get("MIRROR", "NO"))
            if flip is None or mirror is None:
                raise ValueError(f"FLIP/MIRROR must be YES or NO, got {f.get('FLIP')!r}/{f.get('MIRROR')!r}")
            if "NAME" not in f or not f["NAME"].strip():
                raise ValueError("NAME is missing")
            hdr.repeats.append(
                StepRepeat(
                    name=f["NAME"].strip(),
                    x=num(f, "X") * s,
                    y=num(f, "Y") * s,
                    dx=num(f, "DX") * s,
                    dy=num(f, "DY") * s,
                    nx=int(num(f, "NX", 1)),
                    ny=int(num(f, "NY", 1)),
                    angle=num(f, "ANGLE") % 360.0,
                    flip=flip,
                    mirror=mirror,
                    line=block.line,
                )
            )
        except ValueError as exc:
            issues.append(
                error(
                    "parse_error",
                    f"STEP-REPEAT at line {block.line}: {exc}",
                    file=path,
                    subject=f"{path}:{block.line}",
                )
            )
    for rep in hdr.repeats:
        if rep.nx < 1 or rep.ny < 1:
            issues.append(
                error(
                    "parse_error",
                    f"STEP-REPEAT of '{rep.name}' at line {rep.line} has NX={rep.nx}, NY={rep.ny}",
                    file=path,
                    subject=f"{path}:{rep.line}",
                )
            )
    hdr.repeats = [r for r in hdr.repeats if r.nx >= 1 and r.ny >= 1]
    return hdr, issues
