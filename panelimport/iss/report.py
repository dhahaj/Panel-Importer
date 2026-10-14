"""Plain-text report of an ISS export: what ``panelimport iss`` prints.

The GUI's Export ISS dialog shows the same summary, settings and issues.
"""

from __future__ import annotations

from collections import Counter

from panelimport.iss.checks import Prepared
from panelimport.iss.writer import fmt


def summary_lines(prepared: Prepared) -> list[str]:
    layout = prepared.layout
    project = prepared.project
    if layout is None:
        return [f"Project: {len(project.circuits)} circuits, {len(project.placements)} placements (not mapped)"]
    prog = layout.program
    m = layout.machine
    sides = Counter(p.layer for p in project.placements)
    side_text = ", ".join(f"{k} {v}" for k, v in sorted(sides.items())) or "none"
    lines = [
        f"Side:       {m.describe()} (placements: {side_text})",
        f"Panel:      {fmt(prog.width)} × {fmt(prog.height)} mm as the machine sees it; clamp offset {fmt(prog.clamp_offset or 0)}",
        f"Origin P:   ({layout.origin[0]:.4f}, {layout.origin[1]:.4f}) on circuit {layout.circuit_numbers[0]}; "
        f"pwbLayoutOffset ({fmt(prog.pwb_layout_offset[0])}, {fmt(prog.pwb_layout_offset[1])})",
        f"Circuits:   {len(prog.circuits)} ({prog.circuit_layout}), outline {fmt(prog.circuit_width)} × {fmt(prog.circuit_height)}, "
        f"circuitLayoutOffset ({fmt(prog.circuit_layout_offset[0])}, {fmt(prog.circuit_layout_offset[1])})",
        f"Placements: {len(prog.placements)} per circuit, {len(prog.placements) * len(prog.circuits)} on the panel",
        f"Components: {len(prog.components)}",
        f"Fiducials:  {len(prog.fiducials)} on the {m.side} layer"
        + (f" ({', '.join(f.name for f in prog.fiducials)})" if prog.fiducials else "")
        + (f"; left out on the other layer: {', '.join(layout.other_layer_fiducials)}" if layout.other_layer_fiducials else ""),
    ]
    return lines


def format_report(
    prepared: Prepared, *, written: str | None = None, failure: str | None = None, verbose: bool = False
) -> str:
    lines = summary_lines(prepared)
    lines.append("")
    lines.append("Settings:")
    for key, value in prepared.settings.describe():
        if key == "pwb_id" and prepared.layout is not None:
            value = prepared.layout.program.pwb_id or "-"
        lines.append(f"  {key:<22} {value}")
    if verbose and prepared.layout is not None:
        prog = prepared.layout.program
        lines.append("")
        lines.append("  #    allocation X  allocation Y    angle   (circuit)")
        for c, number in zip(prog.circuits, prepared.layout.circuit_numbers):
            lines.append(f"  {c.number:<4} {c.x:12.4f} {c.y:13.4f} {c.angle:8.3f}   ({number})")
        lines.append("")
        lines.append("  designator   component              X          Y      angle")
        for p in prog.placements:
            lines.append(f"  {p.designator:<12} {p.component[:20]:<20} {p.x:10.4f} {p.y:10.4f} {p.angle:8.3f}")
    errors, warnings = prepared.errors, prepared.warnings
    lines.append("")
    lines.append(f"Issues: {len(errors)} errors, {len(warnings)} warnings")
    for issue in prepared.issues:
        lines.append("  " + issue.format())
    lines.append("")
    if written:
        lines.append(f"Written: {written}")
    elif failure:
        lines.append(f"Not written: {failure}")
    elif errors:
        lines.append("Not written: fix the errors first.")
    else:
        lines.append("Ready to write.")
    return "\n".join(lines)
