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

Run `panelimport analyze <export>` first: its output shows what to put in the file and
which open questions the export answers. Real exports are ignored by `.gitignore`
except under this folder.
