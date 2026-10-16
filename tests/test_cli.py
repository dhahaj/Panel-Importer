"""`panelimport analyze` prints the same summary and issues the GUI shows."""

import json

from panelimport.analysis.pipeline import analyze
from panelimport.cli import main
from panelimport.io.odb import OdbJob
from panelimport.settings import Settings
from tests.synthetic.odbgen import sr_panel


def test_analyze_prints_summary_and_issues(tmp_path, capsys):
    src = sr_panel().write_tgz(tmp_path / "p.tgz")
    code = main(["analyze", str(src)])
    out = capsys.readouterr().out
    a = analyze(OdbJob(src), Settings())
    assert code == 0
    assert f"Panel:    {a.summary}" in out
    for issue in a.issues:
        assert issue.format() in out
    assert "Ready to confirm." in out


def test_analyze_exit_code_on_errors(tmp_path, capsys):
    job = sr_panel()
    job.flatten("panel")
    src = job.write_folder(tmp_path)
    assert main(["analyze", str(src)]) == 1
    out = capsys.readouterr().out
    assert "ambiguous_steps" in out
    assert main(["analyze", str(src), "--panel-step", "panel", "--panel-level", "FID1,FID2,FID3"]) == 0


def test_analyze_json(tmp_path, capsys):
    src = sr_panel().write_folder(tmp_path)
    assert main(["analyze", str(src), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == "6 circuits, 3 × 2, pitch 52.000 × 38.500 mm, from STEP-REPEAT"
    assert len(data["circuits"]) == 6 and data["can_confirm"]


def test_analyze_components_csv(tmp_path, capsys):
    src = sr_panel().write_folder(tmp_path)
    out = tmp_path / "parts.csv"
    assert main(["analyze", str(src), "--components-csv", str(out)]) == 0
    assert f"Components: 15 written to {out}" in capsys.readouterr().out
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].startswith("Designator,Level,Part name,") and len(lines) == 16
    assert "C1,board,CAP-100N,,C0603,top,25,10,270,1.6,0.8,,OK 0.000 mm," in lines
    # With --json the output stays JSON; a file that cannot be written is an error.
    assert main(["analyze", str(src), "--json", "--components-csv", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["placements"] == 12
    assert main(["analyze", str(src), "--components-csv", str(tmp_path / "nope" / "parts.csv")]) == 2
    assert "parts.csv" in capsys.readouterr().err


def test_bad_path(tmp_path, capsys):
    assert main(["analyze", str(tmp_path / "nope")]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_verify(tmp_path, capsys):
    from panelimport.model.panel import Acknowledgement
    from panelimport.session import Session

    src = sr_panel().write_tgz(tmp_path / "p.tgz")
    s = Session()
    s.open_source(src)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    s.save(tmp_path / "p.panel.json")
    assert main(["verify", str(tmp_path / "p.panel.json")]) == 0
    assert "reproduces the saved project" in capsys.readouterr().out
    src.write_bytes(src.read_bytes() + b"x")
    assert main(["verify", str(tmp_path / "p.panel.json")]) == 1
