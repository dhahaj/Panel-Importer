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
            # An unknown size is empty in the file and "-" in the table.
            assert ((f"{float(cell):.3f}" if cell else "-") if col in NUMERIC else cell) == text


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


def test_layer_colours_change_in_place(window, tmp_path, app):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsSimpleTextItem

    from panelimport.gui import theme
    from panelimport.gui.canvas import TINT, FeatureLayerItem, MarkerItem

    job = sr_panel(n_parts=20)
    add_copper(job.steps["pcb"], 50, seed=1)
    open_panel(window, tmp_path, app, job)
    canvas = window.canvas
    canvas.select_designator("U1", 1)
    selected = canvas.scene().selectedItems()
    count = len(canvas.scene().items())

    def items(layer, tint=None):
        return [i for i in canvas.layers[layer] if i.data(TINT)[0] == (tint or layer)]

    copper = QColor(255, 0, 0, 90)
    window._set_layer_color("copper_top", copper)
    assert items("copper_top") and all(isinstance(i, FeatureLayerItem) and i.color == copper for i in items("copper_top"))
    window._set_layer_color("centroids_top", QColor("#123456"))
    assert all(m.color == QColor("#123456") for m in items("centroids_top"))
    window._set_layer_color("circuit_outlines", QColor("#00ff00"))
    outlines = [i for i in items("circuit_outlines") if isinstance(i, QGraphicsPathItem)]
    numbers = [i for i in items("circuit_outlines") if isinstance(i, QGraphicsSimpleTextItem)]
    assert len(outlines) == len(numbers) == 6
    assert all(i.pen().color() == QColor("#00ff00") for i in outlines)
    assert all(i.brush().color() == QColor("#00ff00") for i in numbers)
    # Bottom bodies follow the bottom centroid colour, faded; top bodies keep theirs.
    window._set_layer_color("centroids_bottom", QColor("#ff8800"))
    bottom = items("bodies", "centroids_bottom")
    assert bottom and all(i.pen().color() == QColor(255, 136, 0, 110) for i in bottom)
    assert all(i.pen().color() == theme.STYLE["bodies"].color for i in items("bodies"))
    # Circuit-level fiducials stay grey whatever the fiducial colour.
    window._set_layer_color("fiducials", QColor("#0000ff"))
    assert all(m.color == QColor("#0000ff") for m in canvas.layers["fiducials"])

    def painted_blue(selectable: bool) -> bool:
        from PySide6.QtGui import QImage, QPainter

        m = MarkerItem("fiducial", ("F",), QColor("#0000ff"), "")
        m.selectable_fiducial = selectable
        img = QImage(40, 40, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        p.translate(20, 20)
        m.paint(p, None)
        p.end()
        px = [img.pixelColor(x, y) for x in range(40) for y in range(40)]
        return any(c.alpha() and c.blue() > c.red() + 60 for c in px)

    assert painted_blue(True) and not painted_blue(False)
    window._set_layer_color("labels", QColor("#ff00ff"))
    assert MarkerItem.label_color == QColor("#ff00ff")
    # Nothing was rebuilt: same items, same selection.
    assert len(canvas.scene().items()) == count and canvas.scene().selectedItems() == selected
    # A rebuild (any edit) keeps the chosen colours.
    canvas.set_analysis(window.analysis, keep_view=True)
    assert all(i.color == copper for i in canvas.layers["copper_top"])


def test_layers_panel_picks_and_resets_colours(window, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    from panelimport.gui import theme

    panel = window.layers_panel
    emitted = []
    panel.colorChanged.connect(lambda key, color: emitted.append((key, color)))
    assert not panel.color_button.isEnabled() and not panel.reset_button.isEnabled()
    picked = QColor(10, 20, 30, 200)
    asked = []

    def get_color(initial, parent, title, options):
        asked.append((QColor(initial), title, options))
        return picked

    monkeypatch.setattr(QColorDialog, "getColor", get_color)
    panel.list.setCurrentRow([s.key for s in theme.LAYERS].index("paste_top"))
    assert panel.current_key() == "paste_top" and panel.color_button.isEnabled()
    panel.color_button.click()
    assert asked == [(theme.STYLE["paste_top"].color, "Top paste colour", QColorDialog.ShowAlphaChannel)]
    assert emitted == [("paste_top", picked)] and window.canvas.colors["paste_top"] == picked
    assert panel.reset_button.isEnabled()
    item = panel.list.currentItem()
    assert item.icon().pixmap(14).toImage().pixelColor(7, 7) == QColor(10, 20, 30)  # swatch is opaque
    # Cancelling the dialog changes nothing.
    monkeypatch.setattr(QColorDialog, "getColor", lambda *a: QColor())
    panel.list.itemActivated.emit(item)
    assert len(emitted) == 1
    panel.reset_button.click()
    assert emitted[-1] == ("paste_top", theme.STYLE["paste_top"].color)
    assert window.canvas.colors["paste_top"] == theme.STYLE["paste_top"].color
    assert not panel.reset_button.isEnabled() and len(emitted) == 2  # only changed layers are reset


def test_layer_colours_are_remembered(app, tmp_path, boxes):
    from PySide6.QtGui import QColor

    from panelimport.app import dispose
    from panelimport.gui import theme
    from panelimport.gui.main_window import MainWindow

    ini = str(tmp_path / "gui.ini")
    w = MainWindow(Settings(), QSettings(ini, QSettings.IniFormat))
    w._set_layer_color("copper_top", QColor(1, 2, 3, 40))
    w._set_layer_color("fiducials", QColor("#abcdef"))
    w._set_layer_color("fiducials", theme.STYLE["fiducials"].color)  # back to the default
    dispose(w)
    stored = QSettings(ini, QSettings.IniFormat)
    assert stored.value("layer_colors/copper_top") == "#28010203"
    assert stored.value("layer_colors/fiducials") is None
    stored.setValue("layer_colors/paste_top", "not a colour")
    stored.sync()
    w2 = MainWindow(Settings(), QSettings(ini, QSettings.IniFormat))
    assert w2.canvas.colors["copper_top"] == QColor(1, 2, 3, 40)
    assert w2.layers_panel.colors["copper_top"] == QColor(1, 2, 3, 40)
    assert w2.canvas.colors["fiducials"] == theme.STYLE["fiducials"].color
    assert w2.canvas.colors["paste_top"] == theme.STYLE["paste_top"].color
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
