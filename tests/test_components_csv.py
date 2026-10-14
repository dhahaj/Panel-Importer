"""The components CSV lists what the components table lists, with the edits applied."""

import csv

from panelimport.analysis import edits as E
from panelimport.components_csv import COLUMNS, component_rows, write_components_csv
from panelimport.model.panel import Acknowledgement
from panelimport.model.project_file import load_project
from panelimport.session import Session
from tests.synthetic.odbgen import sr_panel


def _session(tmp_path, **kw):
    s = Session()
    s.open_source(sr_panel(**kw).write_tgz(tmp_path / "Panel_ODB.tgz"))
    return s


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def _read_rows(tmp_path, a):
    out = tmp_path / "out.csv"
    write_components_csv(a, out)
    return _read(out)


def _save(s, path):
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    return s.save(path)


def test_every_component_once_in_designator_order(tmp_path):
    s = _session(tmp_path, n_parts=40)
    a = s.update(part_number_attribute="PART_NUMBER")
    out = tmp_path / "out.csv"
    assert write_components_csv(a, out) == 43  # 40 placements + 3 panel-level fiducials
    header, rows = _read(out)
    assert header == list(COLUMNS)
    names = [r["Designator"] for r in rows]
    board = [r["Designator"] for r in rows if r["Level"] == "board"]
    assert names == board + ["FID1", "FID2", "FID3"]
    assert board == sorted(board, key=E.natural_key) and board.index("C2") < board.index("C10")
    by_name = {r["Designator"]: r for r in rows}
    assert list(by_name["C1"].values()) == ["C1", "board", "CAP-100N", "D-1001", "C0603", "top", "25", "10", "270", "OK 0.000 mm", ""]
    assert by_name["C2"]["Side"] == "bottom" and by_name["J1"]["Paste check"] == "no paste"
    assert list(by_name["FID2"].values()) == ["FID2", "panel", "FIDUCIAL", "", "FID1MM", "top", "161.5", "2.5", "0", "", ""]


def test_numbers_are_the_project_files(tmp_path):
    job = sr_panel()
    job.steps["pcb"].components[1].x = 25.123456  # more decimals than the table shows
    s = Session()
    s.open_source(job.write_folder(tmp_path))
    _save(s, tmp_path / "p.panel.json")
    _header, rows = _read_rows(tmp_path, s.analysis)
    project = load_project(tmp_path / "p.panel.json")
    placed = {p.designator: p for p in project.placements} | {p.designator: p for p in project.panel_parts}
    assert len(rows) == len(placed) == 15
    for r in rows:
        p = placed[r["Designator"]]
        assert (float(r["X (mm)"]), float(r["Y (mm)"]), float(r["Rotation (°)"])) == (p.x, p.y, p.rotation)
    assert {r["Designator"]: r["X (mm)"] for r in rows}["C1"] == "25.123456"


def test_edits_are_applied_and_removed_parts_are_listed(tmp_path):
    s = _session(tmp_path)
    a = s.analysis
    edits = E.remove_parts([], [("board", "J1"), ("panel", "FID3")], "through-hole", "hand-soldered")
    added = E.added_edit("board", "U99", {"package": "SOIC8", "x": 40, "y": 12.5, "rotation": 270, "part_number": "IC-9"})
    c1 = E.find_part(a, "board", "C1")
    moved = E.edit_from_values(a, "board", "C1", {**E.shown_values(a, c1), "x": 25.1, "part_number": "D-9"})
    a = s.update(component_edits=E.set_edits(edits, [added, moved]), edit_frame=a.edit_frame)
    _header, rows = _read_rows(tmp_path, a)
    assert len(rows) == len(E.all_parts(a)) == 16
    by_name = {r["Designator"]: r for r in rows}
    assert by_name["J1"]["Status"] == "removed: through-hole — hand-soldered"
    assert by_name["FID3"]["Status"] == "removed: through-hole — hand-soldered"
    assert (by_name["U99"]["X (mm)"], by_name["U99"]["Y (mm)"], by_name["U99"]["Status"]) == ("40", "12.5", "added")
    assert (by_name["C1"]["Part number"], by_name["C1"]["X (mm)"]) == ("D-9", "25.1")
    assert by_name["C1"]["Status"] == "edited: part number, position"
    # Removed parts stay where the table sorts them, not at the end.
    names = [r["Designator"] for r in rows]
    assert names.index("J1") < names.index("Q1") and names[-1] == "FID3"


def test_excel_reads_it(tmp_path):
    s = _session(tmp_path)
    tricky = 'CAP, 100 nF "X7R"\nµ-size'
    edit = E.added_edit("panel", "LBL1", {"part_name": tricky, "x": 1, "y": 2}, note="späť")
    a = s.update(component_edits=[edit], edit_frame=s.analysis.edit_frame)
    out = tmp_path / "out.csv"
    write_components_csv(a, out)
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw  # UTF-8 with a BOM, Excel's line ends
    _header, rows = _read(out)
    row = next(r for r in rows if r["Designator"] == "LBL1")
    assert row["Part name"] == tricky and row["Status"] == "added — späť"


def test_a_project_without_its_source_can_be_exported(tmp_path):
    s = _session(tmp_path)
    _save(s, tmp_path / "p.panel.json")
    live = component_rows(s.analysis)
    (tmp_path / "Panel_ODB.tgz").unlink()
    s2 = Session()
    s2.open_project(tmp_path / "p.panel.json")
    assert s2.read_only
    shown = component_rows(s2.analysis)
    # The snapshot has no paste layer to check against; everything else is the saved model.
    assert [r[:9] for r in shown] == [r[:9] for r in live]
