"""Offscreen GUI tests of the component database window: the list, the editor, unsaved
changes and saving (with a library in memory; one test saves to a real Access file)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from panelimport.app import dispose  # noqa: E402
from panelimport.gui import database_window as dw  # noqa: E402
from panelimport.gui import theme  # noqa: E402
from panelimport.gui.database_window import COLUMNS, PANEL, TABS, ComponentDatabaseWindow, ComponentEditor  # noqa: E402
from panelimport.gui.main_window import MainWindow  # noqa: E402
from panelimport.io.compodb import DatabaseError  # noqa: E402
from panelimport.io.compolib import DatabaseInUse, SaveResult  # noqa: E402
from panelimport.model.library import ADDED, DELETED, DESCRIPTION, EDITED, FIELD, NAME, Changes  # noqa: E402
from panelimport.settings import DatabaseSettings, Settings  # noqa: E402
from tests.synthetic import mdb  # noqa: E402

MDB = r"C:\ComponentDatabase\Data\DETEX_New.mdb"
COL = {key: i for i, (_title, key) in enumerate(COLUMNS)}


@pytest.fixture
def database(monkeypatch):
    """Stand-ins for the database: what reading gives, the saves asked for, who has it open."""
    state = {"library": mdb.sample_library, "saves": [], "save": None, "holders": [], "reads": 0}

    def read(path):
        state["reads"] += 1
        result = state["library"]()
        if isinstance(result, Exception):
            raise result
        return result

    def save(path, library, changes):
        state["saves"].append((path, library, Changes(dict(changes.updates), dict(changes.added), set(changes.deleted))))
        if isinstance(state["save"], Exception):
            raise state["save"]
        return SaveResult(backup=dw.Path(MDB).parent / "PanelImporter backups" / "DETEX_New 2026-11-16 100200.mdb",
                          summary=changes.summary())  # fmt: skip

    monkeypatch.setattr(dw, "read_library", read)
    monkeypatch.setattr(dw, "save_changes", save)
    monkeypatch.setattr(dw, "lock_holders", lambda path: state["holders"])
    return state


@pytest.fixture
def win(app, tmp_path, boxes, database):
    w = ComponentDatabaseWindow(MDB, QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat))
    w.show()
    app.processEvents()
    yield w
    w.changes.clear()
    dispose(w)


def _cell(win, name: str, key: str, role=Qt.DisplayRole):
    row = next(i for i, c in enumerate(win.model.rows) if c.name == name)
    return win.model.data(win.model.index(row, COL[key]), role)


def _shown_names(win) -> list[str]:
    return [win.proxy.index(r, 0).data() for r in range(win.proxy.rowCount())]


def _fill(monkeypatch, fill):
    """Run ``fill(dialog)`` instead of showing the editor, then accept it."""

    def run(dlg):
        fill(dlg)
        dlg.accept()
        return dlg.result()

    monkeypatch.setattr(ComponentEditor, "exec", run)


# ---------------------------------------------------------------------- the list
def test_lists_the_components_like_the_juki_list(win):
    assert win.windowTitle() == f"Component database — {MDB}" and win.count_label.text() == "4 components"
    assert _shown_names(win) == ["D-100", "Q-300", "R-400", "U-200"]
    row = [_cell(win, "D-100", key) for _title, key in COLUMNS]
    assert row == [
        "D-100", "DIODE, SCHOTTKY, 60V 5A", "Chip", "Chip component", "Tape", "12mm emboss 8 mm (8 × 1)", "L(504)",
        "Layer 4", "If possible", "4.814", "3.584", "0.0002", "", "",
    ]  # fmt: skip
    assert [_cell(win, "U-200", key) for key in ("Compo.PkgClassID", "Feeder.FdrTypeID", "feeder", "centering")] == [
        "SOP", "Stick", "MBF44 SOIC", "L(506)",
    ]  # fmt: skip
    assert "Read 4 components from a copy" in win.statusBar().currentMessage()
    assert not win.act_save.isEnabled() and not win.act_edit.isEnabled()

    win.view.sortByColumn(COL["Compo.Width"], Qt.DescendingOrder)  # numbers sort as numbers
    assert _shown_names(win) == ["U-200", "D-100", "Q-300", "R-400"]
    win.filter.setText("sop")
    assert _shown_names(win) == ["U-200"] and win.count_label.text() == "4 components, 1 shown"
    win.filter.setText("0805")  # any text of the row
    assert _shown_names(win) == ["R-400"]


def test_says_who_has_the_database_open(win, database):
    assert win.lock_label.text() == ""
    database["holders"] = ["WIN10 (justware)"]
    win._update_lock()
    assert win.lock_label.text() == "Open in WIN10 (justware): changes can be saved once it is closed there"


def test_a_database_that_cannot_be_read(app, tmp_path, boxes, database):
    database["library"] = lambda: DatabaseError("The component database X was not found")
    w = ComponentDatabaseWindow(MDB, QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat))
    assert boxes[-1] == ("warning", "Component database", "The component database X was not found")
    assert w.library is None and w.count_label.text() == "No database open" and w.windowTitle() == "Component database"
    dispose(w)


# ---------------------------------------------------------------------- the editor
def test_every_setting_is_in_the_editor_once():
    placed = [NAME, DESCRIPTION, "Compo.PkgType"]
    placed += [key for _title, keys in PANEL for key in keys]
    placed += [key for _title, groups in TABS for _group, keys in groups for key in keys]
    assert sorted(placed) == sorted(FIELD)


def test_editor_shows_what_is_stored_and_returns_what_changed(app):
    lib = mdb.sample_library()
    dlg = ComponentEditor(lib, lib.component(Changes(), 1))
    assert dlg.windowTitle() == "Component D-100"
    assert [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())] == [
        "Packaging style", "Laser centering", "Pick conditions", "Placement conditions", "Check",
    ]  # fmt: skip
    assert dlg.shown("Compo.Width") == pytest.approx(4.814) and dlg.widgets["Compo.Width"].suffix() == " mm"
    assert dlg.shown("Laser.LaserHeight") == pytest.approx(-1.165)  # negative, and not clamped
    assert dlg.widgets["LaserGx10.SpdXY"].currentText() == "Fast 2"
    assert dlg.widgets["Feeder.TapeTypeID"].currentText() == "12mm emboss"
    assert dlg.shown("Expansion.EtfPickPosAdjust") is True and dlg.shown("Expansion.Test") is False
    assert dlg.values() == {}  # nothing touched: nothing to write, not even 0 for a NULL

    # Read-only here: the type, the packaging, the vacuum; and what belongs to a switch that is off.
    for key in ("Compo.PkgClassID", "Feeder.FdrTypeID", "LaserGx10.PumpVacuum", "Compo.UseVision"):
        assert not dlg.widgets[key].isEnabled(), key
    assert dlg.widgets["Compo.PkgType"].isReadOnly() and not dlg.widgets[NAME].isReadOnly()
    assert not dlg.widgets["Compo.PackageWidth"].isEnabled() and not dlg.widgets["LaserGx10.PickZ2StepDown"].isEnabled()
    dlg.set_shown("Compo.UsePackage", True)
    dlg.set_shown("LaserGx10.PickZ2StepUse", True)
    assert dlg.widgets["Compo.PackageWidth"].isEnabled() and dlg.widgets["LaserGx10.PickZ2StepDown"].isEnabled()
    assert not dlg.widgets["LaserGx10.PlaceZ2StepDown"].isEnabled()

    dlg.set_shown("Compo.PackageWidth", 4.9)
    dlg.set_shown(DESCRIPTION, " DIODE 60V ")
    dlg.set_shown("Compo.Width", 4.8151)
    dlg.set_shown("Feeder.TapeAngle", 90)
    dlg.set_shown("LaserGx10.SpdXY", 0)
    dlg.set_shown("Expansion.Test", True)
    dlg.set_shown("Inspection.ChipStandCheck", 1)
    assert dlg.values() == {
        DESCRIPTION: "DIODE 60V", "Compo.Width": 48151, "Compo.UsePackage": 1, "Compo.PackageWidth": 49000,
        "Feeder.TapeAngle": 7200, "LaserGx10.SpdXY": 0, "LaserGx10.PickZ2StepUse": 1, "Expansion.Test": True,
        "Inspection.ChipStandCheck": 1,
    }  # fmt: skip
    with pytest.raises(ValueError, match="XY has no option 3"):  # only confirmed or used options
        dlg.set_shown("LaserGx10.SpdXY", 3)
    dispose(dlg)


def test_editor_of_a_stick_component(app):
    lib = mdb.sample_library()
    dlg = ComponentEditor(lib, lib.component(Changes(), 2))  # U-200
    for key in ("Feeder.TapeTypeID", "Feeder.Pitch", "Feeder.TapeAngle", "Feeder.SpliceSensorUse"):
        assert not dlg.widgets[key].isEnabled(), key  # tape settings do not apply
    assert dlg.widgets["Feeder.TapeTypeID"].currentText() == "" and dlg.shown("Feeder.TapeTypeID") is None  # NULL
    assert dlg.widgets["Feeder.StickChangerType"].currentText() == "MBF44 SOIC"
    assert dlg.widgets["LaserGx10.CompoShape"].currentText() == "Code 4"  # used, name not known
    assert dlg.widgets["Laser.LaserAlgo"].currentText() == "Algorithm 2 (unconfirmed)"
    assert dlg.values() == {}
    dispose(dlg)


def test_editor_checks_the_name(app, boxes):
    lib = mdb.sample_library()
    dlg = ComponentEditor(lib, lib.component(Changes(), 1), lambda name: lib.name_taken(Changes(), name, but=1))
    dlg.set_shown(NAME, " u-200 ")
    dlg.accept()
    assert boxes[-1] == ("warning", "Component", "There already is a component named u-200.")
    dlg.set_shown(NAME, "  ")
    dlg.accept()
    assert boxes[-1][2] == "The component needs a name." and dlg.result() != QDialog.Accepted
    dlg.set_shown(NAME, "d-100")  # its own name in another case
    dlg.accept()
    assert dlg.result() == QDialog.Accepted and dlg.values() == {NAME: "d-100"}
    dispose(dlg)


# ---------------------------------------------------------------------- unsaved changes
def test_edit_marks_the_row_until_it_is_saved(win, monkeypatch):
    win.select([1])
    assert win.act_edit.isEnabled() and win.act_copy.isEnabled() and not win.act_revert.isEnabled()
    _fill(monkeypatch, lambda dlg: (dlg.set_shown("Compo.Width", 4.9), dlg.set_shown("LaserGx10.NozzleNo", 506)))
    win.edit_selected()
    assert win.changes.updates == {1: {"Compo.Width": 49000, "LaserGx10.NozzleNo": 506}}
    assert (_cell(win, "D-100", "Compo.Width"), _cell(win, "D-100", "centering"), _cell(win, "D-100", "state")) == (
        "4.9", "L(506)", EDITED,
    )  # fmt: skip
    assert _cell(win, "D-100", "Compo.Width", Qt.ForegroundRole) == theme.EDITED
    assert _cell(win, "D-100", "centering", Qt.ForegroundRole) == theme.EDITED
    assert _cell(win, "D-100", "Compo.Length", Qt.ForegroundRole) is None  # only what changed
    assert _cell(win, "D-100", "Compo.Width", Qt.ToolTipRole) == "In the database: 4.814"
    assert win.windowTitle().endswith(" *") and win.count_label.text() == "4 components · unsaved: 1 edited"
    assert win.act_save.isEnabled() and win.act_revert.isEnabled() and [c.name for c in win.selected()] == ["D-100"]

    # Editing again starts from the unsaved values; setting one back drops it.
    _fill(monkeypatch, lambda dlg: dlg.set_shown("Compo.Width", 4.814) if dlg.shown("Compo.Width") == 4.9 else None)
    win.edit_selected()
    assert win.changes.updates == {1: {"LaserGx10.NozzleNo": 506}}
    win.revert_selected()
    assert not win.changes and not win.windowTitle().endswith("*") and _cell(win, "D-100", "state") == ""


def test_new_from_copy_delete_and_revert(win, boxes):
    win.select([1])
    assert win.new_copy("r-400") is None and boxes[-1][2] == "There already is a component named r-400."
    new = win.new_copy(" D-101 ")
    assert new == -1 and [c.name for c in win.selected()] == ["D-101"]
    assert (_cell(win, "D-101", "state"), _cell(win, "D-101", "Compo.Width")) == (ADDED, "4.814")
    assert _cell(win, "D-101", NAME, Qt.ForegroundRole) == theme.ADDED
    assert win.count_label.text() == "5 components · unsaved: 1 new"

    win.select([2, new])
    win.delete_selected()  # the new one just goes, U-200 is struck through until saved
    assert [c.name for c in win.model.rows] == ["D-100", "Q-300", "R-400", "U-200"]
    assert _cell(win, "U-200", "state") == DELETED and _cell(win, "U-200", NAME, Qt.FontRole).strikeOut()
    assert win.count_label.text() == "3 components · unsaved: 1 deleted"
    win.select([2])
    assert not win.act_edit.isEnabled() and not win.act_delete.isEnabled() and win.act_revert.isEnabled()
    win.revert_selected()
    assert not win.changes

    # Components with vision data are neither copied nor deleted here.
    win.select([3])
    assert win.new_copy("Q-301") is None and "cannot copy" in boxes[-1][2]
    win.delete_selected()
    assert boxes[-1][0] == "information" and boxes[-1][2].startswith("Q-300: has data this program cannot delete")
    assert not win.changes


def test_new_from_copy_asks_for_the_name_and_opens_the_editor(win, monkeypatch):
    monkeypatch.setattr(dw.QInputDialog, "getText", lambda *args, **kw: ("D-102", True))
    _fill(monkeypatch, lambda dlg: (dlg.set_shown(DESCRIPTION, "DIODE 100V"), dlg.set_shown("Compo.Height", 1.2)))
    win.select([1])
    new = win.new_copy()
    assert win.changes.added == {new: 1}
    assert win.changes.updates[new] == {NAME: "D-102", DESCRIPTION: "DIODE 100V", "Compo.Height": 12000}


# ---------------------------------------------------------------------- saving
def test_save_writes_all_changes_and_reads_again(win, database, boxes):
    seen = []
    win.saved.connect(seen.append)
    win.apply(1, {"Compo.Width": 49000})
    win.select([1])
    new = win.new_copy("D-101")
    win.library.delete(win.changes, 2)
    library = win.library
    assert win.save() is True
    path, saved_library, changes = database["saves"][-1]
    assert (path, saved_library) == (MDB, library)
    assert changes == Changes({1: {"Compo.Width": 49000}, new: {NAME: "D-101", "Compo.Width": 49000}}, {new: 1}, {2})
    asked = boxes[-1]
    assert asked[:2] == ("question", "Save to database") and "(1 edited, 1 new, 1 deleted)" in asked[2]
    assert "copied to “PanelImporter backups”" in asked[2] and "only written while no program has it open" in asked[2]
    assert not win.changes and database["reads"] == 2 and seen == [MDB]
    assert "Saved (1 edited, 1 new, 1 deleted); the database as it was is in" in win.statusBar().currentMessage()
    assert not win.act_save.isEnabled() and win.save() is False  # nothing left to save


def test_save_refused_keeps_the_changes(win, database, boxes, monkeypatch):
    win.apply(1, {"Compo.Width": 49000})
    database["save"] = DatabaseInUse("DETEX_New.mdb is open in another program (WIN10 (justware)). Nothing was written.")
    assert win.save() is False
    assert boxes[-1] == ("warning", "Save to database", str(database["save"]))
    assert win.changes.updates == {1: {"Compo.Width": 49000}} and database["reads"] == 1

    # Not confirmed: not saved.  Problems are said before asking.
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.No)
    assert win.save() is False and len(database["saves"]) == 1
    win.apply(1, {NAME: "U-200"})
    assert win.save() is False and boxes[-1] == ("warning", "Save to database", "Two components are named U-200")


def test_closing_or_reloading_asks_about_unsaved_changes(win, database, monkeypatch, boxes):
    win.apply(1, {"Compo.Width": 49000})
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.No)
    win.reload()
    assert win.changes and database["reads"] == 1
    assert win.close() is False and win.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.Yes)
    win.reload()
    assert not win.changes and database["reads"] == 2
    win.apply(1, {"Compo.Width": 49000})
    assert win.close() is True and not win.changes


# ---------------------------------------------------------------------- from the main window
def test_main_window_opens_the_configured_database(app, tmp_path, boxes, database, monkeypatch):
    w = MainWindow(Settings(), QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat), DatabaseSettings(MDB))
    w.show()
    assert w.act_database.text() == "&Component database…" and w.database_window is None
    w.browse_database()
    db = w.database_window
    assert db.isVisible() and db.path == MDB and len(db.model.rows) == 4
    w.browse_database()  # the same window again
    assert w.database_window is db and database["reads"] == 1

    # Saving there makes what the main window read from the database out of date.
    w._library = object()
    db.apply(1, {"Compo.Width": 49000})
    assert db.save() and w._library is None
    # The main window does not close over unsaved changes there.
    db.apply(1, {"Compo.Width": 49500})
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kw: QMessageBox.No)
    assert w.close() is False
    db.changes.clear()
    w.controller.undo_stack.setClean()
    dispose(w)


def test_main_window_without_a_database(window, database):
    window.browse_database()
    assert window.database_window.library is None and database["reads"] == 0
    assert window.database_window.count_label.text() == "No database open"


@pytest.mark.skipif(bool(mdb.unavailable()), reason=mdb.unavailable())
def test_edit_and_save_a_real_database(app, tmp_path, boxes):
    live = mdb.make_database(tmp_path / "DETEX_New.mdb")
    w = ComponentDatabaseWindow(str(live), QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat))
    assert [c.name for c in w.model.rows] == ["D-100", "Q-300", "R-400", "U-200"]
    dlg = w.editor(1)
    dlg.set_shown("Compo.Width", 4.9)
    dlg.set_shown("LaserGx10.SpdXY", 0)
    w.apply(1, dlg.values())
    dispose(dlg)
    w.select([1])
    w.new_copy("D-101")
    assert w.save() is True and boxes[-1][0] == "question"
    assert [c.name for c in w.model.rows] == ["D-100", "D-101", "Q-300", "R-400", "U-200"] and not w.changes
    for name in ("D-100", "D-101"):
        assert (_cell(w, name, "Compo.Width"), _cell(w, name, "state")) == ("4.9", "")
    assert w.library.record(1).values["LaserGx10.SpdXY"] == 0
    assert len(list((tmp_path / "PanelImporter backups").iterdir())) == 1
    dispose(w)
