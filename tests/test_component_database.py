"""The component database in Phase 1 (lookup, issues, the project's snapshot) and in the
ISS program (sizes and comments).  An in-memory database stands in for the .mdb."""

from __future__ import annotations

import json

import pytest

from panelimport import cli, session as session_module
from panelimport.analysis import edits as E
from panelimport.analysis.database import database_summary, part_database
from panelimport.io.compodb import DatabaseError
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.report import format_report
from panelimport.iss.settings import IssSettings
from panelimport.model.database import FOUND, MISSING, NOT_LOOKED_UP, ComponentDatabase, DatabasePart
from panelimport.model.panel import Acknowledgement, ComponentEdit, Decisions
from panelimport.model.project_file import ProjectFileError, load_project, project_from_dict, project_to_dict
from panelimport.session import Session
from tests.conftest import write
from tests.synthetic.odbgen import sr_panel
from tests.synthetic.projects import make_project

MDB = r"C:\ComponentDatabase\Data\DETEX.mdb"


def _database(*parts: DatabasePart) -> ComponentDatabase:
    return ComponentDatabase(path=MDB, read_at="2026-11-14T10:02:00", parts=list(parts), whole=True)


#: The synthetic panel's parts: U1 IC-555 (no part number), C1 D-1001, R1 D-2002, J1 HDR-2, C2 CAP-1U.
PHASE1_DB = _database(
    DatabasePart("IC-555", "TIMER 555 SOIC8", "SOIC8 Emboss", 5.0, 4.0, 1.75),
    DatabasePart("d-1001", "CAP 100N 0603", "0603 Paper", 1.6, 0.8, 0.9),
    DatabasePart("D-2002", "RES 10K 0402", "", 1.0, 0.5, 0.0),
    DatabasePart("HDR-2", "HEADER", "", 0.0, 0.0, 8.5),
)


@pytest.fixture
def job(tmp_path) -> OdbJob:
    return OdbJob(write(sr_panel(units="MM", n_parts=5), tmp_path))


@pytest.fixture
def fake_read(monkeypatch):
    """Session reads PHASE1_DB; the paths asked for are recorded."""
    asked = []

    def read(path):
        asked.append(str(path))
        if "missing" in str(path):
            raise DatabaseError(f"The component database {path} was not found")
        return PHASE1_DB

    monkeypatch.setattr(session_module, "read_database", read)
    return asked


def _open(job, **decisions) -> Session:
    s = Session()
    s.open_job(job, Decisions(part_number_attribute="PART_NUMBER", **decisions), database=MDB)
    return s


def _part(a, designator: str, level: str = "board"):
    return E.find_part(a, level, designator)


# ---------------------------------------------------------------------- Phase 1
def test_import_looks_the_components_up(job, fake_read):
    s = _open(job)
    a = s.analysis
    assert fake_read == [MDB] and a.decisions.component_database is PHASE1_DB
    u1 = part_database(a, _part(a, "U1"))  # no part number: looked up by its part name
    assert (u1.state, u1.record.description, u1.record.pkg_type) == (FOUND, "TIMER 555 SOIC8", "SOIC8 Emboss")
    assert u1.sizes == {"width": 5.0, "length": 4.0, "height": 1.75} and u1.from_database == {"width", "length", "height"}
    c1 = part_database(a, _part(a, "C1"))  # "d-1001" in the database: case does not matter
    assert c1.state == FOUND and c1.record.name == "d-1001"
    # A database dimension of 0 is unknown: the export's stays.
    r1 = part_database(a, _part(a, "R1"))
    assert r1.sizes == {"width": 1.0, "length": 0.5, "height": 0.0} and r1.from_database == {"width", "length"}
    j1 = part_database(a, _part(a, "J1"))
    assert j1.sizes == {"width": 5.08, "length": 2.54, "height": 8.5} and j1.from_database == {"height"}
    c2 = part_database(a, _part(a, "C2"))
    assert (c2.state, c2.record, c2.from_database) == (MISSING, None, set())
    assert database_summary(a) == "DETEX.mdb, read 2026-11-14 10:02:00: 4 of 5 components found"
    (issue,) = [i for i in a.issues if i.code == "not_in_database"]
    assert issue.severity.value == "info" and (issue.designator, issue.subject) == ("C2", "CAP-1U")
    assert "CAP-1U (C2) is not in the component database (DETEX.mdb, read 2026-11-14 10:02:00)" in issue.message
    assert not [i for i in a.issues if i.code == "database_not_looked_up"]


def test_an_edited_size_wins_over_the_database(job, fake_read):
    a = _open(job).analysis
    u1 = _part(a, "U1")
    e = E.edit_from_values(a, "board", "U1", {**E.shown_values(a, u1), "height": 2.5, "width": 0.0})
    s = _open(job, component_edits=[e], edit_frame=a.edit_frame)
    shown = part_database(s.analysis, _part(s.analysis, "U1"))
    # The edited height wins; the width edited to 0 (unknown) does not hide the database's.
    assert shown.sizes == {"width": 5.0, "length": 4.0, "height": 2.5} and shown.from_database == {"width", "length"}
    # An added part takes the database's size unless its edit gives one.
    add = E.added_edit("board", "U9", {"part_name": "IC-555", "package": "SOIC8", "layer": "top", "x": 20.0, "y": 20.0, "rotation": 0.0})
    s = _open(job, component_edits=[add], edit_frame=a.edit_frame)
    assert part_database(s.analysis, _part(s.analysis, "U9")).sizes == {"width": 5.0, "length": 4.0, "height": 1.75}


def test_an_unreadable_database_is_reported_not_fatal(job, fake_read):
    s = Session()
    a = s.open_job(job, Decisions(), database="missing.mdb")
    (issue,) = [i for i in a.issues if i.code == "database_unavailable"]
    assert issue.severity.value == "info" and "missing.mdb was not found; the components are shown without it" in issue.message
    assert a.decisions.component_database is None and a.circuits and database_summary(a) == ""
    s.database_read()
    s.update(component_database=PHASE1_DB)
    assert "database_unavailable" not in [i.code for i in s.analysis.issues]
    assert Session().open_job(job, Decisions(), database=None).decisions.component_database is None


def test_updating_from_the_database_keeps_the_confirmation(job, fake_read):
    s = Session()
    s.open_job(job)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    assert s.analysis.confirmed
    s.update(component_database=PHASE1_DB)
    assert s.analysis.confirmed


def test_the_project_keeps_what_its_components_need(job, fake_read, tmp_path):
    s = _open(job)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    path = tmp_path / "p.panel.json"
    s.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 5
    assert data["component_database"] == {
        "path": MDB,
        "read_at": "2026-11-14T10:02:00",
        "parts": [
            {"name": "d-1001", "description": "CAP 100N 0603", "pkg_type": "0603 Paper", "width": 1.6, "length": 0.8, "height": 0.9},
            {"name": "D-2002", "description": "RES 10K 0402", "pkg_type": "", "width": 1.0, "length": 0.5, "height": 0.0},
            {"name": "HDR-2", "description": "HEADER", "pkg_type": "", "width": 0.0, "length": 0.0, "height": 8.5},
            {"name": "IC-555", "description": "TIMER 555 SOIC8", "pkg_type": "SOIC8 Emboss", "width": 5.0, "length": 4.0, "height": 1.75},
        ],
        "missing": ["CAP-1U", "FIDUCIAL"],
    }
    # Reopening uses the saved snapshot (the database is not read) and reproduces the project.
    fake_read.clear()
    s2 = Session()
    reopened = s2.open_project(path)
    assert reopened.differences == [] and fake_read == []
    a = s2.analysis
    assert part_database(a, _part(a, "U1")).state == FOUND and part_database(a, _part(a, "C2")).state == MISSING
    # A part number the snapshot never saw is "not looked up" until the next update.
    c2 = _part(a, "C2")
    e = E.edit_from_values(a, "board", "C2", {**E.shown_values(a, c2), "part_number": "D-3003"})
    b = s2.update(component_edits=[e], edit_frame=a.edit_frame)
    assert part_database(b, _part(b, "C2")).state == NOT_LOOKED_UP
    (issue,) = [i for i in b.issues if i.code == "database_not_looked_up"]
    assert "1 component(s) were not looked up in the component database (DETEX.mdb, read 2026-11-14 10:02:00): D-3003" in issue.message


def test_without_a_database_the_project_file_is_as_before(job, tmp_path):
    s = Session()
    s.open_job(job)
    s.update(acknowledged=[Acknowledgement.of(i) for i in s.analysis.warnings], confirmed=True)
    path = tmp_path / "p.panel.json"
    s.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 3 and "component_database" not in data


def test_project_file_snapshot_is_strict():
    project = make_project()
    project.version = 5
    project.component_database = _database(DatabasePart("109826", "MCU", "", 7.0, 7.0, 1.2)).for_names(["109826", "X"])
    data = project_to_dict(project)
    assert "whole" not in data["component_database"]
    assert project_from_dict(json.loads(json.dumps(data))) == project
    data["component_database"]["table"] = "Compo"
    with pytest.raises(ProjectFileError, match="unknown keys"):
        project_from_dict(data)


def test_cli_analyze_reads_the_configured_database(job, fake_read, tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"database": {"path": MDB}}), encoding="utf-8")
    cli.main(["analyze", str(job.path), "--settings", str(settings), "--part-number-attribute", "PART_NUMBER"])
    assert fake_read == [MDB]
    assert "Component database: DETEX.mdb, read 2026-11-14 10:02:00: 4 of 5 components found" in capsys.readouterr().out
    cli.main(["analyze", str(job.path), "--settings", str(settings), "--database", ""])
    assert fake_read == [MDB] and "Component database" not in capsys.readouterr().out
    cli.main(["analyze", str(job.path), "--database", "missing.mdb"])
    assert "database_unavailable" in capsys.readouterr().out


# ---------------------------------------------------------------------- ISS
#: make_project's components: R1 and R2 107522-31-1001, C1 107523-3156-1003, U1 109826,
#: each 1.6 × 0.8 × 0.55 with the comment attribute "Description of <designator>".
ISS_DB = _database(
    DatabasePart("107522-31-1001", "RESISTOR 1K 0603", "1206", 1.7, 0.9, 0.0),
    DatabasePart("109826", "ATMEGA4808 MICROCONTROLLER", "", 7.0, 5.0, 1.2),
)


def _project(**sizes):
    project = make_project()
    for p in project.placements:
        if p.designator in sizes:
            p.width, p.length, p.height = sizes[p.designator]
    project.component_database = ISS_DB.for_names(p.part_number for p in project.placements)
    return project


def _components(prepared) -> dict[str, tuple]:
    return {c.name: (c.width, c.length, c.height, c.comment) for c in prepared.layout.program.components}


def test_iss_sizes_and_comments_come_from_the_database():
    prepared = prepare(_project(), IssSettings(), pwb_id="T")
    assert _components(prepared) == {
        "107522-31-1001": (1.7, 0.9, 0.55, "RESISTOR 1K 0603"),  # the database's height is unknown
        "107523-3156-1003": (1.6, 0.8, 0.55, "Description of C1"),  # not in the database
        "109826": (7.0, 5.0, 1.2, "ATMEGA4808 MICROCONTROLLER"),
    }
    (issue,) = prepared.issues
    assert (issue.code, issue.data) == ("component_not_in_database", {"components": ["107523-3156-1003"]})
    assert issue.is_warning and prepared.can_write
    assert "1 component(s) are not in the component database (DETEX.mdb, read 2026-11-14 10:02:00): 107523-3156-1003" in issue.message
    assert "2 of 3 in the component database (DETEX.mdb, read 2026-11-14 10:02:00)" in format_report(prepared)


def test_iss_edit_wins_and_a_quarter_turn_leaves_database_sizes_alone():
    project = _project(R2=(2.0, 0.8, 0.55))  # placements carry their edits
    project.component_edits = [ComponentEdit("R2", width=2.0)]
    assert _components(prepare(project, IssSettings(), pwb_id="T"))["107522-31-1001"][:3] == (2.0, 0.9, 0.55)
    turned = _components(prepare(project, IssSettings(angle_offset=90.0), pwb_id="T"))
    # The database's sizes are the machine's; the export's and the edit's turn with the offset.
    assert turned["109826"][:3] == (7.0, 5.0, 1.2)
    assert turned["107523-3156-1003"][:3] == (0.8, 1.6, 0.55)
    assert turned["107522-31-1001"][:3] == (1.7, 2.0, 0.55)  # the edited width is the machine's length


def test_iss_a_dimension_the_database_decides_is_no_conflict():
    # R1 and R2 disagree on the width; the database knows it, so nothing is in doubt.
    assert prepare(_project(R2=(2.0, 0.8, 0.55)), IssSettings(), pwb_id="T").issues[0].code == "component_not_in_database"
    codes = [i.code for i in prepare(_project(R2=(1.6, 0.8, 0.7)), IssSettings(), pwb_id="T").issues]
    assert "component_size_differs" in codes  # the database's height is unknown: the export decides


def test_iss_components_never_looked_up():
    project = _project()
    project.component_database = ISS_DB.for_names(["109826"])
    issues = {i.code: i for i in prepare(project, IssSettings(), pwb_id="T").issues}
    assert set(issues) == {"component_not_looked_up"}
    assert issues["component_not_looked_up"].data == {"components": ["107522-31-1001", "107523-3156-1003"]}


def test_iss_without_a_database_is_unchanged():
    project = make_project()
    prepared = prepare(project, IssSettings(), pwb_id="T")
    assert prepared.issues == [] and "component database" not in format_report(prepared)
    assert _components(prepared)["109826"] == (1.6, 0.8, 0.55, "Description of U1")


def test_iss_from_a_saved_project(tmp_path):
    project = _project()
    project.version = 5
    path = tmp_path / "p.panel.json"
    path.write_text(json.dumps(project_to_dict(project)), encoding="utf-8")
    assert _components(prepare(load_project(path), IssSettings(), pwb_id="T"))["109826"][:3] == (7.0, 5.0, 1.2)
