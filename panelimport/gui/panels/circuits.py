"""Circuits table with the choice of circuit 1, numbering order and reference point."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from panelimport.analysis.result import PanelAnalysis
from panelimport.settings import CORNERS, ORDERS, REFERENCE_KINDS

COLUMNS = ["#", "ΔX (mm)", "ΔY (mm)", "Rotation (°)", "Mirror", "Source", "Residual (mm)"]


def num_item(value: float | int | None, fmt: str = "{:.3f}") -> QTableWidgetItem:
    item = QTableWidgetItem("-" if value is None else fmt.format(value))
    item.setData(Qt.UserRole, value)
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


def text_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


class CircuitsPanel(QWidget):
    numberingChanged = Signal(str, str)
    referenceChanged = Signal(str)
    circuitActivated = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.first = QComboBox()
        self.first.addItems(CORNERS)
        self.order = QComboBox()
        self.order.addItems(ORDERS)
        self.reference = QComboBox()
        self.reference.addItems(REFERENCE_KINDS)
        form = QFormLayout()
        form.addRow("Circuit 1 corner", self.first)
        form.addRow("Numbering order", self.order)
        form.addRow("Reference point", self.reference)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selected)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(form)
        layout.addWidget(self.table)
        self._updating = False
        self.first.currentTextChanged.connect(self._numbering)
        self.order.currentTextChanged.connect(self._numbering)
        self.reference.currentTextChanged.connect(self._reference)

    def _numbering(self) -> None:
        if not self._updating:
            self.numberingChanged.emit(self.first.currentText(), self.order.currentText())

    def _reference(self, kind: str) -> None:
        if not self._updating:
            self.referenceChanged.emit(kind)

    def _selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows and not self._updating:
            self.circuitActivated.emit(self.table.item(rows[0].row(), 0).data(Qt.UserRole))

    def set_analysis(self, a: PanelAnalysis | None, read_only: bool = False) -> None:
        self._updating = True
        try:
            self.table.setRowCount(0)
            for w in (self.first, self.order, self.reference):
                w.setEnabled(a is not None and not read_only)
            if a is None:
                return
            self.first.setCurrentText(a.numbering.first)
            self.order.setCurrentText(a.numbering.order)
            if a.reference_kind in REFERENCE_KINDS:
                self.reference.setCurrentText(a.reference_kind)
            self.table.setRowCount(len(a.circuits))
            for r, c in enumerate(a.circuits):
                self.table.setItem(r, 0, num_item(c.index, "{}"))
                self.table.setItem(r, 1, num_item(c.dx))
                self.table.setItem(r, 2, num_item(c.dy))
                self.table.setItem(r, 3, num_item(c.rotation))
                self.table.setItem(r, 4, text_item("yes" if c.mirror else "no"))
                self.table.setItem(r, 5, text_item(c.source))
                self.table.setItem(r, 6, num_item(c.residual, "{:.4f}"))
        finally:
            self._updating = False
