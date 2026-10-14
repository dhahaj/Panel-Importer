"""GUI: File → Export ISS… and File → Compare programs… (offscreen)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QFileDialog  # noqa: E402

from panelimport.gui.iss_dialogs import CompareDialog, ExportIssDialog  # noqa: E402
from panelimport.iss.reader import read_program  # noqa: E402
from panelimport.iss.settings import IssSettings  # noqa: E402
from panelimport.model.panel import ComponentEdit  # noqa: E402
from tests.conftest import open_panel  # noqa: E402
from tests.synthetic.projects import make_project  # noqa: E402

pytestmark = pytest.mark.gui
FIXTURES = Path(__file__).parent / "fixtures" / "iss"


def _write_on_exec(monkeypatch, seen: list) -> None:
    def exec_(dlg):
        seen.append(dlg)
        dlg._write()
        return dlg.result()

    monkeypatch.setattr(ExportIssDialog, "exec", exec_)


def _confirmed_top_panel(window, tmp_path, app) -> Path:
    src = open_panel(window, tmp_path, app)
    a = window.analysis
    # The synthetic board has one bottom part (C2); a program places one side only.
    window.controller.apply(
        "Remove C2", component_edits=[ComponentEdit("C2", removed=True, reason="other")], edit_frame=a.edit_frame
    )
    window.confirm_panel()
    for name in ("FID1", "FID2", "FID3"):
        window.accept_fiducial(name)
    app.processEvents()
    assert window.analysis.confirmed and len(window.analysis.fiducials) == 3
    return src


def test_export_iss_needs_a_confirmed_panel(window, tmp_path, app, monkeypatch):
    seen = []
    _write_on_exec(monkeypatch, seen)
    assert not window.act_export_iss.isEnabled() and window.act_compare.isEnabled()
    open_panel(window, tmp_path, app)
    assert not window.act_export_iss.isEnabled()
    window.export_iss()
    assert seen == []


def test_export_iss_writes_next_to_the_project(window, tmp_path, app, monkeypatch):
    seen = []
    _write_on_exec(monkeypatch, seen)
    src = _confirmed_top_panel(window, tmp_path, app)
    assert window.act_export_iss.isEnabled()
    window.act_export_iss.trigger()
    target = src.with_name("Panel_ODB.iss")
    assert seen and seen[0].prepared.can_write and target.exists()
    assert window.statusBar().currentMessage() == f"Wrote {target}"
    prog = read_program(target)
    assert prog.pwb_id == "Panel_ODB" and len(prog.circuits) == 6 and len(prog.fiducials) == 3
    assert "C2" not in {p.designator for p in prog.placements}


def test_export_iss_from_a_project_without_its_source(window, tmp_path, app, monkeypatch):
    seen = []
    _write_on_exec(monkeypatch, seen)
    src = _confirmed_top_panel(window, tmp_path, app)
    target = tmp_path / "Saved.panel.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_project()
    src.unlink()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
    window.open_project()
    assert window.controller.read_only and window.act_export_iss.isEnabled()
    window.act_export_iss.trigger()
    assert (tmp_path / "Saved.iss").exists()  # named after the project
    assert read_program(tmp_path / "Saved.iss").pwb_id == "Saved"


def test_export_dialog_settings_and_errors(app, tmp_path, boxes):
    dlg = ExportIssDialog(make_project(), IssSettings(), tmp_path / "out.iss", pwb_id="Board")
    assert dlg.write_button.isEnabled() and dlg.issues.rowCount() == 0
    assert not dlg.flip.isEnabled()  # a top-layer panel is not turned over
    dlg.rotation.setCurrentText("90")
    dlg.clamp.setValue(12.5)
    dlg.pwb_id.setText("ER-F8")
    dlg.offset.setValue(-90)
    s = dlg.settings()
    assert (s.panel_rotation, s.clamp_offset_y, s.pwb_id, s.angle_offset) == (90, 12.5, "ER-F8", -90)
    assert dlg.prepared.layout.machine.rotation == 90 and dlg.prepared.layout.program.clamp_offset == 12.5
    assert "Panel:      70 × 100 mm" in dlg.summary.text()
    dlg.clamp.setValue(0)
    assert dlg.settings().clamp_offset_y == "auto"
    dlg.grab()  # the preview paints
    dlg._write()
    assert (tmp_path / "out.iss").exists() and read_program(tmp_path / "out.iss").pwb_id == "ER-F8"

    bad = ExportIssDialog(make_project(fiducials=[(2, 2, "top")]), IssSettings(), tmp_path / "bad.iss", pwb_id="B")
    assert not bad.write_button.isEnabled() and bad.issues.item(0, 1).text() == "no_fiducials"
    bad._write()
    assert not (tmp_path / "bad.iss").exists()


def test_export_dialog_bottom_side_and_remembered_settings(app, tmp_path, boxes, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setenv("PANELIMPORT_SETTINGS", str(settings_file))
    dlg = ExportIssDialog(make_project(layer="bottom"), IssSettings(), tmp_path / "b.iss", pwb_id="B")
    assert dlg.flip.isEnabled() and "Bottom layer" in dlg.side_label.text()
    assert dlg.issues.item(0, 1).text() == "bottom_angles_unverified" and dlg.write_button.isEnabled()
    dlg.flip.setCurrentText("front-back")
    assert dlg.prepared.layout.machine.flip == "front-back"
    dlg.grab()
    dlg.pwb_id.setText("ONLY-THIS-ONE")
    dlg.remember.setChecked(True)
    dlg._write()
    remembered = IssSettings.load(settings_file)
    assert remembered.bottom_flip == "front-back" and remembered.pwb_id == ""  # pwbId stays per project
    assert read_program(tmp_path / "b.iss").pwb_id == "ONLY-THIS-ONE"


def test_compare_dialog(app, tmp_path, boxes):
    a, b = FIXTURES / "ER_issgen_panel3.iss", FIXTURES / "ER_issgen_panel3_janets.x21"
    if not (a.exists() and b.exists()):
        pytest.skip("issgen reference programs not present")
    dlg = CompareDialog(None, None, str(a), str(b))
    assert dlg.run()
    assert dlg.summary.text().startswith("Different: 66 common parts × 15 circuits, 7 changed")
    assert dlg.model.rowCount() == 7 * 15
    assert "Circuit layout: A MATRIX → B NONMATRIX" in dlg.details.toPlainText()
    dlg.all_rows.setChecked(True)
    assert dlg.model.rowCount() == 66 * 15
    dlg.path_b.setText(str(tmp_path / "missing.x21"))
    assert not dlg.run() and boxes[-1][:2] == ("warning", "Compare programs")


def test_compare_action_opens_the_dialog(window, monkeypatch):
    opened = []
    monkeypatch.setattr(CompareDialog, "exec", lambda dlg: opened.append(dlg) or 0)
    window.act_compare.trigger()
    assert len(opened) == 1
