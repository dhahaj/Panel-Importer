"""Acceptance against real exports: ``tests/fixtures/<panel>/`` + ``expected.json``.

Each fixture directory holds one ODB++ export (folder, .tgz or .zip) and an
``expected.json`` written from what Altium shows (see tests/fixtures/README.md).
The test is skipped until fixtures are added.
"""

import json
from pathlib import Path

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.io.odb import OdbJob
from panelimport.model.panel import Decisions
from panelimport.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
CASES = sorted(p.parent for p in FIXTURES.glob("*/expected.json"))
TOL = 0.01


def _source(case: Path) -> Path:
    exp = json.loads((case / "expected.json").read_text())
    if exp.get("source"):
        return case / exp["source"]
    for p in sorted(case.iterdir()):
        if p.name != "expected.json" and (p.is_dir() or p.suffix.lower() in (".tgz", ".zip", ".tar", ".gz")):
            return p
    raise FileNotFoundError(f"no export in {case}")


@pytest.mark.skipif(not CASES, reason="no real ODB++ fixtures in tests/fixtures yet")
@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_real_panel(case):
    exp = json.loads((case / "expected.json").read_text())
    settings = Settings.from_dict(exp["settings"]) if "settings" in exp else Settings()
    decisions = Decisions(**exp.get("decisions", {}))
    a = analyze(OdbJob(_source(case)), settings, decisions)
    if "mode" in exp:
        assert a.mode == exp["mode"]
    if "panel_step" in exp:
        assert (a.panel_step or "").lower() == exp["panel_step"].lower()
    if "board_step" in exp:
        assert (a.board_step or "").lower() == exp["board_step"].lower()
    for role, layer in exp.get("layer_roles", {}).items():
        assert a.layer_roles.get(role, "").lower() == layer.lower(), role
    if "circuits" in exp:
        assert len(a.circuits) == exp["circuits"]
    if "grid" in exp:
        g = exp["grid"]
        assert (a.grid.cols, a.grid.rows) == (g["cols"], g["rows"])
        assert a.grid.pitch_x == pytest.approx(g["pitch_x"], abs=TOL)
        assert a.grid.pitch_y == pytest.approx(g["pitch_y"], abs=TOL)
    if "placements" in exp:
        assert len(a.placements) == exp["placements"]
    project = a.to_project()
    for d, xy in exp.get("placement_positions", {}).items():
        p = next(p for p in project.placements if p.designator == d)
        assert (p.x, p.y) == pytest.approx(tuple(xy), abs=TOL), d
    if "max_errors" in exp:
        assert len(a.errors) <= exp["max_errors"], [i.format() for i in a.errors]
