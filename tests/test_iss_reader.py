"""Reading the reference programs: the frame equations hold on every one, and the x21
reader reports exactly what JaNets changed."""

from __future__ import annotations

from pathlib import Path

import pytest

from panelimport.iss.compare import compare_programs, format_comparison, panel_geometry
from panelimport.iss.reader import ReadError, read_iss_bytes, read_program

FIXTURES = Path(__file__).parent / "fixtures" / "iss"
ISS_FILES = ["T3_strip_both.iss", "102605_janets.iss", "102628_portrait_circuitcam.iss", "ER_RevF8_circuitcam.iss", "ER_issgen_panel3.iss"]
X21_FILES = ["102605_janets.x21", "ER_RevF8_production.x21", "ER_issgen_panel3_janets.x21"]


def program(name: str):
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"reference program {name} not in tests/fixtures/iss yet")
    return read_program(path)


def _inside(points, width, height, tol=0.05) -> bool:
    return all(-tol <= x <= width + tol and -tol <= y <= height + tol for x, y in points)


# -------------------------------------------------------------------- reference equations
@pytest.mark.parametrize("name", ISS_FILES + X21_FILES)
def test_reference_programs_give_consistent_panels(name):
    """placement = P + allocation + position, outline LL = P + allocation +
    circuitLayoutOffset, fiducial = P + markPosition: every circuit, part and fiducial
    lands on the panel, and the clamp offset is half the panel height (except issgen's
    copied 84.709)."""
    prog = program(name)
    assert prog.notes == [] or name.startswith("102628")  # 102628 uses a second mark set
    geom = panel_geometry(prog)
    assert len(geom.circuits) == (15 if name.startswith("ER") else 12)
    for c in geom.circuits:
        assert _inside(c.outline, prog.width, prog.height), (name, c.number, c.outline)
    assert _inside([(p.x, p.y) for p in geom.placements], prog.width, prog.height)
    assert _inside([(x, y) for _n, x, y in geom.fiducials], prog.width, prog.height)
    if "issgen" in name:
        assert prog.clamp_offset == pytest.approx(84.709)  # the copied 102605 value (the bug)
    else:
        assert prog.clamp_offset == pytest.approx(prog.height / 2, abs=0.01)


def test_102605_circuit_1_lower_left():
    geom = panel_geometry(program("102605_janets.iss"))
    assert geom.circuits[0].outline[0] == pytest.approx((0.0442, 12.8396), abs=1e-4)
    assert geom.origin == pytest.approx((21.5432, 38.0873), abs=1e-4)  # P inside circuit 1


def test_er_fiducials_and_rails():
    for name in ("ER_RevF8_circuitcam.iss", "ER_RevF8_production.x21"):
        geom = panel_geometry(program(name))
        ys = sorted(y for _n, _x, y in geom.fiducials)
        assert ys[0] == pytest.approx(6.35, abs=0.01)  # 6.35 mm from the bottom edge
        assert min(x for _n, x, _y in geom.fiducials) == pytest.approx(12.7, abs=0.03)
        assert geom.origin == pytest.approx((256.032, 0.0), abs=1e-3)  # CircuitCAM: P at the lower-right
        assert min(min(y for _x, y in c.outline) for c in geom.circuits) == pytest.approx(12.7, abs=1e-3)  # rail


def test_102628_portrait_rails():
    prog = program("102628_portrait_circuitcam.iss")
    assert (prog.width, prog.height) == (169.418, 270.256)
    geom = panel_geometry(prog)
    xs = [x for c in geom.circuits for x, _y in c.outline]
    assert min(xs) == pytest.approx(12.7, abs=1e-3) and prog.width - max(xs) == pytest.approx(12.67, abs=0.01)
    assert sorted((round(x, 2), round(y, 2)) for _n, x, y in geom.fiducials) == [(6.35, 12.7), (6.35, 257.56)]


def test_issgen_and_circuitcam_agree_circuit_relative():
    """The two ER programs put P in different places but every part common to both
    lands at the same circuit-relative position (CircuitCAM's 22 vs issgen's 66)."""
    cc, ig = program("ER_RevF8_circuitcam.iss"), program("ER_issgen_panel3.iss")
    cmp = compare_programs(ig, cc)
    assert len({r.designator for r in cmp.rows}) == 22
    first_row = [r for r in cmp.rows if cc.circuits[r.circuit_b - 1].y == 0]
    assert max(abs(r.dx) for r in first_row) < 0.03
    assert max(abs(r.dy) for r in first_row) < 0.01


# -------------------------------------------------------------------- x21 reader
def test_x21_reports_what_janets_changed():
    """issgen's panel3.iss vs JaNets' save of it: 7 placements (rotations, plus R35 Y
    −0.009 and D12 X −0.001), MATRIX → NONMATRIX, and an extra component named 0."""
    iss, x21 = program("ER_issgen_panel3.iss"), program("ER_issgen_panel3_janets.x21")
    cmp = compare_programs(iss, x21)
    assert cmp.changed_designators == ["C4", "D9", "D12", "Q1", "R35", "U2", "U3"]
    moved = {(r.designator, round(r.dx, 4), round(r.dy, 4)) for r in cmp.rows if r.moved}
    assert moved == {("R35", 0.0, -0.009), ("D12", -0.001, 0.0)}
    assert {r.designator for r in cmp.rows if r.rotated} == {"C4", "D9", "D12", "Q1", "U2", "U3"}
    assert (iss.circuit_layout, x21.circuit_layout) == ("MATRIX", "NONMATRIX")
    assert [(c.x, c.y) for c in iss.circuits] == [(c.x, c.y) for c in x21.circuits]  # same 5 × 3 grid
    assert cmp.components_only_a == [] and cmp.components_only_b == ["0"]
    assert x21.counts["component"] == (35, 34)  # HdCompo total=35 comp=34
    assert not cmp.only_a and not cmp.only_b and not cmp.position_changed  # all within 0.01 mm
    assert all(f.distance == 0 for f in cmp.fiducials) and not cmp.panel_differs() and not cmp.clamp_differs()
    text = format_comparison(cmp)
    assert "Circuit layout: A MATRIX → B NONMATRIX" in text and "Components only in B: '0'" in text
    assert text.splitlines()[-1].startswith("Different: 66 common parts × 15 circuits, 7 changed")


def test_x21_reader_against_its_iss():
    """102605: the .x21 is JaNets' save of a later edit of the ISS (allocations evened
    out, no placements), so the panels agree to about 0.2 mm."""
    iss, x21 = program("102605_janets.iss"), program("102605_janets.x21")
    assert x21.kind == "x21" and len(x21.placements) == 0 and x21.counts["placement"] == (0, 0)
    assert (x21.width, x21.height) == pytest.approx((iss.width, iss.height), abs=0.01)
    assert x21.clamp_offset == pytest.approx(84.705)
    cmp = compare_programs(iss, x21)
    assert len(cmp.circuits) == 12 and not cmp.circuits_only_a and not cmp.circuits_only_b
    assert max(abs(c.dx) for c in cmp.circuits) < 0.25 and max(abs(c.dy) for c in cmp.circuits) < 0.25
    assert len(cmp.fiducials) == 3 and max(f.distance for f in cmp.fiducials) < 0.25


def test_production_x21_header_and_marks():
    prog = program("ER_RevF8_production.x21")
    assert prog.counts["placement"] == (66, 66) and prog.counts["component"] == (34, 34) and prog.counts["mark"] == (2, 0)
    assert [f.name for f in prog.fiducials] == ["FD1", "FD2", "FD3"]
    assert prog.pwb_layout_offset == (0.0, 0.0) and prog.circuit_layout_offset == (-50.8, 12.7)
    assert {p.component for p in prog.placements if p.designator == "D5"} == {"109818"}


# -------------------------------------------------------------------- robustness
def test_unknown_structure_is_reported_not_fatal():
    data = b"""<?xml version="1.0" encoding="utf-8"?>
<productionProgram><core><pwbData><pwbConfiguration><outline x="100" y="50" /></pwbConfiguration>
<circuitConfigurationData><circuitConfiguration index="0"><circuitId>A</circuitId>
<circuitConfiguration>STRANGE</circuitConfiguration></circuitConfiguration></circuitConfigurationData></pwbData>
<placementData><placement index="0"><placementId>R1</placementId><componentName>X</componentName>
<placementPosition x="1" y="abc" /></placement></placementData></core></productionProgram>"""
    prog = read_iss_bytes(data)
    assert (prog.width, prog.height) == (100, 50) and len(prog.circuits) == 1 and prog.placements == []
    assert any("STRANGE" in n for n in prog.notes)
    assert any("pwbLayoutOffset" in n for n in prog.notes)
    assert any("R1" in n for n in prog.notes)


def test_unreadable_files(tmp_path):
    bad = tmp_path / "bad.iss"
    bad.write_text("not xml")
    with pytest.raises(ReadError, match="not XML"):
        read_program(bad)
    other = tmp_path / "other.iss"
    other.write_text("<html />")
    with pytest.raises(ReadError, match="root element <html>"):
        read_program(other)
    with pytest.raises(ReadError):
        read_program(tmp_path / "missing.iss")
