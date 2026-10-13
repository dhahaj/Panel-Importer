"""Settings: tolerances, fiducial patterns and the defaults still to be confirmed."""

from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from panelimport.settings import CORNERS, ORDERS, PANEL_ORIGINS, REFERENCE_KINDS, STEP_REPEAT_ANCHORS, Settings

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
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = copy.deepcopy(settings)
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

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        layout = QVBoxLayout(self)
        layout.addWidget(tol_box)
        layout.addWidget(fid_box)
        layout.addWidget(def_box)
        layout.addWidget(buttons)

    def _defaults(self) -> None:
        fresh = SettingsDialog(Settings(), self)
        for key in self.tol:
            self.tol[key].setValue(fresh.tol[key].value())
        for name in ("patterns", "copy_suffix", "part_number"):
            getattr(self, name).setText(getattr(fresh, name).text())
        for name in ("min_d", "max_d", "clearance", "mask_margin"):
            getattr(self, name).setValue(getattr(fresh, name).value())
        for name in ("corner", "order", "reference", "origin", "anchor"):
            getattr(self, name).setCurrentText(getattr(fresh, name).currentText())

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
        self.accept()
