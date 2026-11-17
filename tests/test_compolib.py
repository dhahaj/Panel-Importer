"""Reading the whole component database and saving changes to it, against a real Access
file made for the test (skipped without the Access ODBC driver)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from panelimport.io import compolib
from panelimport.io.compodb import DatabaseError
from panelimport.io.compolib import (
    BACKUP_DIR,
    DatabaseConflict,
    DatabaseInUse,
    in_use,
    lock_holders,
    read_library,
    save_changes,
)
from panelimport.model.library import NAME, Changes
from tests.synthetic import mdb

needs_database = pytest.mark.skipif(bool(mdb.unavailable()), reason=mdb.unavailable())


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return mdb.make_database(tmp_path_factory.mktemp("mdb") / "template.mdb")


@pytest.fixture
def live(template, tmp_path) -> Path:
    """A fresh copy of the database in a folder of its own."""
    folder = tmp_path / "Data"
    folder.mkdir()
    path = folder / "DETEX_New.mdb"
    path.write_bytes(template.read_bytes())
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _id(lib, name: str) -> int:
    return next(r.compo_id for r in lib.records if r.name == name)


def _connect(path: Path):
    import pyodbc

    return pyodbc.connect(f"DRIVER={{{mdb.DRIVER}}};DBQ={path};", autocommit=True)


def _files(path: Path) -> list[str]:
    return sorted(p.relative_to(path.parent).as_posix() for p in path.parent.rglob("*") if p.is_file())


# ---------------------------------------------------------------------- reading
@needs_database
def test_reads_every_component_from_a_copy(live):
    before = _sha(live)
    lib = read_library(live)
    assert lib == replace(mdb.sample_library(str(live)), read_at=lib.read_at)
    assert _sha(live) == before and _files(live) == ["DETEX_New.mdb"]  # untouched, no .ldb lock file


@needs_database
def test_an_older_database_without_a_setting(live):
    conn = _connect(live)
    conn.cursor().execute("ALTER TABLE Laser DROP COLUMN Gx10LaserHeightLnc60")
    conn.cursor().execute("DROP TABLE Inspection")
    conn.close()
    lib = read_library(live)
    assert "Laser.Gx10LaserHeightLnc60" not in lib.fields and "Inspection.ChipStandCheck" not in lib.fields
    assert "Laser.LaserHeight" in lib.fields and len(lib.records) == 4
    with pytest.raises(ValueError, match="cannot be changed"):
        lib.edit(Changes(), _id(lib, "D-100"), {"Inspection.ChipStandCheck": 1})


def test_missing_file(tmp_path):
    with pytest.raises(DatabaseError, match="was not found"):
        read_library(tmp_path / "none.mdb")
    with pytest.raises(DatabaseError, match="no changes"):
        save_changes(tmp_path / "none.mdb", mdb.sample_library(), Changes())


@needs_database
def test_not_a_component_database(tmp_path):
    bad = tmp_path / "bad.mdb"
    bad.write_text("not an Access database")
    with pytest.raises(DatabaseError, match="could not be opened"):
        read_library(bad)


# ---------------------------------------------------------------------- saving
@needs_database
def test_save_edits_a_copy_and_a_delete(live):
    was = live.read_bytes()
    lib, ch = read_library(live), Changes()
    d, u = _id(lib, "D-100"), _id(lib, "U-200")
    lib.edit(
        ch,
        d,
        {
            "Compo.Description": "DIODE (edited)", "Compo.Width": 48150, "Feeder.Pitch": 4, "Laser.GX4PreRotate": 3200,
            "LaserGx10.SpdXY": 0, "Expansion.Test": True, "Expansion.AutoTeach": 1, "Inspection.ChipStandCheck": 1,
            "Compo.PackageWidth": 30000,
        },
    )  # fmt: skip
    new = lib.add_copy(ch, d, "D-101")
    lib.edit(ch, new, {"Compo.Height": 12000})
    lib.delete(ch, u)

    result = save_changes(live, lib, ch)
    assert result.summary == "1 edited, 1 new, 1 deleted" and result.ids == {new: 5}
    # The database as it was is the backup; nothing else is left next to it.
    assert result.backup.parent == live.parent / BACKUP_DIR and result.backup.read_bytes() == was
    assert _files(live) == ["DETEX_New.mdb", f"{BACKUP_DIR}/{result.backup.name}"]

    after = read_library(live)
    assert [r.name for r in after.records] == ["D-100", "D-101", "Q-300", "R-400"]
    edited = {**mdb.values_of("D-100"), **ch.updates[d]}
    assert after.record(d).values == edited and after.record(d).values["Expansion.Test"] is True
    assert after.record(5).values == {**edited, NAME: "D-101", "Compo.Height": 12000}
    assert after.record(_id(after, "R-400")).values == mdb.values_of("R-400")  # the others are untouched

    # Every row of the component was copied, also in tables this program does not show, and deleted.
    cur = _connect(live).cursor()
    assert cur.execute("SELECT Stroke FROM Adjust WHERE CompoID = 5").fetchone()[0] == 100 * d
    assert bytes(cur.execute("SELECT Picture FROM Compo WHERE CompoID = 5").fetchone()[0]) == mdb.PICTURE
    for table in ("Compo", "Feeder", "Laser", "LaserGx10", "Expansion", "Inspection", "Adjust"):
        assert cur.execute(f"SELECT COUNT(*) FROM [{table}] WHERE CompoID = ?", u).fetchone()[0] == 0, table
        assert cur.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0] == 4, table
    cur.connection.close()


@needs_database
def test_nothing_is_written_while_the_database_is_open(live):
    lib, ch = read_library(live), Changes()
    lib.edit(ch, _id(lib, "D-100"), {"Compo.Width": 48150})
    other = _connect(live)  # JaNets, or the Juki Component Database
    other.cursor().execute("SELECT COUNT(*) FROM Compo").fetchone()
    try:
        before = _sha(live)
        assert in_use(live) and lock_holders(live) and "(" in lock_holders(live)[0]
        with pytest.raises(DatabaseInUse, match=r"DETEX_New.mdb is open in another program \(.+\)\. Close"):
            save_changes(live, lib, ch)
        assert _sha(live) == before and _files(live) == ["DETEX_New.ldb", "DETEX_New.mdb"]
    finally:
        other.close()
    assert not in_use(live)
    save_changes(live, lib, ch)  # closed: the same changes go through
    assert read_library(live).record(_id(lib, "D-100")).values["Compo.Width"] == 48150


@needs_database
def test_a_component_changed_since_it_was_read_is_a_conflict(live):
    lib = read_library(live)
    d, r = _id(lib, "D-100"), _id(lib, "R-400")
    conn = _connect(live)
    conn.cursor().execute("UPDATE Compo SET Width = 99999 WHERE CompoName = 'D-100'")
    conn.close()
    before = _sha(live)
    for make in (
        lambda ch: lib.edit(ch, d, {"Compo.Width": 48150}),  # the same setting
        lambda ch: lib.add_copy(ch, d, "D-101"),  # a copy of what was read
        lambda ch: lib.delete(ch, d),
    ):
        ch = Changes()
        make(ch)
        with pytest.raises(DatabaseConflict, match="D-100 was changed in the database after it was read here"):
            save_changes(live, lib, ch)
        assert _sha(live) == before and _files(live) == ["DETEX_New.mdb"]
    # Another setting of it, or another component, is no conflict; the other program's change stays.
    ch = Changes()
    lib.edit(ch, d, {"Compo.Length": 36000})
    lib.edit(ch, r, {"Compo.Height": 5500})
    save_changes(live, lib, ch)
    after = read_library(live)
    assert (after.record(d).values["Compo.Width"], after.record(d).values["Compo.Length"]) == (99999, 36000)
    assert after.record(r).values["Compo.Height"] == 5500


@needs_database
def test_the_file_changing_while_saving_is_a_conflict(live, monkeypatch):
    lib, ch = read_library(live), Changes()
    lib.edit(ch, _id(lib, "D-100"), {"Compo.Width": 48150})
    verify = compolib._verify

    def other_program_writes(saved, expected):
        verify(saved, expected)
        conn = _connect(live)
        conn.cursor().execute("UPDATE Compo SET Height = 777 WHERE CompoName = 'R-400'")
        conn.close()

    monkeypatch.setattr(compolib, "_verify", other_program_writes)
    with pytest.raises(DatabaseConflict, match="changed by another program while"):
        save_changes(live, lib, ch)
    assert _files(live) == ["DETEX_New.mdb"]  # no backup, no half-written copy
    after = read_library(live)
    assert after.record(_id(lib, "R-400")).values["Compo.Height"] == 777  # what the other program wrote
    assert after.record(_id(lib, "D-100")).values["Compo.Width"] == 48140


@needs_database
def test_a_wrong_result_is_not_written(live, monkeypatch):
    """The changed copy is read back; if it is not what was asked for, the database stays."""
    lib, ch = read_library(live), Changes()
    lib.edit(ch, _id(lib, "D-100"), {"Compo.Width": 48150})
    apply = compolib._apply

    def also_breaks_another(cur, pyodbc, library, changes):
        ids = apply(cur, pyodbc, library, changes)
        cur.execute("UPDATE Compo SET Length = 1 WHERE CompoName = 'R-400'")
        return ids

    monkeypatch.setattr(compolib, "_apply", also_breaks_another)
    before = _sha(live)
    with pytest.raises(DatabaseError, match=r"did not come out as asked for \(R-400\)"):
        save_changes(live, lib, ch)
    assert _sha(live) == before and _files(live) == ["DETEX_New.mdb"]


@needs_database
def test_names_stay_unique_and_vision_components_are_left_alone(live):
    lib = read_library(live)
    before = _sha(live)
    ch = Changes()
    lib.edit(ch, _id(lib, "D-100"), {NAME: "r-400"})
    with pytest.raises(DatabaseError, match="Two components are named R-400"):
        save_changes(live, lib, ch)
    q = _id(lib, mdb.NESTED)
    for make, why in (
        (lambda ch: lib.delete(ch, q), "Q-300 has ElementGroup data and cannot be deleted here"),
        (lambda ch: lib.add_copy(ch, q, "Q-301"), "which has ElementGroup data and cannot be copied here"),
    ):
        ch = Changes()
        make(ch)
        with pytest.raises(DatabaseError, match=why):
            save_changes(live, lib, ch)
    # Also when the library does not know (the row was added after it was read).
    lib.nested.clear()
    ch = Changes()
    lib.delete(ch, q)
    with pytest.raises(DatabaseError, match="Q-300 has ElementGroup data and cannot be deleted here; use the Juki"):
        save_changes(live, lib, ch)
    assert _sha(live) == before and _files(live) == ["DETEX_New.mdb"]
    # Its settings can be edited like any other's.
    ch = Changes()
    lib.edit(ch, q, {"Compo.Width": 30000, NAME: "Q-300A"})
    save_changes(live, lib, ch)
    assert read_library(live).record(q).values[NAME] == "Q-300A"


@needs_database
def test_a_unique_value_cannot_be_copied(live):
    conn = _connect(live)
    conn.cursor().execute("UPDATE Expansion SET OCCPickPosAdjustID = 7 WHERE CompoID = 1")
    conn.close()
    lib, ch = read_library(live), Changes()
    before = _sha(live)
    lib.add_copy(ch, 1, "D-101")
    with pytest.raises(DatabaseError, match=r"D-100 could not be copied as D-101 \(.*Expansion: .+Nothing was written"):
        save_changes(live, lib, ch)
    assert _sha(live) == before


@needs_database
def test_backups_are_kept_and_old_ones_pruned(live, tmp_path, monkeypatch):
    monkeypatch.setattr(compolib, "BACKUPS_KEPT", 2)
    backups = tmp_path / "elsewhere"
    backups.mkdir()
    (backups / "DETEX_New 2020-01-01 000000.mdb").write_bytes(b"old")
    (backups / "DETEX_New 2020-01-02 000000.mdb").write_bytes(b"older")
    (backups / "DETEX_New notes.mdb").write_bytes(b"not a backup of this program")
    (backups / "Other 2020-01-01 000000.mdb").write_bytes(b"another database's")
    lib, ch = read_library(live), Changes()
    lib.edit(ch, _id(lib, "D-100"), {"Compo.Width": 48150})
    result = save_changes(live, lib, ch, backup_dir=backups)
    assert sorted(p.name for p in backups.iterdir()) == [
        "DETEX_New 2020-01-02 000000.mdb",
        result.backup.name,
        "DETEX_New notes.mdb",
        "Other 2020-01-01 000000.mdb",
    ]
    assert _files(live) == ["DETEX_New.mdb"]


# ---------------------------------------------------------------------- the lock file
def test_lock_holders(tmp_path):
    path = tmp_path / "DETEX_New.mdb"
    assert lock_holders(path) == []
    slot = lambda computer, user: computer.encode().ljust(32, b" ")[:32].replace(b" ", b"\0", 1) + user.encode().ljust(32)  # noqa: E731
    (tmp_path / "DETEX_New.ldb").write_bytes(
        b"WIN10\0" + b" " * 26 + b"justware\0" + b" " * 23 + slot("LINE-PC", "Admin") + b"WIN10\0" + b" " * 26
        + b"justware\0" + b" " * 23
    )  # fmt: skip
    assert lock_holders(path) == ["WIN10 (justware)", "LINE-PC (Admin)"]
    assert not in_use(path)  # no such file: nothing has it open
