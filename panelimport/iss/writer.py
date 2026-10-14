"""ISS XML text.  A small dedicated writer, not a general XML library's serializer, so
the rules JaNets depends on cannot drift:

* self-closing tags have a space (``<tag />``): JaNets hangs silently on ``<tag/>``;
* ``<?xml version="1.0" encoding="utf-8"?>``, UTF-8 with BOM, CRLF, 2-space indent;
* numbers have at most 4 decimals, no trailing zeros, no exponent, never ``-0``;
* attributes in the order of the known-good programs; text and attributes escaped;
* Juki's spellings ``witdh`` and ``connecterHeight`` are kept.

The written file is checked before it replaces anything: it must not match
``[^ ]/>``, must parse, and must read back to the same program.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from panelimport.iss.checks import Prepared
from panelimport.iss.mapping import IssLayout, Program
from panelimport.iss.settings import IssSettings

ISS_SUFFIX = ".iss"
XML_DECLARATION = '<?xml version="1.0" encoding="utf-8"?>'
NEWLINE = "\r\n"
INDENT = "  "
_BAD_SELF_CLOSE = re.compile(r"[^ ]/>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class IssWriteError(Exception):
    pass


# -------------------------------------------------------------------- formatting
def fmt(value: float) -> str:
    """At most 4 decimals, trailing zeros stripped, never exponent notation, never -0."""
    v = round(float(value), 4)
    if v != v or v in (float("inf"), float("-inf")):
        raise IssWriteError(f"cannot write the number {value!r}")
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def escape(text: str) -> str:
    text = _CONTROL.sub("", str(text))
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


Attrs = list[tuple[str, str]]


class _Xml:
    def __init__(self) -> None:
        self.lines: list[str] = [XML_DECLARATION]
        self.depth = 0
        self.stack: list[str] = []

    def _attrs(self, attrs: Attrs | None) -> str:
        return "".join(f' {k}="{escape(v)}"' for k, v in (attrs or []))

    def open(self, tag: str, attrs: Attrs | None = None) -> None:
        self.lines.append(f"{INDENT * self.depth}<{tag}{self._attrs(attrs)}>")
        self.stack.append(tag)
        self.depth += 1

    def close(self) -> None:
        tag = self.stack.pop()
        self.depth -= 1
        self.lines.append(f"{INDENT * self.depth}</{tag}>")

    def empty(self, tag: str, attrs: Attrs | None = None) -> None:
        self.lines.append(f"{INDENT * self.depth}<{tag}{self._attrs(attrs)} />")

    def text(self, tag: str, value: str, attrs: Attrs | None = None) -> None:
        if value == "":
            self.empty(tag, attrs)
        else:
            self.lines.append(f"{INDENT * self.depth}<{tag}{self._attrs(attrs)}>{escape(value)}</{tag}>")

    def result(self) -> str:
        if self.stack:
            raise IssWriteError(f"unclosed elements: {self.stack}")
        return NEWLINE.join(self.lines) + NEWLINE


# -------------------------------------------------------------------- document
def last_edit(now: datetime | None = None) -> str:
    """Local time with its UTC offset, e.g. 2026-10-14T09:15:00-05:00."""
    return (now or datetime.now().astimezone()).isoformat(timespec="seconds")


def render(layout: IssLayout, settings: IssSettings, now: datetime | None = None) -> str:
    """The ISS text for ``layout`` (no checks; see :func:`write_iss`)."""
    prog = layout.program
    x = _Xml()
    n_place, n_comp = len(prog.placements), len(prog.components)
    done = settings.header_completion == "total"

    x.open("productionProgram")
    x.open("headerData")
    x.text("targetMachine", "ISS")
    x.text("editMachine", "ISS")
    x.text("lastEdit", last_edit(now))
    x.open("lineConfiguration")
    x.text("lineName", settings.line_name, [("id", str(settings.line_id))])
    x.close()
    x.empty("headPwb", [("total", "1"), ("completion", "1")])
    x.empty("headPlacement", [("total", str(n_place)), ("completion", str(n_place if done else 0))])
    x.empty("headComponent", [("total", str(n_comp)), ("completion", str(n_comp if done else 0))])
    x.close()

    # ---------------------------------------------------------------- core
    x.open("core")
    x.open("pwbData")
    x.text("pwbId", prog.pwb_id)
    x.open("pwbBasic")
    for tag, value in (
        ("referenceSide", "FRONT"),  # the conveyor's fixed rail, not the board side
        ("transferDirection", "LTOR"),
        ("referenceType", "SHAPE"),
        ("circuitType", "STANDARD"),
        ("bocMarkSelect", "ALL"),
        ("markRecognition", "GRAYSCALE"),
        ("badMarkType", "STANDARD"),
        ("badMarkRecognition", "POSITIVE"),
    ):
        x.text(tag, value)
    x.close()
    x.open("pwbConfiguration")
    x.empty("outline", [("x", fmt(prog.width)), ("y", fmt(prog.height))])
    x.empty("pwbThick", [("thick", fmt(settings.pwb_thickness))])
    x.empty("backHeight", [("height", fmt(settings.back_height))])
    x.empty("pwbHeight", [("height", "0")])
    x.close()
    x.open("circuitConfigurationData")
    x.open("circuitConfiguration", [("index", "0")])
    x.text("circuitUse", "USE")
    x.text("circuitId", "A")
    matrix = prog.circuit_layout == "MATRIX"
    x.text("circuitConfiguration", "MATRIX" if matrix else "NONMATRIX")
    x.text("bocMarkType", "PWBBOC")
    x.empty("circuitOutline", [("x", fmt(prog.circuit_width)), ("y", fmt(prog.circuit_height))])
    x.empty("referencePosition")
    if matrix:
        if layout.matrix is None:
            raise IssWriteError("circuit_layout=matrix needs a uniform grid of circuits")
        nx, ny, px, py = layout.matrix
        x.open("matrix")
        x.empty("divideNumber", [("x", str(nx)), ("y", str(ny))])
        x.empty("matrixReferencePosition", [("x", "0"), ("y", "0")])
        x.empty("matrixPitch", [("x", fmt(px)), ("y", fmt(py))])
        x.close()
    else:
        x.open("nonMatrix")
        x.empty("totalCount", [("count", str(len(prog.circuits)))])
        for i, c in enumerate(prog.circuits):
            x.empty(
                "allocation",
                [("index", str(i)), ("x", fmt(c.x)), ("y", fmt(c.y)), ("angle", fmt(c.angle)), ("rangeOver", "0")],
            )
        x.close()
    x.close()
    x.open("circuitConfiguration", [("index", "1")])
    x.text("circuitUse", "NOUSE")
    x.text("circuitId", "B")
    x.text("circuitConfiguration", "SINGLE")
    x.text("bocMarkType", "NOUSE")
    x.empty("circuitOutline")
    x.empty("referencePosition")
    x.close()
    x.close()  # circuitConfigurationData
    x.close()  # pwbData

    x.open("placementData")
    for i, p in enumerate(prog.placements):
        x.open("placement", [("index", str(i))])
        x.text("placementId", p.designator)
        x.text("baseCircuitId", "A")
        x.text("componentName", p.component)
        x.empty("placementPosition", [("x", fmt(p.x)), ("y", fmt(p.y)), ("rangeOver", "False")])
        x.empty("placementAngle", [("angle", fmt(p.angle))])
        x.open("attribute")
        x.empty("skip", [("placement", "NO"), ("adhesive", "NO")])
        x.close()
        x.close()
    x.close()

    x.open("componentData")
    for i, c in enumerate(prog.components):
        x.open("component", [("index", str(i))])
        x.open("componentBasic")
        x.text("componentName", c.name)
        x.text("comment", c.comment)
        x.empty("componentSize", [("witdh", fmt(c.width)), ("length", fmt(c.length)), ("height", fmt(c.height))])
        x.empty("connecterHeight", [("height", "0")])
        x.close()
        x.close()
    x.close()
    x.close()  # core

    # ---------------------------------------------------------------- model
    x.open("model")
    x.open("pwbData")
    x.text("pwbId", prog.pwb_id)
    x.open("pwbBasic")
    x.text("pwbMaterial", "EPOXY")
    x.text("vacuumTable", "NOUSE")
    x.text("traceability", settings.traceability)
    x.close()
    x.open("pwbConfiguration")
    x.empty("pwbLayoutOffset", [("x", fmt(prog.pwb_layout_offset[0])), ("y", fmt(prog.pwb_layout_offset[1]))])
    x.empty("referencePosition", [("x", "0"), ("y", "0")])
    x.empty("clampOffset", [("y", fmt(prog.clamp_offset or 0.0))])
    x.close()
    x.open("circuitConfigurationData")
    x.open("circuitConfiguration", [("index", "0")])
    x.text("circuitId", "A")
    x.empty("circuitLayoutOffset", [("x", fmt(prog.circuit_layout_offset[0])), ("y", fmt(prog.circuit_layout_offset[1]))])
    x.close()
    x.open("circuitConfiguration", [("index", "1")])
    x.text("circuitId", "B")
    x.empty("circuitLayoutOffset", [("x", "0"), ("y", "0")])
    x.close()
    x.close()
    x.close()  # pwbData
    x.open("placementData")
    for i, p in enumerate(prog.placements):
        x.open("placement", [("index", str(i))])
        x.text("placementId", p.designator)
        x.open("attribute")
        x.empty("action", [("placement", "Place"), ("adhesive", "NoAdhesive")])
        x.close()
        x.close()
    x.close()
    if settings.model_component_stubs:
        # Test switch only: JaNets hung on stub records while its database lock was held.
        x.open("componentData")
        for i, c in enumerate(prog.components):
            x.open("component", [("index", str(i))])
            x.open("componentBasic")
            x.text("componentName", c.name)
            x.text("componentType", "NOASSIGN")
            x.close()
            x.close()
        x.close()
    x.close()  # model

    # ---------------------------------------------------------------- machine
    x.open("machine")
    x.open("bocMarkData")
    x.open("circuitData", [("index", "0")])
    _boc_mark(x, "bocMark", "BOC", settings.mark_name, prog.fiducials)
    _boc_mark(x, "secondBocMark", "NoUse", settings.mark_name, [])
    x.close()
    x.close()
    x.close()

    x.close()  # productionProgram
    return x.result()


def _boc_mark(x: _Xml, tag: str, kind: str, name: str, marks) -> None:
    x.open(tag, [("no", "1")])
    x.text("markType", kind)
    x.text("markName", name)
    x.text("solderType", "standard")
    x.empty("effectiveCount", [("count", str(len(marks)))])
    x.open("fiducialMarkData")
    for i in range(3):
        x.open("fiducialMark", [("index", str(i))])
        if i < len(marks):
            x.text("markName", marks[i].name)
            x.empty("markPosition", [("x", fmt(marks[i].x)), ("y", fmt(marks[i].y))])
        else:
            x.empty("markName")
            x.empty("markPosition")
        x.close()
    x.close()
    x.close()


def encode(text: str) -> bytes:
    return text.encode("utf-8-sig")


# -------------------------------------------------------------------- self-test and write
def self_test(data: bytes, program: Program) -> None:
    """The written bytes must not match ``[^ ]/>``, must parse and must read back to ``program``."""
    from panelimport.iss.reader import ReadError, differences, read_iss_bytes

    text = data.decode("utf-8-sig")
    bad = _BAD_SELF_CLOSE.search(text)
    if bad:
        line = text.count("\n", 0, bad.start()) + 1
        raise IssWriteError(f"self-test: self-closing tag without a space on line {line}")
    try:
        ET.fromstring(data)
    except ET.ParseError as exc:
        raise IssWriteError(f"self-test: the output does not parse: {exc}") from None
    try:
        back = read_iss_bytes(data)
    except ReadError as exc:
        raise IssWriteError(f"self-test: the output cannot be read back: {exc}") from None
    diffs = differences(program, back)
    if diffs:
        raise IssWriteError("self-test: the output reads back differently: " + "; ".join(diffs[:5]))


def write_iss(prepared: Prepared, path: str | os.PathLike, now: datetime | None = None) -> Path:
    """Write the program; refuses when the checks found errors.  Nothing is written unless
    the self-test passes."""
    if prepared.layout is None or prepared.errors:
        n = len(prepared.errors)
        raise IssWriteError(f"not written: {n} error{'s' if n != 1 else ''} (see the report)")
    data = encode(render(prepared.layout, prepared.settings, now))
    self_test(data, prepared.layout.program)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def default_iss_path(project_path: str | os.PathLike) -> Path:
    """``<name>.iss`` next to ``<name>.panel.json``."""
    from panelimport.model.project_file import PROJECT_SUFFIX

    p = Path(project_path)
    stem = p.name.removesuffix(PROJECT_SUFFIX) if p.name.endswith(PROJECT_SUFFIX) else p.stem
    return p.with_name(stem + ISS_SUFFIX)


def project_stem(project_path: str | os.PathLike) -> str:
    return default_iss_path(project_path).stem
