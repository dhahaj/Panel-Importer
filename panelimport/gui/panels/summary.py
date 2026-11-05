"""Panel summary line with Confirm and Edit."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from panelimport.analysis.result import PanelAnalysis
from panelimport.iss.mapping import output_mode
from panelimport.iss.settings import IssSettings


def kind_text(a: PanelAnalysis) -> str:
    """The panel type and the ISS output it gets by default (circuit_output auto)."""
    text = f"Panel type: {a.panel_type}"
    if not a.circuits or (a.mode == "single-board" and a.decisions.single_board is None):
        return text
    mode, why = output_mode(a.to_project(), IssSettings())
    output = "flattened into one circuit" if mode == "flatten" else "one allocation per circuit"
    return f"{text} · ISS output: {output} ({why})"


class SummaryBar(QFrame):
    confirmRequested = Signal()
    editRequested = Signal()
    singleBoardRequested = Signal()
    asIsToggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("summaryBar")
        self.setFrameShape(QFrame.StyledPanel)
        self.summary = QLabel("Import an ODB++ export to start (File → Import ODB++…)")
        f = QFont(self.summary.font())
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.summary.setFont(f)
        self.status = QLabel("")
        self.status.setObjectName("summaryStatus")
        self.kind = QLabel("")
        self.kind.setObjectName("summaryKind")
        self.kind.setWordWrap(True)
        self.as_is_btn = QPushButton("Whole panel as one circuit")
        self.as_is_btn.setCheckable(True)
        self.as_is_btn.setToolTip(
            "No STEP-REPEAT: place the panel step as it is, every component where it is, in one circuit"
        )
        self.as_is_btn.clicked.connect(self.asIsToggled)
        self.single_btn = QPushButton("Single-board setup…")
        self.edit_btn = QPushButton("Edit…")
        self.confirm_btn = QPushButton("Confirm panel")
        self.confirm_btn.setObjectName("confirmButton")
        self.single_btn.clicked.connect(self.singleBoardRequested)
        self.edit_btn.clicked.connect(self.editRequested)
        self.confirm_btn.clicked.connect(self.confirmRequested)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.summary)
        text.addWidget(self.kind)
        text.addWidget(self.status)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.addLayout(text, 1)
        row.addWidget(self.as_is_btn)
        row.addWidget(self.single_btn)
        row.addWidget(self.edit_btn)
        row.addWidget(self.confirm_btn)
        self.set_analysis(None)

    def set_analysis(self, a: PanelAnalysis | None, read_only: bool = False) -> None:
        if a is None:
            self.summary.setText("Import an ODB++ export to start (File → Import ODB++…)")
            self.status.setText("")
            self.kind.setText("")
            for b in (self.single_btn, self.edit_btn, self.confirm_btn, self.as_is_btn):
                b.setEnabled(False)
            self.single_btn.setVisible(False)
            self.as_is_btn.setVisible(False)
            return
        self.summary.setText(a.summary)
        self.kind.setText(kind_text(a))
        ok, why = a.can_confirm()
        if read_only:
            self.status.setText("Saved project shown read-only: the source export is missing")
            self.status.setStyleSheet("color: #ffb000;")
        elif a.confirmed:
            n = len(a.fiducials)
            self.status.setText(f"✓ Panel confirmed — {n} of 3 panel fiducials picked")
            self.status.setStyleSheet("color: #3fb950;")
        elif ok:
            self.status.setText("Ready to confirm")
            self.status.setStyleSheet("color: #58a6ff;")
        else:
            self.status.setText(f"Not ready to confirm: {why}")
            self.status.setStyleSheet("color: #ff7b72;")
        self.single_btn.setVisible(a.mode == "single-board")
        self.single_btn.setEnabled(not read_only)
        # Offered for a panel step without STEP-REPEAT, whatever was made of it.
        self.as_is_btn.setVisible(a.mode in ("single-board", "flattened", "as-is"))
        self.as_is_btn.setChecked(a.mode == "as-is")
        self.as_is_btn.setEnabled(not read_only)
        self.edit_btn.setEnabled(not read_only)
        self.confirm_btn.setEnabled(ok and not a.confirmed and not read_only)
        self.confirm_btn.setText("Confirmed" if a.confirmed else "Confirm panel")
