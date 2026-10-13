"""Import, settings and single-board dialogs (offscreen)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QSettings  # noqa: E402

from panelimport.app import dispose  # noqa: E402
from panelimport.settings import Settings  # noqa: E402
from tests.synthetic.odbgen import sr_panel  # noqa: E402


@pytest.fixture(scope="module")
def app():
    from panelimport.app import create_app

    return create_app([])


def test_import_dialog_detects_and_corrects_roles(app, tmp_path):
    from panelimport.gui.import_dialog import ImportDialog

    src = sr_panel().write_tgz(tmp_path / "p.tgz")
    qs = QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat)
    dlg = ImportDialog(settings=qs)
    assert dlg.load(str(src))
    panel, board = dlg.step_roles()
    assert (panel.lower(), board.lower()) == ("panel", "pcb")
    roles = dlg.layer_roles()
    assert roles["paste_top"].lower() == "top_paste" and roles["copper_bottom"].lower() == "bottom_copper"
    # Correct a role: assigning "Top paste" to another layer takes it from the first.
    combo = dict(dlg._layer_combos)["BOTTOM_PASTE"]
    combo.setCurrentIndex(combo.findData("paste_top"))
    roles = dlg.layer_roles()
    assert roles["paste_top"] == "BOTTOM_PASTE" and roles["paste_bottom"] == ""
    # Only one panel step.
    step_combo = dict(dlg._step_combos)["PCB"]
    step_combo.setCurrentText("Panel")
    assert dlg.step_roles()[0] == "PCB"
    assert dict(dlg._step_combos)["PANEL"].currentText() == "—"
    # The last location is remembered.
    assert str(src) == qs.value("import/last_path")
    dlg2 = ImportDialog(settings=qs)
    assert dlg2.path.text() == str(src)
    dispose(dlg)
    dispose(dlg2)


def test_import_dialog_reports_bad_path(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from panelimport.gui.import_dialog import ImportDialog

    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    dlg = ImportDialog(settings=QSettings(str(tmp_path / "gui.ini"), QSettings.IniFormat))
    assert not dlg.load(str(tmp_path / "missing"))
    assert seen and "does not exist" in seen[0]
    dispose(dlg)


def test_settings_dialog_roundtrip(app):
    from panelimport.gui.settings_dialog import SettingsDialog

    s = Settings()
    s.tolerances.centroid_on_pads = 0.3
    s.fiducials.patterns = ["FID*", "FD*"]
    dlg = SettingsDialog(s)
    dlg.copy_suffix.setText(r"_(\d+)$")
    dlg.corner.setCurrentText("upper-left")
    dlg._accept()
    out = dlg.settings
    assert out.tolerances.centroid_on_pads == pytest.approx(0.3)
    assert out.fiducials.patterns == ["FID*", "FD*"]
    assert out.copy_suffix_regex == r"_(\d+)$" and out.circuit1_corner == "upper-left"
    dispose(dlg)


def test_single_board_dialog(app):
    from panelimport.gui.single_board_dialog import SingleBoardDialog

    dlg = SingleBoardDialog()
    dlg.cols.setValue(3)
    dlg.rows.setValue(2)
    dlg.pitch_x.setValue(52)
    dlg.pitch_y.setValue(38.5)
    dlg.origin_x.setValue(5)
    dlg.fiducials.setPlainText("FID1, 2.5, 2.5\nFID2, 161.5, 2.5")
    dlg._accept()
    s = dlg.result_setup
    assert (s.cols, s.rows, s.pitch_x, s.pitch_y, s.origin_x) == (3, 2, 52, 38.5, 5)
    assert [f.name for f in s.fiducials] == ["FID1", "FID2"]
    assert len(s.offsets_list()) == 6
    dispose(dlg)
