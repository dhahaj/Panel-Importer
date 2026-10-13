"""ODB++ attribute definitions and resolution of ``n=v`` attribute assignments.

Feature, component and net records reference attributes by index into the file's
``@`` (names) and ``&`` (text strings) tables.  How the value is read depends on the
attribute type: OPTION values are option indices, TEXT values are ``&`` indices,
INTEGER/FLOAT values are numbers and BOOLEAN attributes have no value.

Types come from ``misc/sysattr*`` and ``misc/userattr`` when the export contains them,
and from a short built-in list of system attributes defined in the specification.
"""

from __future__ import annotations

from dataclasses import dataclass

from panelimport.io.odb.structured import parse_structured
from panelimport.model.issues import Issue, warning

ATTRIBUTE_TYPES = ("BOOLEAN", "TEXT", "OPTION", "INTEGER", "FLOAT")


@dataclass(frozen=True)
class AttrDef:
    name: str
    type: str
    options: tuple[str, ...] = ()


# System attributes from the ODB++ 8.1 "System Attributes" appendix that Phase 1 uses.
BUILTIN_DEFS: dict[str, AttrDef] = {
    d.name: d
    for d in (
        AttrDef(
            ".pad_usage",
            "OPTION",
            ("toeprint", "via", "g_fiducial", "l_fiducial", "tooling_hole", "bond_finger"),
        ),
        AttrDef(".comp_mount_type", "OPTION", ("other", "smt", "thmt", "pressfit")),
        AttrDef(".smd", "BOOLEAN"),
        AttrDef(".nomenclature", "BOOLEAN"),
        AttrDef(".test_point", "BOOLEAN"),
        AttrDef(".no_pop", "BOOLEAN"),
        AttrDef(".comp_ignore", "BOOLEAN"),
        AttrDef(".geometry", "TEXT"),
        AttrDef(".fiducial_name", "TEXT"),
        AttrDef(".fiducial_rdlist", "TEXT"),
        AttrDef(".comp_variant_list", "TEXT"),
        AttrDef(".comp_height", "FLOAT"),
        AttrDef(".comp_weight", "FLOAT"),
    )
}

ATTRIBUTE_DEF_FILES = (
    "misc/sysattr",
    "misc/sysattr.dfm",
    "misc/sysattr.fab",
    "misc/sysattr.assy",
    "misc/sysattr.test",
    "misc/sysattr.gen",
    "misc/userattr",
)


class AttrDefs:
    def __init__(self, defs: dict[str, AttrDef] | None = None) -> None:
        self._defs: dict[str, AttrDef] = dict(BUILTIN_DEFS)
        if defs:
            self._defs.update(defs)

    def get(self, name: str) -> AttrDef | None:
        return self._defs.get(name.lower())

    def __len__(self) -> int:
        return len(self._defs)

    @classmethod
    def parse(cls, files: list[tuple[str, str]]) -> tuple[AttrDefs, list[Issue]]:
        defs: dict[str, AttrDef] = {}
        issues: list[Issue] = []
        for path, text in files:
            doc = parse_structured(text)
            for block in doc.blocks:
                if block.name not in ATTRIBUTE_TYPES:
                    issues.append(
                        warning(
                            "unknown_field",
                            f"Unrecognized attribute definition type '{block.name}'",
                            file=path,
                            subject=f"{path}:{block.name}",
                        )
                    )
                    continue
                name = block.fields.get("NAME", "").strip()
                if not name:
                    continue
                options: tuple[str, ...] = ()
                if block.name == "OPTION":
                    options = tuple(
                        o.strip() for o in block.fields.get("OPTIONS", "").split(";") if o.strip()
                    )
                defs[name.lower()] = AttrDef(name, block.name, options)
        return cls(defs), issues


def resolve_attributes(
    raw: str,
    names: dict[int, str],
    texts: dict[int, str],
    defs: AttrDefs,
) -> dict[str, str]:
    """Resolve ``"0,2=1,5=1.5"`` into ``{name: value}`` using the file's tables.

    Booleans resolve to ``"YES"``.  A value whose attribute type is unknown resolves
    to the ``&`` text string when the file has one with that index (text attributes
    are what the ``&`` table exists for), otherwise it is kept as written.
    """
    out: dict[str, str] = {}
    if not raw:
        return out
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        idx_text, eq, value = item.partition("=")
        try:
            idx = int(idx_text)
        except ValueError:
            out[f"?{idx_text}"] = value if eq else "YES"
            continue
        name = names.get(idx, f"@{idx}")
        if not eq:
            out[name] = "YES"
            continue
        value = value.strip()
        d = defs.get(name)
        if d is not None and d.type == "OPTION":
            try:
                out[name] = d.options[int(value)]
            except (ValueError, IndexError):
                out[name] = value
        elif d is not None and d.type == "TEXT":
            try:
                out[name] = texts.get(int(value), value)
            except ValueError:
                out[name] = value
        elif d is not None:
            out[name] = value
        elif value.isdigit() and int(value) in texts:
            out[name] = texts[int(value)]
        else:
            out[name] = value
    return out
