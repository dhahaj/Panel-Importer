"""Fiducial candidates and the (at most three) accepted panel fiducials."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from panelimport.analysis.result import PanelAnalysis

COLUMNS = ["Pick", "Name", "Source", "X (mm)", "Y (mm)", "Side", "Ø (mm)"]


class FiducialsPanel(QWidget):
    acceptRequested = Signal(str)
    removeRequested = Signal(str)
    fiducialSelected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.itemDoubleClicked.connect(lambda _i: self._toggle())
        self.accept_btn = QPushButton("Accept")
        self.remove_btn = QPushButton("Remove")
        self.accept_btn.clicked.connect(lambda: self._emit(self.acceptRequested))
        self.remove_btn.clicked.connect(lambda: self._emit(self.removeRequested))
        self.info = QLabel("")
        self.info.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.accept_btn)
        buttons.addWidget(self.remove_btn)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel("Panel fiducial candidates (click one on the canvas to accept or remove it):"))
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        layout.addWidget(self.info)
        self._updating = False
        self._picked: list[str] = []

    def current(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 1).text() if rows else None

    def _emit(self, signal) -> None:
        name = self.current()
        if name:
            signal.emit(name)

    def _toggle(self) -> None:
        name = self.current()
        if name:
            (self.removeRequested if name in self._picked else self.acceptRequested).emit(name)

    def _selected(self) -> None:
        name = self.current()
        if name and not self._updating:
            self.fiducialSelected.emit(name)
        self.accept_btn.setEnabled(bool(name) and name not in self._picked and self.table.isEnabled())
        self.remove_btn.setEnabled(bool(name) and name in self._picked and self.table.isEnabled())

    def set_analysis(self, a: PanelAnalysis | None, read_only: bool = False) -> None:
        self._updating = True
        try:
            self.table.setRowCount(0)
            self.table.setEnabled(a is not None and not read_only)
            if a is None:
                self.info.setText("")
                self._picked = []
                return
            self._picked = [f.name for f in a.fiducials]
            panel = [f for f in a.fiducial_candidates if f.selectable]
            self.table.setRowCount(len(panel))
            for r, f in enumerate(panel):
                pick = str(self._picked.index(f.name) + 1) if f.name in self._picked else ""
                values = [pick, f.name, "+".join(f.sources), f"{f.x:.3f}", f"{f.y:.3f}", f.side, f"{f.diameter:.3f}" if f.diameter else "-"]
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v)
                    if c in (3, 4, 6):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(r, c, item)
            local = len(a.fiducial_candidates) - len(panel)
            text = f"{len(self._picked)} of 3 panel fiducials picked."
            if local:
                text += f" {local} circuit-level fiducials are shown in grey on the canvas; they are not selectable."
            if not a.confirmed and not read_only:
                text += " Fiducials are picked after the panel is confirmed."
            self.info.setText(text)
        finally:
            self._updating = False
        self._selected()

    def select(self, name: str) -> None:
        self._updating = True
        try:
            for r in range(self.table.rowCount()):
                if self.table.item(r, 1).text() == name:
                    self.table.selectRow(r)
                    return
        finally:
            self._updating = False
