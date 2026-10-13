"""Parser for ODB++ ``features`` files (layers, profiles and user-defined symbols).

Record types (spec, layers/features): ``L`` line, ``P`` pad, ``A`` arc, ``T`` text,
``B`` barcode and ``S`` surface (with ``OB``/``OS``/``OC``/``OE``/``SE``), plus the
header records ``$`` (symbols), ``@`` (attribute names), ``&`` (attribute texts),
``U``/``UNITS=`` (units), ``F`` (feature count) and ``ID=``.

All coordinates are converted to mm.  Rotations stay clockwise as in ODB++.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from panelimport.io.odb.common import (
    FileProblems,
    Units,
    UnitsDirective,
    parse_units,
    split_quoted,
    split_record,
)
from panelimport.io.odb.symbols import SymbolShape, parse_standard_symbol
from panelimport.model.issues import warning


@dataclass(slots=True)
class Pad:
    x: float
    y: float
    sym: int
    positive: bool
    rotation: float  # degrees clockwise
    mirror: bool
    attrs: str
    index: int
    resize: float = 0.0


@dataclass(slots=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    sym: int
    positive: bool
    attrs: str
    index: int


@dataclass(slots=True)
class Arc:
    x1: float
    y1: float
    x2: float
    y2: float
    xc: float
    yc: float
    sym: int
    positive: bool
    cw: bool
    attrs: str
    index: int


@dataclass(slots=True)
class Contour:
    island: bool
    points: list[tuple[float, float]]


@dataclass(slots=True)
class Surface:
    positive: bool
    contours: list[Contour]
    attrs: str
    index: int


@dataclass(slots=True)
class Text:
    x: float
    y: float
    text: str
    positive: bool
    index: int


@dataclass
class FeatureFile:
    path: str
    units: UnitsDirective
    symbols: dict[int, SymbolShape] = field(default_factory=dict)
    attr_names: dict[int, str] = field(default_factory=dict)
    attr_texts: dict[int, str] = field(default_factory=dict)
    pads: list[Pad] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    surfaces: list[Surface] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    declared_count: int | None = None

    @property
    def feature_count(self) -> int:
        return len(self.pads) + len(self.lines) + len(self.arcs) + len(self.surfaces) + len(self.texts)

    def symbol(self, sym: int) -> SymbolShape:
        shape = self.symbols.get(sym)
        if shape is None:
            return SymbolShape(name=f"${sym}", kind="unknown", width=0.0, height=0.0, resolved=False)
        return shape

    def extent(self) -> tuple[float, float, float, float] | None:
        xs: list[float] = []
        ys: list[float] = []
        for p in self.pads:
            ex = self.symbol(p.sym).local_extent()
            r = max(abs(ex[0]), abs(ex[1]), abs(ex[2]), abs(ex[3]))
            xs += [p.x - r, p.x + r]
            ys += [p.y - r, p.y + r]
        for ln in self.lines:
            w = self.symbol(ln.sym).width / 2
            xs += [ln.x1 - w, ln.x1 + w, ln.x2 - w, ln.x2 + w]
            ys += [ln.y1 - w, ln.y1 + w, ln.y2 - w, ln.y2 + w]
        for a in self.arcs:
            w = self.symbol(a.sym).width / 2
            r = math.hypot(a.x1 - a.xc, a.y1 - a.yc) + w
            xs += [a.xc - r, a.xc + r]
            ys += [a.yc - r, a.yc + r]
        for s in self.surfaces:
            for c in s.contours:
                for x, y in c.points:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)


def arc_points(
    xs: float, ys: float, xe: float, ye: float, xc: float, yc: float, cw: bool, step_deg: float = 5.0
) -> list[tuple[float, float]]:
    """Points along an arc, excluding the start point and ending exactly at the end point.

    Coinciding start and end points describe a full circle (spec, "Angles").
    """
    r = math.hypot(xs - xc, ys - yc)
    if r == 0.0:
        return [(xe, ye)]
    a0 = math.atan2(ys - yc, xs - xc)
    a1 = math.atan2(ye - yc, xe - xc)
    if cw:
        sweep = a0 - a1
    else:
        sweep = a1 - a0
    sweep %= 2 * math.pi
    if sweep < 1e-12:
        sweep = 2 * math.pi
    n = max(2, math.ceil(math.degrees(sweep) / step_deg))
    sign = -1.0 if cw else 1.0
    pts = [
        (xc + r * math.cos(a0 + sign * sweep * i / n), yc + r * math.sin(a0 + sign * sweep * i / n))
        for i in range(1, n)
    ]
    pts.append((xe, ye))
    return pts


def close_contour(contour: Contour) -> None:
    """Drop the closing point that repeats the start (polygons are implicitly closed)."""
    pts = contour.points
    if len(pts) > 1 and abs(pts[-1][0] - pts[0][0]) < 1e-9 and abs(pts[-1][1] - pts[0][1]) < 1e-9:
        pts.pop()


def _orient(tokens: list[str]) -> tuple[float, bool]:
    """Decode ``orient_def``: 0-7 (legacy 90° steps, 4-7 mirrored) or ``8|9 <angle>``."""
    if not tokens:
        return 0.0, False
    code = int(tokens[0])
    if code in (8, 9):
        return float(tokens[1]) % 360.0, code == 9
    if 0 <= code <= 7:
        return float((code % 4) * 90), code >= 4
    raise ValueError(f"invalid orient_def {tokens[0]}")


SymbolResolver = Callable[[str], SymbolShape | None]


def parse_features(
    text: str,
    path: str,
    default_units: Units,
    resolve_user_symbol: SymbolResolver | None = None,
) -> tuple[FeatureFile, FileProblems]:
    problems = FileProblems(path)
    units: Units | None = None
    ff = FeatureFile(path=path, units=UnitsDirective(default_units, False))
    scale = default_units.coord_scale
    started = False
    index = 0
    surface: Surface | None = None
    contour: Contour | None = None
    pending_symbols: list[tuple[int, str, str | None, int]] = []

    def set_units(value: str, line_no: int) -> None:
        nonlocal units, scale
        u = parse_units(value)
        if u is None:
            problems.bad_units(line_no, value)
            return
        if units is not None and u is not units:
            problems.bad_line(line_no, value, "units changed within the file")
            return
        if started and units is None and u is not default_units:
            problems.bad_line(line_no, value, "units declared after features")
            return
        units = u
        scale = u.coord_scale
        ff.units = UnitsDirective(u, True)

    lines = text.splitlines()
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line[0] == "#":
            continue
        try:
            head = line.split(None, 1)[0]
            # ------------------------------------------------------------ surfaces
            if surface is not None:
                tok = line.split()
                rec = tok[0]
                if rec == "OB":
                    if contour is not None:
                        raise ValueError("OB before OE")
                    kind = tok[3].upper() if len(tok) > 3 else "I"
                    if kind not in ("I", "H"):
                        raise ValueError(f"polygon type {tok[3]!r}")
                    contour = Contour(kind == "I", [(float(tok[1]) * scale, float(tok[2]) * scale)])
                    continue
                if rec == "OS":
                    if contour is None:
                        raise ValueError("OS outside a polygon")
                    contour.points.append((float(tok[1]) * scale, float(tok[2]) * scale))
                    continue
                if rec == "OC":
                    if contour is None:
                        raise ValueError("OC outside a polygon")
                    xs, ys = contour.points[-1]
                    xe, ye = float(tok[1]) * scale, float(tok[2]) * scale
                    xc, yc = float(tok[3]) * scale, float(tok[4]) * scale
                    cw = tok[5].upper().startswith("Y")
                    contour.points.extend(arc_points(xs, ys, xe, ye, xc, yc, cw))
                    continue
                if rec == "OE":
                    if contour is None:
                        raise ValueError("OE without OB")
                    close_contour(contour)
                    surface.contours.append(contour)
                    contour = None
                    continue
                if rec == "SE":
                    if contour is not None:
                        raise ValueError("SE before OE")
                    ff.surfaces.append(surface)
                    surface = None
                    continue
                raise ValueError(f"unexpected record {rec!r} inside a surface")

            # ------------------------------------------------------------ header
            c0 = line[0]
            if c0 == "$":
                body = line[1:]
                hash_at = body.find(" #")
                if hash_at >= 0:
                    body = body[:hash_at]
                tok = body.split()
                serial = int(tok[0])
                suffix = tok[2].upper() if len(tok) > 2 else None
                if suffix not in (None, "I", "M"):
                    raise ValueError(f"symbol units {tok[2]!r}")
                pending_symbols.append((serial, tok[1], suffix, line_no))
                continue
            if c0 == "@":
                tok = line[1:].split(None, 1)
                ff.attr_names[int(tok[0])] = tok[1].strip() if len(tok) > 1 else ""
                continue
            if c0 == "&":
                tok = line[1:].split(None, 1)
                ff.attr_texts[int(tok[0])] = tok[1].strip() if len(tok) > 1 else ""
                continue
            if head.upper().startswith("UNITS="):
                set_units(line.split("=", 1)[1], line_no)
                continue
            if head == "U":
                set_units(line.split(None, 1)[1] if " " in line else "", line_no)
                continue
            if head.upper().startswith("ID="):
                continue
            if head == "F":
                ff.declared_count = int(line.split()[1])
                continue

            # ------------------------------------------------------------ features
            if head == "P":
                started = True
                main, attrs, _ = split_record(line)
                tok = main.split()
                if tok[3] == "-1":
                    sym, resize = int(tok[4]), float(tok[5])
                    rest = tok[6:]
                else:
                    sym, resize = int(tok[3]), 0.0
                    rest = tok[4:]
                positive = rest[0].upper() != "N"
                rot, mirror = _orient(rest[2:])
                ff.pads.append(
                    Pad(float(tok[1]) * scale, float(tok[2]) * scale, sym, positive, rot, mirror, attrs, index, resize)
                )
                index += 1
                continue
            if head == "L":
                started = True
                main, attrs, _ = split_record(line)
                tok = main.split()
                ff.lines.append(
                    Line(
                        float(tok[1]) * scale,
                        float(tok[2]) * scale,
                        float(tok[3]) * scale,
                        float(tok[4]) * scale,
                        int(tok[5]),
                        tok[6].upper() != "N",
                        attrs,
                        index,
                    )
                )
                index += 1
                continue
            if head == "A":
                started = True
                main, attrs, _ = split_record(line)
                tok = main.split()
                ff.arcs.append(
                    Arc(
                        float(tok[1]) * scale,
                        float(tok[2]) * scale,
                        float(tok[3]) * scale,
                        float(tok[4]) * scale,
                        float(tok[5]) * scale,
                        float(tok[6]) * scale,
                        int(tok[7]),
                        tok[8].upper() != "N",
                        tok[10].upper().startswith("Y") if len(tok) > 10 else False,
                        attrs,
                        index,
                    )
                )
                index += 1
                continue
            if head == "S":
                started = True
                main, attrs, _ = split_record(line)
                tok = main.split()
                surface = Surface(tok[1].upper() != "N" if len(tok) > 1 else True, [], attrs, index)
                index += 1
                continue
            if head == "T":
                started = True
                before, inside, _after = split_quoted(line)
                tok = before.split()
                ff.texts.append(
                    Text(float(tok[1]) * scale, float(tok[2]) * scale, inside, tok[4].upper() != "N", index)
                )
                index += 1
                continue
            if head == "B":
                started = True
                tok = line.split()
                ff.texts.append(
                    Text(float(tok[1]) * scale, float(tok[2]) * scale, "", tok[5].upper() != "N", index)
                )
                index += 1
                continue
            problems.unknown_record(head, line_no)
        except (ValueError, IndexError) as exc:
            problems.bad_line(line_no, raw, str(exc) or type(exc).__name__)

    if surface is not None:
        problems.bad_line(len(lines), "", "surface not closed with SE")
        if contour is not None:
            surface.contours.append(contour)
        ff.surfaces.append(surface)

    # Symbols are resolved after the units directive is known, wherever it appears.
    file_units = ff.units.units
    for serial, name, suffix, line_no in pending_symbols:
        sym_units = file_units if suffix is None else (Units.INCH if suffix == "I" else Units.MM)
        shape = parse_standard_symbol(name, sym_units.symbol_scale)
        if shape is None and resolve_user_symbol is not None:
            shape = resolve_user_symbol(name)
        if shape is None:
            shape = SymbolShape(name=name, kind="unknown", width=0.0, height=0.0, standard=False, resolved=False)
            problems.add(
                warning(
                    "unknown_symbol",
                    f"Symbol '{name}' (line {line_no}) is neither a standard symbol nor a "
                    "user-defined symbol in this export; its size is unknown",
                    file=path,
                    subject=f"{path}:{name}",
                )
            )
        ff.symbols[serial] = shape
    return ff, problems
