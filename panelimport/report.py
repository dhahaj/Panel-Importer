"""Plain-text report of an analysis: what ``panelimport analyze`` prints.

The GUI shows the same summary line (:attr:`PanelAnalysis.summary`) and the same
issue messages.
"""

from __future__ import annotations

from panelimport.analysis.result import PanelAnalysis
from panelimport.analysis.roles import ROLE_LABELS


def format_report(a: PanelAnalysis, *, verbose: bool = False) -> str:
    job = a.job
    lines = []
    lines.append(f"Source:   {job.path} ({job.source.kind})")
    lines.append(f"ODB++:    version {job.info.version}, {job.info.application}, default units {job.default_units.value}")
    lines.append(f"Steps:    panel={a.panel_step or '-'}  board={a.board_step or '-'}  mode={a.mode}")
    roles = ", ".join(f"{ROLE_LABELS.get(k, k)}={v}" for k, v in sorted(a.layer_roles.items()))
    lines.append(f"Layers:   {roles or '-'}")
    lines.append("")
    lines.append(f"Panel:    {a.summary}")
    if a.circuits:
        rp = a.circuits[0].transform.apply(*a.reference_board)
        lines.append(
            f"Circuit 1: {a.numbering.first}, {a.numbering.order}; reference {a.reference_kind} "
            f"at ({rp[0]:.3f}, {rp[1]:.3f})"
        )
        lines.append("")
        lines.append("  #       dX        dY   rot(CCW)  mirror  source        residual")
        for c in a.circuits:
            res = "-" if c.residual is None else f"{c.residual:.4f}"
            lines.append(
                f"  {c.index:<3} {c.dx:9.3f} {c.dy:9.3f} {c.rotation:9.3f}  {'yes' if c.mirror else 'no':<6}  "
                f"{c.source:<12}  {res}"
            )
    top = sum(1 for p in a.placements if p.layer == "top")
    bottom = len(a.placements) - top
    panel_fids = [f for f in a.fiducial_candidates if f.selectable]
    lines.append("")
    lines.append(
        f"Placements: {len(a.placements)} per circuit (top {top}, bottom {bottom}); "
        f"panel parts: {len(a.panel_parts)}; fiducial candidates: {len(panel_fids)} panel, "
        f"{len(a.fiducial_candidates) - len(panel_fids)} circuit"
    )
    if panel_fids:
        lines.append(
            "Panel fiducials: "
            + ", ".join(f"{f.name} ({f.x:.3f}, {f.y:.3f}; {'+'.join(f.sources)})" for f in panel_fids)
        )
    if verbose and a.placements:
        lines.append("")
        lines.append("  designator   part             package        side      X         Y      rot   paste")
        ref_x, ref_y = a.reference_board
        for p in a.placements:
            paste = p.paste.describe() if p.paste else "-"
            lines.append(
                f"  {p.designator:<12} {p.part_name[:16]:<16} {p.package[:14]:<14} {p.layer:<6} "
                f"{p.x - ref_x:9.3f} {p.y - ref_y:9.3f} {p.rotation:6.1f}  {paste}"
            )
    counts = a.issue_counts()
    lines.append("")
    lines.append(f"Issues: {counts['error']} errors, {counts['warning']} warnings, {counts['info']} info")
    for issue in a.issues:
        ack = " (acknowledged)" if a.is_acknowledged(issue) else ""
        lines.append("  " + issue.format() + ack)
    ok, why = a.can_confirm()
    lines.append("")
    lines.append("Ready to confirm." if ok else f"Not ready to confirm: {why}.")
    return "\n".join(lines)
