"""Offscreen GUI tests: the GUI shows what the CLI prints, selection sync, fiducials,
undo, confirm/save, reopen and canvas performance.  Fixtures (app, boxes, window) are in
conftest.py."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QFileDialog  # noqa: E402

from panelimport.analysis.pipeline import analyze  # noqa: E402
from panelimport.io.odb import OdbJob  # noqa: E402
from panelimport.model.panel import Decisions  # noqa: E402
from panelimport.model.project_file import load_project  # noqa: E402
from panelimport.settings import Settings  # noqa: E402
from tests.conftest import open_panel  # noqa: E402
from tests.synthetic.odbgen import add_copper, sr_panel  # noqa: E402


def test_gui_shows_the_cli_summary_and_issues(window, tmp_path, app):
    src = open_panel(window, tmp_path, app)
    a = analyze(OdbJob(src), Settings())
    assert window.summary.summary.text() == a.summary
    shown = [window.issues_panel.issue_at(r).format() for r in range(window.issues_panel.model.rowCount())]
    assert shown == [i.format() for i in a.issues]
    assert window.circuits_panel.table.rowCount() == 6
    panel = window.components_panel
    assert panel.proxy.rowCount() == 23  # 20 placements + 3 panel-level fiducials
    panel.show_filter.setCurrentIndex(panel.show_filter.findData("board"))
    assert panel.proxy.rowCount() == 20
    assert window.summary.confirm_btn.isEnabled()
    assert not window.act_save.isEnabled()


def test_selection_sync_canvas_and_table(window, tmp_path, app):
    open_panel(window, tmp_path, app)
    window.components_panel.select_designator("U1")
    window._component_selected("U1")
    selected = [m for m in window.canvas._markers if m.isSelected()]
    assert {m.key for m in selected} == {("U1", c) for c in range(1, 7)}
    assert window.inspector.title.text().startswith("U1")
    # canvas -> table
    marker = next(m for m in window.canvas._markers if m.kind == "placement" and m.key == ("R1", 3))
    window.canvas.scene().clearSelection()
    marker.setSelected(True)
    app.processEvents()
    assert window.components_panel.selected_designator() == "R1"


def test_components_table_filters_and_sorts_numerically(window, tmp_path, app):
    from PySide6.QtCore import Qt

    from panelimport.gui.panels.components import COL_SIDE, COL_X

    open_panel(window, tmp_path, app, sr_panel(n_parts=30))
    panel = window.components_panel
    panel.search.setText("C1")
    names = {panel.proxy.index(r, 0).data() for r in range(panel.proxy.rowCount())}
    assert "C1" in names and "U1" not in names
    panel.search.setText("")
    panel.side.setCurrentText("bottom")
    assert {panel.proxy.index(r, COL_SIDE).data() for r in range(panel.proxy.rowCount())} == {"bottom"}
    panel.side.setCurrentText("all")
    panel.table.sortByColumn(COL_X, Qt.AscendingOrder)
    xs = [panel.proxy.index(r, COL_X).data(panel.proxy.sortRole()) for r in range(panel.proxy.rowCount())]
    assert xs == sorted(xs)


def test_fiducials_after_confirm_and_fourth_refused(window, tmp_path, app, boxes):
    job = sr_panel(n_parts=10)
    job.steps["panel"].component("FID4", "FID1MM", 161.5, 82.5, part="FIDUCIAL")
    open_panel(window, tmp_path, app, job)
    window.accept_fiducial("FID1")
    assert boxes and "Confirm the panel first" in boxes[-1][2]
    window.confirm_panel()
    assert window.analysis.confirmed
    for name in ("FID1", "FID2", "FID3"):
        window.accept_fiducial(name)
    assert [f.name for f in window.analysis.fiducials] == ["FID1", "FID2", "FID3"]
    window.accept_fiducial("FID4")
    assert boxes[-1][0] == "warning" and "At most 3" in boxes[-1][2]
    assert [f.name for f in window.analysis.fiducials] == ["FID1", "FID2", "FID3"]
    # Clicking a picked fiducial on the canvas removes it.
    window._on_picked("fiducial_click", ("FID2",))
    assert [f.name for f in window.analysis.fiducials] == ["FID1", "FID3"]
    numbered = {m.key[0]: m.selected_number for m in window.canvas._markers if m.kind == "fiducial"}
    assert numbered["FID1"] == 1 and numbered["FID3"] == 2 and numbered["FID2"] is None


def test_undo_redo_of_edits(window, tmp_path, app):
    open_panel(window, tmp_path, app)
    stack = window.controller.undo_stack
    window.controller.apply("Numbering", numbering_first="upper-left")
    assert window.analysis.numbering.first == "upper-left"
    first_circuit = window.analysis.circuits[0]
    assert first_circuit.dy == 0 and first_circuit.center[1] > 40
    window.controller.apply("Map part number", part_number_attribute="PART_NUMBER")
    assert next(p for p in window.analysis.placements if p.designator == "C1").part_number == "D-1001"
    stack.undo()
    assert next(p for p in window.analysis.placements if p.designator == "C1").part_number == ""
    stack.undo()
    assert window.analysis.numbering.first == "lower-left"
    stack.redo()
    assert window.analysis.numbering.first == "upper-left"
    assert window.circuits_panel.first.currentText() == "upper-left"


def test_warnings_block_confirm_until_acknowledged(window, tmp_path, app):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 3, 1)
    pan.step_repeat("pcb", 5.7, 43.5, 52, 0, 3, 1)
    open_panel(window, tmp_path, app, job)
    assert not window.summary.confirm_btn.isEnabled()
    assert "acknowledged" in window.summary.status.text()
    warning = next(i for i in window.analysis.issues if i.code == "nonuniform_grid")
    window.acknowledge([warning])
    assert window.summary.confirm_btn.isEnabled()
    window.unacknowledge([warning])
    assert not window.summary.confirm_btn.isEnabled()


def test_panel_level_confirmation_from_issue_list(window, tmp_path, app):
    job = sr_panel()
    job.flatten("panel")
    src = job.write_tgz(tmp_path / "flat.tgz")
    window.open_job(OdbJob(src), Decisions(panel_step="panel"))
    designators = sorted(i.designator for i in window.analysis.issues if i.code == "copy_count")
    assert designators == ["FID1", "FID2", "FID3"]
    window.confirm_panel_level(designators)
    assert not [i for i in window.analysis.issues if i.code == "copy_count"]
    assert window.summary.confirm_btn.isEnabled()


def test_confirm_save_and_reopen(window, tmp_path, app, monkeypatch):
    open_panel(window, tmp_path, app)
    window.confirm_panel()
    for name in ("FID1", "FID2", "FID3"):
        window.accept_fiducial(name)
    target = tmp_path / "Panel_ODB.panel.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_project()
    assert target.exists() and window.controller.undo_stack.isClean()
    saved = load_project(target)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    window.open_project()
    assert window.analysis.confirmed
    assert window.analysis.to_project(target) == saved
    assert [f.name for f in window.analysis.fiducials] == ["FID1", "FID2", "FID3"]


def test_export_components_csv(window, tmp_path, app, boxes, monkeypatch):
    import csv

    from panelimport.gui.panels.components import COLUMNS, NUMERIC

    asked = []

    def dialog(parent, title, default, *args, **kwargs):
        asked.append(default)
        return str(tmp_path / "out" / "parts"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", dialog)
    assert not window.act_export_components.isEnabled()
    src = open_panel(window, tmp_path, app)
    window.components_panel.search.setText("C1")  # the file has every component, not only the rows shown
    assert window.act_export_components.isEnabled()
    window.act_export_components.trigger()
    assert asked == [str(src.with_name("Panel_ODB.components.csv"))]
    assert boxes and boxes[-1][:2] == ("warning", "Export components")  # the folder does not exist
    (tmp_path / "out").mkdir()
    window.act_export_components.trigger()
    assert window.statusBar().currentMessage() == f"Exported 23 components to {tmp_path / 'out' / 'parts'}.csv"
    with open(tmp_path / "out" / "parts.csv", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == COLUMNS and len(rows) == 24
    # Each row is the table's row; numbers are not cut to the three decimals shown.
    model = window.components_panel.model
    table = {model.index(r, 0).data(): [model.index(r, c).data() for c in range(len(COLUMNS))] for r in range(model.rowCount())}
    for row in rows[1:]:
        shown = table[row[0]]
        for col, (cell, text) in enumerate(zip(row, shown)):
            assert (f"{float(cell):.3f}" if col in NUMERIC else cell) == text


def test_export_components_from_a_project_without_its_source(window, tmp_path, app, monkeypatch):
    src = open_panel(window, tmp_path, app)
    window.confirm_panel()
    target = tmp_path / "Saved.panel.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_project()
    src.unlink()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    window.open_project()
    assert window.controller.read_only and window.act_export_components.isEnabled()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda parent, title, default, *a, **k: (default, ""))
    window.act_export_components.trigger()
    exported = tmp_path / "Saved.components.csv"  # named after the project
    assert len(exported.read_text(encoding="utf-8-sig").splitlines()) == 24


def test_measure_tool(window, tmp_path, app):
    open_panel(window, tmp_path, app)
    results = []
    window.canvas.measured.connect(lambda dx, dy, d: results.append((dx, dy, d)))
    window.act_measure.trigger()
    a = window.analysis
    u1 = next(p for p in a.placements if p.designator == "U1")
    p1 = a.circuit_position(u1, a.circuits[0])
    p2 = a.circuit_position(u1, a.circuits[1])
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    for x, y in (p1[:2], p2[:2]):
        window.canvas.centerOn(x, y)
        app.processEvents()
        vp = window.canvas.mapFromScene(QPointF(x, y))
        ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(vp), QPointF(vp), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        window.canvas.mousePressEvent(ev)
    assert results and results[-1][0] == pytest.approx(52.0, abs=1e-6) and results[-1][1] == pytest.approx(0, abs=1e-6)


def test_view_from_bottom_mirrors_display_only(window, tmp_path, app):
    open_panel(window, tmp_path, app)
    before = window.canvas.transform().m11()
    window.act_bottom.trigger()
    assert window.canvas.transform().m11() == pytest.approx(-before)
    assert window.summary.summary.text().startswith("6 circuits")


def test_status_bar_shows_circuit_relative_coordinates(window, tmp_path, app):
    open_panel(window, tmp_path, app)
    window._on_cursor(5 + 52 + 10, 5 + 3)
    assert "Circuit 2: X   10.000  Y    3.000" in window.coord_label.text()


def test_layout_is_remembered(app, tmp_path, boxes):
    from panelimport.gui.main_window import MainWindow

    ini = str(tmp_path / "gui.ini")
    w = MainWindow(Settings(), QSettings(ini, QSettings.IniFormat))
    w.show()
    w._toggle_layer("copper_top", False)
    from panelimport.app import dispose

    dispose(w)
    w2 = MainWindow(Settings(), QSettings(ini, QSettings.IniFormat))
    assert w2.canvas.visible["copper_top"] is False
    assert QSettings(ini, QSettings.IniFormat).value("window/state") is not None
    dispose(w2)


def test_windows_show_the_pcb_icon(window):
    from pathlib import Path

    from PySide6.QtGui import QIcon

    pcb = QIcon(str(Path(__file__).parents[1] / "packaging" / "pcb.ico"))
    assert not pcb.isNull()
    assert window.windowIcon().pixmap(32).toImage() == pcb.pixmap(32).toImage()


def test_single_board_flow(window, tmp_path, app):
    from panelimport.model.panel import SingleBoardSetup
    from tests.test_single_board import single_board_job

    src = single_board_job().write_folder(tmp_path)
    window.open_job(OdbJob(src), Decisions())
    assert window.summary.single_btn.isVisible() and not window.summary.confirm_btn.isEnabled()
    window.controller.apply(
        "Single-board setup",
        single_board=SingleBoardSetup(cols=2, rows=1, pitch_x=52, origin_x=5, origin_y=5, panel_width=110, panel_height=46),
    )
    assert window.summary.summary.text() == "2 circuits, 2 × 1, pitch 52.000 × 0.000 mm, from manual entry"
    assert window.summary.confirm_btn.isEnabled()


@pytest.mark.slow
def test_big_panel_loads_and_pans_quickly(window, tmp_path, app):
    job = sr_panel(nx=4, ny=2, dx=102, dy=77, board_w=100, board_h=75, n_parts=250)
    add_copper(job.steps["pcb"], 6000, seed=1)
    src = job.write_tgz(tmp_path / "big.tgz")
    t0 = time.perf_counter()
    window.open_job(OdbJob(src), Decisions())
    app.processEvents()
    load = time.perf_counter() - t0
    assert len(window.analysis.circuits) * len(window.analysis.placements) == 2000
    assert load < 6.0, f"load took {load:.2f} s"
    window.canvas.zoom_to(150, 100, 60)
    app.processEvents()
    frames = []
    bar = window.canvas.verticalScrollBar()
    for _ in range(30):
        t = time.perf_counter()
        bar.setValue(bar.value() + 20)
        app.processEvents()
        frames.append(time.perf_counter() - t)
    frames.sort()
    assert frames[len(frames) // 2] < 0.05, f"median pan frame {frames[len(frames) // 2] * 1000:.0f} ms"
