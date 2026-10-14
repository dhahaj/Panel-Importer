"""Read ISS programs and JaNets ``.x21`` saves into one model (:class:`Program`).

Only what is listed below is read; everything else is ignored, and structure that is
not understood is reported in :attr:`Program.notes` instead of failing.

ISS (``productionProgram``)::

    core/pwbData/pwbId, pwbConfiguration/outline[x y]
    core/pwbData/circuitConfigurationData/circuitConfiguration (circuit A):
        circuitConfiguration, circuitOutline[x y],
        nonMatrix/allocation[index x y angle] or matrix/divideNumber, matrixPitch
    core/placementData/placement: placementId, baseCircuitId, componentName,
        placementPosition[x y], placementAngle[angle], attribute/skip[placement]
    core/componentData/component/componentBasic: componentName, comment, componentSize
    model/pwbData/pwbConfiguration: pwbLayoutOffset[x y], clampOffset[y]
    model/pwbData/circuitConfigurationData/circuitConfiguration (A): circuitLayoutOffset
    machine/bocMarkData/circuitData/bocMark/fiducialMarkData/fiducialMark: markName, markPosition
    headerData/headPlacement, headComponent [total completion]

``.x21`` (``Program``)::

    Core/Pwb/ConfigPwb/OutLine[x y], ClampOffsetY[y]
    Core/Pwb/ConfigCircuit/ConfigCircuit[num]: CircuitType, BocMarkType, CircuitOutLine[x y],
        NonMatrix/Allocation/Allocation[num]/RefPos[x y] + CircuitAngle[a]
    Core/Place/Place[num]: PlaceId, PlacePos[x y], PlaceAngle[angle], CompoName
    Core/Compo/Compo/CompoBasic: CompoName, Comment
    Model/Pwb/LayoutPos[x y] (= pwbLayoutOffset), CircuitLayoutPos/CircuitLayoutPos[num x y], ClampOffset[y]
    Machine/MarkData/MarkData[num]/FiducialMark/FiducialMark[num]: MarkPos[x y], MarkName
    Core/HeaderData/HdPlace, HdCompo, HdMark [total comp]
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from panelimport.iss.mapping import (
    Program,
    ProgramCircuit,
    ProgramComponent,
    ProgramFiducial,
    ProgramPlacement,
    matrix_circuits,
)

PROGRAM_SUFFIXES = (".iss", ".x21")


class ReadError(Exception):
    pass


# -------------------------------------------------------------------- helpers
def _num(e: ET.Element | None, attr: str, notes: list[str] | None = None, where: str = "") -> float | None:
    if e is None:
        return None
    text = e.get(attr)
    if text is None or text.strip() == "":
        return None
    try:
        return float(text)
    except ValueError:
        if notes is not None:
            notes.append(f"{where or e.tag}: {attr}={text!r} is not a number")
        return None


def _xy(e: ET.Element | None, notes: list[str], where: str) -> tuple[float, float] | None:
    if e is None:
        return None
    x, y = _num(e, "x", notes, where), _num(e, "y", notes, where)
    if x is None or y is None:
        return None
    return x, y


def _text(e: ET.Element | None, path: str) -> str:
    if e is None:
        return ""
    return (e.findtext(path) or "").strip()


def _int(text: str | None, default: int = 0) -> int:
    try:
        return int(text) if text is not None else default
    except ValueError:
        return default


def _counts(e: ET.Element | None, total: str, done: str) -> tuple[int, int] | None:
    if e is None:
        return None
    return _int(e.get(total)), _int(e.get(done))


# -------------------------------------------------------------------- entry points
def read_program(path: str | os.PathLike) -> Program:
    """Read an ISS or ``.x21`` file (told apart by the root element)."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReadError(f"{path}: {exc.strerror or exc}") from None
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ReadError(f"{path}: not XML ({exc})") from None
    prog = _read_root(root)
    prog.path = str(path)
    return prog


def read_iss_bytes(data: bytes) -> Program:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ReadError(f"not XML ({exc})") from None
    if root.tag != "productionProgram":
        raise ReadError(f"not an ISS program (root element <{root.tag}>)")
    return read_iss(root)


def _read_root(root: ET.Element) -> Program:
    if root.tag == "productionProgram":
        return read_iss(root)
    if root.tag == "Program":
        return read_x21(root)
    raise ReadError(f"not an ISS or .x21 program (root element <{root.tag}>)")


# -------------------------------------------------------------------- ISS
def read_iss(root: ET.Element) -> Program:
    notes: list[str] = []
    prog = Program(kind="iss", notes=notes)
    core_pwb = root.find("core/pwbData")
    if core_pwb is None:
        notes.append("no core/pwbData")
    prog.pwb_id = _text(core_pwb, "pwbId")
    outline = _xy(root.find("core/pwbData/pwbConfiguration/outline"), notes, "outline")
    if outline is None:
        notes.append("no panel outline (core/pwbData/pwbConfiguration/outline)")
    else:
        prog.width, prog.height = outline

    configs = root.findall("core/pwbData/circuitConfigurationData/circuitConfiguration")
    a = next((c for c in configs if _text(c, "circuitId") == "A"), configs[0] if configs else None)
    if a is None:
        notes.append("no circuit configuration")
        prog.circuits = [ProgramCircuit(1)]
    else:
        prog.circuit_layout = _text(a, "circuitConfiguration") or "?"
        size = _xy(a.find("circuitOutline"), notes, "circuitOutline")
        if size is not None:
            prog.circuit_width, prog.circuit_height = size
        prog.circuits = _iss_circuits(a, prog.circuit_layout, notes)
        for other in configs:
            if other is not a and _text(other, "circuitUse") not in ("NOUSE", ""):
                notes.append(f"circuit {_text(other, 'circuitId') or '?'} is in use ({_text(other, 'circuitUse')}); not read")

    for e in root.findall("core/placementData/placement"):
        pos = _xy(e.find("placementPosition"), notes, f"placement {_text(e, 'placementId')}")
        angle = _num(e.find("placementAngle"), "angle", notes, "placementAngle")
        if pos is None:
            notes.append(f"placement {_text(e, 'placementId') or e.get('index')}: no position; skipped")
            continue
        skip = e.find("attribute/skip")
        prog.placements.append(
            ProgramPlacement(
                designator=_text(e, "placementId"),
                component=_text(e, "componentName"),
                x=pos[0],
                y=pos[1],
                angle=angle or 0.0,
                circuit_id=_text(e, "baseCircuitId") or "A",
                skip=skip is not None and (skip.get("placement") or "").upper() == "YES",
            )
        )
    for e in root.findall("core/componentData/component/componentBasic"):
        size = e.find("componentSize")
        prog.components.append(
            ProgramComponent(
                name=_text(e, "componentName"),
                comment=_text(e, "comment"),
                width=_num(size, "witdh") or 0.0,
                length=_num(size, "length") or 0.0,
                height=_num(size, "height") or 0.0,
            )
        )

    model = root.find("model/pwbData/pwbConfiguration")
    plo = _xy(model.find("pwbLayoutOffset") if model is not None else None, notes, "pwbLayoutOffset")
    if plo is None:
        notes.append("no pwbLayoutOffset; P assumed at the panel's lower-right corner")
    else:
        prog.pwb_layout_offset = plo
    prog.clamp_offset = _num(model.find("clampOffset") if model is not None else None, "y")
    mconfigs = root.findall("model/pwbData/circuitConfigurationData/circuitConfiguration")
    ma = next((c for c in mconfigs if _text(c, "circuitId") == "A"), mconfigs[0] if mconfigs else None)
    clo = _xy(ma.find("circuitLayoutOffset") if ma is not None else None, notes, "circuitLayoutOffset")
    if clo is None:
        notes.append("no circuitLayoutOffset for circuit A")
    else:
        prog.circuit_layout_offset = clo

    boc = root.find("machine/bocMarkData/circuitData/bocMark")
    for i, fm in enumerate(boc.findall("fiducialMarkData/fiducialMark") if boc is not None else []):
        pos = _xy(fm.find("markPosition"), notes, "markPosition")
        if pos is not None:
            prog.fiducials.append(ProgramFiducial(_text(fm, "markName") or f"#{i + 1}", pos[0], pos[1]))
    second = root.find("machine/bocMarkData/circuitData/secondBocMark")
    if second is not None and _text(second, "markType").upper() not in ("NOUSE", ""):
        used = [fm for fm in second.findall("fiducialMarkData/fiducialMark") if _xy(fm.find("markPosition"), [], "") is not None]
        notes.append(f"secondBocMark is in use ({_text(second, 'markType')}, {len(used)} marks); not compared")

    header = root.find("headerData")
    for key, tag in (("placement", "headPlacement"), ("component", "headComponent"), ("pwb", "headPwb")):
        c = _counts(header.find(tag) if header is not None else None, "total", "completion")
        if c is not None:
            prog.counts[key] = c
    return prog


def _iss_circuits(a: ET.Element, layout: str, notes: list[str]) -> list[ProgramCircuit]:
    if layout == "NONMATRIX":
        out = []
        for e in a.findall("nonMatrix/allocation"):
            xy = _xy(e, notes, "allocation")
            if xy is None:
                notes.append(f"allocation {e.get('index')}: no position; skipped")
                continue
            out.append(ProgramCircuit(len(out) + 1, xy[0], xy[1], _num(e, "angle") or 0.0))
        total = _int(a.find("nonMatrix/totalCount").get("count") if a.find("nonMatrix/totalCount") is not None else None, -1)
        if total >= 0 and total != len(out):
            notes.append(f"nonMatrix totalCount {total} but {len(out)} allocations")
        return out or [ProgramCircuit(1)]
    if layout == "MATRIX":
        div, pitch = a.find("matrix/divideNumber"), a.find("matrix/matrixPitch")
        ref = _xy(a.find("matrix/matrixReferencePosition"), notes, "matrixReferencePosition") or (0.0, 0.0)
        if div is None or pitch is None:
            notes.append("MATRIX without divideNumber/matrixPitch; read as one circuit")
            return [ProgramCircuit(1)]
        if ref != (0.0, 0.0):
            notes.append(f"matrixReferencePosition {ref} is not 0,0; not applied")
        nx, ny = _int(div.get("x"), 1), _int(div.get("y"), 1)
        return matrix_circuits(max(nx, 1), max(ny, 1), _num(pitch, "x") or 0.0, _num(pitch, "y") or 0.0)
    if layout != "SINGLE":
        notes.append(f"circuit layout {layout!r} is not understood; read as one circuit")
    return [ProgramCircuit(1)]


# -------------------------------------------------------------------- x21
def read_x21(root: ET.Element) -> Program:
    notes: list[str] = []
    prog = Program(kind="x21", notes=notes)
    pwb = root.find("Core/Pwb")
    if pwb is None:
        notes.append("no Core/Pwb")
    prog.pwb_id = _text(pwb, "PwbId") or (root.find("Info").get("pwbid", "") if root.find("Info") is not None else "")
    outline = _xy(root.find("Core/Pwb/ConfigPwb/OutLine"), notes, "OutLine")
    if outline is None:
        notes.append("no panel outline (Core/Pwb/ConfigPwb/OutLine)")
    else:
        prog.width, prog.height = outline
    core_clamp = _num(root.find("Core/Pwb/ConfigPwb/ClampOffsetY"), "y")

    configs = root.findall("Core/Pwb/ConfigCircuit/ConfigCircuit")
    a = next((c for c in configs if _text(c, "CircuitId") == "A"), configs[0] if configs else None)
    if a is None:
        notes.append("no ConfigCircuit")
        prog.circuits = [ProgramCircuit(1)]
    else:
        prog.circuit_layout = _text(a, "CircuitType") or "?"
        size = _xy(a.find("CircuitOutLine"), notes, "CircuitOutLine")
        if size is not None:
            prog.circuit_width, prog.circuit_height = size
        if prog.circuit_layout == "NONMATRIX":
            for e in a.findall("NonMatrix/Allocation/Allocation"):
                xy = _xy(e.find("RefPos"), notes, "RefPos")
                if xy is None:
                    notes.append(f"Allocation {e.get('num')}: no RefPos; skipped")
                    continue
                angle = _num(e.find("CircuitAngle"), "a") or 0.0
                prog.circuits.append(ProgramCircuit(len(prog.circuits) + 1, xy[0], xy[1], angle))
        else:
            if prog.circuit_layout != "SINGLE":
                notes.append(f"circuit type {prog.circuit_layout!r} is not read from .x21; read as one circuit")
        prog.circuits = prog.circuits or [ProgramCircuit(1)]
        for other in configs:
            if other is not a and _text(other, "CircuitType") not in ("SINGLE", "") :
                notes.append(f"circuit {_text(other, 'CircuitId') or '?'} has type {_text(other, 'CircuitType')}; not read")

    for e in root.findall("Core/Place/Place"):
        pos = _xy(e.find("PlacePos"), notes, f"Place {_text(e, 'PlaceId')}")
        if pos is None:
            notes.append(f"Place {_text(e, 'PlaceId') or e.get('num')}: no PlacePos; skipped")
            continue
        skip = _text(e, "Attr/PlaceSkip").upper()
        prog.placements.append(
            ProgramPlacement(
                designator=_text(e, "PlaceId"),
                component=_text(e, "CompoName"),
                x=pos[0],
                y=pos[1],
                angle=_num(e.find("PlaceAngle"), "angle") or 0.0,
                circuit_id=_text(e, "BaseCircuitId") or "A",
                skip=skip not in ("", "NOUSE", "NO", "FALSE"),
            )
        )
    for e in root.findall("Core/Compo/Compo/CompoBasic"):
        size = e.find("CompoSize")
        prog.components.append(
            ProgramComponent(
                name=_text(e, "CompoName"),
                comment=_text(e, "Comment"),
                width=_num(size, "w") or 0.0,
                length=_num(size, "l") or 0.0,
                height=_num(e.find("CompoHeight"), "h") or 0.0,
            )
        )

    model = root.find("Model/Pwb")
    plo = _xy(model.find("LayoutPos") if model is not None else None, notes, "LayoutPos")
    if plo is None:
        notes.append("no Model/Pwb/LayoutPos; P assumed at the panel's lower-right corner")
    else:
        prog.pwb_layout_offset = plo
    layouts = model.findall("CircuitLayoutPos/CircuitLayoutPos") if model is not None else []
    first = next((e for e in layouts if e.get("num") == "0"), layouts[0] if layouts else None)
    clo = _xy(first, notes, "CircuitLayoutPos")
    if clo is None:
        notes.append("no CircuitLayoutPos for circuit A")
    else:
        prog.circuit_layout_offset = clo
    model_clamp = _num(model.find("ClampOffset") if model is not None else None, "y")
    prog.clamp_offset = model_clamp if model_clamp is not None else core_clamp
    if model_clamp is not None and core_clamp is not None and abs(model_clamp - core_clamp) > 1e-6:
        notes.append(f"clamp offset differs: Model {model_clamp:g}, Core {core_clamp:g}")

    marks = root.findall("Machine/MarkData/MarkData")
    boc = next((m for m in marks if _text(m, "MarkType").upper().startswith("BOC")), None)
    for fm in boc.findall("FiducialMark/FiducialMark") if boc is not None else []:
        pos = _xy(fm.find("MarkPos"), notes, "MarkPos")
        if pos is None:
            continue
        if fm.get("occ", "0") != "0":
            notes.append(f"fiducial mark with occ={fm.get('occ')}; not read")
            continue
        prog.fiducials.append(ProgramFiducial(_text(fm, "MarkName") or f"#{len(prog.fiducials) + 1}", pos[0], pos[1]))

    header = root.find("Core/HeaderData")
    for key, tag in (("placement", "HdPlace"), ("component", "HdCompo"), ("mark", "HdMark"), ("pwb", "HdPwb")):
        c = _counts(header.find(tag) if header is not None else None, "total", "comp")
        if c is not None:
            prog.counts[key] = c
    return prog


# -------------------------------------------------------------------- model comparison
def differences(a: Program, b: Program, tol: float = 1e-9) -> list[str]:
    """Where two programs differ field by field (used by the writer's self-test)."""
    out: list[str] = []

    def num(label, x, y):
        if (x is None) != (y is None) or (x is not None and abs(x - y) > tol):
            out.append(f"{label}: {x!r} ≠ {y!r}")

    for f in ("pwb_id", "circuit_layout"):
        if getattr(a, f) != getattr(b, f):
            out.append(f"{f}: {getattr(a, f)!r} ≠ {getattr(b, f)!r}")
    for f in ("width", "height", "circuit_width", "circuit_height", "clamp_offset"):
        num(f, getattr(a, f), getattr(b, f))
    for f in ("pwb_layout_offset", "circuit_layout_offset"):
        for i, axis in enumerate("xy"):
            num(f"{f}.{axis}", getattr(a, f)[i], getattr(b, f)[i])
    if len(a.circuits) != len(b.circuits):
        out.append(f"circuits: {len(a.circuits)} ≠ {len(b.circuits)}")
    else:
        for ca, cb in zip(a.circuits, b.circuits):
            for f in ("x", "y", "angle"):
                num(f"circuit {ca.number}.{f}", getattr(ca, f), getattr(cb, f))
    if len(a.placements) != len(b.placements):
        out.append(f"placements: {len(a.placements)} ≠ {len(b.placements)}")
    else:
        for pa, pb in zip(a.placements, b.placements):
            for f in ("designator", "component", "circuit_id", "skip"):
                if getattr(pa, f) != getattr(pb, f):
                    out.append(f"placement {pa.designator}.{f}: {getattr(pa, f)!r} ≠ {getattr(pb, f)!r}")
            for f in ("x", "y", "angle"):
                num(f"placement {pa.designator}.{f}", getattr(pa, f), getattr(pb, f))
    if [(c.name, c.comment) for c in a.components] != [(c.name, c.comment) for c in b.components]:
        out.append("components differ")
    else:
        for ca, cb in zip(a.components, b.components):
            for f in ("width", "length", "height"):
                num(f"component {ca.name}.{f}", getattr(ca, f), getattr(cb, f))
    if len(a.fiducials) != len(b.fiducials):
        out.append(f"fiducials: {len(a.fiducials)} ≠ {len(b.fiducials)}")
    else:
        for fa, fb in zip(a.fiducials, b.fiducials):
            if fa.name != fb.name:
                out.append(f"fiducial name: {fa.name!r} ≠ {fb.name!r}")
            num(f"fiducial {fa.name}.x", fa.x, fb.x)
            num(f"fiducial {fa.name}.y", fa.y, fb.y)
    return out
