# Panel Importer — Phase 1

Desktop tool that imports an Altium **panel** exported as **ODB++** and identifies the
panel: circuit count, step-and-repeat, circuit 1, every placement in circuit-relative
coordinates, and the fiducials. The confirmed panel is saved as `<name>.panel.json`,
which Phase 2 (ISS output) reads. Phase 1 writes no machine program and never changes
the export.

```
import ODB++ → automatic detection → review issues → confirm panel → pick fiducials
            → add, edit or remove components (optional) → save project
```

## Running it

Requires Python 3.12.

```bash
pip install -e ".[dev]"          # PySide6, shapely, numpy, unlzw3, pytest, PyInstaller
panelimport-gui                  # the GUI (or: python -m panelimport)
panelimport analyze Panel.tgz    # the same summary and issues the GUI shows
panelimport analyze Panel.tgz --components-csv parts.csv   # also write the components
panelimport verify Panel.panel.json   # saved project vs. its source (SHA-256 + re-analysis)
```

`panelimport analyze` options: `--panel-step`, `--board-step`, `--first` (corner of
circuit 1), `--order`, `--reference`, `--copy-suffix REGEX`, `--part-number-attribute`,
`--panel-level FID1,FID2`, `--bom bom.csv`, `--components-csv FILE`, `--settings file.json`,
`--json`, `-v`.
Exit code 0 = no errors, 1 = errors found, 2 = could not open.

### Windows build (no Python needed on the target machine)

```bash
pyinstaller packaging/panelimport.spec --noconfirm
```

produces `dist/PanelImporter/` with `PanelImporter.exe` (GUI) and `panelimport.exe`
(command line). Copy the whole folder; no installation or admin rights. The
`build` GitHub Actions workflow builds this folder on `windows-latest`, runs both
executables with Python removed from `PATH`, and uploads the folder as the
`PanelImporter-windows` artifact.

## Using the GUI

* **File → Import ODB++…** — choose the ODB++ folder, `.tgz` or `.zip`. The dialog lists
  the steps and layers with the detected panel step, board step and layer roles;
  correct them if needed. The last location is remembered.
* **Canvas** — middle-drag pans, the wheel zooms toward the cursor, `F` fits the panel,
  `M` measures (two clicks: ΔX, ΔY, distance; snaps to markers), `B` views from the
  bottom (display only). Layers toggle on the left. Hovering a centroid shows designator,
  part, package, layer, rotation (normalized and raw) and panel/circuit coordinates; the
  status bar shows the cursor's panel and circuit-relative coordinates.
* **Circuits** tab — offsets, rotation, mirror, source and residual per circuit; choose
  the corner of circuit 1, the numbering order and the reference point.
* **Components** tab — circuit 1's placements and the panel-level parts, sortable,
  filterable and searchable; pick the attribute that holds the part number. Selecting a
  row selects the part on the canvas and vice versa. Components can be edited here (see
  [Component edits](#component-edits)): **Add…** (`Insert`), **Edit…** (`F2` or
  double-click; several rows at once change part name, part number or package),
  **Remove…** (`Delete`), **Restore**, **Revert** and **Find ▾**, which lists
  through-hole, not-populated, fiducial/mechanical and not-in-BOM parts for review.
  Edited values are amber (the export's value is in the tooltip), added parts green,
  removed parts grey and struck through; **Show** filters on them.
* **Issues** — every inconsistency, with severity and location; click to zoom. Errors
  block **Confirm panel**; warnings must be acknowledged (saved with the project);
  copy-count errors in flattened panels can be confirmed as panel-level parts, and
  **Remove part…** removes the components the selected issues name (e.g. a `no_paste`
  through-hole part).
* **Right-click on the canvas** — edit, remove, restore or revert the component under
  the cursor, or add one at that point (board-level inside a circuit, with its
  circuit-relative position filled in; panel-level outside). Double-click a component to
  edit it. Removed components show as a grey ×, edited ones in amber, added ones in green.
* **Fiducials** — after confirming, accept up to three panel fiducials (click them on the
  canvas or use the table); a fourth is refused. Circuit-level fiducials are shown in
  grey and cannot be picked.
* **File → Save project** — writes `<name>.panel.json`. Reopening re-analyses the source
  with the saved decisions and checks that the result is identical; a changed export is
  flagged by its SHA-256, a missing one opens the saved project read-only.
* **File → Export components CSV…** — writes the Components tab's table to
  `<name>.components.csv` (see [Components CSV](#components-csv)). It needs no confirmed
  panel and also works from a read-only project.

Every edit (roles, numbering, reference, part-number mapping, fiducials, acknowledgements,
panel-level confirmations, single-board setup, component edits, confirmation) is
undoable. Window layout and layer visibility are remembered.

## Component edits

Not every component in the export is machine-placed, and the export is not always
right. Phase 1 never changes the export; it records **component edits** with the
project and applies them on top of the export every time it is analysed (reopening
reproduces them, and `panelimport verify` lists them).

* **Remove** — the component is not placed: it leaves `placements` (or `panel_parts`)
  and its per-part checks, with a reason: *through-hole*, *not populated (DNP)*,
  *mechanical / fiducial* or *other*, plus an optional note. It still exists: a removed
  `FID1` is still a fiducial candidate, and it stays on the canvas as a grey ×.
  **Find ▾** proposes candidates, always for review in a checklist before anything is
  removed: through-hole (`.comp_mount_type = thmt/pressfit`, or no paste on its pads),
  not populated (`.no_pop`, or an attribute such as `DNP = True` or a value such as
  `Not Fitted`), fiducial or pinless mechanical parts, and parts missing from a loaded
  BOM. On a flattened panel a removed designator also leaves the copy count and the
  circuit fit.
* **Edit** — override part name, part number, package, side, position or rotation. A
  part-number edit wins over the part-number attribute. A position or rotation edit
  corrects where the part is placed; its pads and body stay where the PCB has them, so
  the paste check now compares the corrected centroid with the part's own pads (and
  warns with `centroid_off_pads` when it is off them).
* **Add** — a component the export does not have, board-level (placed in every circuit)
  or panel-level (placed once). When its package name matches a package in the export,
  it gets that package's pins and body, is drawn and is paste-checked
  (`added_no_paste` warns when no paste is under it).

Board-level X/Y are circuit-relative and panel-level X/Y are panel coordinates, exactly
as the components table shows them and as `placements`/`panel_parts` store them.
Changing the circuit reference, the numbering (which on a flattened panel can move
circuit 1 to a rotated copy) or the panel origin converts the edits, so an edited or
added part never moves on the panel. Component edits do not change the panel structure,
so they keep the panel's confirmation; their warnings still have to be cleared before
saving.

## Components CSV

**File → Export components CSV…** and `panelimport analyze --components-csv FILE` write
one row per component, with the columns of the Components tab: `Designator`, `Level`,
`Part name`, `Part number`, `Package`, `Side`, `X (mm)`, `Y (mm)`, `Rotation (°)`,
`Paste check`, `Status`.

* Every component is written whatever the tab's search and filters show: circuit 1's
  placements (`board`) first, then the panel-level parts (`panel`), each in designator
  order.
* The values are the ones the tab shows, component edits applied: board-level X/Y are
  circuit-relative, panel-level X/Y are panel coordinates, rotation is counter-clockwise.
  Numbers have the project file's precision instead of the three decimals shown.
* Removed components are listed too, with `removed: …` in `Status` (`added` and
  `edited: …` mark the other changed ones); filter on it for the parts that are placed.
* The file is comma-separated UTF-8 with a byte-order mark, which Excel opens directly.

## How the panel is identified

| Mode | When | Circuits come from |
| --- | --- | --- |
| `panel` | the panel step has `STEP-REPEAT` blocks | the expanded step-repeats (nested, multiple blocks, rotation, mirror, flip) |
| `flattened` | no `STEP-REPEAT`, designators repeat | grouped designators, assigned by closed board outlines or by sorting (Y, then X), then a least-squares rigid fit per circuit |
| `single-board` | no `STEP-REPEAT`, every designator once | the grid the user enters after confirming the mode (never chosen silently) |

Conventions:

* Everything is in **mm**; ODB++ inch files are converted on read.
* Angles in the project are **counter-clockwise** degrees; `rotation_raw` keeps the ODB++
  value (clockwise). `rotation = (360 − rotation_raw) mod 360`, top and bottom alike.
  Rotation is only read, shown and stored in Phase 1.
* **Board frame** — the board step's own coordinates. Placements are board-frame
  coordinates minus the circuit reference point (`circuit_reference.board_x/y`).
* **Panel frame** — the panel step's coordinates shifted so the panel origin is 0,0
  (setting `panel_origin`: profile lower-left by default; `panel.origin` stores where
  that is in ODB++ coordinates).
* Circuit `dx`/`dy`/`rotation`/`mirror` are relative to circuit 1.
  `circuit_reference.x/y/rotation/mirror` place circuit 1 itself on the panel.

### What the ODB++ specification settled

From the *ODB++ Format Description v7.0* and *Design Format Specification 8.1 Update 3*:

* `STEP-REPEAT` `X`/`Y` are the "start coordinate for placement of the **datum point** of
  the nested step"; `DX`/`DY` are the distance between datum points; rows fill along X
  first. A setting (`step_repeat_anchor`) can switch to the origin, and a warning is
  raised whenever a step's datum and origin differ, so a real export can confirm it.
* All rotations are clockwise; mirroring negates X; when both apply the feature is
  **rotated first, then mirrored**. `FLIP` mirrors the step and swaps its sides.
* `U MM`/`U INCH` and `UNITS=` declare units; without them a v7 file is inch (v8 uses
  `misc/info UNITS`). Symbol sizes are mils or microns, with an optional `I`/`M` suffix.
* Component records `CMP`/`PRP`/`TOP` plus the BOM records (`CPN`, `IPN`, `DSC`,
  `VND`, `MPN`, …) are all kept as attributes, because the part number may arrive in
  any of them. `.pad_usage = g_fiducial/l_fiducial` marks fiducial features.

## Checks

| Code | Check | Default | Severity |
| --- | --- | --- | --- |
| `crosscheck_mismatch`, `crosscheck_missing`, `crosscheck_extra` | step-repeat expansion vs flattened copies in the panel step | 0.01 mm | Error |
| `copy_count` | designator copy count ≠ N (flattened), with the missing/extra circuit | exact | Error unless confirmed panel-level |
| `fit_residual` | rigid-fit residual (flattened) | 0.01 mm | Error |
| `circuit_rotated`, `circuit_mirrored` | circuit rotated/mirrored relative to circuit 1 (and circuit 1 on the panel) | 0.05° | Warning |
| `nonuniform_grid` | circuits not on a uniform grid | 0.01 mm | Warning |
| `centroid_off_pads` | centroid vs centre of its paste pads (matched through the TOP toeprints) | 0.25 mm | Warning |
| `pattern_shift` | whole side shifted against paste by one vector (median) | 0.1 mm | Error, shows ΔX/ΔY |
| `no_paste` | no paste near a part (likely through-hole) | — | Info |
| `duplicate_designator` | designator twice in one circuit | exact | Error |
| `unknown_units`, `missing_file`, `unknown_record`, `parse_error` | export problems | — | Error |
| `bom_not_in_odb`, `bom_not_in_bom` | optional BOM CSV vs export | exact | Warning |
| `bom_removed` | a BOM part removed as not populated | exact | Warning |
| `edit_conflict`, `edit_invalid` | an added designator the export now has; an incomplete edit | — | Error |
| `edit_orphan` | an edit naming a component the export does not have | — | Warning |
| `edit_frame` | edit positions entered for a different panel structure, used unchanged | — | Warning |
| `outside_outline` | an added or moved part outside the board (or panel) outline | — | Warning |
| `added_no_paste` | no paste under a part added by hand | — | Warning |

Also reported: ambiguous steps (`ambiguous_steps`, Error until chosen), a single-board
export (`single_board`, Error until confirmed), units read by default
(`units_assumed`), datum ≠ origin (`datum_origin_differ`), flipped steps
(`step_flipped`), unrecognized fields (`unknown_field`), selected fiducials that
disappeared (`fiducial_missing`) and a changed source on reopen (`source_changed`).

Tolerances, fiducial patterns (`FID*`), the copy-suffix regex, the part-number attribute,
circuit 1's corner, the numbering order, the reference point, the panel origin and the
STEP-REPEAT anchor are **settings** (Edit → Settings), stored as JSON in
`%APPDATA%\PanelImporter\settings.json` (Windows) or `~/.config/panelimport/settings.json`.
The project file keeps a copy of the settings it was made with.

## Project file

`<name>.panel.json` is the direct serialization of `panelimport.model.panel.PanelProject`:
`format`, `version`, `source` (path relative to the project, SHA-256, steps), `mode`,
`panel` (outline, origin), `grid`, `numbering`, `circuit_reference`, `circuit_outline`,
`circuits`, `part_number_attribute`, `placements` (with every attribute), `panel_parts`,
`component_edits`, `fiducials`, `acknowledged_warnings`, `layer_roles`,
`panel_level_designators`, `single_board`, `settings`. Loading is strict: unknown keys or
a newer version are rejected. Values are rounded to 1 nm, so save → reopen gives an
identical model.

`placements` and `panel_parts` already have the component edits applied: Phase 2 places
exactly what they list. `component_edits` records what the user changed, in the same
frames, leaving out fields at their default:

```json
"component_edits": [
  {"designator": "C7", "level": "board", "part_number": "D-1234", "x": 25.15, "y": 10.0},
  {"designator": "J1", "level": "board", "removed": true, "reason": "through-hole", "note": "hand-soldered"},
  {"designator": "U9", "level": "board", "added": true, "part_name": "", "part_number": "IC-9",
   "package": "SOIC8", "layer": "top", "x": 40.0, "y": 12.0, "rotation": 270.0}
]
```

Version 2 added `component_edits` and `panel_parts[].part_number` (and fills the panel
parts' `package`); version 1 projects still open.

## Tests

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

* `tests/synthetic/odbgen.py` writes minimal ODB++ jobs (MM/INCH, `.Z` members via an
  LZW encoder checked against `unlzw3` and Unix `uncompress`, folder/tgz/zip) and
  flattens step-repeat panels into their twins.
* The suites cover the parsers, every acceptance criterion with synthetic panels, the
  GUI offscreen, a 2,000-placement panel with 48,000 traces (load and pan timing), and
  the rule that `io/`, `analysis/` and `model/` never import Qt.
* `tests/fixtures/` takes Daniel's real exports with an `expected.json` each — see
  [tests/fixtures/README.md](tests/fixtures/README.md). The test is skipped until fixtures are added.

## Code layout

```
panelimport/
  app.py, cli.py, session.py, report.py, components_csv.py, settings.py
  io/odb/      archive (folder/tgz/zip, .Z), matrix, stephdr, features, symbols,
               components, eda, attributes, job (lazy, cached)
  io/bom.py    optional BOM CSV
  model/       issues, panel dataclasses, project_file, serialize
  analysis/    roles, step_repeat, grouping (flattened), transforms (fit, grid,
               numbering), checks, fiducials, layers, edits (component edits,
               suggestions), pipeline, result, snapshot
  gui/         main_window, canvas, geometry, import/settings/single-board/component
               dialogs, controller (undo), panels/
packaging/     PyInstaller spec and entry points
```

## Open questions (to answer from the first real export)

- [ ] Does Detex's Altium export embedded board arrays as `STEP-REPEAT`, flatten them, or
      both? All three are handled; the issue list says which one was found.
- [ ] Which attribute or `PRP` property holds the Detex part number? Pick it in the
      Components tab, then store it in Settings.
- [ ] `STEP-REPEAT` `X`/`Y`: the specification says datum. Confirm with an export whose
      board datum differs from its origin (`datum_origin_differ` warns when they differ).
- [ ] Juki reference point: default is the board profile's lower-left (setting).
- [ ] Circuit 1 and numbering order: default lower-left, row-major (setting).
- [ ] Fiducials as components, attributed features or copper only: all three are detected.
- [ ] Bottom-side placements: read and flagged by layer; whether the machine places them
      is for Phase 2.

Not in Phase 1: ISS output, the DETEX_New.mdb lookup, rotation correction (beyond
editing a component's rotation by hand), editing the PCB data itself (component edits
are stored in the project, not in the export), per-circuit edits (an edit applies to
every circuit), and the Pick-and-Place CSV + Gerber input (to be built after the ODB++
path passes acceptance).
