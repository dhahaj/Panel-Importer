"""Golden: the ER Rev F8 panel (bottom layer) end to end.

ODB++ → Phase 1 project → Phase 2 ISS with default settings (left-right flip, auto
rotation) → compared with the programs that ran the pilot:

* ``ER_RevF8_circuitcam.iss`` (CircuitCAM, 22 parts) and
* ``ER_RevF8_production.x21`` (JaNets' save of the pilot program, 66 parts).

The pilot programs use a 53.086 mm row pitch; the ODB++ step-repeat says 52.578 mm
(confirmed against the bottom paste Gerber).  So the first row of circuits matches
within 0.05 mm and the second and third rows are offset by 0.508 and 1.016 mm in
program Y.  That is the correct result: do not tune toward the pilot program.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from panelimport.iss.checks import prepare
from panelimport.iss.compare import compare_programs
from panelimport.iss.reader import read_program
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import write_iss
from panelimport.session import Session

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT = FIXTURES / "Panel.panel.json"
EXPORT = FIXTURES / "Panel.zip"
CIRCUITCAM = FIXTURES / "iss" / "ER_RevF8_circuitcam.iss"
PRODUCTION = FIXTURES / "iss" / "ER_RevF8_production.x21"
# The three panel fiducials the pilot used (the saved project picked F(6.351,243.307)
# instead of F(176.275,12.703); both sets are valid).
PILOT_FIDUCIALS = ["F(176.275,12.703)", "F(6.351,12.703)", "F(176.275,243.307)"]
ROW_PITCH_ERROR = 0.508  # 53.086 (pilot) − 52.578 (ODB++)

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in (PROJECT, EXPORT, CIRCUITCAM, PRODUCTION)),
    reason="ER golden files (tests/fixtures/Panel.zip, Panel.panel.json, iss/ER_RevF8_*) not present",
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("er")
    shutil.copy(EXPORT, tmp / "Panel.zip")
    data = json.loads(PROJECT.read_text(encoding="utf-8"))
    data["source"]["path"] = "Panel.zip"  # saved on Daniel's PC with an absolute Windows path
    (tmp / "Panel.panel.json").write_text(json.dumps(data), encoding="utf-8")
    session = Session()
    reopened = session.open_project(tmp / "Panel.panel.json")
    assert reopened.source_issue is None and reopened.differences == []  # Phase 1 reproduces the project
    session.update(fiducials=PILOT_FIDUCIALS)
    assert session.analysis.confirmed
    project = session.analysis.to_project(tmp / "Panel.panel.json")
    prepared = prepare(project, IssSettings(), pwb_id="Panel")
    out = write_iss(prepared, tmp / "Panel.iss")
    return prepared, read_program(out)


def _rows_by_pilot_row(cmp) -> dict[float, list]:
    rows: dict[float, list] = {}
    for r in cmp.rows:
        rows.setdefault(round(cmp.b.circuits[r.circuit_b - 1].y, 3), []).append(r)
    return rows


def test_generated_program(generated):
    prepared, prog = generated
    assert [(i.code, i.severity.value) for i in prepared.issues] == [
        ("bottom_angles_unverified", "warning"),
        ("component_size_unknown", "warning"),  # the export has no .comp_height for 17 of them
    ]
    m = prepared.layout.machine
    assert (m.side, m.flip, m.rotation) == ("bottom", "left-right", 90)
    assert (prog.width, prog.height) == (256.0096, 182.626)
    assert prog.clamp_offset == 91.313
    assert len(prog.circuits) == 15 and len(prog.placements) == 66 and len(prog.components) == 34
    assert sorted({c.y for c in prog.circuits}) == [-105.156, -52.578, 0.0]  # the ODB++ pitch
    assert sorted({c.x for c in prog.circuits}) == [-205.232, -153.924, -102.616, -51.308, 0.0]
    assert (prog.circuit_width, prog.circuit_height) == (50.8, 52.07)
    r35 = next(p for p in prog.placements if p.designator == "R35")
    assert (r35.x, r35.y, r35.component) == (41.783, 21.209, "107522-31-1001")
    # Sizes: the package body outline (pins left out) and .comp_height, in mm.
    sizes = {c.name: (c.width, c.length, c.height) for c in prog.components}
    assert sizes["107522-31-1001"] == (1.7, 0.9, 0.5512)  # RESC1608X55: 0.0217 in high
    assert sizes["107523-1156-2204"] == (3.4, 1.8, 1.8009)  # CAPC3216X180
    assert sizes["107053-3"] == (1.3, 2.92, 1.11)  # SOT-23: pins along X, body long in Y
    assert sizes["107522-31-2002"] == (1.7, 0.9, 0.0)  # .comp_height=0: unknown


def test_golden_against_circuitcam(generated):
    _prepared, prog = generated
    cc = read_program(CIRCUITCAM)
    cmp = compare_programs(prog, cc)
    assert len({r.designator for r in cmp.rows}) == 22 and not cmp.only_b
    assert len(cmp.circuits) == 15 and not cmp.circuits_only_a and not cmp.circuits_only_b
    rows = _rows_by_pilot_row(cmp)
    assert sorted(rows) == [0.0, 53.086, 106.172]
    for k, (pilot_y, parts) in enumerate(sorted(rows.items())):
        for r in parts:
            assert abs(r.dx) <= 0.05, (r.designator, r.circuit_a)
            assert abs(r.dy - k * ROW_PITCH_ERROR) <= 0.05, (r.designator, r.circuit_a, pilot_y, r.dy)
    assert all(r.distance <= 0.05 for r in rows[0.0])
    assert len(cmp.fiducials) == 3 and all(f.distance <= 0.05 for f in cmp.fiducials)
    assert cmp.a.clamp_offset == 91.313 and cmp.b.clamp_offset == pytest.approx(91.313) and not cmp.clamp_differs()
    assert cmp.angle_pattern().startswith("vary per part")  # per-part reel corrections, not one offset


def test_golden_against_production(generated):
    _prepared, prog = generated
    prod = read_program(PRODUCTION)
    cmp = compare_programs(prog, prod)
    assert len({r.designator for r in cmp.rows}) == 66 and not cmp.only_a and not cmp.only_b
    rows = _rows_by_pilot_row(cmp)
    assert sorted(rows) == [0.0, 53.086, 106.172]
    for k, parts in enumerate(rows[y] for y in sorted(rows)):
        offsets = sorted(r.dy - k * ROW_PITCH_ERROR for r in parts)
        assert abs(offsets[len(offsets) // 2]) <= 0.01  # the median part: the pitch error exactly
    # Every part within 0.05 mm in the first row, except three that were entered by hand
    # in JaNets (positions rounded to 0.01 mm; not in CircuitCAM's program).
    far = {r.designator for r in rows[0.0] if r.distance > 0.05}
    assert far == {"C12", "D10", "L1"}
    assert len(cmp.fiducials) == 3 and all(f.distance <= 0.05 for f in cmp.fiducials)
    assert cmp.a.clamp_offset == 91.313 and cmp.b.clamp_offset == pytest.approx(91.313) and not cmp.clamp_differs()
    # Findings for review: the production program places other part numbers here.
    other = {(r.designator, r.component_a, r.component_b) for r in cmp.rows if r.component_a != r.component_b}
    assert other == {
        ("R15", "107522-11-1107", "107522-31-1107"),
        ("R17", "107522-11-1107", "107522-31-1107"),
        ("R23", "107522-31-1001", "107522-31-2002"),
    }
    assert cmp.angle_pattern().startswith("vary per part")
