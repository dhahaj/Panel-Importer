"""Offscreen GUI tests of the component database: the settings section, the read on import,
Update from database, the From database… picker, and how the tables show it."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

from panelimport import session as session_module  # noqa: E402
from panelimport.analysis import edits as E  # noqa: E402
from panelimport.app import dispose  # noqa: E402
from panelimport.gui import main_window as main_window_module  # noqa: E402
from panelimport.gui import theme  # noqa: E402
from panelimport.gui.component_dialog import ComponentDialog, DatabasePicker  # noqa: E402
from panelimport.gui.main_window import MainWindow  # noqa: E402
from panelimport.gui.panels.components import (  # noqa: E402
    COL_DATABASE,
    COL_DESCRIPTION,
    COL_PKG_TYPE,
    FIELD_COLUMNS,
)
from panelimport.gui.settings_dialog import SettingsDialog  # noqa: E402
from panelimport.io import compodb  # noqa: E402
from panelimport.io.compodb import DatabaseError  # noqa: E402
from panelimport.model.database import ComponentDatabase, DatabasePart  # noqa: E402
from panelimport.settings import DatabaseSettings, Settings  # noqa: E402
from tests.conftest import open_panel  # noqa: E402
from tests.test_gui_edits import _row  # noqa: E402

MDB = r"C:\ComponentDatabase\Data\DETEX.mdb"


def _db() -> ComponentDatabase:
    return ComponentDatabase(
        path=MDB,
        read_at="2026-11-14T10:02:00",
        parts=[
            DatabasePart("CAP-100N", "CAP CER 0.1UF 0603", "0603", 1.7, 0.9, 0.5),
            DatabasePart("CAP-22N", "CAP CER 22NF 0603", "0603", 1.6, 0.8, 0.45),
            DatabasePart("RES-10K", "RES 10K 0402", "0402", 1.0, 0.5, 0.35),
        ],
        whole=True,
    )


@pytest.fixture
def reads(monkeypatch):
    """Stand-in reads of the database: on import (session) and from the window."""
    calls: list[str] = []
    state = {"import": _db, "window": _db}

    def reader(where):
        def read(path):
            calls.append(where)
            result = state[where]()
            if isinstance(result, Exception):
                raise result
            return result

        return read

    monkeypatch.setattr(session_module, "read_database", reader("import"))
    monkeypatch.setattr(main_window_module, "read_database", reader("window"))
    return state, calls


@pytest.fixture
def db_window(app, tmp_path, boxes, reads):
    w = MainWindow(Settings(), QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat), DatabaseSettings(MDB))
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    yield w
    w.controller.undo_stack.setClean()
    dispose(w)


def test_settings_dialog_database_section(app, monkeypatch):
    dlg = SettingsDialog(Settings(), database=DatabaseSettings(MDB))
    assert dlg.database_path.text() == MDB
    monkeypatch.setattr(compodb, "read_database", lambda path: _db())
    dlg._test_database()
    assert dlg.database_result.text() == "3 components."

    def fail(path):
        raise DatabaseError(f"The component database {path} was not found")

    monkeypatch.setattr(compodb, "read_database", fail)
    dlg.database_path.setText(r"  D:\other.mdb ")
    dlg._test_database()
    assert dlg.database_result.text() == r"The component database D:\other.mdb was not found"
    dlg._accept()
    assert dlg.database == DatabaseSettings(r"D:\other.mdb")
    dispose(dlg)


def test_import_reads_the_database(db_window, tmp_path, app, reads):
    _state, calls = reads
    open_panel(db_window, tmp_path, app)
    a = db_window.analysis
    assert calls == ["import"] and a.decisions.component_database.whole
    assert "component database DETEX.mdb, read 2026-11-14 10:02:00" in db_window.statusBar().currentMessage()

    c1 = _row(db_window.components_panel, ("board", "C1"))  # CAP-100N, at 90°: never swapped
    width = c1[FIELD_COLUMNS["width"]]
    assert (width.text(), c1[FIELD_COLUMNS["length"]].text(), c1[FIELD_COLUMNS["height"]].text()) == (
        "1.700",
        "0.900",
        "0.500",
    )
    assert width.foreground().color() == theme.DATABASE and width.toolTip() == "From the component database; export: 1.600"
    assert (c1[COL_DESCRIPTION].text(), c1[COL_PKG_TYPE].text(), c1[COL_DATABASE].text()) == (
        "CAP CER 0.1UF 0603",
        "0603",
        "found",
    )
    c2 = _row(db_window.components_panel, ("board", "C2"))  # CAP-1U
    assert c2[COL_DATABASE].text() == "not found" and c2[FIELD_COLUMNS["width"]].toolTip() == ""
    assert "database DETEX.mdb" in db_window.components_panel.count.text()
    assert {i.code for i in a.issues} >= {"not_in_database"}

    db_window._component_selected("C1")
    table = db_window.inspector.table
    rows = [(table.item(r, 0).text(), table.item(r, 1).text()) for r in range(table.rowCount())]
    at = rows.index(("Component database", "found"))
    assert rows[at + 1 : at + 5] == [
        ("    description", "CAP CER 0.1UF 0603"),
        ("    Juki package", "0603"),
        ("    size (mm)", "1.7000 × 0.9000 × 0.5000"),
        ("Size in the program (mm)", "1.7000 × 0.9000 × 0.5000"),
    ]


def test_import_without_the_database(db_window, tmp_path, app, reads):
    state, _calls = reads
    state["import"] = lambda: DatabaseError("The component database was not found")
    open_panel(db_window, tmp_path, app)
    a = db_window.analysis
    assert a.decisions.component_database is None
    assert "database_unavailable" in {i.code for i in a.issues}
    assert _row(db_window.components_panel, ("board", "C1"))[COL_DATABASE].text() == ""


def test_update_from_database_is_one_undo_step(db_window, tmp_path, app, reads, boxes):
    state, calls = reads
    state["import"] = lambda: DatabaseError("The component database was not found")
    open_panel(db_window, tmp_path, app)
    assert db_window.act_update_database.isEnabled() and db_window.components_panel.act_database.isEnabled()

    db_window.components_panel.databaseUpdateRequested.emit()
    a = db_window.analysis
    assert calls == ["import", "window"] and a.decisions.component_database.whole
    assert "database_unavailable" not in {i.code for i in a.issues}
    assert db_window.controller.undo_stack.undoText() == "Update from component database"
    assert db_window.statusBar().currentMessage().endswith(": 2 of 8 components found")
    db_window.controller.undo_stack.undo()
    assert db_window.analysis.decisions.component_database is None

    # A failed read changes nothing and says why.
    state["window"] = lambda: DatabaseError("could not be opened as an Access database")
    db_window.update_database()
    assert boxes[-1] == ("warning", "Component database", "could not be opened as an Access database")
    assert db_window.controller.undo_stack.count() == 1  # only the undone update


def test_no_database_set(window, tmp_path, app, boxes):
    open_panel(window, tmp_path, app)
    assert not window.act_update_database.isEnabled() and not window.components_panel.act_database.isEnabled()
    window.update_database()
    assert boxes[-1][0] == "information" and "Settings" in boxes[-1][2]
    dlg = ComponentDialog(window, window.analysis, [("board", "C1")], database=window._picker_database())
    assert not dlg.pick_btn.isEnabled() and dlg.database_note.isHidden()
    dispose(dlg)


def test_settings_set_the_database(window, tmp_path, app, monkeypatch):
    open_panel(window, tmp_path, app)

    def fill(dlg):
        dlg.database_path.setText(MDB)
        dlg._accept()
        return QDialog.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fill)
    window.edit_settings()
    assert window.database == DatabaseSettings(MDB) and DatabaseSettings.load().path == MDB
    assert window.act_update_database.isEnabled() and window.components_panel.act_database.isEnabled()


def test_pick_the_part_number_from_the_database(db_window, tmp_path, app, reads, monkeypatch):
    state, calls = reads
    state["import"] = lambda: DatabaseError("The component database was not found")
    open_panel(db_window, tmp_path, app)

    def pick(dlg):
        assert dlg.search.text() == "CAP-100N" and dlg.chosen().name == "CAP-100N"  # starts at the current one
        dlg.search.setText("22nf")  # searches descriptions too
        assert dlg.count.text() == "1 of 3 components" and dlg.chosen().name == "CAP-22N"
        return QDialog.Accepted

    def fill(d):
        assert d.pick_btn.isEnabled()
        d._pick()
        assert d.part_number.text() == "CAP-22N" and d.picked is not None
        assert "CAP CER 22NF 0603; size 1.6 × 0.8 × 0.45 mm" in d.database_note.text()
        return QDialog.Accepted

    monkeypatch.setattr(DatabasePicker, "exec", pick)
    monkeypatch.setattr(ComponentDialog, "exec", fill)
    db_window.edit_components([("board", "C1")])
    a = db_window.analysis
    assert calls == ["import", "window"] and E.find_part(a, "board", "C1").part_number == "CAP-22N"
    assert a.decisions.component_database.whole
    assert _row(db_window.components_panel, ("board", "C1"))[COL_DESCRIPTION].text() == "CAP CER 22NF 0603"
    stack = db_window.controller.undo_stack
    assert stack.count() == 1 and stack.undoText() == "Edit C1"
    stack.undo()
    a = db_window.analysis
    assert a.decisions.component_database is None and E.find_part(a, "board", "C1").part_number == ""


def test_database_picker_search(app):
    db = _db()
    db.parts.append(DatabasePart("ARES-10K", "Array"))
    dlg = DatabasePicker(None, db, "res-10k")
    assert dlg.count.text() == "2 of 4 components" and dlg.chosen().name == "RES-10K"  # the exact match
    dlg.search.setText("CAP")
    assert dlg.count.text() == "2 of 4 components" and dlg.chosen().name == "CAP-22N"  # natural order
    dlg.search.setText("nothing")
    assert dlg.chosen() is None and not dlg.ok.isEnabled()
    dispose(dlg)
    # Nothing like the current part number: everything is shown.
    dlg = DatabasePicker(None, db, "D-1001")
    assert dlg.search.text() == "" and dlg.count.text() == "4 of 4 components"
    dispose(dlg)
