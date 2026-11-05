# Non-grid panels: design and plan

Approved 2026-11-05. Panel-Importer already expands every `STEP-REPEAT` record
(nested, rotated, mirrored, flipped) and writes one NONMATRIX allocation per circuit.
This work closes three gaps: rotated copies, mixed designs and a single-circuit
("flatten") output, plus an "as-is" fallback for flat panels.

## What the reference programs prove

| Encoding | Evidence | Use |
| --- | --- | --- |
| NONMATRIX, own X/Y per allocation, angle 0 | `102605_janets.iss` (JaNets' save, allocations off-grid by up to 0.04 mm); ER CircuitCAM program ran the pilot | grids and irregular offsets |
| Allocation angle ≠ 0 | none (every allocation in 5 `.iss` and 3 `.x21` has angle 0) | never written |
| Circuit B with its own placements | circuit B is always `SINGLE`/`NOUSE` | never written |
| Per-circuit fiducials | only PWBBOC panel marks | never written |
| NONMATRIX with one allocation | the writer's own elements, count 1 | flatten output; open the first one in JaNets before a run |

## Model

* Phase 1 `CircuitInfo` is the circuit instance: index, board → panel transform,
  rotation, mirror, flip, outline, step-repeat path. It gains `design` (the step name).
* Mixed panels: the analysis keeps one design record per board step (outline,
  reference point, placements). The project file goes to version 4 with
  `circuits[].design` and `designs[]` (steps other than `board_step`). Versions 1–3
  still open; `placements`, `circuit_outline` and `circuit_reference.board_x/y` keep
  describing the board step.
* Component edits gain `design` (empty = the board step).
* Circuit dx/dy is the move of each circuit's own reference point from circuit 1's, so
  `circuit_transforms` stays one formula for every design.

## Output choice (Phase 2)

New ISS setting `circuit_output = auto | circuits | flatten` (default `auto`);
`circuit_layout` (nonmatrix/matrix) is unchanged and applies when circuits are written.

* `auto` → circuits when there is one design and no circuit is rotated or mirrored
  relative to circuit 1 (grids, irregular offsets): the existing code path, unchanged.
* `auto` → flatten for rotated copies and mixed designs.
* `circuits` with rotated copies or several designs → error (`rotated_circuit` was a
  warning).
* Mirrored or flipped copies → error in every mode (`mirrored_circuit`).

## Flatten output

One allocation at 0,0; circuit outline = the program panel; P = the program panel's
lower-left corner. Each placement of each circuit is the machine transform applied to
the circuit transform applied to the part; its angle comes from the same composed
transform, then the usual bottom offset, direction and angle offset. Designators get
the circuit number (`R12_2`); a clash is an error. Warning `flatten_no_bad_marks`.
Panel fiducials as today; non-fiducial panel parts still left out with a warning.

## Bottom side

Circuit transform first (copy on the panel), then the machine transform (flip, panel
rotation, shift). Flatten reuses `machine_transform` and `direction_angle`.

## Flat panels

`flattened` and `single-board` stay. New `as-is` mode: the panel step is one circuit,
every component at its panel position, written with flatten output; chosen by the user
when the rigid fit fails.

## GUI

* Summary bar: panel type (grid, irregular, mixed, flat; "nested" when sub-panels) and
  the output `auto` picks.
* Canvas: design name in the circuit label when there are several; an orientation mark
  at each circuit's reference corner.
* Circuits tab: Design column. Export ISS: Circuits = Auto / Allocations / Flatten with
  the reason.

## Plan (one commit or more per step, branch `feature/non-grid-panels`)

1. **Golden files.** `tests/fixtures/golden/*.iss` from the current code with a fixed
   `lastEdit`: the ER panel and synthetic step-and-repeat panels through Phase 1 (top,
   both bottom flips, portrait, rotated circuit 1, non-uniform, nested, MATRIX).
   `tests/test_golden_bytes.py` compares bytes; `PANELIMPORT_REGEN_GOLDEN=1` rewrites.
2. **Transform tests.** `tests/test_instance_math.py`: 0/90/180/270 about the datum,
   nested composition, mirror, bottom composition, hand-computed positions.
3. **Flatten output.** `iss/settings.py` (`circuit_output`), `iss/mapping.py`
   (`build_layout` → `_flatten`), `iss/checks.py` (mode errors and warnings), writer
   unchanged. Tests: hand values, grid forced to flatten = circuits expanded.
4. **Mixed designs.** `analysis/roles.py`, `analysis/pipeline.py`, `analysis/result.py`,
   `model/panel.py`, `model/serialize.py`, `model/project_file.py`, `analysis/edits.py`,
   `iss/mapping.py`. Synthetic mixed fixture end to end.
5. **As-is mode.** `analysis/pipeline.py`, decisions, GUI action.
6. **GUI.** summary, canvas, circuits panel, export dialog.
7. **README**, full test run, goldens unchanged.
