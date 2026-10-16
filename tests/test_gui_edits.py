"""Offscreen GUI tests of component edits: remove (with suggestions), add, edit, restore,
revert, the canvas menu, the issue list, undo and save/reopen."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QFileDialog  # noqa: E402

from panelimport.analysis import edits as E  # noqa: E402
from panelimport.app import dispose  # noqa: E402
from panelimport.gui.component_dialog import ComponentDialog, RemoveDialog  # noqa: E402
from panelimport.gui.panels.components import COL_DESIGNATOR, COL_STATUS, FIELD_COLUMNS, KEY_ROLE  # noqa: E402
from tests.conftest import open_panel  # noqa: E402
from tests.synthetic.odbgen import sr_panel  # noqa: E402


def _row(panel, key):
    model = panel.model
    for r in range(model.rowCount()):
        if tuple(model.index(r, COL_DESIGNATOR).data(KEY_ROLE)) == key:
            return [model.item(r, c) for c in range(model.columnCount())]
    return None


@pytest.fixture
def dialogs(monkeypatch):
    """Answer the next dialogs with functions that fill them in (None: cancel)."""
    answers: list = []
    seen: list = []

    def fake_exec(dlg):
        seen.append(dlg)
        fill = answers.pop(0) if answers else None
        if fill is None:
            return QDialog.Rejected
        fill(dlg)
        return QDialog.Accepted

    monkeypatch.setattr(ComponentDialog, "exec", fake_exec)
    monkeypatch.setattr(RemoveDialog, "exec", fake_exec)
    return answers, seen


def test_remove_suggested_through_hole_parts_and_undo(window, tmp_path, app, dialogs):
    answers, seen = dialogs
    open_panel(window, tmp_path, app)
    assert "(1)" in window.components_panel.suggest_actions["through-hole"].text()
    answers.append(lambda d: None)
    window.components_panel.suggestRequested.emit("through-hole")
    dlg = seen[-1]
    assert dlg.chosen() == [("board", "J1")] and dlg.chosen_reason() == "through-hole"
    assert dlg.table.item(0, 3).text() == "no paste on its pads"
    a = window.analysis
    assert [p.designator for p in a.removed_placements] == ["J1"]
    assert "no_paste" not in [i.code for i in a.issues]
    row = _row(window.components_panel, ("board", "J1"))
    assert row[COL_STATUS].text() == "removed: through-hole" and row[COL_DESIGNATOR].font().strikeOut()
    markers = [m for m in window.canvas._markers if m.key[0] == "J1"]
    assert len(markers) == 6 and all(m.state == "removed" for m in markers)
    assert set(window.canvas.layers["removed"]) >= set(markers)
    stack = window.controller.undo_stack
    assert stack.undoText().startswith("Remove J1")
    stack.undo()
    assert not window.analysis.removed_placements
    stack.redo()
    assert [p.designator for p in window.analysis.removed_placements] == ["J1"]
    # Restore from the table.
    window.components_panel.select_keys([("board", "J1")])
    window.components_panel.act_restore.trigger()
    assert not window.analysis.removed_placements


def test_remove_dialog_unchecked_rows_stay(window, tmp_path, app, dialogs):
    answers, _seen = dialogs

    def keep_fid2(d):
        d.table.item(1, 0).setCheckState(Qt.Unchecked)
        d.reason.setCurrentIndex(d.reason.findData("mechanical"))
        d.note.setText("not machine-placed")

    open_panel(window, tmp_path, app)
    answers.append(keep_fid2)
    window.suggest_removals("mechanical")
    removed = {p.designator: p.edit for p in window.analysis.removed_panel_parts}
    assert set(removed) == {"FID1", "FID3"}
    assert removed["FID1"].reason == "mechanical" and removed["FID1"].note == "not machine-placed"
    # Removed fiducial components are still fiducial candidates.
    assert {"FID1", "FID3"} <= {f.name for f in window.analysis.fiducial_candidates if f.selectable}


def test_add_component_from_the_canvas_menu(window, tmp_path, app, dialogs):
    answers, seen = dialogs
    open_panel(window, tmp_path, app)
    a = window.analysis
    menu = window.canvas_menu(None, 5 + 52 + 40.0, 5 + 12.0)  # inside circuit 2
    add = next(act for act in menu.actions() if act.text().startswith("Add component here"))
    assert "circuit 2, X 40.000 Y 12.000" in add.text()

    def fill(d):
        assert d.chosen_level() == "board" and (d.x.value(), d.y.value()) == (40.0, 12.0)
        d.designator.setText("U99")
        d.package.setCurrentText("SOIC8")
        d.part_number.setText("IC-99")
        d.rotation.setValue(90)

    answers.append(fill)
    add.trigger()
    u99 = E.find_part(window.analysis, "board", "U99")
    assert u99 is not None and u99.state == "added" and u99.body and len(u99.toeprints) == 8
    assert (u99.x - a.reference_board[0], u99.rotation, u99.part_number) == (40.0, 90.0, "IC-99")
    markers = [m for m in window.canvas._markers if m.key[0] == "U99"]
    assert len(markers) == 6 and all(m.state == "added" for m in markers)
    assert window.components_panel.selected_keys() == [("board", "U99")]
    assert window.inspector.title.text().startswith("U99")
    # Outside every circuit the same menu adds a panel-level component.
    menu = window.canvas_menu(None, 1.0, 1.0)
    add = next(act for act in menu.actions() if act.text().startswith("Add component here"))
    assert "panel X 1.000 Y 1.000" in add.text()


def test_add_dialog_validation(window, tmp_path, app):
    open_panel(window, tmp_path, app)
    dlg = ComponentDialog(window, window.analysis)
    assert dlg.validate() == "Enter a designator."
    dlg.designator.setText("c1")
    assert "already is a board-level C1" in dlg.validate()
    dlg.designator.setText("C 9")
    assert "spaces" in dlg.validate()
    dlg.level.setCurrentIndex(dlg.level.findData("panel"))
    dlg.designator.setText("FID2")
    assert "panel-level FID2" in dlg.validate()
    dlg.accept()
    assert dlg.error.isVisibleTo(dlg) and dlg.result() != QDialog.Accepted
    dlg.designator.setText("LBL1")
    assert dlg.validate() == ""
    dispose(dlg)


def test_edit_one_component(window, tmp_path, app, dialogs):
    answers, seen = dialogs
    open_panel(window, tmp_path, app)

    def fill(d):
        assert d.designator.text() == "C1" and not d.designator.isEnabled()
        d.part_number.setText("D-9")
        d.x.setValue(d.x.value() + 0.1)
        d.note.setText("datasheet centroid")

    answers.append(fill)
    window.edit_components([("board", "C1")])
    c1 = E.find_part(window.analysis, "board", "C1")
    assert c1.state == "edited" and c1.part_number == "D-9"
    assert c1.export == {"part_number": "", "x": 25.0, "y": 10.0}
    assert c1.edit.note == "datasheet centroid"
    row = _row(window.components_panel, ("board", "C1"))
    assert row[FIELD_COLUMNS["part_number"]].toolTip() == "Export: (empty)"
    assert row[FIELD_COLUMNS["x"]].toolTip() == "Export: 25.000"
    edited_colour = row[FIELD_COLUMNS["x"]].foreground().color()
    assert row[FIELD_COLUMNS["part_name"]].toolTip() == ""  # unchanged fields are not marked
    assert row[FIELD_COLUMNS["package"]].foreground().color() != edited_colour
    window._component_selected("C1")
    table = window.inspector.table
    rows = [(table.item(r, 0).text(), table.item(r, 1).text()) for r in range(table.rowCount())]
    x = rows.index(("Circuit X (mm)", "25.1000"))
    assert rows[x + 1] == ("    export", "25.0000") and rows[x + 2] == ("Circuit Y (mm)", "10.0000")
    assert ("Status", "edited: part number, position — datasheet centroid") in rows
    # The dialog shows the export's values next to what changed, with a way back.
    dlg = ComponentDialog(window, window.analysis, [("board", "C1")])
    assert dlg.hints["part_number"].isVisibleTo(dlg) and not dlg.hints["package"].isVisibleTo(dlg)
    dlg.resets["x"].click()
    assert not dlg.hints["x"].isVisibleTo(dlg)
    dispose(dlg)
    # Revert from the table.
    window.components_panel.select_keys([("board", "C1")])
    window.components_panel.act_revert.trigger()
    assert E.find_part(window.analysis, "board", "C1").state == ""


def test_ok_without_changes_creates_no_edit(window, tmp_path, app, dialogs):
    answers, _seen = dialogs
    job = sr_panel(n_parts=5)
    job.steps["pcb"].components[1].x = 25.123456  # more decimals than the dialog shows
    open_panel(window, tmp_path, app, job)
    depth = window.controller.undo_stack.count()
    answers.append(lambda d: None)
    window.edit_components([("board", "C1")])
    assert window.controller.undo_stack.count() == depth
    assert not window.analysis.component_edits


def test_edit_several_components(window, tmp_path, app, dialogs):
    answers, seen = dialogs
    open_panel(window, tmp_path, app)

    def fill(d):
        assert d.mode == "many" and not d.x.isEnabled()
        d.part_number.setText("D-CAP")

    answers.append(fill)
    window.edit_components([("board", "C1"), ("board", "C2")])
    assert {E.find_part(window.analysis, "board", n).part_number for n in ("C1", "C2")} == {"D-CAP"}
    assert window.controller.undo_stack.undoText() == "Edit C1, C2"


def test_edit_component_sizes(window, tmp_path, app, dialogs):
    answers, _seen = dialogs
    open_panel(window, tmp_path, app)

    def fill(d):
        width, height = d.editors["width"], d.editors["height"]
        assert width.value() == pytest.approx(1.6) and height.text() == "unknown"  # no .comp_height
        height.setValue(0.55)
        assert d.hints["height"].isVisibleTo(d) and d.hints["height"].text() == "export: unknown"
        assert not d.hints["width"].isVisibleTo(d)

    answers.append(fill)
    window.edit_components([("board", "C1")])
    c1 = E.find_part(window.analysis, "board", "C1")
    assert c1.state == "edited" and c1.height == 0.55 and c1.export == {"height": 0.0}
    row = _row(window.components_panel, ("board", "C1"))
    assert row[FIELD_COLUMNS["width"]].text() == "1.600" and row[FIELD_COLUMNS["width"]].toolTip() == ""
    assert row[FIELD_COLUMNS["height"]].text() == "0.550" and row[FIELD_COLUMNS["height"]].toolTip() == "Export: -"
    assert row[COL_STATUS].text() == "edited: size"
    assert _row(window.components_panel, ("board", "U1"))[FIELD_COLUMNS["height"]].text() == "-"
    window._component_selected("C1")
    table = window.inspector.table
    rows = [(table.item(r, 0).text(), table.item(r, 1).text()) for r in range(table.rowCount())]
    h = rows.index(("Height (mm)", "0.5500"))
    assert rows[h + 1] == ("    export", "unknown") and ("Width (X, mm)", "1.6000") in rows

    # Several at once: a size that is set applies to each, the others stay each one's.
    def fill_many(d):
        assert d.mode == "many" and d.editors["width"].isEnabled() and d.editors["width"].text() == "(keep each one's)"
        d.editors["height"].setValue(0.9)

    answers.append(fill_many)
    window.edit_components([("board", "C1"), ("board", "U1")])
    sizes = [E.find_part(window.analysis, "board", n) for n in ("C1", "U1")]
    assert [(round(p.width, 4), round(p.length, 4), p.height) for p in sizes] == [(1.6, 0.8, 0.9), (5.31, 3.9, 0.9)]


def test_remove_part_from_the_issue_list(window, tmp_path, app, dialogs):
    answers, seen = dialogs
    open_panel(window, tmp_path, app)
    panel = window.issues_panel
    row = next(r for r in range(panel.model.rowCount()) if panel.issue_at(r).code == "no_paste")
    panel.table.selectRow(row)
    assert panel.remove_btn.isEnabled()
    answers.append(lambda d: None)
    panel.remove_btn.click()
    assert seen[-1].chosen_reason() == "through-hole"
    assert [p.designator for p in window.analysis.removed_placements] == ["J1"]


def test_edits_save_and_reopen_in_the_gui(window, tmp_path, app, dialogs, monkeypatch):
    answers, _seen = dialogs
    open_panel(window, tmp_path, app)
    answers.append(lambda d: None)
    window.remove_components([("board", "J1")])
    answers.append(lambda d: d.part_number.setText("D-1"))
    window.edit_components([("board", "R1")])
    window.acknowledge(window.analysis.warnings)
    window.confirm_panel()
    for name in ("FID1", "FID2", "FID3"):
        window.accept_fiducial(name)
    target = tmp_path / "Panel_ODB.panel.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_project()
    saved = window.controller.session.saved_project
    assert [e.designator for e in saved.component_edits] == ["J1", "R1"]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    window.open_project()
    assert window.analysis.confirmed
    assert window.analysis.to_project(target) == saved
    assert _row(window.components_panel, ("board", "J1"))[COL_STATUS].text() == "removed: through-hole"
    assert window.components_panel.act_add.isEnabled()


def test_edits_keep_confirmation_and_selection(window, tmp_path, app, dialogs):
    answers, _seen = dialogs
    open_panel(window, tmp_path, app)
    window.confirm_panel()
    assert window.analysis.confirmed
    window.components_panel.select_keys([("board", "R1")])
    answers.append(lambda d: None)
    window.components_panel.act_remove.trigger()
    assert window.analysis.confirmed  # component edits do not touch the panel structure
    assert window.components_panel.selected_keys() == [("board", "R1")]


def test_double_click_on_the_canvas_edits(window, tmp_path, app, dialogs):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    answers, seen = dialogs
    open_panel(window, tmp_path, app)
    a = window.analysis
    r1 = E.find_part(a, "board", "R1")
    x, y, _r = a.circuit_position(r1, a.circuits[2])
    window.canvas.zoom_to(x, y, 3)
    app.processEvents()
    vp = QPointF(window.canvas.mapFromScene(QPointF(x, y)))
    ev = QMouseEvent(QEvent.MouseButtonDblClick, vp, vp, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    answers.append(lambda d: d.part_number.setText("D-R1"))
    window.canvas.mouseDoubleClickEvent(ev)
    assert seen and seen[-1].keys == [("board", "R1")]
    assert E.find_part(window.analysis, "board", "R1").part_number == "D-R1"
