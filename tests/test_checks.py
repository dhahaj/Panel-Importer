"""Paste, BOM, units and fiducial checks."""

import pytest

from panelimport.io.bom import BomError, read_bom
from panelimport.io.odb import OdbJob
from panelimport.settings import Settings
from tests.conftest import codes, issues_of, run, write
from tests.synthetic.odbgen import sr_panel


def test_shifted_paste_reports_vector(tmp_path):
    """A shifted paste layer is reported with its shift vector."""
    job = sr_panel(n_parts=30)
    for p in job.steps["pcb"].pads["top_paste"]:
        p.x += 0.3
        p.y -= 0.2
    a = run(job, tmp_path)
    (shift,) = issues_of(a, "pattern_shift")
    assert shift.severity.value == "error"
    assert shift.data["dx"] == pytest.approx(-0.3, abs=1e-6)
    assert shift.data["dy"] == pytest.approx(0.2, abs=1e-6)
    assert "ΔX -0.300, ΔY +0.200" in shift.message
    assert not issues_of(a, "centroid_off_pads")  # explained by the shift


def test_small_paste_shift_is_not_an_error(tmp_path):
    job = sr_panel(n_parts=30)
    for p in job.steps["pcb"].pads["top_paste"]:
        p.x += 0.05
    a = run(job, tmp_path)
    assert "pattern_shift" not in codes(a)


def test_centroid_off_its_pads(tmp_path):
    job = sr_panel()
    board = job.steps["pcb"]
    board.component("Q9", "SOT23", 44.0, 8.0, paste_offset=(0.4, 0.0))
    a = run(job, tmp_path)
    (issue,) = issues_of(a, "centroid_off_pads")
    assert issue.designator == "Q9" and issue.severity.value == "warning"
    assert issue.data["dx"] == pytest.approx(-0.4, abs=1e-6)
    q9 = next(p for p in a.placements if p.designator == "Q9")
    assert q9.paste.status == "off"


def test_through_hole_part_has_no_paste(tmp_path):
    a = run(sr_panel(), tmp_path)
    (issue,) = issues_of(a, "no_paste")
    assert issue.designator == "J1" and issue.severity.value == "info"
    assert next(p for p in a.placements if p.designator == "J1").paste.status == "no-paste"


def test_bottom_paste_checked(tmp_path):
    a = run(sr_panel(), tmp_path)
    c2 = next(p for p in a.placements if p.designator == "C2")
    assert c2.layer == "bottom" and c2.paste.status == "ok"


def test_missing_paste_layer_role(tmp_path):
    a = run(sr_panel(), tmp_path, layer_roles={"paste_top": ""})
    assert "no_paste_layer" in codes(a)


def test_bom_cross_check(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_text(
        "Project,Demo\n\nComment,Designator,Quantity\n"
        '100n,"C1, C2",2\n10k,R1,1\n555,U1,1\nghost,X9,1\n',
        encoding="utf-8",
    )
    parsed = read_bom(bom)
    assert parsed.designators == ["C1", "C2", "R1", "U1", "X9"]
    from panelimport.analysis.pipeline import analyze
    from panelimport.model.panel import Decisions

    a = analyze(OdbJob(write(sr_panel(n_parts=5), tmp_path)), Settings(), Decisions(), bom=parsed)
    assert [i.designator for i in issues_of(a, "bom_not_in_odb")] == ["X9"]
    assert [i.designator for i in issues_of(a, "bom_not_in_bom")] == ["J1"]
    assert all(i.severity.value == "warning" for i in issues_of(a, "bom_not_in_odb"))


def test_bom_without_designator_column(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_text("a,b\n1,2\n")
    with pytest.raises(BomError):
        read_bom(bom)


def test_inch_and_mm_give_the_same_result(tmp_path):
    a = run(sr_panel(units="MM"), tmp_path / "mm").to_project()
    b = run(sr_panel(units="INCH"), tmp_path / "in").to_project()
    flat = lambda p: [v for c in p.circuits for v in (c.dx, c.dy)]  # noqa: E731
    assert flat(a) == pytest.approx(flat(b), abs=1e-4)
    pa = {p.designator: (p.x, p.y) for p in a.placements}
    pb = {p.designator: (p.x, p.y) for p in b.placements}
    assert pa.keys() == pb.keys()
    for k in pa:
        assert pa[k] == pytest.approx(pb[k], abs=1e-4)


def test_units_default_is_reported(tmp_path):
    a = run(sr_panel(units="INCH", units_style="none", version=(7, 0)), tmp_path)
    (issue,) = issues_of(a, "units_assumed")
    assert issue.severity.value == "info"  # consistent INCH default, per ODB++ v7
    assert a.summary.startswith("6 circuits, 3 × 2, pitch 52.000 × 38.500 mm")


def test_mixed_units_are_a_warning(tmp_path):
    job = sr_panel(units="MM")
    root = write(job, tmp_path)
    paste = root / "steps" / "pcb" / "layers" / "top_paste" / "features"
    paste.write_text("\n".join(l for l in paste.read_text().splitlines() if not l.startswith(("U ", "UNITS="))))
    info_file = root / "misc" / "info"
    info_file.write_text("\n".join(l for l in info_file.read_text().splitlines() if not l.startswith("UNITS")))
    from panelimport.analysis.pipeline import analyze

    a = analyze(OdbJob(root), Settings())
    (issue,) = issues_of(a, "units_assumed")
    assert issue.severity.value == "warning"


def test_unknown_record_blocks_confirmation(tmp_path):
    job = sr_panel()
    root = write(job, tmp_path)
    comps = root / "steps" / "pcb" / "layers" / "comp_+_top" / "components"
    comps.write_text(comps.read_text() + "XYZ something new\n")
    from panelimport.analysis.pipeline import analyze

    a = analyze(OdbJob(root), Settings())
    (issue,) = issues_of(a, "unknown_record")
    assert issue.severity.value == "error" and "XYZ" in issue.message
    assert not a.can_confirm()[0]


def test_missing_required_file(tmp_path):
    root = write(sr_panel(), tmp_path)
    (root / "steps" / "pcb" / "eda" / "data").unlink()
    from panelimport.analysis.pipeline import analyze

    a = analyze(OdbJob(root), Settings())
    assert any(i.code == "missing_file" and "eda/data" in i.message for i in a.issues)


def test_feature_and_attribute_fiducials(tmp_path):
    job = sr_panel(with_fiducials=False)
    pan = job.steps["panel"]
    pan.fiducial_feature(3, 3, attr=True)
    pan.fiducial_feature(160, 3, attr=False)
    pan.pad("top_copper", 80, 3, "round", 1.0)  # no mask opening: not a fiducial
    pan.pad("top_mask", 80, 3, "round", 1.0)
    a = run(job, tmp_path)
    panel = {f.name: f for f in a.fiducial_candidates if f.selectable}
    assert set(panel) == {"F(3.000,3.000)", "F(160.000,3.000)"}
    assert panel["F(3.000,3.000)"].sources == ["attribute"]
    assert panel["F(160.000,3.000)"].sources == ["copper"]
    assert panel["F(160.000,3.000)"].diameter == pytest.approx(1.0)


def test_isolation_required_for_copper_fiducial(tmp_path):
    job = sr_panel(with_fiducials=False)
    pan = job.steps["panel"]
    pan.fiducial_feature(160, 3, attr=False)
    pan.line("top_copper", 158, 3.9, 162, 3.9, 0.2)  # trace within the clearance
    a = run(job, tmp_path)
    assert not [f for f in a.fiducial_candidates if f.selectable]
    assert "no_fiducials" in codes(a)


def test_circuit_fiducials_are_not_selectable(tmp_path):
    job = sr_panel()
    job.steps["pcb"].component("FID9", "FID1MM", 48, 34, part="FIDUCIAL")
    a = run(job, tmp_path)
    local = [f for f in a.fiducial_candidates if f.level == "circuit" and f.designator == "FID9"]
    assert len(local) == 6 and not any(f.selectable for f in local)


def test_at_most_three_panel_fiducials(tmp_path):
    job = sr_panel()
    job.steps["panel"].component("FID4", "FID1MM", 161.5, 82.5, part="FIDUCIAL")
    a = run(job, tmp_path, fiducials=["FID1", "FID2", "FID3", "FID4"])
    assert [f.name for f in a.fiducials] == ["FID1", "FID2", "FID3"]
    assert "fiducial_count" in codes(a)
