"""The components as a CSV file: what the GUI's components table lists.

One row per component: circuit 1's placements (X/Y circuit-relative) and the panel-level
parts (X/Y in panel coordinates), with the component edits applied.  Removed components
are included; their Status column says so.  Used by both the CLI and the GUI.  Never
imports Qt.
"""

from __future__ import annotations

import csv
import os

from panelimport.analysis.edits import all_parts, natural_key, shown_values, status_text
from panelimport.analysis.result import PanelAnalysis, r6

COMPONENTS_SUFFIX = ".components.csv"

#: The columns of the GUI's components table.
COLUMNS = (
    "Designator",
    "Level",
    "Part name",
    "Part number",
    "Package",
    "Side",
    "X (mm)",
    "Y (mm)",
    "Rotation (°)",
    "Paste check",
    "Status",
)


def _number(v: float) -> str:
    """Rounded like the project file (1 nm, 1 µ°), without trailing zeros."""
    return f"{r6(v):.6f}".rstrip("0").rstrip(".")


def component_rows(a: PanelAnalysis) -> list[list[str]]:
    """Every component of the analysis, board level first, each in designator order."""
    rows = []
    for level, part in sorted(all_parts(a), key=lambda lp: (lp[0], natural_key(lp[1].designator))):
        values = shown_values(a, part)
        rows.append(
            [
                part.designator,
                level,
                values["part_name"],
                values["part_number"],
                values["package"],
                values["layer"],
                _number(values["x"]),
                _number(values["y"]),
                _number(values["rotation"]),
                (part.paste.describe() if part.paste else "-") if level == "board" else "",
                status_text(part),
            ]
        )
    return rows


def write_components_csv(a: PanelAnalysis, path: str | os.PathLike) -> int:
    """Write the components to ``path`` and return how many rows were written.

    UTF-8 with a byte-order mark, so that Excel reads "°" and non-ASCII part names."""
    rows = component_rows(a)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return len(rows)
