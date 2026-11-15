# Component database: design and plan

Approved 2026-11-14. Most of Detex's component data lives in the JaNets component
database (`C:\ComponentDatabase\Data\DETEX.mdb`). This work reads the component
records from it (part number/`CompoName`, `Description`, `PkgType`, width, length,
height), shows them with the components and uses them in the ISS program.

This reverses an earlier rule ("the tool never opens a component database", from the
July `DETEX_New.ldb` deadlock): the tool reads a **copy** of the database and never
opens the live file, and Phase 2 still reads only the project file.

## What the database and the reference programs prove

| Fact | Evidence |
| --- | --- |
| Table `Compo`, one row per component, `CompoName` unique (211 rows, no duplicates, also case-insensitively) | `tests/fixtures/DETEX.mdb` |
| `Width`, `Length`, `Height` are integers in 0.0001 mm | every size CircuitCAM wrote equals the database's ÷ 10000: 12 components in `ER_RevF8_circuitcam.iss`, 4 in `102628_portrait_circuitcam.iss`; parts the database lacks were written as 0 |
| CircuitCAM writes them unswapped (`witdh` = `Width`) | same programs |
| JaNets writes `Description` as the component comment | `102605_janets.iss` (`DIODE SIGNAL (250mA)` = `PP-5932-1`) |
| `PkgType` is Juki's package (tape) name, not the footprint: an 0603 cap has `1206`; empty for 104 of 211 | `DETEX.mdb` |
| The file is an encoded Jet 4 database: pure-Python readers (access-parser) fail; the Access ODBC driver reads it | tried both |

`PkgType` belongs to `model/componentData/packageData`, which the writer leaves out
(stubs there hung JaNets), so it is shown, never written.

## Reading (`panelimport/io/compodb.py`, no Qt)

* Setting: the `database` section of the settings file, `{"path": "..."}`; empty = off.
  It is per PC and not copied into projects. Edit → Settings has a *Component database*
  group: path, Browse…, Test.
* `read_database(path)`: copy the `.mdb` to a temporary folder (the live file is read
  as bytes only, so the tool never takes a slot in `DETEX.ldb`), open the copy
  read-only with the Access ODBC driver, `SELECT CompoName, Description, PkgType,
  Width, Length, Height FROM Compo`, close, delete the folder.
* `pyodbc` on Windows only; the 64-bit program needs the 64-bit driver
  (`Microsoft Access Driver (*.mdb, *.accdb)`, the Access Database Engine). Elsewhere,
  or without the driver, a clear `DatabaseError`; the import continues without
  database data (`database_unavailable`, info).

## Snapshot in the project

* `ComponentDatabase` (path, read time, `parts`, `missing`) and `DatabasePart` (name,
  description, pkg_type, width, length, height in mm) in `model/database.py`.
* `Decisions.component_database` holds it. Right after a read it is the whole database
  (`whole`: every name not in `parts` is missing). The project stores only what its
  components need: the records found and the names not found. On reopen, a name in
  neither (e.g. a part number typed after the read) is *not looked up*.
* Matching: the component name JaNets looks up (part number, else part name),
  stripped, case-insensitive (Jet compares text case-insensitively).
* Read on import (GUI and `panelimport analyze`) when a database is configured, and on
  **Update from database** (Components tab, Edit menu; undoable). Reopening a project
  uses its stored snapshot, so `verify` reproduces it.
* Project file version 5 adds `component_database`; a project without one is written
  as before (version 3 or 4), so older builds still open it.

## Precedence (sizes)

Per dimension: a size edited in Phase 1 (> 0) → the database's (> 0) → the export's
body size → 0. The same rule in the Components tab, the CSV, the inspector and the
ISS. Database sizes are in the machine's frame, so an `angle_offset` of ±90° does not
swap them (it still swaps export and edited sizes). A dimension taken from the
database is not a `component_size_differs` conflict.

## ISS

* `componentSize`: the precedence above (`component_size = body`).
* `comment`: the database's `Description`, else the `comment_attributes`, else the part
  name.
* `component_not_in_database` (warning): components the database does not have; they
  need a JaNets record before the program runs. `component_not_looked_up` (warning):
  names the snapshot never checked.

## Display

* Components tab: columns *Description*, *Juki package* and *Database* (found, not
  found, not looked up); sizes taken from the database are blue with the export's in
  the tooltip; the count line says how many components the database has. **Update from
  database** button.
* Edit dialog: **From database…** next to the part number searches `CompoName` and
  `Description` and sets the part number (an ordinary part-number edit, with the read
  database in the same undo step). The size note shows the database's size.
* Inspector: description, Juki package, database state.
* Components CSV: the tab's columns.
* Issues: `not_in_database` (info, per component name), `database_not_looked_up`
  (info), `database_unavailable` (info).

## Tests

* Reader against `tests/fixtures/DETEX.mdb` (skipped without the file, `pyodbc` or the
  driver): rows, units, the fixture unchanged and no lock file next to it; the
  CircuitCAM programs' sizes equal the database's.
* With an in-memory database (no driver): matching, snapshot pruning and states,
  project v5 round trip and v3/v4 unchanged, precedence per dimension, no swap at ±90°,
  comment, the checks, CSV and GUI (settings group, update, picker, undo). Golden ISS
  bytes unchanged for projects without a snapshot.
