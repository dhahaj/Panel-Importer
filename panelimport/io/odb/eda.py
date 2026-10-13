"""Parser for ODB++ ``steps/<step>/eda/data``.

Phase 1 needs the packages (``PKG``) with their outlines and pins (``PIN``) for package
names and body outlines.  Net (``NET``, ``SNT``, ``FID``) and feature-group (``FGR``)
records are recognised and skipped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from panelimport.io.odb.common import (
    FileProblems,
    Units,
    UnitsDirective,
    parse_units,
    split_quoted,
    split_record,
)
from panelimport.io.odb.features import Contour, arc_points, close_contour


@dataclass
class OutlineShape:
    kind: str  # "rect" | "circle" | "square" | "contour"
    params: tuple[float, ...] = ()  # rect: llx, lly, w, h; circle: xc, yc, r; square: xc, yc, half
    contours: list[Contour] = field(default_factory=list)

    def polygons(self, segments: int = 32) -> list[list[tuple[float, float]]]:
        """Closed outline(s) as point lists, islands only (mm, package frame)."""
        if self.kind == "rect":
            x, y, w, h = self.params
            return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
        if self.kind == "square":
            xc, yc, s = self.params
            return [[(xc - s, yc - s), (xc + s, yc - s), (xc + s, yc + s), (xc - s, yc + s)]]
        if self.kind == "circle":
            xc, yc, r = self.params
            return [
                [
                    (xc + r * math.cos(2 * math.pi * i / segments), yc + r * math.sin(2 * math.pi * i / segments))
                    for i in range(segments)
                ]
            ]
        return [c.points for c in self.contours if c.island]


@dataclass
class PackagePin:
    name: str
    type: str
    x: float
    y: float
    fhs: float
    etype: str
    mtype: str
    outlines: list[OutlineShape] = field(default_factory=list)


@dataclass
class Package:
    index: int
    name: str
    pitch: float
    bbox: tuple[float, float, float, float]
    line: int
    attrs_raw: str = ""
    outlines: list[OutlineShape] = field(default_factory=list)
    pins: list[PackagePin] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class EdaData:
    path: str
    units: UnitsDirective
    source: str = ""
    layers: list[str] = field(default_factory=list)
    packages: list[Package] = field(default_factory=list)
    net_count: int = 0
    properties: dict[str, str] = field(default_factory=dict)


_SKIPPED = frozenset(("SNT", "FID"))


def parse_eda(text: str, path: str, default_units: Units) -> tuple[EdaData, FileProblems]:
    problems = FileProblems(path)
    eda = EdaData(path=path, units=UnitsDirective(default_units, False))
    scale = default_units.coord_scale
    context = "board"
    pkg: Package | None = None
    pin: PackagePin | None = None
    contour_group: OutlineShape | None = None
    contour: Contour | None = None
    started = False

    def add_outline(shape: OutlineShape) -> None:
        if context == "pin" and pin is not None:
            pin.outlines.append(shape)
        elif context == "pkg" and pkg is not None:
            pkg.outlines.append(shape)
        else:
            raise ValueError("outline record outside a package or pin")

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line[0] == "#":
            continue
        try:
            head = line.split(None, 1)[0]
            upper = head.upper()

            if contour_group is not None:
                tok = line.split()
                if head == "OB":
                    if contour is not None:
                        raise ValueError("OB before OE")
                    contour = Contour(
                        (tok[3].upper() if len(tok) > 3 else "I") == "I",
                        [(float(tok[1]) * scale, float(tok[2]) * scale)],
                    )
                    continue
                if head == "OS":
                    if contour is None:
                        raise ValueError("OS outside a polygon")
                    contour.points.append((float(tok[1]) * scale, float(tok[2]) * scale))
                    continue
                if head == "OC":
                    if contour is None:
                        raise ValueError("OC outside a polygon")
                    xs, ys = contour.points[-1]
                    contour.points.extend(
                        arc_points(
                            xs,
                            ys,
                            float(tok[1]) * scale,
                            float(tok[2]) * scale,
                            float(tok[3]) * scale,
                            float(tok[4]) * scale,
                            tok[5].upper().startswith("Y"),
                        )
                    )
                    continue
                if head == "OE":
                    if contour is None:
                        raise ValueError("OE without OB")
                    close_contour(contour)
                    contour_group.contours.append(contour)
                    contour = None
                    continue
                if head == "CE":
                    if contour is not None:
                        raise ValueError("CE before OE")
                    add_outline(contour_group)
                    contour_group = None
                    continue
                raise ValueError(f"unexpected record {head!r} inside a contour")

            if upper.startswith("UNITS=") or head == "U":
                value = line.split("=", 1)[1] if "=" in head else (line.split(None, 1)[1] if " " in line else "")
                u = parse_units(value)
                if u is None:
                    problems.bad_units(line_no, value)
                elif started and u is not eda.units.units:
                    problems.bad_line(line_no, raw, "units declared after data records")
                else:
                    eda.units = UnitsDirective(u, True)
                    scale = u.coord_scale
                continue
            if upper.startswith("ID="):
                continue
            if head == "HDR":
                eda.source = line[3:].strip()
                continue
            if head == "LYR":
                eda.layers.extend(line.split()[1:])
                continue
            if line[0] in "@&":
                continue  # net attribute tables; net attributes are not used
            if head == "PRP":
                before, inside, _after = split_quoted(line)
                tok = before.split()
                if len(tok) < 2:
                    raise ValueError("PRP without a name")
                value = inside if "'" in line else " ".join(tok[2:])
                if context in ("pkg", "pin") and pkg is not None:
                    pkg.properties[tok[1]] = value
                elif context == "board":
                    eda.properties[tok[1]] = value
                continue
            if head == "NET":
                started = True
                context = "net"
                eda.net_count += 1
                continue
            if head in _SKIPPED:
                continue
            if head == "FGR":
                context = "fgr"
                continue
            if head == "PKG":
                started = True
                main, attrs, _id = split_record(line)
                tok = main.split()
                if len(tok) < 7:
                    raise ValueError("PKG record needs a name, pitch and bounding box")
                nums = [float(t) * scale for t in tok[-5:]]
                pkg = Package(
                    index=len(eda.packages),
                    name=" ".join(tok[1:-5]),
                    pitch=nums[0],
                    bbox=(nums[1], nums[2], nums[3], nums[4]),
                    line=line_no,
                    attrs_raw=attrs,
                )
                eda.packages.append(pkg)
                pin = None
                context = "pkg"
                continue
            if head == "PIN":
                if pkg is None:
                    raise ValueError("PIN before the first PKG")
                main, _attrs, _id = split_record(line)
                tok = [t for t in main.split() if not t.upper().startswith("ID=")]
                if len(tok) < 8:
                    raise ValueError("PIN record needs 7 fields")
                pin = PackagePin(
                    name=tok[1],
                    type=tok[2].upper(),
                    x=float(tok[3]) * scale,
                    y=float(tok[4]) * scale,
                    fhs=float(tok[5]) * scale,
                    etype=tok[6].upper(),
                    mtype=tok[7].upper(),
                )
                pkg.pins.append(pin)
                context = "pin"
                continue
            if head == "RC":
                tok = line.split()
                add_outline(OutlineShape("rect", tuple(float(t) * scale for t in tok[1:5])))
                continue
            if head == "CR":
                tok = line.split()
                add_outline(OutlineShape("circle", tuple(float(t) * scale for t in tok[1:4])))
                continue
            if head == "SQ":
                tok = line.split()
                add_outline(OutlineShape("square", tuple(float(t) * scale for t in tok[1:4])))
                continue
            if head == "CT":
                if context not in ("pkg", "pin"):
                    raise ValueError("contour outside a package or pin")
                contour_group = OutlineShape("contour")
                continue
            problems.unknown_record(head, line_no)
        except (ValueError, IndexError) as exc:
            problems.bad_line(line_no, raw, str(exc) or type(exc).__name__)

    if contour_group is not None:
        problems.bad_line(0, "CT", "contour not closed with CE")
    return eda, problems
