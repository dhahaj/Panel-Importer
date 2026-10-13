"""Session behaviour shared by the CLI and the GUI."""

import pytest

from panelimport.io.bom import BomError
from panelimport.io.odb import OdbOpenError
from panelimport.model.panel import SingleBoardSetup
from panelimport.session import Session
from tests.synthetic.odbgen import sr_panel
from tests.test_single_board import single_board_job


def test_unreadable_bom_leaves_session_unchanged(tmp_path):
    s = Session()
    s.open_source(sr_panel().write_folder(tmp_path))
    before = (s.decisions, s.analysis, s.bom)
    bad = tmp_path / "bom.csv"
    bad.write_text("Comment,Quantity\n100n,2\n")
    with pytest.raises(BomError):
        s.update(bom_path=str(bad))
    assert (s.decisions, s.analysis, s.bom) == before


def test_unreadable_panel_export_leaves_session_unchanged(tmp_path):
    s = Session()
    s.open_source(single_board_job().write_folder(tmp_path))
    before = (s.decisions, s.analysis)
    with pytest.raises(OdbOpenError):
        s.update(single_board=SingleBoardSetup(panel_source=str(tmp_path / "missing.tgz")))
    assert (s.decisions, s.analysis) == before


def test_structural_edits_reset_confirmation(tmp_path):
    s = Session()
    s.open_source(sr_panel().write_folder(tmp_path))
    s.update(confirmed=True)
    s.update(fiducials=["FID1"], part_number_attribute="PART_NUMBER")
    assert s.analysis.confirmed
    s.update(numbering_first="upper-right")
    assert not s.analysis.confirmed
