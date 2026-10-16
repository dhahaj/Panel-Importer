"""ISS serialization: the known-good shape (T3), the hard rules, and the self-test."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from panelimport.iss import writer
from panelimport.iss.checks import prepare
from panelimport.iss.reader import read_program
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import IssWriteError, encode, escape, fmt, render, write_iss
from tests.synthetic.projects import make_project

FIXTURES = Path(__file__).parent / "fixtures" / "iss"
NOW = datetime(2026, 10, 14, 9, 15, 0, tzinfo=timezone(timedelta(hours=-5)))


def _need(name: str) -> Path:
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"reference program {name} not in tests/fixtures/iss yet")
    return path


def _text(project=None, settings: IssSettings | None = None) -> str:
    settings = settings or IssSettings()
    prepared = prepare(project or make_project(), settings, pwb_id="Panel")
    return render(prepared.layout, settings, NOW)


def structure(e: ET.Element) -> tuple:
    """Tag and element order, with runs of identically shaped siblings collapsed
    (repeat counts and values ignored)."""
    children: list[tuple] = []
    for c in e:
        s = structure(c)
        if not children or children[-1] != s:
            children.append(s)
    return (e.tag, tuple(children))


# -------------------------------------------------------------------- shape
def test_skeleton_matches_t3():
    t3 = ET.parse(_need("T3_strip_both.iss")).getroot()
    ours = ET.fromstring(encode(_text()))
    assert structure(ours) == structure(t3)


def test_skeleton_header_and_fixed_values():
    root = ET.fromstring(encode(_text()))
    assert root.findtext("headerData/targetMachine") == "ISS"
    assert root.findtext("headerData/editMachine") == "ISS"
    assert root.findtext("headerData/lastEdit") == "2026-10-14T09:15:00-05:00"
    name = root.find("headerData/lineConfiguration/lineName")
    assert (name.text, name.get("id")) == ("Line", "1")
    assert root.find("headerData/headPwb").attrib == {"total": "1", "completion": "1"}
    assert root.find("headerData/headPlacement").attrib == {"total": "4", "completion": "0"}
    assert root.find("headerData/headComponent").attrib == {"total": "3", "completion": "0"}
    basic = root.find("core/pwbData/pwbBasic")
    assert [(c.tag, c.text) for c in basic] == [
        ("referenceSide", "FRONT"),
        ("transferDirection", "LTOR"),
        ("referenceType", "SHAPE"),
        ("circuitType", "STANDARD"),
        ("bocMarkSelect", "ALL"),
        ("markRecognition", "GRAYSCALE"),
        ("badMarkType", "STANDARD"),
        ("badMarkRecognition", "POSITIVE"),
    ]
    a = root.find("core/pwbData/circuitConfigurationData/circuitConfiguration[@index='0']")
    assert [a.findtext(t) for t in ("circuitUse", "circuitId", "circuitConfiguration", "bocMarkType")] == [
        "USE", "A", "NONMATRIX", "PWBBOC"
    ]
    assert a.find("nonMatrix/totalCount").get("count") == "2"
    assert a.find("nonMatrix/allocation").attrib == {"index": "0", "x": "0", "y": "0", "angle": "0", "rangeOver": "0"}
    b = root.find("core/pwbData/circuitConfigurationData/circuitConfiguration[@index='1']")
    assert [b.findtext(t) for t in ("circuitUse", "circuitId", "circuitConfiguration", "bocMarkType")] == [
        "NOUSE", "B", "SINGLE", "NOUSE"
    ]
    p = root.find("core/placementData/placement")
    assert p.find("placementPosition").get("rangeOver") == "False"
    assert p.find("attribute/skip").attrib == {"placement": "NO", "adhesive": "NO"}
    assert root.find("model/placementData/placement/attribute/action").attrib == {"placement": "Place", "adhesive": "NoAdhesive"}
    assert root.find("model/componentData") is None  # left out: JaNets takes component data from its database
    assert [root.findtext(f"model/pwbData/pwbBasic/{t}") for t in ("pwbMaterial", "vacuumTable", "traceability")] == [
        "EPOXY", "NOUSE", "TwoDimensions"
    ]
    mark = root.find("machine/bocMarkData/circuitData/bocMark")
    assert [mark.findtext(t) for t in ("markType", "markName", "solderType")] == ["BOC", "BOCMARK01", "standard"]
    assert mark.find("effectiveCount").get("count") == "3"
    second = root.find("machine/bocMarkData/circuitData/secondBocMark")
    assert second.findtext("markType") == "NoUse" and second.find("effectiveCount").get("count") == "0"
    assert len(second.findall("fiducialMarkData/fiducialMark")) == 3


def test_attribute_order_is_the_skeletons():
    text = _text()
    assert '<placementPosition x="' in text and '" rangeOver="False" />' in text
    assert re.search(r'<allocation index="1" x="[^"]+" y="[^"]+" angle="[^"]+" rangeOver="0" />', text)
    assert re.search(r'<componentSize witdh="1.6" length="0.8" height="0.55" />', text)
    assert '<headPlacement total="4" completion="0" />' in text


def test_settings_reach_the_file():
    s = IssSettings(
        header_completion="total",
        traceability="NOUSE",
        line_name="SMT 1",
        line_id=3,
        mark_name="MARKS",
        pwb_thickness=0.8,
        back_height=40,
        clamp_offset_y=91.313,
        pwb_id="ER-F8",
    )
    root = ET.fromstring(encode(_text(settings=s)))
    assert root.find("headerData/headPlacement").attrib == {"total": "4", "completion": "4"}
    assert root.findtext("model/pwbData/pwbBasic/traceability") == "NOUSE"
    assert (root.findtext("headerData/lineConfiguration/lineName"), root.find("headerData/lineConfiguration/lineName").get("id")) == ("SMT 1", "3")
    assert root.findtext("machine/bocMarkData/circuitData/bocMark/markName") == "MARKS"
    assert root.find("core/pwbData/pwbConfiguration/pwbThick").get("thick") == "0.8"
    assert root.find("core/pwbData/pwbConfiguration/backHeight").get("height") == "40"
    assert root.find("model/pwbData/pwbConfiguration/clampOffset").get("y") == "91.313"
    assert root.findtext("core/pwbData/pwbId") == root.findtext("model/pwbData/pwbId") == "ER-F8"


def test_model_component_stubs_switch():
    root = ET.fromstring(encode(_text(settings=IssSettings(model_component_stubs=True))))
    stubs = root.findall("model/componentData/component/componentBasic/componentName")
    assert [s.text for s in stubs] == [c.findtext("componentBasic/componentName") for c in root.findall("core/componentData/component")]
    assert [c.tag for c in root.find("model")] == ["pwbData", "placementData", "componentData"]


def test_matrix_switch():
    project = make_project(width=100, height=120, circuits=[(0, 0, 0), (45.0, 0, 0), (0, 55.0, 0), (45.0, 55.0, 0)])
    root = ET.fromstring(encode(_text(project, IssSettings(circuit_layout="matrix", panel_rotation=0))))
    a = root.find("core/pwbData/circuitConfigurationData/circuitConfiguration[@index='0']")
    assert a.findtext("circuitConfiguration") == "MATRIX" and a.findtext("bocMarkType") == "PWBBOC"
    assert a.find("matrix/divideNumber").attrib == {"x": "2", "y": "2"}
    assert a.find("matrix/matrixReferencePosition").attrib == {"x": "0", "y": "0"}
    assert a.find("matrix/matrixPitch").attrib == {"x": "45", "y": "55"}
    assert a.find("nonMatrix") is None


# -------------------------------------------------------------------- serialization rules
def test_bom_crlf_declaration_indent():
    data = encode(_text())
    assert data.startswith(b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?>\r\n<productionProgram>\r\n  <headerData>\r\n')
    assert data.endswith(b"</productionProgram>\r\n")
    assert b"\n" not in data.replace(b"\r\n", b"")  # every line ends in CRLF
    for line in data.decode("utf-8-sig").split("\r\n")[1:-1]:
        indent = len(line) - len(line.lstrip(" "))
        assert indent % 2 == 0 and not line.startswith("\t")


def test_self_closing_tags_have_a_space():
    text = _text(settings=IssSettings(model_component_stubs=True))
    assert "/>" in text
    assert not re.search(r"[^ ]/>", text)


@pytest.mark.parametrize(
    "value, text",
    [
        (0.0, "0"),
        (-0.0, "0"),
        (-0.00004, "0"),
        (1e-7, "0"),
        (2.0, "2"),
        (37, "37"),
        (91.3130000477539, "91.313"),
        (1 / 3, "0.3333"),
        (-12.70305, "-12.703"),
        (256.03202539, "256.032"),
        (41.78300001, "41.783"),
        (1e20, "100000000000000000000"),
        (-5.5812, "-5.5812"),
        (123.45675, "123.4567"),
    ],
)
def test_number_format(value, text):
    assert fmt(value) == text
    assert "e" not in fmt(value).lower()


def test_number_format_rejects_nan():
    with pytest.raises(IssWriteError):
        fmt(float("nan"))


def test_witdh_and_connecterheight_are_kept():
    text = _text()
    assert 'witdh="' in text and "<connecterHeight " in text
    assert 'width="' not in text and "connectorHeight" not in text


def test_escaping():
    assert escape('R&D <5A> "x" \'y\'') == "R&amp;D &lt;5A&gt; &quot;x&quot; &apos;y&apos;"
    assert escape("bad\x01char") == "badchar"
    project = make_project(parts=[("R1", 1, 1, 0, "A&B<1>")])
    project.placements[0].attributes = {"DSC": 'RES 1K & "10%" <0603>'}
    data = encode(_text(project))
    root = ET.fromstring(data)  # parses
    assert root.findtext("core/componentData/component/componentBasic/comment") == 'RES 1K & "10%" <0603>'
    assert root.findtext("core/placementData/placement/componentName") == "A&B<1>"
    assert b"A&amp;B&lt;1&gt;" in data


def test_comment_with_unicode():
    project = make_project(parts=[("R1", 1, 1, 0, "P-1")])
    project.placements[0].attributes = {"DSC": "RES 0.11 Ω ±1%"}
    root = ET.fromstring(encode(_text(project)))
    assert root.findtext("core/componentData/component/componentBasic/comment") == "RES 0.11 Ω ±1%"


# -------------------------------------------------------------------- write and self-test
def test_write_and_read_back(tmp_path):
    prepared = prepare(make_project(), IssSettings(), pwb_id="Panel")
    out = write_iss(prepared, tmp_path / "Panel.iss", NOW)
    back = read_program(out)
    assert back.kind == "iss" and back.pwb_id == "Panel"
    assert [(p.designator, p.x, p.y, p.angle) for p in back.placements] == [
        (p.designator, p.x, p.y, p.angle) for p in prepared.layout.program.placements
    ]
    assert not (tmp_path / "Panel.iss.tmp").exists()


def test_write_refuses_errors(tmp_path):
    project = make_project(fiducials=[(2.0, 2.0, "top")])  # one fiducial: no_fiducials
    prepared = prepare(project, IssSettings(), pwb_id="Panel")
    assert not prepared.can_write
    with pytest.raises(IssWriteError, match="1 error"):
        write_iss(prepared, tmp_path / "Panel.iss")
    assert not (tmp_path / "Panel.iss").exists()


def test_self_test_catches_a_bad_file(tmp_path, monkeypatch):
    prepared = prepare(make_project(), IssSettings(), pwb_id="Panel")
    target = tmp_path / "Panel.iss"
    target.write_bytes(b"old")
    real = writer.render
    monkeypatch.setattr(writer, "render", lambda *a, **k: real(*a, **k).replace(" />", "/>", 1))
    with pytest.raises(IssWriteError, match="without a space"):
        write_iss(prepared, target)
    monkeypatch.setattr(writer, "render", lambda *a, **k: real(*a, **k).replace('angle="30"', 'angle="31"', 1))
    with pytest.raises(IssWriteError, match="reads back differently"):
        write_iss(prepared, target)
    monkeypatch.setattr(writer, "render", lambda *a, **k: real(*a, **k).replace("</core>", "", 1))
    with pytest.raises(IssWriteError, match="does not parse"):
        write_iss(prepared, target)
    assert target.read_bytes() == b"old"  # nothing replaced


def test_default_paths():
    assert writer.default_iss_path("/x/ER Rev F8.panel.json") == Path("/x/ER Rev F8.iss")
    assert writer.project_stem("/x/ER Rev F8.panel.json") == "ER Rev F8"
    assert writer.default_iss_path("/x/other.json") == Path("/x/other.iss")


def test_partial_schema_validation():
    """The schema reconstructed from AegisMachines.dll is partial (every attribute is
    marked required, value restrictions were lost), so it only says something by
    comparison: the output may not draw a complaint that T3, which opens in JaNets,
    does not draw too."""
    lxml = pytest.importorskip("lxml.etree")
    schema = lxml.XMLSchema(lxml.parse(str(_need("iss_schema_0.xsd"))))

    def complaints(doc) -> set[str]:
        schema.validate(doc)
        return {e.message for e in schema.error_log}

    known = complaints(lxml.parse(str(_need("T3_strip_both.iss"))).getroot())
    assert complaints(lxml.fromstring(encode(_text()))) <= known
    # The stub switch adds incomplete model components (test switch only).
    stubs = complaints(lxml.fromstring(encode(_text(settings=IssSettings(model_component_stubs=True))))) - known
    assert stubs and all(m.startswith("Element 'component': Missing child element(s).") for m in stubs)
