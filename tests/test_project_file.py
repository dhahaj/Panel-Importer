"""Project file: save, reopen, identity and source hashing."""

import json

import pytest

from panelimport.model.panel import Acknowledgement, PanelProject
from panelimport.model.project_file import (
    ProjectFileError,
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
)
from panelimport.session import Session, SessionError
from tests.synthetic.odbgen import sr_panel


def _confirmed_session(tmp_path, **job_kw):
    src = sr_panel(**job_kw).write_tgz(tmp_path / "Panel_ODB.tgz")
    s = Session()
    s.open_source(src)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings])
    s.update(confirmed=True)
    s.update(fiducials=["FID1", "FID2", "FID3"], part_number_attribute="PART_NUMBER")
    return s, src


def test_save_requires_confirmation(tmp_path):
    src = sr_panel().write_tgz(tmp_path / "p.tgz")
    s = Session()
    s.open_source(src)
    with pytest.raises(SessionError):
        s.save(tmp_path / "p.panel.json")


def test_save_reopen_identical(tmp_path):
    """Save, reopen, and the model is identical."""
    s, _src = _confirmed_session(tmp_path)
    path = tmp_path / "Panel_ODB.panel.json"
    saved = s.save(path)
    loaded = load_project(path)
    assert loaded == saved
    assert loaded.source.path == "Panel_ODB.tgz"
    assert [f.name for f in loaded.fiducials] == ["FID1", "FID2", "FID3"]
    c1 = next(p for p in loaded.placements if p.designator == "C1")
    assert c1.part_number == "D-1001"

    s2 = Session()
    result = s2.open_project(path)
    assert result.source_issue is None
    assert result.differences == []
    assert s2.analysis.confirmed
    assert s2.analysis.to_project(path) == saved
    # Saving again writes byte-identical JSON.
    first = path.read_text()
    s2.save(path)
    assert path.read_text() == first


def test_project_json_layout(tmp_path):
    s, _src = _confirmed_session(tmp_path)
    s.save(tmp_path / "x.panel.json")
    data = json.loads((tmp_path / "x.panel.json").read_text())
    assert data["format"] == "panel-project" and data["version"] == 1
    assert list(data)[:3] == ["format", "version", "generator"]
    for key in (
        "source",
        "mode",
        "panel",
        "grid",
        "numbering",
        "circuit_reference",
        "circuits",
        "part_number_attribute",
        "placements",
        "panel_parts",
        "fiducials",
        "acknowledged_warnings",
    ):
        assert key in data
    assert data["grid"] == {"cols": 3, "rows": 2, "pitch_x": 52.0, "pitch_y": 38.5, "uniform": True, "source": "step-repeat"}
    assert data["circuits"][1]["dx"] == 52.0
    assert data["panel"]["outline"][0] == [0.0, 0.0]
    assert set(data["placements"][0]) >= {"designator", "x", "y", "rotation", "rotation_raw", "layer", "attributes"}


def test_edited_source_is_flagged(tmp_path):
    s, src = _confirmed_session(tmp_path)
    path = tmp_path / "Panel_ODB.panel.json"
    s.save(path)
    src.write_bytes(src.read_bytes() + b"\0" * 512)
    s2 = Session()
    result = s2.open_project(path)
    assert result.source_issue is not None and result.source_issue.code == "source_changed"
    changed = [i for i in s2.analysis.issues if i.code == "source_changed"]
    assert len(changed) == 1 and changed[0].severity.value == "warning"
    assert not s2.analysis.confirmed


def test_missing_source(tmp_path):
    s, src = _confirmed_session(tmp_path)
    path = tmp_path / "Panel_ODB.panel.json"
    s.save(path)
    src.unlink()
    s2 = Session()
    result = s2.open_project(path)
    assert result.source_issue.code == "source_missing"
    assert s2.read_only and s2.saved_project == load_project(path)
    # The read-only snapshot shows the saved model.
    snap = s2.analysis
    assert snap.summary == "6 circuits, 3 × 2, pitch 52.000 × 38.500 mm, from STEP-REPEAT"
    saved = load_project(path)
    for live, shown in zip(s.analysis.circuits, snap.circuits):
        key = lambda pts: sorted((round(x, 4), round(y, 4)) for x, y in pts)  # noqa: E731
        assert key(live.outline) == key(shown.outline)
    u1_live = next(p for p in s.analysis.placements if p.designator == "U1")
    u1_snap = next(p for p in snap.placements if p.designator == "U1")
    for c_live, c_snap in zip(s.analysis.circuits, snap.circuits):
        assert s.analysis.circuit_position(u1_live, c_live)[:2] == pytest.approx(snap.circuit_position(u1_snap, c_snap)[:2], abs=1e-5)
    assert [f.name for f in snap.fiducials] == [f.name for f in saved.fiducials]


def test_acknowledgements_are_saved(tmp_path):
    job = sr_panel()
    pan = job.steps["panel"]
    pan.repeats.clear()
    pan.step_repeat("pcb", 5, 5, 52, 0, 3, 1)
    pan.step_repeat("pcb", 5.7, 43.5, 52, 0, 3, 1)
    src = job.write_folder(tmp_path)
    s = Session()
    s.open_source(src)
    assert s.analysis.can_confirm() == (False, "1 warning must be acknowledged first")
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    project = s.save(tmp_path / "p.panel.json")
    assert [a.code for a in project.acknowledged_warnings] == ["nonuniform_grid"]
    data = json.loads((tmp_path / "p.panel.json").read_text())
    assert data["acknowledged_warnings"] == [{"code": "nonuniform_grid", "subject": "grid"}]


def test_strict_loading(tmp_path):
    good = project_to_dict(PanelProject())
    assert project_from_dict(good) == PanelProject()
    with pytest.raises(ProjectFileError, match="unknown keys"):
        project_from_dict({**good, "surprise": 1})
    with pytest.raises(ProjectFileError, match="version"):
        project_from_dict({**good, "version": 2})
    with pytest.raises(ProjectFileError, match="format"):
        project_from_dict({**good, "format": "other"})
    bad = json.loads(json.dumps(good))
    bad["grid"]["cols"] = "three"
    with pytest.raises(ProjectFileError):
        project_from_dict(bad)
    p = tmp_path / "x.panel.json"
    p.write_text("{not json")
    with pytest.raises(ProjectFileError):
        load_project(p)


def test_settings_snapshot_roundtrip(tmp_path):
    s, _src = _confirmed_session(tmp_path)
    s.settings.tolerances.centroid_on_pads = 0.3
    s.reanalyze()
    s.update(confirmed=True)
    project = s.save(tmp_path / "x.panel.json")
    assert load_project(tmp_path / "x.panel.json").settings.tolerances.centroid_on_pads == 0.3
    save_project(project, tmp_path / "y.panel.json")
    assert load_project(tmp_path / "y.panel.json") == project
