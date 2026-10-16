import math

import pytest

from panelimport.io.odb.attributes import AttrDefs, resolve_attributes
from panelimport.io.odb.common import Units, split_record
from panelimport.io.odb.components import parse_components
from panelimport.io.odb.eda import parse_eda
from panelimport.io.odb.features import arc_points, parse_features
from panelimport.io.odb.matrix import parse_matrix
from panelimport.io.odb.stephdr import parse_stephdr
from panelimport.io.odb.structured import parse_structured
from panelimport.io.odb.symbols import parse_standard_symbol

INCH = 25.4


# ------------------------------------------------------------------ structured text
def test_structured_blocks_and_fields():
    doc = parse_structured(
        """UNITS=MM
# comment
STEP-REPEAT {
   NAME=PCB
   X = 5.0
}
OPTION
{
  NAME=.viacap_layer
  OPTIONS=top;bottom
}
"""
    )
    assert doc.fields["UNITS"] == "MM"
    assert [b.name for b in doc.blocks] == ["STEP-REPEAT", "OPTION"]
    assert doc.blocks[0].fields == {"NAME": "PCB", "X": "5.0"}
    assert not doc.problems


def test_structured_reports_unclosed_array():
    doc = parse_structured("STEP {\n NAME=A\n")
    assert doc.problems


# ------------------------------------------------------------------ matrix
MATRIX = """STEP {
   COL=2
   NAME=PANEL
}
STEP {
   COL=1
   ID=67890
   NAME=PCB
}
LAYER {
   ROW=1
   CONTEXT=BOARD
   TYPE=COMPONENT
   NAME=COMP_+_TOP
   POLARITY=POSITIVE
   OLD_NAME =
   ADD_TYPE=
   COLOR=606090
}
LAYER {
   ROW=2
   CONTEXT=BOARD
   TYPE=SOLDER_PASTE
   NAME=spt
   POLARITY=POSITIVE
   REF=123
   WEIRD_FIELD=1
}
"""


def test_matrix():
    m, issues = parse_matrix(MATRIX)
    assert [s.name for s in m.steps] == ["PCB", "PANEL"]
    assert m.step("panel").col == 2
    assert m.layer("SPT").type == "SOLDER_PASTE"
    assert m.layer("spt").ref == "123"
    assert [i.code for i in issues] == ["unknown_field"]
    assert "WEIRD_FIELD" in issues[0].message


# ------------------------------------------------------------------ stephdr
def test_stephdr_spec_example_inch():
    text = """X_DATUM=0
Y_DATUM=0
STEP-REPEAT {
   NAME=1UP
   X=1.5
   Y=1.6
   DX=1.2
   DY=1.2
   NX=6
   NY=6
   ANGLE=0
   FLIP=NO
   MIRROR=NO
}
TOP_ACTIVE=1
ONLINE_DRC_NAME=
AFFECTING_BOM=
"""
    hdr, issues = parse_stephdr(text, "steps/p/stephdr", Units.INCH)
    assert not issues
    assert not hdr.units.declared
    (rep,) = hdr.repeats
    assert rep.name == "1UP" and rep.nx == 6 and rep.ny == 6
    assert rep.x == pytest.approx(1.5 * INCH)
    assert rep.dy == pytest.approx(1.2 * INCH)


def test_stephdr_units_and_unknown_repeat_field():
    text = """UNITS=MM
X_DATUM=1
Y_DATUM=2
X_ORIGIN=3
Y_ORIGIN=4
STEP-REPEAT {
   NAME=PCB
   X=5
   Y=5
   DX=52
   DY=38.5
   NX=3
   NY=2
   ANGLE=90
   FLIP=NO
   MIRROR=YES
   SCALE=2
}
"""
    hdr, issues = parse_stephdr(text, "p", Units.INCH)
    assert hdr.units.units is Units.MM and hdr.units.declared
    assert hdr.datum == (1.0, 2.0) and hdr.origin == (3.0, 4.0)
    assert hdr.repeats[0].mirror and hdr.repeats[0].angle == 90
    (issue,) = issues
    assert issue.code == "unknown_field" and issue.severity.value == "error"


def test_stephdr_bad_units():
    _hdr, issues = parse_stephdr("UNITS=FURLONG\n", "p", Units.INCH)
    assert [i.code for i in issues] == ["unknown_units"]


# ------------------------------------------------------------------ symbols
@pytest.mark.parametrize(
    "name,kind,w,h",
    [
        ("r254", "round", 0.254, 0.254),
        ("s100", "square", 0.1, 0.1),
        ("rect600x900", "rect", 0.6, 0.9),
        ("rect600x900xr50", "rounded_rect", 0.6, 0.9),
        ("rect600x900xc50x1", "chamfered_rect", 0.6, 0.9),
        ("oval500x1000", "oval", 0.5, 1.0),
        ("oval_h500x1000", "half_oval", 0.5, 1.0),
        ("di300x400", "diamond", 0.3, 0.4),
        ("oct800x800x200", "octagon", 0.8, 0.8),
        ("donut_r1000x500", "donut_r", 1.0, 1.0),
        ("donut_sr1000x500", "donut_sr", 1.0, 1.0),
        ("donut_rc1000x600x100", "donut_rc", 1.0, 0.6),
        ("ths1000x800x45x4x100", "round_thermal", 1.0, 1.0),
        ("s_ths1000x800x45x4x100xr50", "square_thermal", 1.0, 1.0),
        ("rc_ths1000x600x45x4x100x50", "rect_thermal", 1.0, 0.6),
        ("el400x200", "ellipse", 0.4, 0.2),
        ("hole300xpx10x10", "hole", 0.3, 0.3),
        ("null1", "null", 0.0, 0.0),
        ("hplate1000x500x200", "stencil", 1.0, 0.5),
    ],
)
def test_standard_symbols_in_microns(name, kind, w, h):
    shape = parse_standard_symbol(name, Units.MM.symbol_scale)
    assert shape is not None and shape.kind == kind
    assert shape.width == pytest.approx(w) and shape.height == pytest.approx(h)


def test_symbol_in_mils_and_rotated():
    shape = parse_standard_symbol("rect20x10_30", Units.INCH.symbol_scale)
    assert shape.kind == "rect" and shape.rotation == 30
    assert shape.width == pytest.approx(20 * 0.0254)
    assert parse_standard_symbol("my_custom_pad", 0.001) is None


# ------------------------------------------------------------------ features
FEATURES_SPEC = """#
#Units
U MM
#
$0 r120
$1 rect20x60 M
$2 rect3x5 I
$3 const_1
@0 .smd
@1 .pad_usage
&0 fid_0_0_0
#
#Layer features
#
P 1.0 2.0 0 P 0 0;0
P 1.0 2.0 3 P 4 8 30.0
P 1.0 2.0 -1 1 0.02 P 4 1
P 1.0 2.0 2 P 4 9 45;1=2
L 0 0 1 1 0 P 0 ;0
A 1 0 -1 0 0 0 0 P 0 Y
T 4.033375 6.377506 standard P 0 0.2 0.2 2.00000 '$$DATE ; with semicolon' 1;0
S P 0
OB 0 0 I
OS 0 10
OC 10 0 5 5 Y
OS 0 0
OE
OB 2 2 H
OS 2 3
OS 3 3
OE
SE
"""


def test_features_spec_examples():
    user = []

    def resolver(name):
        user.append(name)
        return None

    ff, problems = parse_features(FEATURES_SPEC, "f", Units.INCH, resolver)
    assert ff.units.units is Units.MM and ff.units.declared
    assert ff.symbol(0).width == pytest.approx(0.12)  # standard symbol: file units (microns)
    assert ff.symbol(1).width == pytest.approx(0.02)  # explicit M: microns
    assert ff.symbol(2).width == pytest.approx(3 * 0.0254)  # explicit I: mils
    assert user == ["const_1"]
    issues = problems.to_issues()
    assert [i.code for i in issues] == ["unknown_symbol"]
    p0, p1, p2, p3 = ff.pads
    assert (p0.rotation, p0.mirror) == (0.0, False)
    assert (p1.rotation, p1.mirror) == (30.0, False)
    assert (p2.rotation, p2.mirror, p2.sym, p2.resize) == (90.0, False, 1, 0.02)
    assert (p3.rotation, p3.mirror, p3.attrs) == (45.0, True, "1=2")
    assert len(ff.lines) == 1 and len(ff.arcs) == 1
    assert ff.texts[0].text == "$$DATE ; with semicolon"
    (surface,) = ff.surfaces
    assert [c.island for c in surface.contours] == [True, False]
    assert len(surface.contours[0].points) > 4  # the arc was approximated


def test_features_default_units_and_unknown_record():
    ff, problems = parse_features("$0 r10\nP 1 1 0 P 0 0\nZ 1 2 3\n", "f", Units.INCH)
    assert ff.units.units is Units.INCH and not ff.units.declared
    assert ff.pads[0].x == pytest.approx(25.4)
    assert ff.symbol(0).width == pytest.approx(0.254)
    issues = problems.to_issues()
    assert [i.code for i in issues] == ["unknown_record"]
    assert issues[0].severity.value == "error"


def test_features_units_keyword_and_malformed_line():
    ff, problems = parse_features("UNITS=MM\n$0 r10\nP 1 1 0 P\nP x 1 0 P 0 0\n", "f", Units.INCH)
    assert ff.units.units is Units.MM
    assert [i.code for i in problems.to_issues()] == ["parse_error"]


def test_features_unrecognised_units():
    _ff, problems = parse_features("U FEET\n", "f", Units.INCH)
    assert [i.code for i in problems.to_issues()] == ["unknown_units"]


def test_arc_points_directions():
    ccw = arc_points(1, 0, 0, 1, 0, 0, cw=False)
    cw = arc_points(1, 0, 0, 1, 0, 0, cw=True)
    assert ccw[-1] == (0, 1) and cw[-1] == (0, 1)
    assert all(x >= -1e-9 and y >= -1e-9 for x, y in ccw)  # quarter circle through Q1
    assert any(y < -0.5 for _x, y in cw)  # three quarters through Q4
    full = arc_points(1, 0, 1, 0, 0, 0, cw=True)
    assert len(full) > 8 and full[-1] == (1, 0)
    assert all(math.isclose(math.hypot(x, y), 1.0) for x, y in full)


# ------------------------------------------------------------------ components
COMPONENTS_SPEC = """#
#Component attribute names
#
@0 .comp_ign_spacing
@1 .no_tp_under
@2 .comp_mount_type
@3 PART_NUMBER
&0 D-1234
# CMP 0
CMP 13 -0.04 1.22 270.0 N B70 2248827-0001
;1,2=1,3=0
PRP REFLOC 'IN,0.2,-0.225,270,CC,0.035,0.035,0.009,std,1'
PRP VALUE '22UF' 1 2
TOP 0 -0.198 1.62 270.0 N 223 0 B70-1
TOP 1 0.118 1.62 270.0 N 223 1 B70-2
#
# BOM DATA
CPN 070-000-016
PKG
IPN
DSC 16-ETSSOP FAN1654
VPL_VND MOTOROLA
VND MOTOROLA INC.
MPN 0 Y MC74HC259ADT
QLF 0
CHS 1
PRIORITY 1
# CMP 1
CMP 3 5.017 1.791 180.0 M C400 ??? ;ID=77
"""


def test_components_spec_example():
    cf, problems = parse_components(COMPONENTS_SPEC, "c", Units.INCH, AttrDefs())
    assert not problems.to_issues()
    b70, c400 = cf.components
    assert b70.name == "B70" and b70.part_name == "2248827-0001" and b70.pkg_ref == 13
    assert b70.x == pytest.approx(-0.04 * INCH) and b70.rotation == 270.0 and not b70.mirror
    assert b70.attributes == {".no_tp_under": "YES", ".comp_mount_type": "smt", "PART_NUMBER": "D-1234"}
    assert b70.properties["VALUE"] == "22UF"
    assert len(b70.toeprints) == 2 and b70.toeprints[1].name == "B70-2"
    attrs = b70.all_attributes()
    assert attrs["BOM.CPN"] == "070-000-016"
    assert attrs["BOM.MPN"] == "0 Y MC74HC259ADT"
    assert attrs["REFLOC"].startswith("IN,0.2")
    assert c400.mirror and c400.id == "77" and c400.part_name == "???"


def test_component_height_is_in_the_files_units():
    text = """UNITS=INCH
@0 .comp_height
CMP 0 1 1 0 N R1 X ;0=0.0217
CMP 0 2 2 0 N R2 X ;0=0.0000
CMP 0 3 3 0 N R3 X
"""
    cf, problems = parse_components(text, "c", Units.MM, AttrDefs())
    assert not problems.to_issues()
    assert [c.height for c in cf.components] == pytest.approx([0.0217 * INCH, 0.0, 0.0])  # 0: not given
    text = """UNITS=MM
@0 .COMP_HEIGHT
CMP 0 1 1 0 N R1 X ;0=1.25
CMP 0 2 2 0 N R2 X ;0=tall
"""
    cf, _problems = parse_components(text, "c", Units.INCH, AttrDefs())
    assert [c.height for c in cf.components] == [1.25, 0.0]


def test_components_unknown_record():
    _cf, problems = parse_components("CMP 0 1 1 0 N R1 X\nXYZ 1\n", "c", Units.MM, AttrDefs())
    assert [i.code for i in problems.to_issues()] == ["unknown_record"]


def test_attribute_definitions_and_resolution():
    defs, issues = AttrDefs.parse(
        [
            (
                "misc/userattr",
                "TEXT {\n NAME=PART_NO\n}\nOPTION {\n NAME=grade\n OPTIONS=a;b;c\n}\nINTEGER {\n NAME=count\n}\n",
            )
        ]
    )
    assert not issues
    names = {0: "PART_NO", 1: "grade", 2: "count", 3: "unknown_attr", 4: ".pad_usage"}
    texts = {0: "D-1", 1: "zzz"}
    assert resolve_attributes("0=1,1=2,2=1,3=0,4=2", names, texts, defs) == {
        "PART_NO": "zzz",
        "grade": "c",
        "count": "1",
        "unknown_attr": "D-1",
        ".pad_usage": "g_fiducial",
    }


def test_split_record():
    assert split_record("P 1 2 0 P 0 0;0=1,3;ID=12") == ("P 1 2 0 P 0 0", "0=1,3", "12")
    assert split_record("CMP 0 1 2 0 N R1 X;;ID=5") == ("CMP 0 1 2 0 N R1 X", "", "5")
    assert split_record("L 0 0 1 1 0 P 0") == ("L 0 0 1 1 0 P 0", "", None)


# ------------------------------------------------------------------ eda/data
EDA_SPEC = """#
HDR Mentor Boardstation database
UNITS=INCH
LYR sst sst+1 sigt
#
PRP MILLING_ORIGIN 'MILLING 0 0.0 0' 0 0
#@0 .critical_net
# NET 0
NET /D_CL_TX_CLK ;0,2=1;ID=1030
SNT TOP T 16 0
FID C 2 33
# PKG 1
PKG *PDXC-L10/HX-L127W51T97 0.1 -0.25 -0.145 0.25 0.145
RC -0.25 -0.1 0.5 0.2
PIN 1 T -0.2 -0.1105 0 E S ID=1034
RC -0.2125 -0.145 0.025 0.069
PIN 2 T -0.2 0.1105 0 E S
CR -0.2 0.1105 0.011811
PKG ROUND 0.1 -0.15 -0.15 0.15 0.15
CT
OB 0.15 0 I
OC 0.15 0 0 0 Y
OE
CE
PIN P T 0.0688976 0 0 E T
SQ 0.0688976 0 0.01
FGR TEXT
PRP string '030'
FID C 14 11018
"""


def test_eda_spec_example():
    eda, problems = parse_eda(EDA_SPEC, "e", Units.MM)
    assert not problems.to_issues()
    assert eda.units.units is Units.INCH and eda.source.startswith("Mentor")
    assert eda.layers == ["sst", "sst+1", "sigt"]
    assert eda.net_count == 1
    p0, p1 = eda.packages
    assert p0.name == "*PDXC-L10/HX-L127W51T97" and p0.pitch == pytest.approx(2.54)
    assert [pin.name for pin in p0.pins] == ["1", "2"]
    assert p0.pins[0].x == pytest.approx(-0.2 * INCH) and p0.pins[0].mtype == "S"
    assert p0.outlines[0].kind == "rect" and p0.pins[1].outlines[0].kind == "circle"
    assert p1.outlines[0].kind == "contour" and len(p1.outlines[0].polygons()[0]) > 8
    assert "string" not in p1.properties  # PRP after FGR belongs to the feature group


def test_package_body_size_leaves_out_the_pins():
    text = """UNITS=MM
PKG A 1 -2 -1 2 1
RC -1.5 -0.5 3 1
PIN 1 S -1.8 0 0 E S
RC -2 -0.4 0.4 0.8
PKG B 1 -0.5 -0.5 0.5 0.5
PIN 1 S 0 0 0 E S
CR 0 0 0.5
PKG C 1 -1 -1 1 1
CR 0 0 0.75
SQ 0.5 0 0.5
"""
    eda, problems = parse_eda(text, "e", Units.INCH)
    assert not problems.to_issues()
    a, b, c = eda.packages
    assert a.body_size == pytest.approx((3.0, 1.0))  # the pin's outline reaches further and is left out
    assert b.body_size is None  # pins only: no body
    assert c.body_size == pytest.approx((1.75, 1.5))  # every body outline counts
    inch, _problems = parse_eda("UNITS=INCH\nPKG D 0.05 -0.1 -0.05 0.1 0.05\nRC -0.1 -0.05 0.2 0.1\n", "e", Units.MM)
    assert inch.packages[0].body_size == pytest.approx((0.2 * INCH, 0.1 * INCH))


def test_eda_unknown_record():
    _eda, problems = parse_eda("PKG A 0 0 0 1 1\nRC 0 0 1 1\nWHAT 1\n", "e", Units.MM)
    assert [i.code for i in problems.to_issues()] == ["unknown_record"]
