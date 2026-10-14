"""Phase 2 dialogs: File → Export ISS… and File → Compare programs…

Export shows the main ISS settings, the side being written (and the flip axis for a
bottom-layer panel), a summary, the pre-write issues and a preview of the panel as the
machine will see it; errors disable **Write**.  Compare reads two programs (ISS or
``.x21``) and shows the part-by-part table; nothing is edited.
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from panelimport.gui import theme
from panelimport.iss.checks import Prepared, prepare
from panelimport.iss.compare import DEFAULT_TOLERANCE, Comparison, compare_programs, format_comparison, panel_geometry
from panelimport.iss.mapping import panel_side
from panelimport.iss.reader import ReadError, read_program
from panelimport.iss.report import summary_lines
from panelimport.iss.settings import BOTTOM_FLIPS, IssSettings
from panelimport.iss.writer import ISS_SUFFIX, IssWriteError, write_iss
from panelimport.model.panel import PanelProject

ROTATIONS = ["auto", "0", "90", "180", "270"]
PROGRAM_FILTER = "Placement programs (*.iss *.x21);;ISS programs (*.iss);;JaNets programs (*.x21);;All files (*)"


def _spin(value: float, lo: float, hi: float, suffix: str, decimals: int = 4) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(lo, hi)
    s.setSuffix(suffix)
    s.setValue(value)
    return s


# -------------------------------------------------------------------- preview
class ProgramPreview(QWidget):
    """The program's panel as the machine sees it: lower-left at 0,0, X along the
    conveyor, the FRONT (fixed) rail at the bottom.  Drawn from the program itself."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 220)
        self.prepared: Prepared | None = None

    def set_prepared(self, prepared: Prepared | None) -> None:
        self.prepared = prepared
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.CANVAS_BACKGROUND)
        layout = self.prepared.layout if self.prepared else None
        if layout is None or layout.program.width <= 0 or layout.program.height <= 0:
            p.setPen(QColor("#8b949e"))
            p.drawText(self.rect(), Qt.AlignCenter, "No preview")
            return
        prog = layout.program
        geom = panel_geometry(prog, self.prepared.settings.angle_direction)
        margin = 28.0
        scale = min((self.width() - 2 * margin) / prog.width, (self.height() - 2 * margin) / prog.height)
        ox = (self.width() - prog.width * scale) / 2
        oy = (self.height() + prog.height * scale) / 2

        def pt(x: float, y: float) -> QPointF:
            return QPointF(ox + x * scale, oy - y * scale)

        p.setPen(QPen(theme.STYLE["panel_outline"].color, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(pt(0, prog.height), pt(prog.width, 0)))
        circuit_pen = QPen(theme.STYLE["circuit_outlines"].color, 1)
        for c, number in zip(geom.circuits, layout.circuit_numbers):
            p.setPen(circuit_pen)
            p.drawPolygon(QPolygonF([pt(x, y) for x, y in c.outline]))
            cx = sum(x for x, _ in c.outline) / 4
            cy = sum(y for _, y in c.outline) / 4
            p.drawText(QRectF(pt(cx, cy) - QPointF(20, 8), pt(cx, cy) + QPointF(20, 8)), Qt.AlignCenter, str(number))
        dot = theme.STYLE["centroids_bottom" if layout.machine.side == "bottom" else "centroids_top"].color
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(dot))
        for part in geom.placements:
            p.drawEllipse(pt(part.x, part.y), 1.6, 1.6)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(theme.STYLE["fiducials"].color, 1.5))
        for _name, x, y in geom.fiducials:
            p.drawEllipse(pt(x, y), 5, 5)
        # P, the program origin.
        p.setPen(QPen(theme.SELECTED_FIDUCIAL, 1.5))
        o = pt(*geom.origin)
        p.drawLine(o - QPointF(6, 0), o + QPointF(6, 0))
        p.drawLine(o - QPointF(0, 6), o + QPointF(0, 6))
        p.drawText(o + QPointF(5, -5), "P")
        # Conveyor direction (left to right) and the fixed FRONT rail.
        p.setPen(QPen(QColor("#8b949e"), 1))
        y = self.height() - 8
        p.drawText(QRectF(0, y - 14, self.width(), 14), Qt.AlignCenter, "FRONT rail · conveyor →")
        p.drawText(QRectF(4, 2, self.width() - 8, 16), Qt.AlignLeft, layout.machine.describe())


# -------------------------------------------------------------------- export
class ExportIssDialog(QDialog):
    def __init__(
        self,
        project: PanelProject,
        settings: IssSettings,
        output: Path,
        *,
        pwb_id: str,
        confirmed: bool = True,
        qsettings: QSettings | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export ISS")
        self.project = project
        self.base = copy.deepcopy(settings)
        self.default_pwb_id = pwb_id
        self.confirmed = confirmed
        self.qsettings = qsettings
        self.prepared: Prepared | None = None
        self.written: Path | None = None

        # ---------------------------------------------------------- settings
        box = QGroupBox("Settings")
        form = QFormLayout(box)
        self.pwb_id = QLineEdit(settings.pwb_id)
        self.pwb_id.setPlaceholderText(pwb_id)
        self.rotation = QComboBox()
        self.rotation.addItems(ROTATIONS)
        self.rotation.setCurrentText(str(settings.panel_rotation))
        self.clamp = _spin(0.0 if settings.clamp_offset_y == "auto" else float(settings.clamp_offset_y), 0.0, 1000.0, " mm")
        self.clamp.setSpecialValueText("auto (panel height / 2)")
        self.direction = QComboBox()
        self.direction.addItems(["ccw", "cw"])
        self.direction.setCurrentText(settings.angle_direction)
        self.offset = _spin(settings.angle_offset, -360.0, 360.0, " °", 3)
        form.addRow("pwbId", self.pwb_id)
        form.addRow("Panel rotation (CCW)", self.rotation)
        form.addRow("Clamp offset Y", self.clamp)
        form.addRow("Angle direction", self.direction)
        form.addRow("Angle offset", self.offset)

        side_box = QGroupBox("Side")
        side_form = QFormLayout(side_box)
        side = panel_side(project)
        self.side_label = QLabel({"bottom": "Bottom layer", "top": "Top layer", "mixed": "Both layers (refused)"}[side] + " (from the placements)")
        self.flip = QComboBox()
        self.flip.addItems(list(BOTTOM_FLIPS))
        self.flip.setCurrentText(settings.bottom_flip)
        self.flip.setEnabled(side == "bottom")
        self.bottom_offset = _spin(settings.bottom_angle_offset, -360.0, 360.0, " °", 3)
        self.bottom_offset.setEnabled(side == "bottom")
        side_form.addRow("Placements on", self.side_label)
        side_form.addRow("Turned over", self.flip)
        side_form.addRow("Bottom angle offset", self.bottom_offset)

        self.summary = QLabel()
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary.setWordWrap(True)
        summary_box = QGroupBox("Summary")
        QVBoxLayout(summary_box).addWidget(self.summary)

        self.preview = ProgramPreview()
        preview_box = QGroupBox("As the machine sees it")
        QVBoxLayout(preview_box).addWidget(self.preview)

        # ---------------------------------------------------------- issues
        self.issues = QStandardItemModel(0, 4)
        self.issues.setHorizontalHeaderLabels(["Severity", "Code", "Message", "Where"])
        self.issue_view = _table(self.issues)
        self.issue_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        # ---------------------------------------------------------- output
        self.output = QLineEdit(str(output))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Write to"))
        out_row.addWidget(self.output, 1)
        out_row.addWidget(browse)
        self.remember = QCheckBox("Save these settings as the default")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.write_button = self.buttons.addButton("Write", QDialogButtonBox.AcceptRole)
        self.buttons.accepted.connect(self._write)
        self.buttons.rejected.connect(self.reject)

        left = QVBoxLayout()
        left.addWidget(box)
        left.addWidget(side_box)
        left.addWidget(summary_box)
        left.addStretch(1)
        top = QHBoxLayout()
        top.addLayout(left, 0)
        top.addWidget(preview_box, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(top, 3)
        layout.addWidget(QLabel("Checks before writing (errors must be fixed in the project)"))
        layout.addWidget(self.issue_view, 2)
        layout.addLayout(out_row)
        layout.addWidget(self.remember)
        layout.addWidget(self.buttons)
        self.resize(1000, 760)

        for w in (self.rotation, self.direction, self.flip):
            w.currentTextChanged.connect(self._refresh)
        for w in (self.clamp, self.offset, self.bottom_offset):
            w.valueChanged.connect(self._refresh)
        self.pwb_id.textChanged.connect(self._refresh)
        self._refresh()

    # ---------------------------------------------------------------- state
    def settings(self) -> IssSettings:
        s = copy.deepcopy(self.base)
        s.pwb_id = self.pwb_id.text().strip()
        rot = self.rotation.currentText()
        s.panel_rotation = rot if rot == "auto" else int(rot)
        s.clamp_offset_y = "auto" if self.clamp.value() == self.clamp.minimum() else round(self.clamp.value(), 4)
        s.angle_direction = self.direction.currentText()
        s.angle_offset = self.offset.value()
        s.bottom_flip = self.flip.currentText()
        s.bottom_angle_offset = self.bottom_offset.value()
        return s

    def _refresh(self, *_args) -> None:
        settings = self.settings()
        self.prepared = prepare(self.project, settings, pwb_id=self.default_pwb_id, confirmed=self.confirmed)
        self.summary.setText("\n".join(summary_lines(self.prepared)))
        self.preview.set_prepared(self.prepared)
        self.issues.removeRows(0, self.issues.rowCount())
        for issue in self.prepared.issues:
            sev = QStandardItem(issue.severity.label)
            sev.setForeground(QBrush(theme.SEVERITY_COLOR[issue.severity.value]))
            self.issues.appendRow([sev, QStandardItem(issue.code), QStandardItem(issue.message), QStandardItem(issue.where())])
        self.issue_view.resizeColumnToContents(0)
        self.issue_view.resizeColumnToContents(1)
        errors = len(self.prepared.errors)
        self.write_button.setEnabled(self.prepared.can_write)
        self.write_button.setToolTip(f"{errors} error(s) must be fixed first" if errors else "")

    def _browse(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self, "Export ISS", self.output.text(), "ISS programs (*.iss)")
        if name:
            if not name.lower().endswith(ISS_SUFFIX):
                name += ISS_SUFFIX
            self.output.setText(name)

    def _write(self) -> None:
        if self.prepared is None or not self.prepared.can_write:
            return
        path = Path(self.output.text().strip())
        if not path.name:
            return
        if path.exists():
            r = QMessageBox.question(self, "Export ISS", f"{path} exists. Replace it?")
            if r != QMessageBox.Yes:
                return
        try:
            self.written = write_iss(self.prepared, path)
        except (IssWriteError, OSError) as exc:
            QMessageBox.warning(self, "Export ISS", f"Not written: {exc}")
            return
        if self.remember.isChecked():
            defaults = self.settings()
            defaults.pwb_id = self.base.pwb_id  # the pwbId belongs to this project, not to every export
            try:
                defaults.save()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Export ISS", f"Written, but the settings were not saved: {exc}")
        self.accept()


# -------------------------------------------------------------------- compare
COMPARE_COLUMNS = ["Designator", "A#", "B#", "X (A)", "Y (A)", "ΔX", "ΔY", "Angle A", "Angle B", "Δangle", "Component"]


class CompareDialog(QDialog):
    def __init__(self, qsettings: QSettings | None = None, parent=None, a: str = "", b: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare programs")
        self.qsettings = qsettings
        self.comparison: Comparison | None = None
        self.path_a = QLineEdit(a)
        self.path_b = QLineEdit(b)
        self.tolerance = _spin(DEFAULT_TOLERANCE, 0.0, 10.0, " mm")
        self.all_rows = QCheckBox("Show every part")
        self.all_rows.toggled.connect(lambda _on: self._fill())
        run = QPushButton("Compare")
        run.clicked.connect(self.run)

        form = QFormLayout()
        for label, edit in (("Program A", self.path_a), ("Program B", self.path_b)):
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            btn = QPushButton("Browse…")
            btn.clicked.connect(lambda _c=False, e=edit: self._browse(e))
            row.addWidget(btn)
            form.addRow(label, row)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Positions match within"))
        opts.addWidget(self.tolerance)
        opts.addWidget(self.all_rows)
        opts.addStretch(1)
        opts.addWidget(run)
        form.addRow(opts)

        self.summary = QLabel("Pick two programs (ISS or .x21) and press Compare.")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.model = QStandardItemModel(0, len(COMPARE_COLUMNS))
        self.model.setHorizontalHeaderLabels(COMPARE_COLUMNS)
        self.table = _table(self.model)
        self.table.setSortingEnabled(True)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.details)
        split.setSizes([500, 200])

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(split, 1)
        layout.addWidget(buttons)
        self.resize(1100, 760)

    def _browse(self, edit: QLineEdit) -> None:
        start = edit.text() or (str(self.qsettings.value("programs/last_dir", str(Path.home()))) if self.qsettings else "")
        name, _ = QFileDialog.getOpenFileName(self, "Program", start, PROGRAM_FILTER)
        if name:
            edit.setText(name)
            if self.qsettings is not None:
                self.qsettings.setValue("programs/last_dir", str(Path(name).parent))

    def run(self) -> bool:
        try:
            a = read_program(self.path_a.text().strip())
            b = read_program(self.path_b.text().strip())
        except (ReadError, OSError) as exc:
            QMessageBox.warning(self, "Compare programs", str(exc))
            return False
        self.comparison = compare_programs(a, b, tolerance=self.tolerance.value())
        self._fill()
        return True

    def _fill(self) -> None:
        cmp = self.comparison
        self.model.removeRows(0, self.model.rowCount())
        if cmp is None:
            return
        self.summary.setText(cmp.summary())
        self.table.setSortingEnabled(False)
        rows = cmp.rows if self.all_rows.isChecked() else cmp.changed
        far = QBrush(theme.SEVERITY_COLOR["error"])
        for r in rows:
            comp = r.component_a if r.component_a == r.component_b else f"{r.component_a} → {r.component_b}"
            values = [r.designator, r.circuit_a, r.circuit_b, r.a[0], r.a[1], r.dx, r.dy, r.a[2], r.b[2], r.dangle, comp]
            items = []
            for v in values:
                item = QStandardItem()
                if isinstance(v, float):
                    item.setData(round(v, 4), Qt.DisplayRole)
                elif isinstance(v, int):
                    item.setData(v, Qt.DisplayRole)
                else:
                    item.setText(str(v))
                items.append(item)
            if r.distance > cmp.tolerance:
                for item in items[5:7]:
                    item.setForeground(far)
            self.model.appendRow(items)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        text = format_comparison(cmp, name_a=self.path_a.text(), name_b=self.path_b.text())
        # The table already lists the parts; the text keeps the panel, circuit and fiducial sections.
        head, sep, tail = text.partition("\nParts that differ")
        rest = tail.split("\n", 1)[1] if sep else ""
        extra = "\n".join(line for line in rest.splitlines() if not line.startswith("  ") and not line.startswith(" *"))
        self.details.setPlainText(head + ("\n" + extra if extra else ""))


def _table(model: QStandardItemModel) -> QTableView:
    view = QTableView()
    view.setModel(model)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.verticalHeader().setVisible(False)
    view.setWordWrap(False)
    return view
