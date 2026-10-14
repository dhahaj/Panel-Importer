"""``panelimport iss`` and ``panelimport iss-compare``: exit codes 0 = written / same,
1 = errors (nothing written) / different, 2 = could not open."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from panelimport.cli import main
from panelimport.iss.reader import read_program
from panelimport.iss.settings import IssSettings
from panelimport.model.project_file import save_project
from tests.synthetic.projects import make_project

FIXTURES = Path(__file__).parent / "fixtures" / "iss"


def saved(tmp_path: Path, project=None, name: str = "Board.panel.json") -> Path:
    project = project or make_project()
    project.source.path = "Board_ODB.tgz"  # not there: the program is written from the project alone
    return save_project(project, tmp_path / name)


def test_iss_writes_next_to_the_project(tmp_path, capsys):
    path = saved(tmp_path)
    assert main(["iss", str(path)]) == 0
    out = capsys.readouterr().out
    target = tmp_path / "Board.iss"
    assert f"Written: {target}" in out and target.exists()
    prog = read_program(target)
    assert prog.pwb_id == "Board" and len(prog.circuits) == 2 and len(prog.placements) == 4
    assert "Issues: 0 errors, 0 warnings" in out
    for key, _value in IssSettings().describe():  # the report lists every value used
        assert f"  {key} " in out


def test_iss_output_option_and_verbose(tmp_path, capsys):
    path = saved(tmp_path)
    target = tmp_path / "out" / "Program.iss"
    target.parent.mkdir()
    assert main(["iss", str(path), "-o", str(target), "-v"]) == 0
    out = capsys.readouterr().out
    assert target.exists() and not (tmp_path / "Board.iss").exists()
    assert "allocation X" in out and "R1" in out


def test_iss_check_writes_nothing(tmp_path, capsys):
    path = saved(tmp_path)
    assert main(["iss", str(path), "--check"]) == 0
    assert "Ready to write." in capsys.readouterr().out
    assert not (tmp_path / "Board.iss").exists()


def test_iss_errors_write_nothing(tmp_path, capsys):
    path = saved(tmp_path, make_project(fiducials=[(2, 2, "top")]))
    assert main(["iss", str(path)]) == 1
    out = capsys.readouterr().out
    assert "ERROR   no_fiducials" in out and "Not written: fix the errors first." in out
    assert not (tmp_path / "Board.iss").exists()
    assert main(["iss", str(path), "--check"]) == 1


def test_iss_cannot_open(tmp_path, capsys):
    assert main(["iss", str(tmp_path / "missing.panel.json")]) == 2
    bad = tmp_path / "bad.panel.json"
    bad.write_text("{not json")
    assert main(["iss", str(bad)]) == 2
    assert "invalid JSON" in capsys.readouterr().err
    other = tmp_path / "other.panel.json"
    other.write_text(json.dumps({"format": "something-else"}))
    assert main(["iss", str(other)]) == 2
    assert "not a panel project" in capsys.readouterr().err


def test_iss_set_overrides(tmp_path, capsys):
    path = saved(tmp_path)
    args = ["iss", str(path), "--set", "panel_rotation=90", "--set", "clamp_offset_y=91.313", "--set", "header_completion=total"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "  panel_rotation         90" in out and "  clamp_offset_y         91.313" in out
    root = ET.parse(tmp_path / "Board.iss").getroot()
    assert root.find("core/pwbData/pwbConfiguration/outline").attrib == {"x": "70", "y": "100"}
    assert root.find("model/pwbData/pwbConfiguration/clampOffset").get("y") == "91.313"
    assert root.find("headerData/headPlacement").get("completion") == "4"


@pytest.mark.parametrize(
    "pair, message",
    [
        ("nope=1", "unknown ISS setting 'nope'"),
        ("panel_rotation=45", "panel_rotation=45 is not one of"),
        ("bottom_flip=up", "bottom_flip='up'"),
        ("pwb_thickness=thick", "not a valid float"),
        ("panel_rotation", "expected key=value"),
    ],
)
def test_iss_bad_set(tmp_path, capsys, pair, message):
    assert main(["iss", str(saved(tmp_path)), "--set", pair]) == 2
    assert message in capsys.readouterr().err


def test_iss_settings_file(tmp_path, capsys, monkeypatch):
    path = saved(tmp_path)
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"copy_suffix_regex": "", "iss": {"pwb_id": "FROM-FILE", "angle_offset": 90}}))
    assert main(["iss", str(path), "--settings", str(settings_file), "--set", "angle_offset=-90"]) == 0
    prog = read_program(tmp_path / "Board.iss")
    assert prog.pwb_id == "FROM-FILE"
    assert prog.placements[0].angle == 300  # 30 − 90: --set wins over the file
    # The user's settings file (PANELIMPORT_SETTINGS) is the default.
    monkeypatch.setenv("PANELIMPORT_SETTINGS", str(settings_file))
    assert main(["iss", str(path)]) == 0
    assert read_program(tmp_path / "Board.iss").placements[0].angle == 120


def test_iss_self_test_failure_writes_nothing(tmp_path, capsys, monkeypatch):
    from panelimport.iss import writer

    real = writer.render
    monkeypatch.setattr(writer, "render", lambda *a, **k: real(*a, **k).replace(" />", "/>", 1))
    path = saved(tmp_path)
    assert main(["iss", str(path)]) == 1
    out = capsys.readouterr().out
    assert "Not written: self-test: self-closing tag without a space" in out and "Ready to write" not in out
    assert not (tmp_path / "Board.iss").exists()


def test_iss_broken_settings_file(tmp_path, capsys):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{broken")
    assert main(["iss", str(saved(tmp_path)), "--settings", str(settings_file)]) == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_iss_source_changed_warns(tmp_path, capsys):
    project = make_project()
    path = save_project(project, tmp_path / "Board.panel.json")
    data = json.loads(path.read_text())
    (tmp_path / "Board_ODB.zip").write_bytes(b"changed export")
    data["source"] = {**data["source"], "path": "Board_ODB.zip", "sha256": "0" * 64}
    path.write_text(json.dumps(data))
    assert main(["iss", str(path)]) == 0
    out = capsys.readouterr().out
    assert "WARNING source_changed" in out and (tmp_path / "Board.iss").exists()


def test_iss_bottom_project(tmp_path, capsys):
    path = saved(tmp_path, make_project(layer="bottom"))
    assert main(["iss", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Side:       bottom layer: left-right flip, then rotated 0° CCW" in out
    assert "WARNING bottom_angles_unverified" in out


# -------------------------------------------------------------------- iss-compare
def test_iss_compare_same_and_different(tmp_path, capsys):
    path = saved(tmp_path)
    assert main(["iss", str(path)]) == 0
    assert main(["iss", str(path), "-o", str(tmp_path / "turned.iss"), "--set", "panel_rotation=180"]) == 0
    capsys.readouterr()
    program = str(tmp_path / "Board.iss")
    assert main(["iss-compare", program, program]) == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1].startswith("Same placements: 4 common parts × 2 circuits")
    assert main(["iss-compare", program, str(tmp_path / "turned.iss")]) == 1
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1].startswith("Different:")
    assert main(["iss-compare", program, program, "--all"]) == 0
    assert "Parts: 8 of 8 rows" in capsys.readouterr().out


def test_iss_compare_fixtures(capsys):
    a, b = FIXTURES / "ER_issgen_panel3.iss", FIXTURES / "ER_issgen_panel3_janets.x21"
    if not (a.exists() and b.exists()):
        pytest.skip("issgen reference programs not present")
    assert main(["iss-compare", str(a), str(b)]) == 1
    out = capsys.readouterr().out
    assert "Circuit layout: A MATRIX → B NONMATRIX" in out
    assert " R35 " in out and "-0.0090" in out
    assert main(["iss-compare", str(a), str(b), "--tolerance", "0.005"]) == 1
    assert "1 moved > 0.005 mm, 1 moved ≤ 0.005 mm" in capsys.readouterr().out  # R35, D12


def test_iss_compare_cannot_open(tmp_path, capsys):
    bad = tmp_path / "bad.x21"
    bad.write_text("garbage")
    assert main(["iss-compare", str(bad), str(bad)]) == 2
    assert "not XML" in capsys.readouterr().err
