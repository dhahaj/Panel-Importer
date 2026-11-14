"""Settings: tolerances, fiducial patterns, the defaults still to be confirmed, and
where the component database is."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
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
    QPushButton,
    QVBoxLayout,
)

from panelimport.io import compodb
from panelimport.settings import (
    CORNERS,
    ORDERS,
    PANEL_ORIGINS,
    REFERENCE_KINDS,
    STEP_REPEAT_ANCHORS,
    DatabaseSettings,
    Settings,
)

TOLERANCES = [
    ("crosscheck", "Step-repeat vs flattened copies", " mm"),
    ("fit_residual", "Fit residual (flattened panels)", " mm"),
    ("rotation", "Circuit rotated relative to circuit 1", " °"),
    ("grid", "Non-uniform grid", " mm"),
    ("centroid_on_pads", "Centroid from paste-pad centre", " mm"),
    ("pattern_shift", "Whole-pattern paste shift (median)", " mm"),
    ("pad_match_radius", "Toeprint to paste-pad matching radius", " mm"),
    ("fiducial_merge", "Merge fiducial candidates within", " mm"),
]


def _spin(value: float, suffix: str, decimals: int = 4, hi: float = 100.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(0.0, hi)
    s.setSingleStep(0.01)
    s.setSuffix(suffix)
    s.setValue(value)
    return s


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, database: DatabaseSettings | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = copy.deepcopy(settings)
        self.database = copy.deepcopy(database or DatabaseSettings())
        tol_box = QGroupBox("Tolerances")
        tol = QFormLayout(tol_box)
        self.tol = {}
        for key, label, suffix in TOLERANCES:
            self.tol[key] = _spin(getattr(settings.tolerances, key), suffix)
            tol.addRow(label, self.tol[key])

        fid_box = QGroupBox("Fiducial candidates")
        fid = QFormLayout(fid_box)
        self.patterns = QLineEdit(", ".join(settings.fiducials.patterns))
        self.min_d = _spin(settings.fiducials.min_diameter, " mm", 3, 20)
        self.max_d = _spin(settings.fiducials.max_diameter, " mm", 3, 20)
        self.clearance = _spin(settings.fiducials.clearance, " mm", 3, 20)
        self.mask_margin = _spin(settings.fiducials.mask_margin, " mm", 3, 5)
        fid.addRow("Designator/package patterns", self.patterns)
        fid.addRow("Min. pad diameter", self.min_d)
        fid.addRow("Max. pad diameter", self.max_d)
        fid.addRow("Copper-free clearance", self.clearance)
        fid.addRow("Mask opening larger by", self.mask_margin)

        def combo(values, current):
            c = QComboBox()
            c.addItems(values)
            c.setCurrentText(current)
            return c

        def_box = QGroupBox("Defaults to confirm against a real export / golden ISS")
        d = QFormLayout(def_box)
        self.copy_suffix = QLineEdit(settings.copy_suffix_regex)
        self.copy_suffix.setPlaceholderText(r"e.g. _(\d+)$ — empty: copies share identical names")
        self.part_number = QLineEdit(settings.part_number_attribute)
        self.corner = combo(CORNERS, settings.circuit1_corner)
        self.order = combo(ORDERS, settings.numbering_order)
        self.reference = combo(REFERENCE_KINDS, settings.circuit_reference)
        self.origin = combo(PANEL_ORIGINS, settings.panel_origin)
        self.anchor = combo(STEP_REPEAT_ANCHORS, settings.step_repeat_anchor)
        d.addRow("Designator copy suffix (regex)", self.copy_suffix)
        d.addRow("Part-number attribute", self.part_number)
        d.addRow("Circuit 1 corner", self.corner)
        d.addRow("Numbering order", self.order)
        d.addRow("Circuit reference point", self.reference)
        d.addRow("Panel origin", self.origin)
        d.addRow("STEP-REPEAT X/Y place the child's", self.anchor)

        db_box = QGroupBox("Component database (JaNets)")
        db = QFormLayout(db_box)
        self.database_path = QLineEdit(self.database.path)
        self.database_path.setPlaceholderText(r"e.g. C:\ComponentDatabase\Data\DETEX.mdb — empty: not used")
        self.database_path.setToolTip(
            "Read on import and on Update from database: a copy is read, the database itself is never opened"
        )
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_database)
        path_row = QHBoxLayout()
        path_row.addWidget(self.database_path, 1)
        path_row.addWidget(browse)
        self.database_test = QPushButton("Test")
        self.database_test.setToolTip("Read the database now and say how many components it has")
        self.database_test.clicked.connect(self._test_database)
        self.database_result = QLabel(compodb.unavailable())
        self.database_result.setWordWrap(True)
        test_row = QHBoxLayout()
        test_row.addWidget(self.database_test)
        test_row.addWidget(self.database_result, 1)
        db.addRow("Database file", path_row)
        db.addRow("", test_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        layout = QVBoxLayout(self)
        layout.addWidget(tol_box)
        layout.addWidget(fid_box)
        layout.addWidget(def_box)
        layout.addWidget(db_box)
        layout.addWidget(buttons)

    def _defaults(self) -> None:
        fresh = SettingsDialog(Settings(), self)
        for key in self.tol:
            self.tol[key].setValue(fresh.tol[key].value())
        for name in ("patterns", "copy_suffix", "part_number", "database_path"):
            getattr(self, name).setText(getattr(fresh, name).text())
        for name in ("min_d", "max_d", "clearance", "mask_margin"):
            getattr(self, name).setValue(getattr(fresh, name).value())
        for name in ("corner", "order", "reference", "origin", "anchor"):
            getattr(self, name).setCurrentText(getattr(fresh, name).currentText())

    def _browse_database(self) -> None:
        current = self.database_path.text().strip()
        start = str(Path(current).parent) if current else r"C:\ComponentDatabase\Data"
        path, _ = QFileDialog.getOpenFileName(
            self, "Component database", start, "Access databases (*.mdb *.accdb);;All files (*)"
        )
        if path:
            self.database_path.setText(str(Path(path)))

    def _test_database(self) -> None:
        path = self.database_path.text().strip()
        if not path:
            self.database_result.setText("No database set.")
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            db = compodb.read_database(path)
        except compodb.DatabaseError as exc:
            self.database_result.setText(str(exc))
        else:
            self.database_result.setText(f"{len(db.parts)} components.")
        finally:
            QGuiApplication.restoreOverrideCursor()

    def _accept(self) -> None:
        s = Settings()
        for key, spin in self.tol.items():
            setattr(s.tolerances, key, spin.value())
        s.fiducials.patterns = [p.strip() for p in self.patterns.text().split(",") if p.strip()]
        s.fiducials.min_diameter = self.min_d.value()
        s.fiducials.max_diameter = self.max_d.value()
        s.fiducials.clearance = self.clearance.value()
        s.fiducials.mask_margin = self.mask_margin.value()
        s.copy_suffix_regex = self.copy_suffix.text().strip()
        s.part_number_attribute = self.part_number.text().strip()
        s.circuit1_corner = self.corner.currentText()
        s.numbering_order = self.order.currentText()
        s.circuit_reference = self.reference.currentText()
        s.panel_origin = self.origin.currentText()
        s.step_repeat_anchor = self.anchor.currentText()
        problems = s.validate()
        if problems:
            QMessageBox.warning(self, "Settings", "\n".join(problems))
            return
        self.settings = s
        self.database = DatabaseSettings(path=self.database_path.text().strip())
        self.accept()
