"""Browse and edit the JaNets component database: the list of components and, for one
component, the pages the Juki Component Database editor has (component data, packaging
style, laser centering, pick and placement conditions, check).

Changes stay in the window until **Save to database**, which writes them all at once
(:func:`panelimport.io.compolib.save_changes`: a backup first, and only while no program
has the database open).  What can be changed, and why some settings are read-only, is
in :mod:`panelimport.model.library`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSettings, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QGuiApplication, QKeySequence
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
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTableView,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from panelimport.gui import theme
from panelimport.io.compodb import DatabaseError
from panelimport.io.compolib import BACKUP_DIR, lock_holders, read_library, save_changes
from panelimport.model.library import (
    ADDED,
    CHOICE,
    DELETED,
    DESCRIPTION,
    EDITED,
    FIELD,
    FLAG,
    NAME,
    NUMBER,
    TEXT,
    Changes,
    Component,
    ComponentLibrary,
    Field,
    nozzle_for,
)

#: The settings the nozzle is picked from (see :func:`nozzle_for`).
SIZE_KEYS = ("Compo.Width", "Compo.Length", "Compo.UsePackage", "Compo.PackageWidth", "Compo.PackageLength")

HINT_STYLE = "color: #8b949e;"
WARNING_STYLE = "color: #ffb000;"
SORT_ROLE = Qt.UserRole
STATE_COLOR = {EDITED: theme.EDITED, ADDED: theme.ADDED, DELETED: theme.REMOVED}

#: The list: column title → a setting, or what the Juki list combines from several.
COLUMNS: list[tuple[str, str]] = [
    ("Component name", NAME),
    ("Comment", DESCRIPTION),
    ("Component type", "Compo.PkgClassID"),
    ("Kind of shape", "Compo.Rx7ComponentType"),
    ("Packaging style", "Feeder.FdrTypeID"),
    ("Feeder type", "feeder"),
    ("Centering: 3010-20", "centering"),
    ("Layer", "Expansion.CompoLayer"),
    ("Tombstone detection", "Inspection.ChipStandCheck"),
    ("Width", "Compo.Width"),
    ("Length", "Compo.Length"),
    ("Height", "Compo.Height"),
    ("Package code", "Compo.PkgType"),
    ("Change", "state"),
]
#: Settings a combined column is made from (it is marked edited when one of them is).
COMBINED = {
    "feeder": ("Feeder.TapeTypeID", "Feeder.Pitch"),
    "centering": ("LaserGx10.Gx10LA", "LaserGx10.NozzleNo"),
}

#: The editor's left side, as in the Juki editor: group → settings.
PANEL: list[tuple[str, list[str]]] = [
    ("Component", ["Compo.PkgClassID", "Compo.Rx7ComponentType", "Feeder.FdrTypeID"]),
    ("Outer dimensions", ["Compo.Width", "Compo.Length", "Compo.Height"]),
    ("Package size", ["Compo.UsePackage", "Compo.PackageWidth", "Compo.PackageLength"]),
    ("Centering method", ["Compo.UseLaser", "Compo.UseVision", "Compo.GX4PriorityLV"]),
]
#: The editor's pages: page → groups → settings.
TABS: list[tuple[str, list[tuple[str, list[str]]]]] = [
    (
        "Packaging style",
        [
            ("Tape", ["Feeder.TapeTypeID", "Feeder.Pitch", "Feeder.TapeAngle", "Feeder.SpliceSensorUse"]),
            ("Stick", ["Feeder.StickTypeID", "Feeder.StickChangerType"]),
            ("Component reject to", ["Expansion.ScrapTypeGx6", "Expansion.ScrapType"]),
        ],
    ),
    (
        "Laser centering",
        [
            ("General settings", ["Laser.LaserHeight", "Laser.LaserAlgo", "Laser.GX4PreRotate"]),
            (
                "3010-20",
                [
                    "LaserGx10.Gx10LA", "LaserGx10.NozzleNo", "LaserGx10.PumpVacuum", "Laser.Gx10LaserHeightLnc60",
                    "LaserGx10.CompoShape",
                ],
            ),
            (
                "3010-20 speeds",
                [
                    "LaserGx10.SpdXY", "LaserGx10.SpdPickDownZ", "LaserGx10.SpdPickUpZ", "LaserGx10.SpdPlaceDownZ",
                    "LaserGx10.SpdPlaceUpZ", "LaserGx10.SpdPlaceDownZGx10V", "LaserGx10.SpdPlaceUpZGx10V",
                    "LaserGx10.SpdThetaInLA", "LaserGx10.SpdTheta",
                ],
            ),
        ],
    ),
    (
        "Pick conditions",
        [
            (
                "General settings",
                ["Expansion.Retry", "Expansion.PickPosAdjust", "Expansion.EtfPickPosAdjust", "Expansion.AutoTeach"],
            ),
            (
                "3010-20",
                [
                    "Expansion.FCTypePickGx10", "Expansion.OverPickGx10", "LaserGx10.PickZ2StepUse",
                    "LaserGx10.PickZ2StepDown", "LaserGx10.PickZ2StepUp",
                ],
            ),
            ("JM-10", ["Expansion.OverPickJM10"]),
        ],
    ),
    (
        "Placement conditions",
        [
            ("General settings", ["Expansion.Test", "Expansion.CompoCheck", "Expansion.CompoLayer"]),
            (
                "3010-20",
                [
                    "Expansion.FCTypePlaceGx10", "Expansion.OverPlaceGx10", "LaserGx10.PlaceZ2StepUse",
                    "LaserGx10.PlaceZ2StepDown", "LaserGx10.PlaceZ2StepUp",
                ],
            ),
        ],
    ),
    ("Check", [("Inspection", ["Inspection.ChipStandCheck"])]),
]  # fmt: skip


# ---------------------------------------------------------------------- the list
class LibraryModel(QAbstractTableModel):
    """The components as they are with the unsaved changes."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.library: ComponentLibrary | None = None
        self.rows: list[Component] = []

    def set_rows(self, library: ComponentLibrary | None, rows: list[Component]) -> None:
        self.beginResetModel()
        self.library, self.rows = library, rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section][0]
        return None

    def text(self, c: Component, key: str) -> str:
        if key == "state":
            return c.state
        if key == "feeder":
            return self.library.feeder_text(c.values)
        if key == "centering":
            return self.library.centering_text(c.values)
        return self.library.text(key, c.values)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or self.library is None:
            return None
        c, key = self.rows[index.row()], COLUMNS[index.column()][1]
        number = key in FIELD and FIELD[key].kind == NUMBER
        if role == Qt.DisplayRole:
            return self.text(c, key)
        if role == SORT_ROLE:
            return float(c.values.get(key) or 0) if number else self.text(c, key).upper()
        if role == Qt.TextAlignmentRole and number:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            changed = key in ("state", NAME) or key in c.changed or any(k in c.changed for k in COMBINED.get(key, ()))
            if c.state in (ADDED, DELETED) or (c.state == EDITED and changed):
                return STATE_COLOR[c.state]
        if role == Qt.FontRole and c.state == DELETED:
            font = QFont()
            font.setStrikeOut(True)
            return font
        if role == Qt.ToolTipRole and key in c.changed and c.state == EDITED and c.compo_id > 0:
            was = self.library.text(key, self.library.record(c.compo_id).values)
            return f"In the database: {was or '(empty)'}"
        return None


# ---------------------------------------------------------------------- one component
class ComponentEditor(QDialog):
    """The settings of one component.  :meth:`values` are the ones the user changed, as
    they are stored."""

    def __init__(
        self,
        library: ComponentLibrary,
        component: Component,
        name_taken: Callable[[str], bool] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.library, self.component = library, component
        self._name_taken = name_taken or (lambda name: False)
        self.widgets: dict[str, QWidget] = {}
        self._initial: dict[str, object] = {}
        self._built_for: dict[str, object] = {}  # choice → the value of the setting its options depend on
        self._size: dict[str, object] = {}  # the size the nozzle was last picked for
        self.setWindowTitle(f"Component {component.name}" + (" (new)" if component.state == ADDED else ""))

        head = QFormLayout()
        for key in (NAME, DESCRIPTION, "Compo.PkgType"):
            self._add_row(head, key)
        self.widgets[NAME].setMinimumWidth(320)

        side = QWidget()
        side.setMaximumWidth(400)
        left = QVBoxLayout(side)
        left.setContentsMargins(0, 0, 0, 0)
        for title, keys in PANEL:
            left.addWidget(self._group(title, keys))
        left.addStretch(1)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(False)
        for title, groups in TABS:
            page = QWidget()
            column = QVBoxLayout(page)
            for group_title, keys in groups:
                column.addWidget(self._group(group_title, keys))
            column.addStretch(1)
            self.tabs.addTab(page, title)
        body = QHBoxLayout()
        body.addWidget(side)
        body.addWidget(self.tabs, 1)

        hint = QLabel(
            "Lengths are in mm, angles in degrees. The options are the Juki Component Database's own, and the "
            "feed pitches are those of the tape width; “Code n” is a value JaNets has no name for. Greyed settings "
            "are read-only here: change them in the Juki Component Database."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(HINT_STYLE)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(head)
        layout.addLayout(body, 1)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self.resize(1180, 760)
        self._size = self._now_size()
        self._refresh()

    # ------------------------------------------------------------------ building
    def _group(self, title: str, keys: list[str]) -> QGroupBox:
        box = QGroupBox(title)
        form = QFormLayout(box)
        for key in keys:
            self._add_row(form, key)
        return box

    def _add_row(self, form: QFormLayout, key: str) -> None:
        f = FIELD[key]
        widget = self._make(f, self.component.values.get(key))
        tips = [f.note] if f.note else []
        if key not in self.library.fields:
            tips.append("This database does not have this setting")
        elif f.read_only:
            tips.append("Read-only here")
        widget.setToolTip(". ".join(tips))
        self.widgets[key] = widget
        self._initial[key] = self.shown(key)
        form.addRow(f.label, widget)

    def _make(self, f: Field, raw) -> QWidget:
        if f.kind == TEXT:
            w = QLineEdit(f.shown(raw))
            if f.max_length:
                w.setMaxLength(f.max_length)
        elif f.kind == NUMBER:
            w = QDoubleSpinBox()
            w.setDecimals(f.decimals)
            value = f.shown(raw)
            w.setRange(min(f.lo, value), max(f.hi, value))  # never show another value than the stored one
            w.setSingleStep(10.0 ** -min(f.decimals, 2))
            w.setAccelerated(True)
            if f.unit:
                w.setSuffix(f" {f.unit}")
            w.setValue(value)
            w.valueChanged.connect(self._refresh)
        elif f.kind == FLAG:
            w = QCheckBox()
            w.setChecked(bool(raw))
            w.toggled.connect(self._refresh)
        else:
            w = QComboBox()
            self._fill(w, f, raw, self.component.values)
            if f.per:
                self._built_for[f.key] = self.component.values.get(f.per)
            w.currentIndexChanged.connect(self._refresh)
        return w

    def _fill(self, w: QComboBox, f: Field, raw, values) -> None:
        """The options of ``f`` for a component with ``values``, ``raw`` selected (a
        stored value that is not an option is kept as the last one)."""
        options = self.library.options(f, values)
        if raw is None:
            options = [(None, ""), *options]
        elif raw not in {code for code, _label in options}:
            options = [*options, (raw, self.library.label(f, raw, values))]
        w.blockSignals(True)
        w.clear()
        for code, label in options:
            w.addItem(label, code)
        w.setCurrentIndex(0 if raw is None else w.findData(raw))
        w.blockSignals(False)

    def _now(self, key: str):
        """A setting as it is now: as shown, or as stored when the dialog does not show it."""
        return self.shown(key) if key in self.widgets else self.component.values.get(key)

    def _refresh(self, *_args) -> None:
        """Rebuild the options that depend on a changed setting (a pitch that is not one
        of the new tape width's becomes its first, as in JaNets), and enable what can be
        changed: not the read-only settings, nor those that only apply to another
        packaging or while their switch is off."""
        size = self._now_size()
        if size != self._size:  # a new size picks the nozzle, as in the Juki editor
            self._size = size
            self._pick_nozzle(size)
        for key, built_for in list(self._built_for.items()):
            f, now = FIELD[key], self._now(FIELD[key].per)
            if now != built_for:
                values = {**self.component.values, f.per: now}
                codes = [code for code, _label in self.library.options(f, values)]
                current = self.shown(key)
                self._fill(self.widgets[key], f, current if current in codes else next(iter(codes), None), values)
                self._built_for[key] = now
        for key, widget in self.widgets.items():
            f = FIELD[key]
            enabled = key in self.library.fields and not f.read_only
            if enabled and f.when is not None:
                switch, value = f.when
                enabled = int(self._now(switch) or 0) == value
            if isinstance(widget, QLineEdit):
                widget.setReadOnly(not enabled)
                widget.setStyleSheet("" if enabled else HINT_STYLE)
            else:
                widget.setEnabled(enabled)

    def _now_size(self) -> dict[str, object]:
        """The size as it is now, as stored."""
        return {
            key: FIELD[key].stored(self.shown(key), self.component.values.get(key)) if key in self.widgets
            else self.component.values.get(key)
            for key in SIZE_KEYS
        }  # fmt: skip

    def _pick_nozzle(self, size: dict[str, object]) -> None:
        picked = nozzle_for({**self.component.values, **size})
        if picked is None:
            return
        for key, value in zip(("LaserGx10.NozzleNo", "LaserGx10.PumpVacuum"), picked):
            f = FIELD[key]
            if key in self.widgets and key in self.library.fields and not f.read_only:
                widget = self.widgets[key]
                if isinstance(widget, QComboBox) and widget.findData(value) < 0:
                    continue  # a nozzle this database cannot be set to
                self.set_shown(key, f.shown(value))

    # ------------------------------------------------------------------ values
    def shown(self, key: str):
        """The setting as the dialog shows it now: text, number, True/False or an
        option's code."""
        widget = self.widgets[key]
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return widget.currentData()

    def set_shown(self, key: str, value) -> None:
        widget = self.widgets[key]
        if isinstance(widget, QLineEdit):
            widget.setText(str(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        else:
            index = widget.findData(value)
            if index < 0:
                raise ValueError(f"{FIELD[key].label} has no option {value}")
            widget.setCurrentIndex(index)

    def values(self) -> dict[str, object]:
        """The settings the user changed in this dialog, as they are stored."""
        changed: dict[str, object] = {}
        for key in self.widgets:
            f = FIELD[key]
            if f.read_only or key not in self.library.fields:
                continue
            now = self.shown(key)
            if now == self._initial[key] or (f.kind == CHOICE and now is None):
                continue  # untouched settings keep exactly what is stored
            changed[key] = f.stored(now, self.component.values.get(key))
        return changed

    def problem(self) -> str:
        name = self.shown(NAME).strip()
        if not name:
            return "The component needs a name."
        if self._name_taken(name):
            return f"There already is a component named {name}."
        return ""

    def accept(self) -> None:
        problem = self.problem()
        if problem:
            QMessageBox.warning(self, "Component", problem)
            return
        super().accept()


# ---------------------------------------------------------------------- the window
class ComponentDatabaseWindow(QMainWindow):
    saved = Signal(str)  # the database's path, after changes were written to it

    def __init__(self, path: str = "", qsettings: QSettings | None = None, parent=None) -> None:
        super().__init__(parent)
        self.qsettings = qsettings or QSettings()
        self.path = ""
        self.library: ComponentLibrary | None = None
        self.changes = Changes()
        self.resize(1300, 760)

        self.model = LibraryModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SORT_ROLE)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(22)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(lambda pos: self.menu().exec(self.view.viewport().mapToGlobal(pos)))
        self.view.doubleClicked.connect(lambda _index: self.edit_selected())
        self.view.selectionModel().selectionChanged.connect(lambda *_a: self._update_actions())
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter: any text of the row, e.g. a part number or “SOP”")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._filter_changed)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 0)
        layout.addWidget(self.filter)
        layout.addWidget(self.view, 1)
        self.setCentralWidget(central)

        self.count_label = QLabel("")
        self.lock_label = QLabel("")
        self.lock_label.setStyleSheet(WARNING_STYLE)
        self.statusBar().addPermanentWidget(self.lock_label)
        self.statusBar().addPermanentWidget(self.count_label)
        self._create_actions()
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(3000)
        self._lock_timer.timeout.connect(self._update_lock)
        geometry = self.qsettings.value("database_window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._refresh()
        if path:
            self.open(path)

    def _action(self, text: str, slot, shortcut=None, tip: str = "") -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        if tip:
            act.setStatusTip(tip)
            act.setToolTip(tip)
        act.triggered.connect(lambda _checked=False: slot())
        return act

    def _create_actions(self) -> None:
        self.act_open = self._action("&Open database…", self.open_file, QKeySequence.Open)
        self.act_reload = self._action("&Reload", self.reload, "F5", "Read the database again")
        self.act_save = self._action(
            "&Save to database", self.save, QKeySequence.Save,
            "Write the changes: a backup first, and only while no program has the database open",
        )  # fmt: skip
        self.act_close = self._action("&Close", self.close, QKeySequence.Close)
        self.act_edit = self._action("&Edit…", self.edit_selected, "Return", "Change the selected component")
        self.act_copy = self._action(
            "&New from copy…", self.new_copy, QKeySequence.New, "A new component with the selected one's settings"
        )
        self.act_new_defaults = self._action(
            "New with de&faults…", lambda: self.new_copy(defaults=True), "Ctrl+Shift+N",
            "A new component with the selected one's packaging and size and the default settings "
            "(trash box, laser centering, Algorithm 1, fastest speeds, …), its nozzle picked from the size",
        )  # fmt: skip
        self.act_delete = self._action("&Delete", self.delete_selected, QKeySequence.Delete)
        self.act_revert = self._action(
            "Re&vert changes", self.revert_selected, tip="Drop the unsaved changes to the selected components"
        )
        # Return and Delete act on the list only, not while typing in the filter.
        for a in (self.act_edit, self.act_delete):
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.view.addAction(a)
        m = self.menuBar().addMenu("&File")
        for a in (self.act_open, self.act_reload, None, self.act_save, None, self.act_close):
            m.addSeparator() if a is None else m.addAction(a)
        m = self.menuBar().addMenu("&Component")
        for a in (self.act_edit, self.act_copy, self.act_new_defaults, None, self.act_delete, self.act_revert):
            m.addSeparator() if a is None else m.addAction(a)
        tb = QToolBar("Database")
        tb.setObjectName("databaseToolbar")
        for a in (self.act_open, self.act_reload, self.act_save, None, self.act_edit, self.act_copy, self.act_new_defaults,
                  self.act_delete,
                  self.act_revert):  # fmt: skip
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(tb)

    def menu(self) -> QMenu:
        menu = QMenu(self)
        for a in (self.act_edit, self.act_copy, self.act_new_defaults, None, self.act_delete, self.act_revert):
            menu.addSeparator() if a is None else menu.addAction(a)
        return menu

    # ------------------------------------------------------------------ state
    def _refresh(self) -> None:
        keep = [c.compo_id for c in self.selected()]
        rows = self.library.components(self.changes) if self.library is not None else []
        fit = self.library is not None and not self.model.rows  # a database was just opened
        self.model.set_rows(self.library, rows)
        if fit:
            self.view.resizeColumnsToContents()
            self.view.setColumnWidth(1, min(self.view.columnWidth(1), 340))
        self.select(keep)
        name = Path(self.path).name if self.path else ""
        star = " *" if self.changes else ""
        self.setWindowTitle(f"Component database — {self.path}{star}" if name else "Component database")
        if self.library is None:
            self.count_label.setText("No database open")
        else:
            shown = self.proxy.rowCount()
            total = sum(1 for c in rows if c.state != DELETED)
            text = f"{total} components" + (f", {shown} shown" if shown != len(rows) else "")
            if self.changes:
                text += f" · unsaved: {self.changes.summary()}"
            self.count_label.setText(text)
        self._update_lock()
        self._update_actions()

    def _filter_changed(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())
        self._refresh()

    def _update_actions(self) -> None:
        chosen = self.selected()
        self.act_reload.setEnabled(self.library is not None)
        self.act_save.setEnabled(bool(self.changes))
        self.act_edit.setEnabled(len(chosen) == 1 and chosen[0].state != DELETED)
        self.act_copy.setEnabled(len(chosen) == 1 and chosen[0].state != DELETED)
        self.act_new_defaults.setEnabled(self.act_copy.isEnabled())
        self.act_delete.setEnabled(any(c.state != DELETED for c in chosen))
        self.act_revert.setEnabled(any(c.state for c in chosen))

    def _update_lock(self) -> None:
        holders = lock_holders(self.path) if self.path else []
        self.lock_label.setText(
            f"Open in {', '.join(holders)}: changes can be saved once it is closed there" if holders else ""
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._lock_timer.start()
        self._update_lock()

    def hideEvent(self, event) -> None:
        self._lock_timer.stop()
        super().hideEvent(event)

    def selected(self) -> list[Component]:
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.view.selectionModel().selectedRows()})
        return [self.model.rows[r] for r in rows if r < len(self.model.rows)]

    def select(self, compo_ids) -> None:
        """Select the components with these ids (those the filter shows)."""
        wanted = set(compo_ids)
        selection = self.view.selectionModel()
        selection.clearSelection()
        first = None
        for row, c in enumerate(self.model.rows):
            if c.compo_id in wanted:
                index = self.proxy.mapFromSource(self.model.index(row, 0))
                if index.isValid():
                    selection.select(index, selection.SelectionFlag.Select | selection.SelectionFlag.Rows)
                    first = first or index
        if first is not None:
            selection.setCurrentIndex(first, selection.SelectionFlag.NoUpdate)  # keep the others selected
            self.view.scrollTo(first)

    def find(self, name: str) -> Component | None:
        return next((c for c in self.model.rows if c.name.upper() == name.strip().upper()), None)

    # ------------------------------------------------------------------ files
    def _busy(self) -> None:
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)

    def _idle(self) -> None:
        QGuiApplication.restoreOverrideCursor()

    def _read(self, path: str) -> ComponentLibrary | None:
        self._busy()
        try:
            return read_library(path)
        except DatabaseError as exc:
            problem = str(exc)
        finally:
            self._idle()
        QMessageBox.warning(self, "Component database", problem)
        return None

    def _discard_ok(self) -> bool:
        if not self.changes:
            return True
        r = QMessageBox.question(
            self, "Component database", f"Discard the unsaved changes ({self.changes.summary()})?"
        )
        return r == QMessageBox.Yes

    def open(self, path: str) -> bool:
        """Show the database at ``path`` (dropping unsaved changes, after asking)."""
        if not self._discard_ok():
            return False
        library = self._read(path)
        if library is None:
            return False
        self.path, self.library = str(path), library
        self.changes.clear()
        self.qsettings.setValue("database_window/last_dir", str(Path(path).parent))
        self._refresh()
        self.statusBar().showMessage(f"Read {len(library.records)} components from a copy of {path}", 8000)
        return True

    def open_file(self) -> None:
        start = str(Path(self.path).parent) if self.path else str(self.qsettings.value("database_window/last_dir", ""))
        path, _ = QFileDialog.getOpenFileName(
            self, "Component database", start, "Access databases (*.mdb *.accdb);;All files (*)"
        )
        if path:
            self.open(str(Path(path)))

    def reload(self) -> None:
        if self.path:
            self.open(self.path)

    # ------------------------------------------------------------------ edits
    def edit_selected(self) -> None:
        chosen = self.selected()
        if len(chosen) != 1 or chosen[0].state == DELETED:
            return
        self.edit(chosen[0].compo_id)

    def editor(self, compo_id: int) -> ComponentEditor:
        component = self.library.component(self.changes, compo_id)
        return ComponentEditor(
            self.library, component, lambda name: self.library.name_taken(self.changes, name, but=compo_id), self
        )

    def edit(self, compo_id: int) -> None:
        dlg = self.editor(compo_id)
        if dlg.exec():
            self.apply(compo_id, dlg.values())

    def apply(self, compo_id: int, values: dict[str, object]) -> None:
        """Take the settings changed in the editor as unsaved changes."""
        self.library.edit(self.changes, compo_id, values)
        self._refresh()
        self.select([compo_id])

    def new_copy(self, name: str | None = None, defaults: bool = False) -> int | None:
        """A new component that is a copy of the selected one, with the default settings
        when ``defaults``; asks for its name and then shows it in the editor.  Returns its
        (negative) id."""
        chosen = self.selected()
        if len(chosen) != 1 or chosen[0].state == DELETED:
            return None
        source = chosen[0]
        if source.compo_id in self.library.nested or self.changes.added.get(source.compo_id) in self.library.nested:
            QMessageBox.information(
                self,
                "New component",
                f"{source.name} has data this program cannot copy (vision elements or light patterns). "
                "Copy it in the Juki Component Database.",
            )
            return None
        ask = name is None
        if ask:
            name, ok = QInputDialog.getText(
                self, "New component",
                f"Name of the new component (a copy of {source.name}{' with the default settings' if defaults else ''}):",
                text=source.name,
            )
            if not ok:
                return None
        name = name.strip()
        if not name or self.library.name_taken(self.changes, name):
            QMessageBox.warning(
                self, "New component", f"There already is a component named {name}." if name else "The component needs a name."
            )
            return None
        new_id = self.library.add_copy(self.changes, source.compo_id, name)
        if defaults:
            self.library.apply_defaults(self.changes, new_id)
        self.filter.clear()
        self._refresh()
        self.select([new_id])
        if ask:
            self.edit(new_id)
        return new_id

    def delete_selected(self) -> None:
        chosen = [c for c in self.selected() if c.state != DELETED]
        blocked = [c.name for c in chosen if c.compo_id in self.library.nested]
        if blocked:
            QMessageBox.information(
                self,
                "Delete",
                f"{', '.join(blocked)}: has data this program cannot delete (vision elements or light patterns). "
                "Delete it in the Juki Component Database.",
            )
        for c in chosen:
            if c.name not in blocked:
                self.library.delete(self.changes, c.compo_id)
        self._refresh()

    def revert_selected(self) -> None:
        for c in self.selected():
            self.library.revert(self.changes, c.compo_id)
        self._refresh()

    # ------------------------------------------------------------------ saving
    def save(self) -> bool:
        if self.library is None or not self.changes:
            return False
        problems = self.library.problems(self.changes)
        if problems:
            QMessageBox.warning(self, "Save to database", "\n".join(problems))
            return False
        r = QMessageBox.question(
            self,
            "Save to database",
            f"Write the changes ({self.changes.summary()}) to {self.path}?\n\n"
            f"The database is copied to “{BACKUP_DIR}” next to it first. It is only written while no program "
            "has it open.",
        )
        if r != QMessageBox.Yes:
            return False
        keep = [c.name for c in self.selected()]
        self._busy()
        try:
            result, problem = save_changes(self.path, self.library, self.changes), ""
        except DatabaseError as exc:
            result, problem = None, str(exc)
        finally:
            self._idle()
        if result is None:
            QMessageBox.warning(self, "Save to database", problem)
            return False
        self.changes.clear()
        library = self._read(self.path)
        if library is not None:
            self.library = library
        self._refresh()
        self.select([c.compo_id for c in self.model.rows if c.name in keep])
        self.statusBar().showMessage(f"Saved ({result.summary}); the database as it was is in {result.backup}", 15000)
        self.saved.emit(self.path)
        return True

    def closeEvent(self, event) -> None:
        if not self._discard_ok():
            event.ignore()
            return
        self.changes.clear()
        self._refresh()
        self.qsettings.setValue("database_window/geometry", self.saveGeometry())
        super().closeEvent(event)
