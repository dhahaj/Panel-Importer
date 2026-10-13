"""Single-board setup: the circuit grid, circuit 1's origin, the panel outline and fiducials."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from panelimport.model.panel import Fiducial, SingleBoardSetup


def _mm(value: float = 0.0, lo: float = -2000.0, hi: float = 2000.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(4)
    s.setSuffix(" mm")
    s.setValue(value)
    return s


class SingleBoardDialog(QDialog):
    def __init__(self, parent=None, setup: SingleBoardSetup | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Single-board setup")
        setup = setup or SingleBoardSetup()
        intro = QLabel(
            "This export is a single board (no STEP-REPEAT, every designator once). Enter how the board is "
            "repeated on the panel. The generated copies are drawn over the panel outline so a wrong origin or "
            "pitch shows up immediately."
        )
        intro.setWordWrap(True)

        self.cols = QSpinBox()
        self.cols.setRange(1, 100)
        self.cols.setValue(setup.cols)
        self.rows = QSpinBox()
        self.rows.setRange(1, 100)
        self.rows.setValue(setup.rows)
        self.pitch_x = _mm(setup.pitch_x)
        self.pitch_y = _mm(setup.pitch_y)
        self.use_table = QCheckBox("Use a per-circuit offset table instead")
        self.table = QPlainTextEdit()
        self.table.setPlaceholderText("One circuit per line: dX, dY (mm) from circuit 1, e.g.\n0, 0\n52, 0\n0, 38.5")
        if setup.offsets:
            self.use_table.setChecked(True)
            self.table.setPlainText("\n".join(f"{o[0]}, {o[1]}" for o in setup.offsets))
        self.use_table.toggled.connect(self._toggle)
        grid = QGroupBox("Circuit grid")
        g = QFormLayout(grid)
        g.addRow("Columns", self.cols)
        g.addRow("Rows", self.rows)
        g.addRow("Pitch X", self.pitch_x)
        g.addRow("Pitch Y", self.pitch_y)
        g.addRow(self.use_table)
        g.addRow(self.table)

        self.origin_x = _mm(setup.origin_x)
        self.origin_y = _mm(setup.origin_y)
        origin = QGroupBox("Circuit 1 board origin, measured from the panel origin")
        o = QFormLayout(origin)
        o.addRow("X", self.origin_x)
        o.addRow("Y", self.origin_y)

        self.width = _mm(setup.panel_width, 0)
        self.height = _mm(setup.panel_height, 0)
        self.panel_source = QLineEdit(setup.panel_source or "")
        self.panel_source.setPlaceholderText("optional: a panel ODB++ export for the outline, paste and fiducials")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        src_row = QHBoxLayout()
        src_row.addWidget(self.panel_source, 1)
        src_row.addWidget(browse)
        src = QWidget()
        src.setLayout(src_row)
        self.fiducials = QPlainTextEdit()
        self.fiducials.setPlaceholderText("Panel fiducials, one per line: name, X, Y (mm), up to 3")
        self.fiducials.setPlainText("\n".join(f"{f.name}, {f.x}, {f.y}" for f in setup.fiducials))
        panel = QGroupBox("Panel")
        p = QFormLayout(panel)
        p.addRow("Width", self.width)
        p.addRow("Height", self.height)
        p.addRow("Panel export", src)
        p.addRow("Fiducials", self.fiducials)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Confirm single-board mode")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(grid)
        layout.addWidget(origin)
        layout.addWidget(panel)
        layout.addWidget(buttons)
        self._toggle(self.use_table.isChecked())
        self.result_setup: SingleBoardSetup | None = None

    def _toggle(self, on: bool) -> None:
        self.table.setEnabled(on)
        for w in (self.cols, self.rows, self.pitch_x, self.pitch_y):
            w.setEnabled(not on)

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Panel ODB++ export", "", "ODB++ (*.tgz *.zip *.tar);;All files (*)")
        if not f:
            f = QFileDialog.getExistingDirectory(self, "Panel ODB++ folder")
        if f:
            self.panel_source.setText(f)

    @staticmethod
    def _rows(text: str, n: int) -> list[list[str]]:
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.replace(";", ",").split(",")]
            if len(parts) != n:
                raise ValueError(f"expected {n} values: {line!r}")
            out.append(parts)
        return out

    def _accept(self) -> None:
        try:
            offsets = None
            if self.use_table.isChecked():
                offsets = [[float(a), float(b)] for a, b in self._rows(self.table.toPlainText(), 2)]
                if not offsets:
                    raise ValueError("the offset table is empty")
            fids = [Fiducial(n, float(x), float(y), "manual") for n, x, y in self._rows(self.fiducials.toPlainText(), 3)]
            if len(fids) > 3:
                raise ValueError("at most 3 panel fiducials")
        except ValueError as exc:
            QMessageBox.warning(self, "Single-board setup", str(exc))
            return
        self.result_setup = SingleBoardSetup(
            cols=self.cols.value(),
            rows=self.rows.value(),
            pitch_x=self.pitch_x.value(),
            pitch_y=self.pitch_y.value(),
            offsets=offsets,
            origin_x=self.origin_x.value(),
            origin_y=self.origin_y.value(),
            panel_width=self.width.value(),
            panel_height=self.height.value(),
            fiducials=fids,
            panel_source=self.panel_source.text().strip() or None,
        )
        self.accept()
