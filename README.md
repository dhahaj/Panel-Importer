# Panel Importer

Desktop tool that imports an Altium **panel** exported as **ODB++**, identifies it, and
writes the **Juki ISS** placement program for it.

* **Phase 1** identifies the panel: circuit count, step-and-repeat, circuit 1, every
  placement in circuit-relative coordinates, and the fiducials. The confirmed panel is
  saved as `<name>.panel.json`. Phase 1 never changes the export.
* **Phase 2** reads a confirmed `<name>.panel.json` and writes `<name>.iss`, which
  JaNets opens and fills with component data from its own database; it also compares
  any two programs (ISS or JaNets `.x21`) part by part. See [Phase 2: ISS output](#phase-2-iss-output).

```
import ODB++ → automatic detection → review issues → confirm panel → pick fiducials
            → add, edit or remove components (optional) → save project → export ISS
```

## Running it

Requires Python 3.12.

```bash
pip install -e ".[dev]"          # PySide6, shapely, numpy, unlzw3, pytest, PyInstaller
panelimport-gui                  # the GUI (or: python -m panelimport)
panelimport analyze Panel.tgz    # the same summary and issues the GUI shows
panelimport analyze Panel.tgz --components-csv parts.csv   # also write the components
panelimport verify Panel.panel.json   # saved project vs. its source (SHA-256 + re-analysis)

panelimport iss Panel.panel.json -o Program.iss            # write the ISS program
panelimport iss Panel.panel.json --check                   # checks and report only
panelimport iss Panel.panel.json --set panel_rotation=90 --set clamp_offset_y=91.313
panelimport iss-compare Generated.iss D:\ER_RevF8\Program.x21   # part-by-part diff
```

`panelimport analyze` options: `--panel-step`, `--board-step`, `--first` (corner of
circuit 1), `--order`, `--reference`, `--copy-suffix REGEX`, `--part-number-attribute`,
`--panel-level FID1,FID2`, `--bom bom.csv`, `--components-csv FILE`, `--settings file.json`,
`--json`, `-v`.
Exit code 0 = no errors, 1 = errors found, 2 = could not open.

`panelimport iss` options: `-o FILE` (default `<name>.iss` next to the project),
`--check`, `--set KEY=VALUE` (repeatable), `--settings file.json`, `-v` (also list the
allocations and placements). Exit code 0 = written with no errors, 1 = errors (nothing
written), 2 = could not open. `panelimport iss-compare A B` options: `--tolerance MM`
(default 0.01), `--all` (every part, not only the ones that differ), `--angle-direction
ccw|cw`. Exit code 0 = same placements, 1 = different, 2 = could not open.

### Windows and Linux builds (no Python needed on the target machine)

```bash
pyinstaller packaging/panelimport.spec --noconfirm
```

produces `dist/PanelImporter/` with `PanelImporter.exe` (GUI) and `panelimport.exe`
(command line); on Linux they are `PanelImporter` and `panelimport`. Copy the whole
folder; no installation or admin rights. The `build` GitHub Actions workflow builds this
folder on `windows-latest` (running both executables with Python removed from `PATH`)
and on `ubuntu-22.04`, and uploads them as the `PanelImporter-windows` and
`PanelImporter-linux` artifacts. The Linux build runs on distributions with glibc 2.35
or newer; the GUI needs the usual X11/Wayland libraries (on Debian/Ubuntu,
`libgl1 libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3 libxcb-cursor0`).

### Releases

Pushing a tag `v<version>` that matches `panelimport.__version__` builds both bundles
and publishes a GitHub release with `PanelImporter-<version>-windows-x64.zip`,
`PanelImporter-<version>-linux-x64.tar.gz` and their SHA-256 sums. The tag's annotation
becomes the release notes:

```bash
git tag -a v0.3.0 --cleanup=verbatim -F notes.md && git push origin v0.3.0
```

## Using the GUI

* **File → Import ODB++…** — choose the ODB++ folder, `.tgz` or `.zip`. The dialog lists
  the steps and layers with the detected panel step, board step and layer roles;
  correct them if needed. The last location is remembered.
* **Canvas** — middle-drag pans, the wheel zooms toward the cursor, `F` fits the panel,
  `M` measures (two clicks: ΔX, ΔY, distance; snaps to markers), `B` views from the
  bottom (display only). Layers toggle on the left. Hovering a centroid shows designator,
  part, package, layer, rotation (normalized and raw) and panel/circuit coordinates; the
  status bar shows the cursor's panel and circuit-relative coordinates.
* **Layers** tab — tick a layer to show it. Double-click a layer (or select it and press
  **Colour…**, or right-click it) to pick its colour, transparency included; **Reset
  colours** restores the defaults. The ISS export preview uses the same colours.
* **Circuits** tab — offsets, rotation, mirror, source and residual per circuit; choose
  the corner of circuit 1, the numbering order and the reference point.
* **Components** tab — circuit 1's placements and the panel-level parts, sortable,
  filterable and searchable; pick the attribute that holds the part number. Selecting a
  row selects the part on the canvas and vice versa. Components can be edited here (see
  [Component edits](#component-edits)): **Add…** (`Insert`), **Edit…** (`F2` or
  double-click; several rows at once change part name, part number, package or size),
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
* **File → Export ISS…** (`Ctrl+E`) — once the panel is confirmed (or from a saved
  project whose export is missing). The dialog shows the main ISS settings (pwbId, panel
  rotation, clamp offset, angle direction and offset), the side being written (from the
  placements) with the flip axis for a bottom-layer panel, a summary, the checks, and a
  preview of the panel **as the machine will see it** (after the flip and rotation, P
  marked, FRONT rail at the bottom), so the flip axis can be checked against the real
  panel. Every change re-runs the checks; errors disable **Write**. Writes `<name>.iss`
  next to the project by default; *Save these settings as the default* stores them in
  the settings file (the pwbId stays per project).
* **File → Compare programs…** — pick two ISS/`.x21` files and see the part-by-part
  table, the summary line and the panel, circuit and fiducial comparison. Rows can be
  selected and sorted; nothing is edited.

Every edit (roles, numbering, reference, part-number mapping, fiducials, acknowledgements,
panel-level confirmations, single-board setup, component edits, confirmation) is
undoable. Window layout, layer visibility and layer colours are remembered.

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
* **Edit** — override part name, part number, package, side, position, rotation or
  size. A part-number edit wins over the part-number attribute. A position or rotation
  edit corrects where the part is placed; its pads and body stay where the PCB has them,
  so the paste check now compares the corrected centroid with the part's own pads (and
  warns with `centroid_off_pads` when it is off them).
* **Add** — a component the export does not have, board-level (placed in every circuit)
  or panel-level (placed once). When its package name matches a package in the export,
  it gets that package's pins, body and body size, is drawn and is paste-checked
  (`added_no_paste` warns when no paste is under it).

**Component size** is the body's width (along the part's own X axis at rotation 0),
length (its Y axis) and height, in mm; 0 means unknown. The export gives width and
length from the package's body outline in `eda/data` (pads left out) and the height
from the `.comp_height` attribute (in the file's units). The Components tab, the
inspector and the edit dialog show and change them; with several rows selected a size
that is set applies to each, and one left at *(keep each one's)* stays as it is.

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
`Width (mm)`, `Length (mm)`, `Height (mm)`, `Paste check`, `Status`.

* Every component is written whatever the tab's search and filters show: circuit 1's
  placements (`board`) first, then the panel-level parts (`panel`), each in designator
  order.
* The values are the ones the tab shows, component edits applied: board-level X/Y are
  circuit-relative, panel-level X/Y are panel coordinates, rotation is counter-clockwise.
  Numbers have the project file's precision instead of the three decimals shown; an
  unknown size is empty.
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

## Phase 2: ISS output

`panelimport/iss/` reads a confirmed project and writes a Juki ISS program from it alone:
the export, DETEX_New.mdb and every other database are never opened. Component records
carry the name JaNets looks up (the Detex part number); size, package, pick and vision
data, mark teaching, nozzles, feeders and rotation corrections come from JaNets or the
machine.

### The frame

Every ISS program has one origin **P**; JaNets, CircuitCAM and issgen all use

```
placement on panel   = P + allocation[k] + placementPosition          (allocation angle 0)
circuit k outline LL = P + allocation[k] + circuitLayoutOffset         (model/pwbData)
pwbLayoutOffset      = panel lower-right corner − P                    (model/pwbData)
fiducial on panel    = P + markPosition
clampOffset.y        = panel height / 2
```

with P in different places (the reader tests check these equations on every reference
program). Phase 2 computes everything panel-absolute from the project, applies one
**machine transform** for the side being written — the bottom flip if any, then the panel
rotation, then a shift that puts the panel's lower-left corner at 0,0 — and derives the
ISS values from the transformed geometry:

* **P** is circuit 1's transformed reference point, moved to the lower-left of its
  transformed outline. With the default `profile-lower-left` reference P *is* that
  corner and `circuitLayoutOffset` is 0,0. With another reference, P keeps the
  reference's offset from the outline's lower-left (turned with the circuit), so an
  untransformed panel has P at the reference point and `circuitLayoutOffset` = the
  outline's lower-left, exactly as the frame table in the brief says.
* Each **allocation** is the change in a circuit's P (the same circuit-frame point placed
  by that circuit); its angle is the circuit's rotation relative to circuit 1, as seen by
  the machine (a mirror reverses it). Allocations are assumed to turn about the allocation
  point; rotated allocations warn until that is confirmed in JaNets.
* Each **placement position** is the transformed position in circuit 1 minus P.
* **Angles** follow the geometry: a part's angle is the direction of its X axis after the
  transform, so a left-right flip maps θ to 180° − θ, a front-back flip to −θ, and the
  panel rotation is added. Then `bottom_angle_offset` (bottom only), `angle_direction`
  (`cw` negates) and `angle_offset`, normalized to [0, 360).

The same code handles top, bottom, rotated panels and rotated circuit 1. A panel is placed
on **one side**: the placements' layer decides which; both layers is an error. Only the
fiducials on that layer are written. `referenceSide` stays `FRONT` (the conveyor's fixed
rail, not the board side).

**Bottom-layer panels** are written as the machine sees them, turned over. With the
defaults (`bottom_flip = left-right`, `panel_rotation = auto`: a portrait panel turns 90°
CCW so its long side runs along the conveyor) the transform is program (u, v) = (H − y,
W − x), the one the ER pilot program used.

### What is written

The skeleton of `T3_strip_both.iss` (the tests compare element trees): UTF-8 with BOM,
CRLF, 2-space indent; self-closing tags always `<tag />` (JaNets hangs on `<tag/>`);
numbers with at most 4 decimals, no trailing zeros, no exponent, never `-0`; attributes
in the known-good order; Juki's `witdh` and `connecterHeight`; text escaped. A small
dedicated writer produces it, and every file is checked before it replaces anything: no
`[^ ]/>`, it parses, and it reads back to the same program.

* `NONMATRIX` with every allocation listed, `bocMarkType PWBBOC` (what JaNets converts
  issgen's MATRIX into). `circuit_layout = matrix` writes `divideNumber`/`matrixPitch`
  for full uniform grids; JaNets numbers MATRIX circuits from the grid's lower-left, so
  P moves to that circuit (positions on the panel do not change).
* One component record per distinct component name, in first-use order: the part number,
  or the part name with a warning. `comment` = the first of `comment_attributes` present
  (`DSC`, `Description`, `Comment`), else the part name.
* `componentSize` (`witdh`, `length`, `height`) is the component's size from the project
  (`component_size = body`): one per component, so its placements are combined per
  dimension — a size edited in Phase 1 wins for the whole component, otherwise the
  export's, 0 where none is known. An angle offset of ±90° swaps width and length, so
  they stay in the frame the machine turns the part in.
  `model/componentData` is left out (`model_component_stubs` adds stubs, test only).
* Fiducial mark names are the project's names when they are plain identifiers
  (`FID1`), else `F1`, `F2`, `F3` (copper fiducials are named like `F(6.351,12.703)`).
* Panel-level parts that are not fiducials are left out with a warning.

### Settings

In the Phase 1 settings file under the `iss` key; `--set key=value` overrides one value
for one run, and the report lists every value used.

| Setting | Default | Notes |
| --- | --- | --- |
| `pwb_id` | project file name stem | `pwbId` in core and model |
| `panel_rotation` | `auto` | `auto` (portrait → 90° CCW, landscape → 0) or 0/90/180/270 CCW, after the bottom flip |
| `bottom_flip` | `left-right` | `left-right` (x → W − x) or `front-back` (y → H − y) |
| `bottom_angle_offset` | 0 | added to bottom angles after mirroring |
| `pwb_thickness`, `back_height` | 1.6, 37 | mm |
| `clamp_offset_y` | `auto` | `auto` = program panel height / 2, or mm |
| `circuit_layout` | `nonmatrix` | `matrix` for full uniform grids only |
| `angle_direction`, `angle_offset` | `ccw`, 0 | `cw` negates every angle; the offset is added to placement angles |
| `header_completion` | `zero` | `zero` (CircuitCAM, issgen) or `total` (T3, JaNets) |
| `model_component_stubs` | false | test switch: stub `model/componentData` |
| `component_size` | `body` | `body`: each component's body size and height from the project; `zero`: 0 for every component |
| `comment_attributes` | `DSC, Description, Comment` | first one present wins |
| `line_name`, `line_id`, `mark_name`, `traceability` | `Line`, 1, `BOCMARK01`, `TwoDimensions` | `traceability` may be `NOUSE` |

### Checks before writing

Errors stop the write; warnings go in the report and the dialog.

| Code | Check | Severity |
| --- | --- | --- |
| `project_invalid` | not a readable v1–v3 project (exit 2 on the command line), or not confirmed, or missing circuits/outlines | Error |
| `no_fiducials`, `too_many_fiducials` | fewer than 2 / more than 3 fiducials on the placements' layer | Error |
| `mirrored_circuit` | any circuit, or circuit 1 itself, mirrored | Error |
| `rotated_circuit` | an allocation angle ≠ 0 (never tested in JaNets) | Warning |
| `no_part_number` / `no_component_name` | part name used / no name at all | Warning / Error |
| `component_name_chars` | a name with characters outside `A-Z a-z 0-9 - _ .` | Warning |
| `duplicate_designator` | a designator twice in circuit 1 | Error |
| `mixed_sides` | placements on both layers | Error |
| `bottom_angles_unverified` | a bottom-layer program (angle mapping not yet verified) | Warning |
| `panel_parts_skipped` | panel-level parts that are not fiducials, listed | Warning |
| `outside_circuit` / `outside_panel` | a placement outside the circuit outline / any placement or fiducial outside the panel | Warning / Error |
| `no_placements` | nothing to place | Error |
| `source_changed` | the project's source export changed (written from the project anyway) | Warning |
| `component_size_unknown` | components written with a size of 0 in some dimension, listed | Warning |
| `component_size_differs` | placements of one component with different known sizes (and no edit choosing one) | Warning |
| `component_size_old_project` | a project file older than version 3 has no sizes: all are written as 0 | Warning |
| `matrix_layout` | a setting the project cannot satisfy | Error |

A saved project is confirmed by construction (Phase 1 saves only confirmed panels); the
GUI exports only a confirmed panel.

### Comparing programs

`iss-compare` and **Compare programs…** read ISS and `.x21` into one model (only the
elements listed in `iss/reader.py`; structure that is not understood is reported as a
note, never fatal), turn both into panel-absolute positions with their own P, match the
circuits by where their parts are (so differently numbered programs still line up), and
list per designator and circuit ΔX, ΔY and Δangle, the parts and components only in one
program, the circuits and allocations, the fiducials, panel size, clamp offset, layout
type and header completeness. Every change a program can store (4 decimals) is listed;
positions *match* within the tolerance (0.01 mm), flagged `*` beyond it. Angles are
reported, not judged; the summary says whether the differences are one constant offset
or vary per part (reel corrections).

Examples from the reference programs:

* `ER_issgen_panel3.iss` vs JaNets' save of it: 7 changed parts (rotations of C4, D9,
  D12, Q1, U2, U3; R35 Y −0.009; D12 X −0.001), MATRIX → NONMATRIX, an extra component `0`.
* **Golden (ER Rev F8, bottom layer, default settings)** vs the programs that ran the pilot:
  the generated program uses the ODB++ row pitch 52.578 mm; the pilot used 53.086 mm. The
  first row of circuits matches within 0.05 mm, the second and third rows are offset by
  0.508 and 1.016 mm in program Y, fiducials within 0.05 mm (0.022 mm from the panel
  outline), clamp offset 91.313. Angles vary per part. Against `ER_RevF8_production.x21`,
  three parts entered by hand in JaNets (C12, D10, L1; not in CircuitCAM's program) are
  0.05–0.35 mm off, and R15, R17 (107522-31-1107 vs the project's 107522-11-1107) and
  R23 (107522-31-2002 vs 107522-31-1001) carry other part numbers in production.

### Diagnosing JaNets problems

JaNets fails silently. `OpenFilePath Start` without `End` in
`C:\JUKI\JaNets\Log\Juki.Iss.IntelliPE.ProgramEditor.log` means it is stuck opening;
two 64-byte slots from the same PC in `C:\ComponentDatabase\Data\DETEX_New.ldb` is the
July deadlock. Flip one compatibility switch at a time (`header_completion`,
`circuit_layout`, `traceability`, …) and use `iss-compare` against the `.x21` JaNets
saves, so a change is never guessed at.

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

Version 3 added the component sizes: `width`, `length` and `height` in `placements`,
`panel_parts` and `component_edits`. Version 2 added `component_edits` and
`panel_parts[].part_number` (and fills the panel parts' `package`). Older projects still
open; reopening a version 1 or 2 project with its export takes the sizes from the export
without counting that as a difference from the saved project.

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
* Phase 2 (`tests/test_iss_*.py`): frame round trips (project → ISS → reader → panel
  positions within 0.0001 mm) over every reference kind × circuit-1 corner (synthetic and
  through Phase 1's pipeline), non-uniform grids, panel rotations, a rotated circuit 1,
  rotated allocations and both bottom flips with and without rotation; three bottom-layer
  panels worked out by hand; the T3 skeleton, serialization rules and self-test; every
  check; the reference equations on every program in `tests/fixtures/iss/`; the `.x21`
  reader against issgen's program; and the ER golden comparison (`Panel.zip` +
  `Panel.panel.json`). Tests whose reference files are missing are skipped.

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
  iss/         Phase 2: settings, mapping (project → ISS frame), checks, writer,
               reader (ISS and .x21), compare, report — never imports Qt
  gui/         main_window, canvas, geometry, import/settings/single-board/component
               dialogs, iss_dialogs (Export ISS, Compare programs), controller (undo), panels/
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

Not in Phase 1: ISS output (Phase 2), the DETEX_New.mdb lookup, rotation correction (beyond
editing a component's rotation by hand), editing the PCB data itself (component edits
are stored in the project, not in the export), per-circuit edits (an edit applies to
every circuit), and the Pick-and-Place CSV + Gerber input (to be built after the ODB++
path passes acceptance).

## Open questions (Phase 2, to answer in JaNets and on the machine)

- [ ] **Bottom-layer angles:** the exact mapping from Altium's bottom rotation to the
      program angle (`bottom_angles_unverified` warns until then). Against the pilot
      programs the differences vary per part (reel corrections), not one offset.
- [ ] **Placement angle convention:** are Juki angles CCW like the project?
      `angle_direction` and `angle_offset` cover either answer.
- [ ] **Rotated allocations:** do allocation angles turn about the allocation point, and
      which way? Assumed about the point, CCW; `rotated_circuit` warns.
- [ ] **Header completion counts:** do they change anything (`zero` vs `total`)?
- [ ] **Component `0`:** where did the extra component in `panel3.x21` come from?
- [ ] **Panel-level parts** besides fiducials: they are left out with a warning.
- [ ] **Line configuration:** does transfer to the machine need JaNets' full
      `lineConfiguration/configuration` block? Opening does not.
- [ ] **ER fiducials:** the saved ER project picked F(6.351,243.307) where the pilot used
      F(176.275,12.703) (both on the bottom copper); the golden test uses the pilot's three.
