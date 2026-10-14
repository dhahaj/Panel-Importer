"""Details of the selected placement, panel part, fiducial or circuit."""

from __future__ import annotations

from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from panelimport.analysis.edits import shown_values, status_text
from panelimport.analysis.result import PanelAnalysis
from panelimport.gui import theme

EXPORT_LABEL = "    export"  # the row under an edited value, showing the export's


def _field(part, a: PanelAnalysis, label: str, field: str, fmt: str = "{}") -> list[tuple]:
    """A value's row, followed by the export's value when an edit changed it."""
    value = shown_values(a, part)[field]
    rows: list[tuple] = [(label, fmt.format(value) if value != "" else "-")]
    if field in part.export:
        old = shown_values(a, part, export=True)[field]
        rows.append((EXPORT_LABEL, fmt.format(old) if old != "" else "(empty)"))
    return rows


def _status_rows(part) -> list[tuple]:
    rows: list[tuple] = [("Status", status_text(part) or "as exported")]
    if part.edit is not None and part.edit.note:
        rows.append(("Note", part.edit.note))
    return rows


class Inspector(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.title = QLabel("Nothing selected")
        self.title.setWordWrap(True)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.table)

    def _rows(self, title: str, rows: list[tuple]) -> None:
        self.title.setText(title)
        self.table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            key = QTableWidgetItem(k)
            item = QTableWidgetItem(v)
            item.setToolTip(v)
            if k == EXPORT_LABEL:  # what the export had, under the edited value
                for cell in (key, item):
                    cell.setForeground(QBrush(theme.REMOVED))
            elif k == "Status" and v != "as exported":
                item.setForeground(QBrush(theme.EDITED))
            self.table.setItem(r, 0, key)
            self.table.setItem(r, 1, item)
        self.table.resizeRowsToContents()

    def clear(self) -> None:
        self._rows("Nothing selected", [])

    def show_placement(self, a: PanelAnalysis, designator: str, circuit: int | None = None) -> None:
        p = next((p for p in [*a.placements, *a.removed_placements] if p.designator == designator), None)
        if p is None:
            self.clear()
            return
        rows = [
            ("Designator", p.designator),
            *_status_rows(p),
            *_field(p, a, "Part name", "part_name"),
            *_field(p, a, "Part number", "part_number"),
            *_field(p, a, "Package", "package"),
            *_field(p, a, "Layer", "layer"),
            *_field(p, a, "Circuit X (mm)", "x", "{:.4f}"),
            *_field(p, a, "Circuit Y (mm)", "y", "{:.4f}"),
            *_field(p, a, "Rotation (CCW)", "rotation", "{:.3f}°"),
            ("Rotation raw (ODB++, CW)", f"{p.rotation_raw:.3f}°"),
            ("Paste check", p.paste.describe() if p.paste else "-"),
        ]
        if p.written and p.written != p.designator:
            rows.append(("Written as", p.written))
        c = next((c for c in a.circuits if c.index == circuit), a.circuits[0] if a.circuits else None)
        if c is not None:
            x, y, rot = a.circuit_position(p, c)
            rows.append((f"Panel X (circuit {c.index})", f"{x:.4f}"))
            rows.append((f"Panel Y (circuit {c.index})", f"{y:.4f}"))
            rows.append((f"Panel rotation in circuit {c.index}", f"{rot:.3f}°"))
        for k, v in sorted(p.attributes.items()):
            rows.append((f"  {k}", v))
        self._rows(f"{p.designator} — {p.part_name}", rows)

    def show_panel_part(self, a: PanelAnalysis, designator: str) -> None:
        pp = next((p for p in [*a.panel_parts, *a.removed_panel_parts] if p.designator == designator), None)
        if pp is None:
            self.clear()
            return
        rows = [
            ("Designator", pp.designator),
            *_status_rows(pp),
            *_field(pp, a, "Part name", "part_name"),
            *_field(pp, a, "Part number", "part_number"),
            *_field(pp, a, "Package", "package"),
            *_field(pp, a, "Layer", "layer"),
            *_field(pp, a, "Panel X (mm)", "x", "{:.4f}"),
            *_field(pp, a, "Panel Y (mm)", "y", "{:.4f}"),
            *_field(pp, a, "Rotation (CCW)", "rotation", "{:.3f}°"),
            ("Rotation raw (CW)", f"{pp.rotation_raw:.3f}°"),
            ("Step", pp.step or "-"),
        ]
        for k, v in sorted(pp.attributes.items()):
            rows.append((f"  {k}", v))
        self._rows(f"{pp.designator} — panel-level part", rows)

    def show_fiducial(self, a: PanelAnalysis, name: str) -> None:
        f = next((f for f in a.fiducial_candidates if f.name == name), None)
        if f is None:
            self.clear()
            return
        picked = [x.name for x in a.fiducials]
        self._rows(
            f"Fiducial {f.name}",
            [
                ("Level", "panel" if f.selectable else f"circuit {f.circuit}"),
                ("Picked", f"yes (#{picked.index(f.name) + 1})" if f.name in picked else "no"),
                ("Sources", ", ".join(f.sources)),
                ("Panel X (mm)", f"{f.x:.4f}"),
                ("Panel Y (mm)", f"{f.y:.4f}"),
                ("Side", f.side),
                ("Diameter (mm)", f"{f.diameter:.3f}" if f.diameter else "-"),
                ("Notes", "; ".join(f.notes) or "-"),
            ],
        )

    def show_circuit(self, a: PanelAnalysis, index: int) -> None:
        c = next((c for c in a.circuits if c.index == index), None)
        if c is None:
            self.clear()
            return
        self._rows(
            f"Circuit {c.index}",
            [
                ("ΔX from circuit 1 (mm)", f"{c.dx:.4f}"),
                ("ΔY from circuit 1 (mm)", f"{c.dy:.4f}"),
                ("Rotation (CCW)", f"{c.rotation:.3f}°"),
                ("Mirrored", "yes" if c.mirror else "no"),
                ("Flipped (sides swapped)", "yes" if c.flip else "no"),
                ("Source", c.source),
                ("Residual (mm)", "-" if c.residual is None else f"{c.residual:.5f}"),
                ("Instance", c.label),
            ],
        )
