"""A small JaNets-like component database: as a library in memory, and as a real Access
file made through the ODBC driver (Windows with the Access Database Engine only).

The tables and columns are the real database's that the program reads, plus what makes
copying and deleting hard: a binary column, a table that sorts before the one its rows
depend on (``Adjust`` → ``Expansion``), a unique column and a table that is not one row
per component (``ElementGroup``).
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from panelimport.io import compodb
from panelimport.model.library import FIELD, FIELDS, FLAG, NAME, TEXT, ComponentLibrary, ComponentRecord

#: Part 101672-10 of DETEX_New.mdb, as the Juki editor's screenshots show it.
BASE: dict[str, object] = {
    "Compo.Description": "DIODE, SCHOTTKY, 60V 5A", "Compo.PkgType": None, "Compo.PkgClassID": 1,
    "Compo.Rx7ComponentType": 1, "Feeder.FdrTypeID": 1, "Compo.Width": 48140, "Compo.Length": 35840,
    "Compo.Height": 2, "Compo.UsePackage": 0, "Compo.PackageWidth": None, "Compo.PackageLength": None,
    "Compo.UseLaser": True, "Compo.UseVision": False, "Compo.GX4PriorityLV": 0,
    "Feeder.TapeTypeID": 3, "Feeder.Pitch": 8, "Feeder.TapeAngle": 0, "Feeder.SpliceSensorUse": 0,
    "Feeder.StickTypeID": None, "Feeder.StickChangerType": None,
    "Expansion.ScrapTypeGx6": 0, "Expansion.ScrapType": 0,
    "Laser.LaserHeight": -11650, "Laser.LaserAlgo": 1, "Laser.GX4PreRotate": 2400,
    "LaserGx10.Gx10LA": 1, "LaserGx10.NozzleNo": 504, "LaserGx10.PumpVacuum": 217,
    "LaserGx10.SpdXY": 4, "LaserGx10.SpdPickDownZ": 4, "LaserGx10.SpdPickUpZ": 4, "LaserGx10.SpdPlaceDownZ": 4,
    "LaserGx10.SpdPlaceUpZ": 4, "LaserGx10.SpdPlaceDownZGx10V": 4, "LaserGx10.SpdPlaceUpZGx10V": 4,
    "LaserGx10.SpdThetaInLA": 0, "LaserGx10.SpdTheta": 0,
    "Laser.Gx10LaserHeightLnc60": -11650, "LaserGx10.CompoShape": 2,
    "Expansion.Retry": 1, "Expansion.PickPosAdjust": False, "Expansion.EtfPickPosAdjust": True,
    "Expansion.AutoTeach": 0, "Expansion.FCTypePickGx10": 0, "Expansion.OverPickGx10": 2000,
    "LaserGx10.PickZ2StepUse": 0, "LaserGx10.PickZ2StepDown": 20000, "LaserGx10.PickZ2StepUp": 5000,
    "Expansion.OverPickJM10": 2000,
    "Expansion.Test": False, "Expansion.CompoCheck": False, "Expansion.CompoLayer": 4,
    "Expansion.FCTypePlaceGx10": 0, "Expansion.OverPlaceGx10": 5000,
    "LaserGx10.PlaceZ2StepUse": 0, "LaserGx10.PlaceZ2StepDown": 7000, "LaserGx10.PlaceZ2StepUp": 20000,
    "Inspection.ChipStandCheck": 2,
}  # fmt: skip
#: The components by name (CompoID 1, 2, 3, 4 in this order), as differences from ``BASE``.
COMPONENTS: dict[str, dict[str, object]] = {
    "D-100": {},
    "U-200": {
        "Compo.Description": "MICRO, PROGRAMMED", "Compo.PkgClassID": 101, "Compo.Rx7ComponentType": 2,
        "Compo.Width": 60000, "Compo.Length": 49000, "Compo.Height": 17500, "Compo.GX4PriorityLV": 1,
        "Feeder.FdrTypeID": 2, "Feeder.TapeTypeID": None, "Feeder.Pitch": None, "Feeder.TapeAngle": None,
        "Feeder.StickTypeID": 13, "Feeder.StickChangerType": 221,
        "Laser.LaserAlgo": 2, "LaserGx10.NozzleNo": 506, "LaserGx10.CompoShape": 4,
        "LaserGx10.SpdPlaceUpZ": 2, "LaserGx10.SpdPlaceDownZ": 1, "Inspection.ChipStandCheck": 0,
    },
    "Q-300": {
        "Compo.Description": "N-CHANNEL MOSFET", "Compo.PkgClassID": 11, "Compo.Rx7ComponentType": 2,
        "Compo.PkgType": "SOT23", "Feeder.TapeTypeID": 2, "Feeder.Pitch": 4, "Inspection.ChipStandCheck": 1,
    },
    "R-400": {
        "Compo.Description": "RES SMD 470 OHM 1% 1/8W 0805", "Compo.Width": 20000, "Compo.Length": 12500,
        "Compo.Height": 5000, "Compo.UsePackage": 1, "Compo.PackageWidth": 20000, "Compo.PackageLength": 12500,
        "Feeder.TapeTypeID": 1, "Feeder.Pitch": 4, "Feeder.TapeAngle": 21600, "Feeder.SpliceSensorUse": 1,
        "LaserGx10.NozzleNo": 503, "Inspection.ChipStandCheck": 0,
    },
}  # fmt: skip
LOOKUPS = {
    "pkg_class": {1: "Chip", 11: "SOT", 101: "SOP"},
    "feeder_type": {1: "Tape", 2: "Stick"},
    "tape_type": {1: "8mm paper", 2: "8mm emboss", 3: "12mm emboss", 4: "16mm emboss"},
}
#: The component with vision data (a row in ``ElementGroup``).
NESTED = "Q-300"
PICTURE = bytes(range(256)) * 4
DRIVER = compodb.DRIVERS[0]


def values_of(name: str) -> dict[str, object]:
    return {NAME: name, **BASE, **COMPONENTS[name]}


def sample_library(path: str = r"C:\ComponentDatabase\Data\DETEX_New.mdb") -> ComponentLibrary:
    """What reading :func:`make_database` gives, without a database."""
    records = [ComponentRecord(i, values_of(name)) for i, name in enumerate(COMPONENTS, start=1)]
    return ComponentLibrary(
        path=path,
        read_at="2026-11-16T10:02:00",
        records=sorted(records, key=lambda r: r.name.upper()),
        lookups={name: dict(rows) for name, rows in LOOKUPS.items()},
        nested={list(COMPONENTS).index(NESTED) + 1: ["ElementGroup"]},
    )


def unavailable() -> str:
    """Why no database can be made here; "" when one can."""
    if sys.platform != "win32":
        return "Access databases are made and read on Windows only"
    return compodb.unavailable()


def _column_type(key: str) -> str:
    f = FIELD[key]
    if f.kind == TEXT:
        return f"TEXT({f.max_length or 50})"
    return "YESNO" if f.kind == FLAG and isinstance(BASE[key], bool) else "LONG"


def make_database(path: Path) -> Path:
    """Write the database to ``path`` (which must not exist)."""
    import pyodbc

    created = ctypes.WinDLL("odbccp32").SQLConfigDataSourceW(
        None, 1, DRIVER, ctypes.create_unicode_buffer(f"CREATE_DBV4={path} General\0")  # Jet 4, like the real one
    )
    if not created or not path.is_file():
        raise RuntimeError(f"The Access driver did not create {path}")
    conn = pyodbc.connect(f"DRIVER={{{DRIVER}}};DBQ={path};", autocommit=True)
    cur = conn.cursor()
    extra = {
        "Compo": ", Picture LONGBINARY, EditTime DATETIME",
        "Expansion": ", OCCPickPosAdjustID LONG",
    }
    tables = list(dict.fromkeys(f.table for f in FIELDS))
    for table in tables:
        columns = ", ".join(f"[{f.column}] {_column_type(f.key)}" for f in FIELDS if f.table == table)
        key = "COUNTER" if table == "Compo" else "LONG"
        parent = "" if table == "Compo" else f", CONSTRAINT Compo{table} FOREIGN KEY (CompoID) REFERENCES Compo (CompoID)"
        cur.execute(
            f"CREATE TABLE [{table}] (CompoID {key} CONSTRAINT PrimaryKey PRIMARY KEY, {columns}"
            f"{extra.get(table, '')}{parent})"
        )
    cur.execute("CREATE UNIQUE INDEX CompoName ON Compo (CompoName)")
    cur.execute("CREATE UNIQUE INDEX OCCPickPosAdjustID ON Expansion (OCCPickPosAdjustID)")
    cur.execute(
        "CREATE TABLE Adjust (CompoID LONG CONSTRAINT PrimaryKey PRIMARY KEY, Stroke LONG, "
        "CONSTRAINT ExpansionAdjust FOREIGN KEY (CompoID) REFERENCES Expansion (CompoID))"
    )
    cur.execute("CREATE TABLE ElementGroup (ElementGroupID COUNTER CONSTRAINT PrimaryKey PRIMARY KEY, CompoID LONG)")
    cur.execute("CREATE INDEX CompoID ON ElementGroup (CompoID)")
    cur.execute("CREATE TABLE PkgClass (PkgClassID LONG CONSTRAINT PrimaryKey PRIMARY KEY, EngClass TEXT(50))")
    cur.execute("CREATE TABLE FeederType (FdrTypeID LONG CONSTRAINT PrimaryKey PRIMARY KEY, FdrTypeEng TEXT(50))")
    cur.execute("CREATE TABLE Lookup (ID COUNTER CONSTRAINT PrimaryKey PRIMARY KEY, TapeTypeID LONG, TapeType TEXT(50))")
    for table, id_column, text_column, rows in (
        ("PkgClass", "PkgClassID", "EngClass", LOOKUPS["pkg_class"]),
        ("FeederType", "FdrTypeID", "FdrTypeEng", LOOKUPS["feeder_type"]),
        ("Lookup", "TapeTypeID", "TapeType", LOOKUPS["tape_type"]),
    ):
        for code, text in rows.items():
            cur.execute(f"INSERT INTO [{table}] ([{id_column}], [{text_column}]) VALUES (?, ?)", code, text)
    for compo_id, name in enumerate(COMPONENTS, start=1):
        values = values_of(name)
        for table in tables:
            row = {f.column: values[f.key] for f in FIELDS if f.table == table}
            if table == "Compo":
                row["Picture"] = PICTURE if name == "D-100" else None
            else:
                row["CompoID"] = compo_id
            names = ", ".join(f"[{c}]" for c in row)
            cur.execute(f"INSERT INTO [{table}] ({names}) VALUES ({', '.join('?' for _ in row)})", *row.values())
        cur.execute("INSERT INTO Adjust (CompoID, Stroke) VALUES (?, ?)", compo_id, 100 * compo_id)
    cur.execute("INSERT INTO ElementGroup (CompoID) VALUES (?)", list(COMPONENTS).index(NESTED) + 1)
    conn.close()
    return path
