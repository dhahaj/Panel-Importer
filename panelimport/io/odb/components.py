"""Parser for ODB++ ``components`` files (``layers/comp_+_top/components`` etc.).

Records (spec, layers/components): ``CMP`` component, ``PRP`` property, ``TOP``
toeprint, and the BOM description records ``CPN``, ``PKG``, ``IPN``, ``DSC``,
``VPL_VND``, ``VPL_MPN``, ``VND``, ``MPN`` (v7) plus ``LNFILE``, ``QLF``, ``CHS``,
``PRIORITY`` (v8.1).  Every attribute, property and BOM field is kept, because the
Detex part number may arrive in any of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from panelimport.io.odb.attributes import AttrDefs, resolve_attributes
from panelimport.io.odb.common import (
    FileProblems,
    Units,
    UnitsDirective,
    parse_units,
    split_quoted,
    split_record,
)

BOM_RECORDS = frozenset(
    ("CPN", "PKG", "IPN", "DSC", "VPL_VND", "VPL_MPN", "VND", "MPN", "LNFILE", "QLF", "CHS", "PRIORITY")
)


@dataclass(slots=True)
class Toeprint:
    pin_num: int
    x: float
    y: float
    rotation: float
    mirror: bool
    net_num: int
    subnet_num: int
    name: str


@dataclass
class OdbComponent:
    index: int  # position in the file (comp_num in eda/data SNT records)
    pkg_ref: int
    x: float  # mm, step coordinates
    y: float
    rotation: float  # degrees clockwise, as written
    mirror: bool
    name: str  # reference designator
    part_name: str
    line: int
    id: str | None = None
    attrs_raw: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    properties: dict[str, str] = field(default_factory=dict)
    bom: list[tuple[str, str]] = field(default_factory=list)
    toeprints: list[Toeprint] = field(default_factory=list)

    def all_attributes(self) -> dict[str, str]:
        """Attributes, ``PRP`` properties and BOM fields in one flat mapping.

        Properties use their own name unless an attribute already uses it with a
        different value (then ``PRP.<name>``); BOM fields are ``BOM.<record>``, with a
        ``.<n>`` suffix for repeats (alternate parts).
        """
        out = dict(self.attributes)
        for key, value in self.properties.items():
            if key in out and out[key] != value:
                key = f"PRP.{key}"
            out[key] = value
        counts: dict[str, int] = {}
        for record, value in self.bom:
            n = counts.get(record, 0)
            counts[record] = n + 1
            out[f"BOM.{record}" if n == 0 else f"BOM.{record}.{n + 1}"] = value
        return out


@dataclass
class ComponentFile:
    path: str
    units: UnitsDirective
    attr_names: dict[int, str] = field(default_factory=dict)
    attr_texts: dict[int, str] = field(default_factory=dict)
    components: list[OdbComponent] = field(default_factory=list)


def parse_components(
    text: str, path: str, default_units: Units, defs: AttrDefs
) -> tuple[ComponentFile, FileProblems]:
    problems = FileProblems(path)
    cf = ComponentFile(path=path, units=UnitsDirective(default_units, False))
    scale = default_units.coord_scale
    current: OdbComponent | None = None
    started = False

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line[0] == "#":
            continue
        try:
            head = line.split(None, 1)[0]
            c0 = line[0]
            if c0 == "@":
                tok = line[1:].split(None, 1)
                cf.attr_names[int(tok[0])] = tok[1].strip() if len(tok) > 1 else ""
                continue
            if c0 == "&":
                tok = line[1:].split(None, 1)
                cf.attr_texts[int(tok[0])] = tok[1].strip() if len(tok) > 1 else ""
                continue
            if c0 == ";":
                # Attribute list continued on its own line after a CMP record.
                if current is None:
                    raise ValueError("attribute line without a CMP record")
                _main, attrs, rec_id = split_record(line)
                current.attrs_raw = ",".join(a for a in (current.attrs_raw, attrs) if a)
                if rec_id:
                    current.id = rec_id
                continue
            upper = head.upper()
            if upper.startswith("UNITS="):
                u = parse_units(line.split("=", 1)[1])
                if u is None:
                    problems.bad_units(line_no, line.split("=", 1)[1])
                elif started and u is not cf.units.units:
                    problems.bad_line(line_no, raw, "units declared after components")
                else:
                    cf.units = UnitsDirective(u, True)
                    scale = u.coord_scale
                continue
            if head == "U":
                value = line.split(None, 1)[1] if " " in line else ""
                u = parse_units(value)
                if u is None:
                    problems.bad_units(line_no, value)
                elif started and u is not cf.units.units:
                    problems.bad_line(line_no, raw, "units declared after components")
                else:
                    cf.units = UnitsDirective(u, True)
                    scale = u.coord_scale
                continue
            if upper.startswith("ID="):
                continue
            if head == "CMP":
                started = True
                main, attrs, rec_id = split_record(line)
                tok = main.split()
                if len(tok) < 7:
                    raise ValueError("CMP record needs at least 6 fields")
                mirror_flag = tok[5].upper()
                if mirror_flag not in ("N", "M"):
                    raise ValueError(f"mirror flag {tok[5]!r}")
                current = OdbComponent(
                    index=len(cf.components),
                    pkg_ref=int(tok[1]),
                    x=float(tok[2]) * scale,
                    y=float(tok[3]) * scale,
                    rotation=float(tok[4]),
                    mirror=mirror_flag == "M",
                    name=tok[6],
                    part_name=" ".join(tok[7:]),
                    line=line_no,
                    id=rec_id,
                    attrs_raw=attrs,
                )
                cf.components.append(current)
                continue
            if head == "PRP":
                if current is None:
                    raise ValueError("PRP before the first CMP")
                before, inside, _after = split_quoted(line)
                tok = before.split()
                if len(tok) < 2:
                    raise ValueError("PRP without a name")
                if "'" in line:
                    current.properties[tok[1]] = inside
                else:
                    current.properties[tok[1]] = " ".join(tok[2:])
                continue
            if head == "TOP":
                if current is None:
                    raise ValueError("TOP before the first CMP")
                main, _attrs, _id = split_record(line)
                tok = main.split()
                current.toeprints.append(
                    Toeprint(
                        pin_num=int(tok[1]),
                        x=float(tok[2]) * scale,
                        y=float(tok[3]) * scale,
                        rotation=float(tok[4]),
                        mirror=tok[5].upper() == "M",
                        net_num=int(tok[6]),
                        subnet_num=int(tok[7]),
                        name=" ".join(tok[8:]),
                    )
                )
                continue
            if upper in BOM_RECORDS:
                if current is None:
                    raise ValueError(f"{head} before the first CMP")
                value = line.split(None, 1)[1].strip() if " " in line else ""
                current.bom.append((upper, value))
                continue
            problems.unknown_record(head, line_no)
        except (ValueError, IndexError) as exc:
            problems.bad_line(line_no, raw, str(exc) or type(exc).__name__)

    for comp in cf.components:
        comp.attributes = resolve_attributes(comp.attrs_raw, cf.attr_names, cf.attr_texts, defs)
    return cf, problems
