# Panel Importer — Phase 1

Desktop tool that imports an Altium **panel** exported as **ODB++** and identifies the
panel: circuit count, step-and-repeat, circuit 1, every placement in circuit-relative
coordinates, and the fiducials. The confirmed panel is saved as `<name>.panel.json`,
which Phase 2 (ISS output) reads. Phase 1 writes no machine program and never changes
the export.

```
import ODB++ → automatic detection → review issues → confirm panel → pick fiducials → save project
```

## Running it

Requires Python 3.12.

```bash
pip install -e ".[dev]"          # PySide6, shapely, numpy, unlzw3, pytest, PyInstaller
panelimport-gui                  # the GUI (or: python -m panelimport)
panelimport analyze Panel.tgz    # the same summary and issues the GUI shows
panelimport verify Panel.panel.json   # saved project vs. its source (SHA-256 + re-analysis)
```

`panelimport analyze` options: `--panel-step`, `--board-step`, `--first` (corner of
circuit 1), `--order`, `--reference`, `--copy-suffix REGEX`, `--part-number-attribute`,
`--panel-level FID1,FID2`, `--bom bom.csv`, `--settings file.json`, `--json`, `-v`.
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
* **Components** tab — circuit 1's placements, sortable, filterable and searchable; pick
  the attribute that holds the part number. Selecting a row selects the part on the
  canvas and vice versa.
* **Issues** — every inconsistency, with severity and location; click to zoom. Errors
  block **Confirm panel**; warnings must be acknowledged (saved with the project);
  copy-count errors in flattened panels can be confirmed as panel-level parts.
* **Fiducials** — after confirming, accept up to three panel fiducials (click them on the
  canvas or use the table); a fourth is refused. Circuit-level fiducials are shown in
  grey and cannot be picked.
* **File → Save project** — writes `<name>.panel.json`. Reopening re-analyses the source
  with the saved decisions and checks that the result is identical; a changed export is
  flagged by its SHA-256, a missing one opens the saved project read-only.

Every edit (roles, numbering, reference, part-number mapping, fiducials, acknowledgements,
panel-level confirmations, single-board setup, confirmation) is undoable. Window layout
and layer visibility are remembered.

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
`fiducials`, `acknowledged_warnings`, `layer_roles`, `panel_level_designators`,
`single_board`, `settings`. Loading is strict: unknown keys or a newer version are
rejected. Values are rounded to 1 nm, so save → reopen gives an identical model.

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
  app.py, cli.py, session.py, report.py, settings.py
  io/odb/      archive (folder/tgz/zip, .Z), matrix, stephdr, features, symbols,
               components, eda, attributes, job (lazy, cached)
  io/bom.py    optional BOM CSV
  model/       issues, panel dataclasses, project_file, serialize
  analysis/    roles, step_repeat, grouping (flattened), transforms (fit, grid,
               numbering), checks, fiducials, layers, pipeline, result, snapshot
  gui/         main_window, canvas, geometry, import/settings/single-board dialogs,
               controller (undo), panels/
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

Not in Phase 1: ISS output, the DETEX_New.mdb lookup, rotation correction, editing PCB
data, and the Pick-and-Place CSV + Gerber input (to be built after the ODB++ path passes
acceptance).
