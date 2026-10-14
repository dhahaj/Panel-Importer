# Real ODB++ fixtures

Put each real export in its own folder with an `expected.json`:

```
tests/fixtures/
  detex-panel-1/
    Panel_ODB.tgz          # or the ODB++ folder, or a .zip
    expected.json
```

`expected.json` holds what Altium shows for that panel. Every key is optional; the test
checks the ones present:

```json
{
  "source": "Panel_ODB.tgz",
  "mode": "panel",
  "panel_step": "panel",
  "board_step": "pcb",
  "layer_roles": {"paste_top": "top_paste", "copper_top": "top_layer"},
  "circuits": 6,
  "grid": {"cols": 3, "rows": 2, "pitch_x": 52.0, "pitch_y": 38.5},
  "placements": 312,
  "placement_positions": {"C14": [12.35, 8.10]},
  "max_errors": 0,
  "decisions": {"panel_level": ["FID1", "FID2", "FID3"]},
  "settings": {"copy_suffix_regex": ""}
}
```

* `circuits`, `grid` and the pitch must match within 0.01 mm (acceptance criterion).
* `placement_positions` are circuit-relative (the reference point is the lower-left of
  the board profile unless `settings` says otherwise).
* Include at least one single-board export (`"mode": "single-board"`).
* `decisions` are read like the project file, so they can hold component edits too,
  e.g. to leave out what the machine does not place before counting `placements`:
  `"component_edits": [{"designator": "J1", "removed": true, "reason": "through-hole"}]`.

Run `panelimport analyze <export>` first: its output shows what to put in the file and
which open questions the export answers. Real exports are ignored by `.gitignore`
except under this folder.

## ISS reference programs (Phase 2)

`tests/fixtures/iss/` holds the programs the Phase 2 tests check against; a test whose
file is missing is skipped with a message.

| File | Source | Use |
| --- | --- | --- |
| `T3_strip_both.iss` | generated, opens in JaNets | skeleton and element order to match |
| `102605_janets.iss` | JaNets (102605, 12 circuits) | frame equations, P inside the board |
| `102605_janets.x21` | JaNets save of a later edit of the same panel | `.x21` reader against a known ISS |
| `102628_portrait_circuitcam.iss` | CircuitCAM, portrait panel | frame equations, portrait panel |
| `ER_RevF8_circuitcam.iss` | CircuitCAM, ER (bottom layer), ran the pilot | golden comparison |
| `ER_RevF8_production.x21` | JaNets save of the pilot program | golden comparison, `.x21` reader |
| `ER_issgen_panel3.iss`, `ER_issgen_panel3_janets.x21` | issgen output + JaNets' save of it | what JaNets changed |
| `iss_schema_0.xsd` | reconstructed from AegisMachines.dll | partial validation: compared with T3's complaints |

The ER golden input is `tests/fixtures/Panel.zip` (the ODB++ export) with its confirmed
`tests/fixtures/Panel.panel.json`; the test re-runs Phase 1 on it, so the project's
source path is rewritten to the zip next to it. Still wanted: one **top-layer** panel as
ODB++ with its confirmed `.panel.json` (and its program, if it has run) for the
top-layer golden test.

