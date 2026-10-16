"""Dialogs for component edits: add or edit a component, and review a removal.

Coordinates are the ones the components table shows: circuit-relative for board-level
components (placed in every circuit), panel coordinates for panel-level components.
Sizes are in the part's own frame (rotation 0); 0 is unknown.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from panelimport.analysis.edits import EPS, REASON_LABELS, TEXT_FIELDS, all_parts, find_part, natural_key, shown_values
from panelimport.analysis.result import PanelAnalysis
from panelimport.analysis.transforms import angle_diff
from panelimport.model.panel import SIZE_FIELDS

Key = tuple[str, str]
LEVEL_LABELS = {"board": "Board — placed in every circuit", "panel": "Panel — placed once"}
HINT_STYLE = "color: #8b949e;"
UNKNOWN = "unknown"  # a size of 0
KEEP = "(keep each one's)"
SIZE_TIPS = {
    "width": "Body size along the part's X axis at rotation 0 (ISS componentSize witdh)",
    "length": "Body size along the part's Y axis at rotation 0 (ISS componentSize length)",
    "height": "Body height (ISS componentSize height)",
}
NUMBER_FIELDS = ("x", "y", "rotation") + SIZE_FIELDS


def _spin(lo: float, hi: float, decimals: int, suffix: str) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setSuffix(suffix)
    box.setSingleStep(0.1)
    box.setAccelerated(True)
    return box


class ComponentDialog(QDialog):
    """Add a component (``keys`` empty), edit one, or edit the text fields of several."""

    def __init__(
        self,
        parent: QWidget | None,
        analysis: PanelAnalysis,
        keys: list[Key] | None = None,
        *,
        level: str = "board",
        position: dict[str, tuple[float, float] | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.a = analysis
        self.keys = list(keys or [])
        self.mode = "add" if not self.keys else ("one" if len(self.keys) == 1 else "many")
        self.part = find_part(analysis, *self.keys[0]) if self.mode == "one" else None
        self.is_added = self.mode == "add" or (self.part is not None and self.part.state == "added")
        self.position = position or {}

        self.level = QComboBox()
        for key, label in LEVEL_LABELS.items():
            self.level.addItem(label, key)
        self.level.setCurrentIndex(max(self.level.findData(self.keys[0][0] if self.keys else level), 0))
        self.level.setEnabled(self.mode == "add")
        self.designator = QLineEdit()
        self.part_name = QLineEdit()
        self.part_number = QLineEdit()
        self.package = QComboBox()
        self.package.setEditable(True)
        self.package.addItems(sorted({p.package for _lv, p in all_parts(analysis) if p.package}, key=natural_key))
        self.side = QComboBox()
        self.side.addItems(["top", "bottom"])
        self.x = _spin(-100000, 100000, 4, " mm")
        self.y = _spin(-100000, 100000, 4, " mm")
        self.rotation = _spin(0, 360, 3, "°")
        self.rotation.setWrapping(True)
        self.rotation.setSingleStep(90)
        self.sizes = {f: _spin(0, 1000, 4, " mm") for f in SIZE_FIELDS}
        for field, box in self.sizes.items():
            box.setSpecialValueText(KEEP if self.mode == "many" else UNKNOWN)
            box.setToolTip(SIZE_TIPS[field] + ("" if self.mode == "many" else "; 0 = unknown"))
        self.size_note = QLabel(
            "Body size in the part's own frame, from the ODB++ package outline and .comp_height. The ISS "
            "program has one size per part number: an edited size is used for all its placements."
        )
        self.size_note.setWordWrap(True)
        self.size_note.setStyleSheet(HINT_STYLE)
        self.note = QLineEdit()
        self.note.setPlaceholderText("optional: why, for the record")
        self.frame = QLabel("")
        self.frame.setWordWrap(True)
        self.frame.setStyleSheet(HINT_STYLE)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #ff7b72;")
        self.error.setWordWrap(True)
        self.error.hide()

        self.editors = {
            "part_name": self.part_name,
            "part_number": self.part_number,
            "package": self.package,
            "layer": self.side,
            "x": self.x,
            "y": self.y,
            "rotation": self.rotation,
            **self.sizes,
        }
        self.hints: dict[str, QLabel] = {}
        self.resets: dict[str, QToolButton] = {}
        self.export = (
            shown_values(analysis, self.part, export=True) if self.part is not None and not self.is_added else None
        )
        self.initial = shown_values(analysis, self.part) if self.part is not None else None

        form = QFormLayout()
        form.addRow("Level", self.level)
        form.addRow("Designator", self.designator)
        for label, field in (
            ("Part name", "part_name"),
            ("Part number", "part_number"),
            ("Package", "package"),
            ("Side", "layer"),
            ("X", "x"),
            ("Y", "y"),
            ("Rotation (CCW)", "rotation"),
        ):
            form.addRow(label, self._with_hint(field))
        form.addRow("", self.frame)
        for label, field in (("Width (X)", "width"), ("Length (Y)", "length"), ("Height", "height")):
            form.addRow(label, self._with_hint(field))
        form.addRow("", self.size_note)
        form.addRow("Note", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.revert_btn = None
        if self.export is not None:
            self.revert_btn = buttons.addButton("Export values", QDialogButtonBox.ResetRole)
            self.revert_btn.setToolTip("Put back every value the export has")
            self.revert_btn.clicked.connect(self._revert_all)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

        self._fill()
        for field, editor in self.editors.items():
            signal = editor.valueChanged if isinstance(editor, QDoubleSpinBox) else (
                editor.currentTextChanged if isinstance(editor, QComboBox) else editor.textChanged
            )
            signal.connect(lambda *_a: self._refresh_hints())
        self.level.currentIndexChanged.connect(self._level_changed)
        self._refresh_hints()
        self._show_frame()
        self.setMinimumWidth(460)
        # Focus where typing usually starts (taken when the dialog is shown).
        (self.designator if self.mode == "add" else self.part_number).setFocus()

    # ------------------------------------------------------------------ building
    def _with_hint(self, field: str) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.editors[field], 1)
        hint = QLabel("")
        hint.setStyleSheet(HINT_STYLE)
        reset = QToolButton()
        reset.setText("↺")
        reset.setToolTip("Back to the export's value")
        reset.clicked.connect(lambda _c=False, f=field: self._set(f, self.export[f]))
        row.addWidget(hint)
        row.addWidget(reset)
        self.hints[field] = hint
        self.resets[field] = reset
        hint.hide()
        reset.hide()
        return box

    def _fill(self) -> None:
        if self.mode == "many":
            self.setWindowTitle(f"Edit {len(self.keys)} components")
            self.designator.setText(", ".join(k[1] for k in self.keys[:6]) + (" …" if len(self.keys) > 6 else ""))
            self.designator.setEnabled(False)
            for field in TEXT_FIELDS:
                self._set(field, "")
            for line in (self.part_name, self.part_number):
                line.setPlaceholderText("(keep each one's)")
            self.package.lineEdit().setPlaceholderText("(keep each one's)")
            for field in ("layer", "x", "y", "rotation"):
                self.editors[field].setEnabled(False)
            self.frame.setText(f"Fields left empty or at {KEEP} keep each component's value.")
            return
        if self.mode == "add":
            self.setWindowTitle("Add component")
            for field in TEXT_FIELDS:
                self._set(field, "")
            xy = self.position.get(self.level.currentData())
            if xy is not None:
                self.x.setValue(xy[0])
                self.y.setValue(xy[1])
            return
        self.setWindowTitle(f"Edit {self.part.designator}")
        self.designator.setText(self.part.designator)
        self.designator.setEnabled(self.is_added)
        for field, value in shown_values(self.a, self.part).items():
            self._set(field, value)
        if self.part.edit is not None:
            self.note.setText(self.part.edit.note)

    def _set(self, field: str, value) -> None:
        editor = self.editors[field]
        if isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value) % 360.0 if field == "rotation" else float(value))
        elif isinstance(editor, QComboBox):
            editor.setCurrentText(str(value))
        else:
            editor.setText(str(value))

    def _get(self, field: str):
        editor = self.editors[field]
        if isinstance(editor, QDoubleSpinBox):
            return editor.value()
        if isinstance(editor, QComboBox):
            return editor.currentText().strip()
        return editor.text().strip()

    def _differs(self, field: str) -> bool:
        value, export = self._get(field), self.export[field]
        if field == "rotation":
            return angle_diff(value, export) > 10 ** -self.rotation.decimals() / 2 + EPS
        if field in NUMBER_FIELDS:
            return abs(value - export) > 10 ** -self.editors[field].decimals() / 2 + EPS
        return value != export

    def _refresh_hints(self) -> None:
        if self.export is None:
            return
        for field in self.editors:
            differs = self._differs(field)
            value = self.export[field]
            if field in SIZE_FIELDS:
                text = f"{value:.4f}" if value else UNKNOWN
            elif field in ("x", "y"):
                text = f"{value:.4f}"
            else:
                text = f"{value:.3f}°" if field == "rotation" else (value or "(empty)")
            self.hints[field].setText(f"export: {text}")
            self.hints[field].setVisible(differs)
            self.resets[field].setVisible(differs)

    def _revert_all(self) -> None:
        for field in self.editors:
            self._set(field, self.export[field])

    def _level_changed(self) -> None:
        # Coordinates prefilled from a canvas click follow the level, unless typed over.
        level, other = self.level.currentData(), "panel" if self.level.currentData() == "board" else "board"
        before = self.position.get(other)
        now = self.position.get(level)
        untouched = before is None or (abs(self.x.value() - before[0]) < 1e-9 and abs(self.y.value() - before[1]) < 1e-9)
        if now is not None and untouched:
            self.x.setValue(now[0])
            self.y.setValue(now[1])
        self._show_frame()

    def _show_frame(self) -> None:
        if self.mode == "many":
            return
        level = self.level.currentData()
        if level == "board":
            self.frame.setText(
                f"X/Y are circuit-relative, from each circuit's reference point ({self.a.reference_kind}), "
                "as in the components table. The component is placed in every circuit."
            )
        else:
            self.frame.setText("X/Y are panel coordinates, from the panel origin. The component is placed once.")

    # ------------------------------------------------------------------ results
    def chosen_level(self) -> str:
        return self.level.currentData()

    def chosen_designator(self) -> str:
        return self.designator.text().strip()

    def values(self) -> dict[str, object]:
        """The values entered; for several components only the text fields filled in and
        the sizes set.

        A number the spin box shows rounded but nobody changed comes back exact (the
        current or the export value), so that OK alone never creates an edit."""
        if self.mode == "many":
            return {f: self._get(f) for f in TEXT_FIELDS + SIZE_FIELDS if self._get(f)}
        out = {f: self._get(f) for f in self.editors}
        for field in NUMBER_FIELDS:
            half = 10 ** -self.editors[field].decimals() / 2 + EPS
            for known in (self.initial, self.export):
                if known is None:
                    continue
                exact = known[field]
                near = angle_diff(out[field], exact) if field == "rotation" else abs(out[field] - exact)
                if near <= half:
                    out[field] = exact
                    break
        return out

    def note_text(self) -> str:
        return self.note.text().strip()

    def validate(self) -> str:
        """An error message, or "" when the entries can be applied."""
        if not self.is_added or self.mode == "many":
            return ""
        name = self.chosen_designator()
        if not name:
            return "Enter a designator."
        if any(c.isspace() for c in name):
            return "A designator cannot contain spaces."
        level = self.chosen_level()
        own = self.keys[0] if self.keys else None
        for lv, part in all_parts(self.a):
            if lv == level and part.designator.lower() == name.lower() and (lv, part.designator) != own:
                return f"There already is a {level}-level {part.designator}."
        return ""

    def accept(self) -> None:
        problem = self.validate()
        if problem:
            self.error.setText(problem)
            self.error.show()
            return
        super().accept()


class RemoveDialog(QDialog):
    """Review components before they are removed (not placed), with a reason."""

    def __init__(
        self,
        parent: QWidget | None,
        rows: list[tuple[Key, str, str]],
        reason: str = "through-hole",
        title: str = "Remove components",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.rows = rows
        intro = QLabel(
            "These components will not be placed. They stay in the export, are shown greyed out and "
            "can be restored at any time (or undone)."
        )
        intro.setWordWrap(True)
        self.table = QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(["Designator", "Level", "Part", "Why"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, ((level, designator), part, why) in enumerate(rows):
            item = QTableWidgetItem(designator)
            item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, item)
            for c, text in enumerate((level, part, why), start=1):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        all_btn = QPushButton("Check all")
        none_btn = QPushButton("Check none")
        all_btn.clicked.connect(lambda: self._check_all(True))
        none_btn.clicked.connect(lambda: self._check_all(False))
        checks = QHBoxLayout()
        checks.addWidget(all_btn)
        checks.addWidget(none_btn)
        checks.addStretch(1)
        self.reason = QComboBox()
        for key, label in REASON_LABELS.items():
            self.reason.addItem(label, key)
        self.reason.setCurrentIndex(max(self.reason.findData(reason), 0))
        self.note = QLineEdit()
        self.note.setPlaceholderText("optional, e.g. hand-soldered after reflow")
        form = QFormLayout()
        form.addRow("Reason", self.reason)
        form.addRow("Note", self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.table.itemChanged.connect(lambda _i: self._update_ok())
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table)
        layout.addLayout(checks)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self._update_ok()
        self.resize(560, min(560, 220 + 26 * len(rows)))

    def _check_all(self, on: bool) -> None:
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _update_ok(self) -> None:
        n = len(self.chosen())
        ok = self.buttons.button(QDialogButtonBox.Ok)
        ok.setText(f"Remove {n}")
        ok.setEnabled(n > 0)

    def chosen(self) -> list[Key]:
        return [
            self.rows[r][0] for r in range(self.table.rowCount()) if self.table.item(r, 0).checkState() == Qt.Checked
        ]

    def chosen_reason(self) -> str:
        return self.reason.currentData()

    def note_text(self) -> str:
        return self.note.text().strip()
