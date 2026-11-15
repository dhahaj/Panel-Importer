"""Reading the JaNets component database, and what the reference programs prove about it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from panelimport.io import compodb
from panelimport.io.compodb import DatabaseError, read_database
from panelimport.iss.reader import read_program
from panelimport.iss.settings import IssSettings
from panelimport.model.database import FOUND, MISSING, NOT_LOOKED_UP, ComponentDatabase, DatabasePart, with_database
from panelimport.model.serialize import SerializationError
from panelimport.settings import DatabaseSettings, Settings

FIXTURES = Path(__file__).parent / "fixtures"
DETEX = FIXTURES / "DETEX.mdb"
CIRCUITCAM = ("ER_RevF8_circuitcam.iss", "102628_portrait_circuitcam.iss")


def _readable() -> str | None:
    """Why the fixture database cannot be read here, or None."""
    if not DETEX.exists():
        return "tests/fixtures/DETEX.mdb is not there"
    return compodb.unavailable() or None


needs_database = pytest.mark.skipif(_readable() is not None, reason=_readable() or "")


@pytest.fixture(scope="module")
def detex() -> ComponentDatabase:
    return read_database(DETEX)


# ---------------------------------------------------------------------- the fixture
@needs_database
def test_reads_every_component(detex):
    assert detex.whole and detex.path == str(DETEX) and detex.read_at
    assert len(detex.parts) == 211
    assert detex.find("PP-5932-1") == DatabasePart("PP-5932-1", "DIODE SIGNAL (250mA)", "", 1.24, 2.89, 0.99)
    assert detex.find("107523-1156-1003") == DatabasePart(
        "107523-1156-1003", "CAPACITOR CER 0.1UF 50V X7R 1206", "1206", 3.2, 1.6, 0.85
    )
    assert detex.find("pp-5932-1") is detex.find("PP-5932-1")  # case-insensitive, like Jet
    assert detex.state("107522-31-1001") == MISSING  # whole: anything else is missing
    # Text is stripped (some descriptions end in spaces in the database).
    assert all(p.name == p.name.strip() and p.description == p.description.strip() for p in detex.parts)


@needs_database
def test_leaves_the_database_alone(tmp_path):
    live = tmp_path / "DETEX.mdb"
    live.write_bytes(DETEX.read_bytes())
    before = hashlib.sha256(live.read_bytes()).hexdigest()
    read_database(live)
    assert hashlib.sha256(live.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["DETEX.mdb"]  # no .ldb lock file


@needs_database
@pytest.mark.parametrize("name", CIRCUITCAM)
def test_circuitcam_sizes_are_the_database_sizes(detex, name):
    """Why sizes are divided by 10000 and written unswapped: CircuitCAM did exactly that."""
    path = FIXTURES / "iss" / name
    if not path.exists():
        pytest.skip(f"{name} is not there")
    found = 0
    for c in read_program(path).components:
        part = detex.find(c.name)
        if part is None:
            assert (c.width, c.length, c.height) == (0, 0, 0)
        else:
            assert (c.width, c.length, c.height) == (part.width, part.length, part.height), c.name
            found += 1
    assert found >= 4


def test_missing_file(tmp_path):
    with pytest.raises(DatabaseError, match="was not found"):
        read_database(tmp_path / "none.mdb")


@needs_database
def test_not_a_database(tmp_path):
    bad = tmp_path / "bad.mdb"
    bad.write_text("not an Access database")
    with pytest.raises(DatabaseError, match="could not be opened"):
        read_database(bad)


def test_no_driver(tmp_path, monkeypatch):
    class FakeOdbc:
        Error = Exception

        @staticmethod
        def drivers():
            return ["SQL Server"]

    db = tmp_path / "x.mdb"
    db.write_bytes(b"")
    monkeypatch.setattr(compodb, "_pyodbc", lambda: FakeOdbc)
    with pytest.raises(DatabaseError, match="Access Database Engine"):
        read_database(db)
    assert "Access Database Engine" in compodb.unavailable()


# ---------------------------------------------------------------------- the snapshot
def _db() -> ComponentDatabase:
    return ComponentDatabase(
        path=r"C:\ComponentDatabase\Data\DETEX.mdb",
        read_at="2026-11-14T10:02:00",
        parts=[DatabasePart("PP-1", "Diode", "SOT23", 1.3, 2.9, 0.95), DatabasePart("R-1", "Resistor", "", 1.6, 0.8, 0)],
        whole=True,
    )


def test_for_names_keeps_what_the_components_need():
    snap = _db().for_names(["r-1 ", "NEW-1", "", "R-1", "new-1"])
    assert snap.parts == [_db().parts[1]] and snap.missing == ["NEW-1"] and not snap.whole
    assert (snap.state("R-1"), snap.state("new-1"), snap.state("PP-1")) == (FOUND, MISSING, NOT_LOOKED_UP)
    assert snap.for_names(["R-1", "NEW-1", "PP-1"]) == snap  # not looked up stays out
    assert snap.label == "DETEX.mdb, read 2026-11-14 10:02:00"


def test_with_database_per_dimension():
    rec = DatabasePart("X", width=3.2, length=1.6, height=0)
    # Export sizes give way to the database; an unknown database height keeps the export's.
    assert with_database((3.0, 1.5, 0.6), set(), rec) == ((3.2, 1.6, 0.6), {"width", "length"})
    # An edited size wins; an edit to 0 (unknown) does not hide the database.
    assert with_database((3.0, 0.0, 0.6), {"width", "length"}, rec) == ((3.0, 1.6, 0.6), {"length"})
    assert with_database((3.0, 1.5, 0.6), set(), None) == ((3.0, 1.5, 0.6), set())


# ---------------------------------------------------------------------- settings
def test_settings_section(tmp_path):
    path = tmp_path / "settings.json"
    assert DatabaseSettings.load(path) == DatabaseSettings()
    Settings(part_number_attribute="Detex_P/N").save(path)
    IssSettings(panel_rotation=90).save(path)
    DatabaseSettings(r"C:\ComponentDatabase\Data\DETEX.mdb").save(path)
    data = json.loads(path.read_text())
    assert data["database"] == {"path": r"C:\ComponentDatabase\Data\DETEX.mdb"} and data["iss"]["panel_rotation"] == 90
    # Phase 1 reads past the section, keeps it when it saves, and does not copy it into projects.
    loaded = Settings.load(path)
    loaded.save(path)
    assert "database" not in loaded.to_dict()
    assert DatabaseSettings.load(path).path == r"C:\ComponentDatabase\Data\DETEX.mdb"
    assert IssSettings.load(path).panel_rotation == 90


def test_settings_section_rejects_unknown_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"database": {"path": "x", "table": "Compo"}}))
    with pytest.raises(SerializationError, match="unknown keys"):
        DatabaseSettings.load(path)
