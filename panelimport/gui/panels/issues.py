"""The issue list: severity, message, designator/circuit; clicking zooms to the issue."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from panelimport.analysis.result import PanelAnalysis
from panelimport.gui import theme
from panelimport.model.issues import Issue

COLUMNS = ["Severity", "Code", "Message", "Where", "Status"]


class IssuesPanel(QWidget):
    issueActivated = Signal(object)
    acknowledgeRequested = Signal(list)
    unacknowledgeRequested = Signal(list)
    panelLevelRequested = Signal(list)
    removePartsRequested = Signal(list)  # issues naming components to remove

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.filters = {s: QCheckBox(s.capitalize()) for s in ("error", "warning", "info")}
        for cb in self.filters.values():
            cb.setChecked(True)
            cb.toggled.connect(lambda _on: self._refill())
        self.model = QStandardItemModel(0, len(COLUMNS))
        self.model.setHorizontalHeaderLabels(COLUMNS)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.clicked.connect(self._clicked)
        self.table.selectionModel().selectionChanged.connect(self._update_buttons)
        self.ack_btn = QPushButton("Acknowledge")
        self.unack_btn = QPushButton("Un-acknowledge")
        self.panel_btn = QPushButton("Confirm as panel-level")
        self.remove_btn = QPushButton("Remove part…")
        self.remove_btn.setToolTip("Do not place the components these issues name (e.g. through-hole or not populated)")
        self.ack_btn.setToolTip("Warnings must be acknowledged before the panel can be confirmed")
        self.panel_btn.setToolTip("For designators whose copy count differs from N: they are fiducials, tooling or other panel parts")
        self.ack_btn.clicked.connect(lambda: self.acknowledgeRequested.emit(self._selected(lambda i: not i.is_error)))
        self.unack_btn.clicked.connect(lambda: self.unacknowledgeRequested.emit(self._selected(lambda i: not i.is_error)))
        self.panel_btn.clicked.connect(
            lambda: self.panelLevelRequested.emit(
                sorted({i.designator for i in self._selected(lambda i: i.code == "copy_count") if i.designator})
            )
        )
        self.remove_btn.clicked.connect(lambda: self.removePartsRequested.emit(self._selected(self._names_part)))
        top = QHBoxLayout()
        for cb in self.filters.values():
            top.addWidget(cb)
        top.addStretch(1)
        top.addWidget(self.ack_btn)
        top.addWidget(self.unack_btn)
        top.addWidget(self.panel_btn)
        top.addWidget(self.remove_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.analysis: PanelAnalysis | None = None
        self.read_only = False
        self._rows: list[Issue] = []
        self._update_buttons()

    def set_analysis(self, a: PanelAnalysis | None, read_only: bool = False) -> None:
        self.analysis = a
        self.read_only = read_only
        self._refill()

    def _refill(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self._rows = []
        a = self.analysis
        if a is None:
            self._update_buttons()
            return
        counts = a.issue_counts()
        for sev, cb in self.filters.items():
            cb.setText(f"{sev.capitalize()}s ({counts[sev]})" if sev != "info" else f"Info ({counts[sev]})")
        for issue in a.issues:
            if not self.filters[issue.severity.value].isChecked():
                continue
            acked = a.is_acknowledged(issue)
            status = "acknowledged" if acked else ("needs acknowledgement" if issue.is_warning else "")
            if issue.is_error:
                status = "blocks confirmation"
            values = [issue.severity.label, issue.code, issue.message, issue.where(), status]
            row = [QStandardItem(v) for v in values]
            row[0].setForeground(QBrush(theme.SEVERITY_COLOR[issue.severity.value]))
            row[2].setToolTip(issue.message)
            if acked:
                for item in row:
                    item.setForeground(QBrush(Qt.gray))
            self.model.appendRow(row)
            self._rows.append(issue)
        for col in (0, 1, 3, 4):
            self.table.resizeColumnToContents(col)
        self._update_buttons()

    def issue_at(self, row: int) -> Issue:
        return self._rows[row]

    def _selected(self, predicate=lambda i: True) -> list[Issue]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self._rows[r] for r in rows if predicate(self._rows[r])]

    def _clicked(self, index) -> None:
        if 0 <= index.row() < len(self._rows):
            self.issueActivated.emit(self._rows[index.row()])

    def _names_part(self, issue: Issue) -> bool:
        """Whether the issue names a component that is placed."""
        a = self.analysis
        if a is None or not issue.designator:
            return False
        return any(p.designator == issue.designator for p in [*a.placements, *a.panel_parts])

    def _update_buttons(self, *args) -> None:
        sel = self._selected() if self._rows else []
        a = self.analysis
        editable = a is not None and not self.read_only
        self.ack_btn.setEnabled(editable and any(not i.is_error and not a.is_acknowledged(i) for i in sel))
        self.unack_btn.setEnabled(editable and any(not i.is_error and a.is_acknowledged(i) for i in sel))
        self.panel_btn.setEnabled(editable and any(i.code == "copy_count" for i in sel))
        self.remove_btn.setEnabled(editable and any(self._names_part(i) for i in sel))
