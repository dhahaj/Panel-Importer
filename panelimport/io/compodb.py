"""Read the JaNets component database (an Access ``.mdb``, table ``Compo``).

The live database is never opened: it is copied to a temporary folder and the copy is
read, so this program never takes a slot in the database's ``.ldb`` lock file (two
slots from one PC deadlocked JaNets in July).  The copy is opened read-only through
the Microsoft Access ODBC driver; Detex's database is an encoded Jet 4 file, which
pure-Python readers cannot read.  Windows only: ``pyodbc`` and the driver whose
bitness matches this program's (the Access Database Engine).

``Width``, ``Length`` and ``Height`` are integers in 0.0001 mm: every size CircuitCAM
wrote in the reference programs is the database's divided by 10000.
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
from datetime import datetime
from pathlib import Path

from panelimport.model.database import ComponentDatabase, DatabasePart

#: Access ODBC drivers, preferred first.
DRIVERS = ("Microsoft Access Driver (*.mdb, *.accdb)", "Microsoft Access Driver (*.mdb)")
#: Compo sizes per mm.
UNITS_PER_MM = 10000
QUERY = "SELECT CompoName, Description, PkgType, Width, Length, Height FROM Compo"


class DatabaseError(Exception):
    pass


def read_database(path: str | os.PathLike) -> ComponentDatabase:
    """Every component record of the database at ``path`` (``whole``)."""
    path = Path(path)
    if not path.is_file():
        raise DatabaseError(f"The component database {path} was not found")
    pyodbc = _pyodbc()
    driver = _driver(pyodbc)
    read_at = datetime.now().isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory(prefix="panelimport-db-", ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / "components.mdb"
        try:
            shutil.copyfile(path, copy)
        except OSError as exc:
            raise DatabaseError(f"The component database {path} could not be copied: {exc}") from None
        try:
            conn = pyodbc.connect(f"DRIVER={{{driver}}};DBQ={copy};ReadOnly=1;", readonly=True, autocommit=True)
        except pyodbc.Error as exc:
            raise DatabaseError(f"{path} could not be opened as an Access database: {_message(exc)}") from None
        try:
            rows = conn.cursor().execute(QUERY).fetchall()
        except pyodbc.Error as exc:
            raise DatabaseError(f"{path} has no component table (Compo) with the expected columns: {_message(exc)}") from None
        finally:
            conn.close()
    parts = [
        DatabasePart(
            name=(name or "").strip(),
            description=(description or "").strip(),
            pkg_type=(pkg_type or "").strip(),
            width=_mm(width),
            length=_mm(length),
            height=_mm(height),
        )
        for name, description, pkg_type, width, length, height in rows
        if (name or "").strip()
    ]
    return ComponentDatabase(path=str(path), read_at=read_at, parts=parts, whole=True)


def unavailable() -> str:
    """Why no component database can be read on this PC; "" when one can."""
    try:
        _driver(_pyodbc())
    except DatabaseError as exc:
        return str(exc)
    return ""


def _mm(value) -> float:
    return round((value or 0) / UNITS_PER_MM, 4)


def _message(exc: Exception) -> str:
    return str(exc.args[-1] if exc.args else exc)


def _pyodbc():
    try:
        import pyodbc
    except ImportError:
        raise DatabaseError(
            "Reading the component database needs pyodbc and the Microsoft Access ODBC driver (Windows only)"
        ) from None
    return pyodbc


def _driver(pyodbc) -> str:
    installed = set(pyodbc.drivers())
    for name in DRIVERS:
        if name in installed:
            return name
    bits = struct.calcsize("P") * 8
    raise DatabaseError(
        f"No Microsoft Access ODBC driver for {bits}-bit programs is installed; install the {bits}-bit "
        "Microsoft Access Database Engine to read the component database"
    )
