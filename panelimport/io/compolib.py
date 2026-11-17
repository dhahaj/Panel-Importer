"""Read every component of the JaNets component database, and save changes to it.

Like :mod:`panelimport.io.compodb`, this never opens the live database: a copy in a
temporary folder is opened, so this program never takes a slot in the database's
``.ldb`` lock file (two slots from one PC deadlocked JaNets in July).

Saving keeps to that.  The changes are made in a copy, the copy is read back and
compared with what was asked for, the live file is copied to a backup, and only then
is the live file replaced by the changed copy in one step (``os.replace``).  That step
is refused while any program has the database open (Windows does not let an open
``.mdb`` be replaced), so JaNets or the Juki Component Database never has the file
changed under it and nothing written there in the meantime can be lost:

* the database is open somewhere → nothing is written (:class:`DatabaseInUse`);
* a component was changed in the database since it was read here → nothing is
  written (:class:`DatabaseConflict`);
* the file changed while the copy was being prepared → nothing is written.

Only the columns the user changed are written.  A new component is a copy of every
per-component row of another one under a new ``CompoID`` and name; deleting removes
those rows.  Components with rows in tables that are not one row per component (vision
elements, light patterns, …) are neither copied nor deleted here.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from panelimport.io.compodb import DatabaseError, _driver, _message, _pyodbc
from panelimport.model.library import FIELDS, LOOKUPS, NAME, TABLES, Changes, ComponentLibrary, ComponentRecord

KEY = "CompoID"
#: Backups of the database, in this folder next to it; the newest ``BACKUPS_KEPT`` stay.
BACKUP_DIR = "PanelImporter backups"
BACKUPS_KEPT = 50
#: The changed copy next to the live file, just before it replaces it.
STAGED_SUFFIX = ".panelimport-new"
_SLOT = 64  # one user of an .ldb: computer name and security name, 32 bytes each
_SHARING_VIOLATION = 32


class DatabaseInUse(DatabaseError):
    """The database is open in a program; it is only replaced while it is closed."""


class DatabaseConflict(DatabaseError):
    """The database no longer holds what was read here."""


@dataclass
class SaveResult:
    backup: Path
    summary: str
    ids: dict[int, int] = field(default_factory=dict)  # new components: id here → CompoID


# ---------------------------------------------------------------------- who has it open
def lock_holders(path: str | os.PathLike) -> list[str]:
    """Who the database's lock file lists, e.g. ``["WIN10 (justware)"]``; the file can
    outlive its users, so this is a hint (:func:`in_use` is the test)."""
    path = Path(path)
    holders: list[str] = []
    for suffix in (".ldb", ".laccdb"):
        try:
            data = path.with_suffix(suffix).read_bytes()
        except OSError:
            continue
        for i in range(0, len(data) - _SLOT + 1, _SLOT):
            computer, user = (_slot_text(data[i + j : i + j + 32]) for j in (0, 32))
            who = f"{computer} ({user})" if user else computer
            if computer and who not in holders:
                holders.append(who)
    return holders


def _slot_text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", "replace").strip()


def in_use(path: str | os.PathLike) -> bool:
    """Whether a program has the file open (Windows; elsewhere always False)."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE,
    ]  # fmt: skip
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    # GENERIC_READ, share with nobody, OPEN_EXISTING: fails while anyone has it open.
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        return ctypes.get_last_error() == _SHARING_VIOLATION
    kernel32.CloseHandle(handle)
    return False


def _require_closed(path: Path) -> None:
    if in_use(path):
        who = lock_holders(path)
        raise DatabaseInUse(
            f"{path.name} is open in another program"
            + (f" ({', '.join(who)})" if who else "")
            + ". Close JaNets and the Juki Component Database on every PC that has it open, then save again. "
            "Nothing was written."
        )


# ---------------------------------------------------------------------- reading
def read_library(path: str | os.PathLike) -> ComponentLibrary:
    """Every component of the database at ``path``, read from a copy."""
    path = Path(path)
    if not path.is_file():
        raise DatabaseError(f"The component database {path} was not found")
    pyodbc = _pyodbc()
    driver = _driver(pyodbc)
    with tempfile.TemporaryDirectory(prefix="panelimport-db-", ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / "components.mdb"
        try:
            shutil.copyfile(path, copy)
        except OSError as exc:
            raise DatabaseError(f"The component database {path} could not be copied: {exc}") from None
        return _read_copy(pyodbc, driver, copy, path)


def _connect(pyodbc, driver: str, copy: Path, path: Path, read_only: bool):
    options = "ReadOnly=1;" if read_only else ""
    try:
        return pyodbc.connect(f"DRIVER={{{driver}}};DBQ={copy};{options}", readonly=read_only, autocommit=read_only)
    except pyodbc.Error as exc:
        raise DatabaseError(f"{path} could not be opened as an Access database: {_message(exc)}") from None


def _read_copy(pyodbc, driver: str, copy: Path, path: Path) -> ComponentLibrary:
    conn = _connect(pyodbc, driver, copy, path, read_only=True)
    try:
        return _read(conn.cursor(), pyodbc, path)
    except pyodbc.Error as exc:
        raise DatabaseError(f"{path} could not be read as a component database: {_message(exc)}") from None
    finally:
        conn.close()


def _read(cur, pyodbc, path: Path) -> ComponentLibrary:
    read_at = datetime.now().isoformat(timespec="seconds")
    columns = {table: _columns(cur, pyodbc, table) for table in TABLES}
    if NAME.split(".")[1] not in (columns["Compo"] or ()):
        raise DatabaseError(f"{path} has no component table (Compo)")
    records: dict[int, ComponentRecord] = {}
    present: set[str] = set()
    for table in TABLES:  # Compo first: it says which components there are
        have = [f for f in FIELDS if f.table == table and f.column in (columns[table] or ())]
        if not have:
            continue
        present.update(f.key for f in have)
        select = ", ".join(f"[{c}]" for c in [KEY] + [f.column for f in have])
        for row in cur.execute(f"SELECT {select} FROM [{table}]").fetchall():
            if table == "Compo":
                records[row[0]] = ComponentRecord(row[0])
            record = records.get(row[0])
            if record is not None:  # rows of components that are gone are left alone
                record.values.update((f.key, _value(v)) for f, v in zip(have, row[1:]))
    lookups: dict[str, dict[int, str]] = {}
    for name, (table, id_column, text_column) in LOOKUPS.items():
        try:
            rows = cur.execute(f"SELECT [{id_column}], [{text_column}] FROM [{table}]").fetchall()
        except pyodbc.Error:
            rows = []
        lookups[name] = {int(i): str(text).strip() for i, text in rows if i is not None and text}
    _per_component, nested_tables = _component_tables(cur, pyodbc)
    nested: dict[int, list[str]] = {}
    for table in nested_tables:
        for (compo_id,) in cur.execute(f"SELECT DISTINCT [{KEY}] FROM [{table}]").fetchall():
            if compo_id in records:
                nested.setdefault(compo_id, []).append(table)
    return ComponentLibrary(
        path=str(path),
        read_at=read_at,
        records=sorted(records.values(), key=lambda r: r.name.upper()),
        lookups=lookups,
        fields=frozenset(present),
        nested=nested,
    )


def _value(value):
    return float(value) if isinstance(value, Decimal) else value


def _columns(cur, pyodbc, table: str) -> list[str] | None:
    """The table's columns; None when the database has no such table."""
    try:
        cur.execute(f"SELECT * FROM [{table}] WHERE 1 = 0")
    except pyodbc.Error:
        return None
    return [d[0] for d in cur.description]


def _component_tables(cur, pyodbc) -> tuple[dict[str, list[str]], list[str]]:
    """The tables with a ``CompoID``: those with one row per component (a unique index
    on ``CompoID`` alone) with their columns, ``Compo`` first; and the names of the
    others, whose rows hang together in ways only the Juki editor knows."""
    per_component: dict[str, list[str]] = {}
    nested: list[str] = []
    for name in sorted(t.table_name for t in cur.tables(tableType="TABLE")):
        columns = _columns(cur, pyodbc, name)
        if not columns or KEY not in columns:
            continue
        unique: dict[str, list[str]] = {}
        for s in cur.statistics(name):
            if s.index_name and not s.non_unique:
                unique.setdefault(s.index_name, []).append(s.column_name)
        if [KEY] in unique.values():
            per_component[name] = columns
        else:
            nested.append(name)
    ordered = {t: per_component[t] for t in sorted(per_component, key=lambda t: (t != "Compo", t))}
    return ordered, nested


# ---------------------------------------------------------------------- saving
def save_changes(
    path: str | os.PathLike, library: ComponentLibrary, changes: Changes, backup_dir: str | os.PathLike | None = None
) -> SaveResult:
    """Write ``changes`` (made to ``library``) to the database at ``path``; see the
    module's description.  Raises :class:`DatabaseError` with nothing written."""
    path = Path(path)
    if not changes:
        raise DatabaseError("There are no changes to save")
    problems = library.problems(changes)
    if problems:
        raise DatabaseError("\n".join(problems))
    if not path.is_file():
        raise DatabaseError(f"The component database {path} was not found")
    _require_closed(path)
    pyodbc = _pyodbc()
    driver = _driver(pyodbc)
    with tempfile.TemporaryDirectory(prefix="panelimport-db-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp) / "components.mdb"
        try:
            shutil.copyfile(path, work)
        except OSError as exc:
            raise DatabaseError(f"The component database {path} could not be copied: {exc}") from None
        before = _sha256(work)
        conn = _connect(pyodbc, driver, work, path, read_only=False)
        try:
            # What the database holds now: the library, unless another program changed it since.
            current = _read(conn.cursor(), pyodbc, path)
            ids = _apply(conn.cursor(), pyodbc, library, changes)
            conn.commit()
        except pyodbc.Error as exc:
            conn.rollback()
            raise DatabaseError(f"The changes could not be made: {_message(exc)}. Nothing was written.") from None
        except DatabaseError:
            conn.rollback()
            raise
        finally:
            conn.close()
        _verify(_read_copy(pyodbc, driver, work, path), current.expected(changes, ids))
        backup = _swap(path, work, before, Path(backup_dir) if backup_dir else path.parent / BACKUP_DIR)
    return SaveResult(backup=backup, summary=changes.summary(), ids=ids)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apply(cur, pyodbc, library: ComponentLibrary, changes: Changes) -> dict[int, int]:
    tables, nested = _component_tables(cur, pyodbc)
    if "Compo" not in tables:
        raise DatabaseError("The database has no component table (Compo). Nothing was written.")
    for compo_id in sorted(changes.deleted):
        record = library.record(compo_id)
        _unchanged(cur, library, record, record.values)
        _no_nested_rows(cur, nested, record, "deleted")
        stuck = _each(
            pyodbc,
            [t for t in tables if t != "Compo"] + ["Compo"],
            lambda table, compo_id=compo_id: cur.execute(f"DELETE FROM [{table}] WHERE [{KEY}] = ?", compo_id),
        )
        left = [
            t for t in tables if cur.execute(f"SELECT COUNT(*) FROM [{t}] WHERE [{KEY}] = ?", compo_id).fetchone()[0]
        ]
        if stuck or left:
            raise DatabaseError(
                f"{record.name} could not be deleted ({_why(stuck) or ', '.join(left)}). Nothing was written."
            )
    ids: dict[int, int] = {}
    next_id = 1 + max(
        cur.execute(f"SELECT MAX([{KEY}]) FROM [{t}]").fetchone()[0] or 0 for t in [*tables, *nested]
    )
    for new_id in sorted(changes.added, reverse=True):  # in the order they were added
        source = library.record(changes.added[new_id])
        _unchanged(cur, library, source, source.values)
        _no_nested_rows(cur, nested, source, "copied")
        _copy(cur, pyodbc, tables, source, next_id, changes.updates[new_id][NAME])
        ids[new_id] = next_id
        next_id += 1
    for compo_id, values in changes.updates.items():
        if compo_id in changes.deleted:
            continue
        record = library.record(compo_id)
        if compo_id not in ids:
            _unchanged(cur, library, record, {key: record.values.get(key) for key in values})
        name = values.get(NAME) or record.name if record else values[NAME]
        for table in TABLES:
            columns = {key.split(".", 1)[1]: v for key, v in values.items() if key.split(".", 1)[0] == table}
            if not columns:
                continue
            assign = ", ".join(f"[{c}] = ?" for c in columns)
            cur.execute(f"UPDATE [{table}] SET {assign} WHERE [{KEY}] = ?", *columns.values(), ids.get(compo_id, compo_id))
            if cur.rowcount != 1:
                raise DatabaseConflict(
                    f"{name} has no row in {table} to change; set it up in the Juki Component Database. "
                    "Nothing was written."
                )
    return ids


def _unchanged(cur, library: ComponentLibrary, record: ComponentRecord, values: dict[str, object]) -> None:
    """Stop when the database no longer holds ``values`` for ``record``."""
    for table in TABLES:
        keys = [key for key in values if key.split(".", 1)[0] == table and key in library.fields]
        if not keys:
            continue
        select = ", ".join(f"[{key.split('.', 1)[1]}]" for key in keys)
        row = cur.execute(f"SELECT {select} FROM [{table}] WHERE [{KEY}] = ?", record.compo_id).fetchone()
        if row is None or any(not _same(_value(now), values[key]) for key, now in zip(keys, row)):
            raise DatabaseConflict(
                f"{record.name} was changed in the database after it was read here. Reload the database and make "
                "the changes again. Nothing was written."
            )


def _same(a, b) -> bool:
    return a == b and (a is None) == (b is None)


def _no_nested_rows(cur, nested: list[str], record: ComponentRecord, what: str) -> None:
    for table in nested:
        if cur.execute(f"SELECT COUNT(*) FROM [{table}] WHERE [{KEY}] = ?", record.compo_id).fetchone()[0]:
            raise DatabaseError(
                f"{record.name} has {table} data and cannot be {what} here; use the Juki Component Database. "
                "Nothing was written."
            )


def _each(pyodbc, tables: list[str], action) -> list[tuple[str, Exception]]:
    """Run ``action(table)`` for every table, putting off the ones a relationship holds
    back until the others are done.  Returns the tables that never went through, with
    why."""
    pending = list(tables)
    while pending:
        failed: list[tuple[str, Exception]] = []
        for table in pending:
            try:
                action(table)
            except pyodbc.IntegrityError as exc:
                failed.append((table, exc))
        if len(failed) == len(pending):
            return failed
        pending = [table for table, _exc in failed]
    return []


def _why(stuck: list[tuple[str, Exception]]) -> str:
    return "; ".join(f"{table}: {_message(exc)}" for table, exc in stuck[:3])


def _copy(cur, pyodbc, tables: dict[str, list[str]], source: ComponentRecord, new_id: int, name: str) -> None:
    """Copy every per-component row of ``source`` under ``new_id``: ``Compo`` first, the
    rest in whatever order their relationships allow."""

    def copy_row(table: str) -> None:
        columns = tables[table]
        row = cur.execute(f"SELECT * FROM [{table}] WHERE [{KEY}] = ?", source.compo_id).fetchone()
        if row is None:
            return
        values = list(row)
        values[columns.index(KEY)] = new_id
        if table == "Compo":
            values[columns.index("CompoName")] = name
        names = ", ".join(f"[{c}]" for c in columns)
        marks = ", ".join("?" for _ in columns)
        cur.execute(f"INSERT INTO [{table}] ({names}) VALUES ({marks})", values)

    stuck = _each(pyodbc, ["Compo"], copy_row) or _each(pyodbc, [t for t in tables if t != "Compo"], copy_row)
    if stuck:
        raise DatabaseError(f"{source.name} could not be copied as {name} ({_why(stuck)}). Nothing was written.")


def _verify(saved: ComponentLibrary, expected: dict[int, dict[str, object]]) -> None:
    """The changed copy, read back, must hold exactly what was asked for."""
    found = {r.compo_id: r.values for r in saved.records}
    wrong = sorted(set(found) ^ set(expected))
    for compo_id in set(found) & set(expected):
        if any(not _same(found[compo_id].get(key), value) for key, value in expected[compo_id].items()):
            wrong.append(compo_id)
    if wrong:
        names = sorted({str((expected.get(i) or found.get(i) or {}).get(NAME) or i) for i in wrong})
        raise DatabaseError(
            "The changed copy of the database did not come out as asked for "
            f"({', '.join(names[:5])}{', …' if len(names) > 5 else ''}). Nothing was written."
        )


def _swap(path: Path, work: Path, before: str, backup_dir: Path) -> Path:
    """Back the live database up and replace it with ``work``, unless it is open or is
    no longer the file ``work`` was copied from (hash ``before``)."""
    staged = path.with_name(path.name + STAGED_SUFFIX)
    try:
        shutil.copyfile(work, staged)
        if _sha256(path) != before:
            raise DatabaseConflict(
                f"{path.name} was changed by another program while the changes were being saved. Reload the "
                "database and save again. Nothing was written."
            )
        _require_closed(path)
        backup = _backup(path, backup_dir)
        try:
            os.replace(staged, path)
        except OSError:
            backup.unlink(missing_ok=True)
            _require_closed(path)  # the usual reason: it was opened just now
            raise
    except OSError as exc:
        raise DatabaseError(f"{path} could not be written: {exc}. Nothing was written.") from None
    finally:
        staged.unlink(missing_ok=True)
    _prune(backup_dir, path)
    return backup


def _backup(path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
    backup = backup_dir / f"{path.stem} {stamp}{path.suffix}"
    n = 1
    while backup.exists():
        n += 1
        backup = backup_dir / f"{path.stem} {stamp}-{n}{path.suffix}"
    shutil.copy2(path, backup)
    return backup


def _prune(backup_dir: Path, path: Path) -> None:
    """Keep the newest ``BACKUPS_KEPT`` backups this program made of ``path``."""
    made = re.compile(re.escape(path.stem) + r" \d{4}-\d\d-\d\d \d{6}(-\d+)?" + re.escape(path.suffix), re.IGNORECASE)
    try:
        backups = sorted(p for p in backup_dir.iterdir() if p.is_file() and made.fullmatch(p.name))
    except OSError:
        return
    for old in backups[:-BACKUPS_KEPT]:
        try:
            old.unlink()
        except OSError:
            pass
