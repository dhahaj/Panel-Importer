"""Details of the selected placement, panel part, fiducial or circuit."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from panelimport.analysis.result import PanelAnalysis


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
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.table)

    def _rows(self, title: str, rows: list[tuple[str, str]]) -> None:
        self.title.setText(title)
        self.table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(k))
            item = QTableWidgetItem(v)
            item.setToolTip(v)
            self.table.setItem(r, 1, item)

    def clear(self) -> None:
        self._rows("Nothing selected", [])

    def show_placement(self, a: PanelAnalysis, designator: str, circuit: int | None = None) -> None:
        p = next((p for p in a.placements if p.designator == designator), None)
        if p is None:
            self.clear()
            return
        rx, ry = a.reference_board
        rows = [
            ("Designator", p.designator),
            ("Part name", p.part_name),
            ("Part number", p.part_number or "-"),
            ("Package", p.package or "-"),
            ("Layer", p.layer),
            ("Circuit X (mm)", f"{p.x - rx:.4f}"),
            ("Circuit Y (mm)", f"{p.y - ry:.4f}"),
            ("Rotation (CCW)", f"{p.rotation:.3f}°"),
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
        pp = next((p for p in a.panel_parts if p.designator == designator), None)
        if pp is None:
            self.clear()
            return
        self._rows(
            f"{pp.designator} — panel-level part",
            [
                ("Designator", pp.designator),
                ("Part name", pp.part_name),
                ("Layer", pp.layer),
                ("Panel X (mm)", f"{pp.x:.4f}"),
                ("Panel Y (mm)", f"{pp.y:.4f}"),
                ("Rotation (CCW)", f"{pp.rotation:.3f}°"),
                ("Rotation raw (CW)", f"{pp.rotation_raw:.3f}°"),
                ("Step", pp.step),
            ],
        )

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
