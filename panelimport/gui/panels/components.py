"""Every component: circuit 1's placements and the panel-level parts.

Sortable, filterable and searchable; pick the attribute that holds the part number.
Components can be added, edited, removed (not placed) and restored; edited values are
coloured, with the export's value in the tooltip, and removed ones are greyed.
"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from panelimport.analysis.edits import SUGGESTIONS, all_parts, shown_values, status_text, suggest_removals
from panelimport.analysis.result import PanelAnalysis
from panelimport.gui import theme

COLUMNS = [
    "Designator",
    "Level",
    "Part name",
    "Part number",
    "Package",
    "Side",
    "X (mm)",
    "Y (mm)",
    "Rotation (°)",
    "Paste check",
    "Status",
]
COL_DESIGNATOR, COL_LEVEL, COL_SIDE, COL_X, COL_STATUS = 0, 1, 5, 6, 10
FIELD_COLUMNS = {"part_name": 2, "part_number": 3, "package": 4, "layer": 5, "x": 6, "y": 7, "rotation": 8}
NUMERIC = {6, 7, 8}
SORT_ROLE = Qt.UserRole + 1
KEY_ROLE = Qt.UserRole + 2  # (level, designator) on the designator cell
STATE_ROLE = Qt.UserRole + 3

SHOW = {
    "all": "All components",
    "placed": "Placed",
    "board": "Board level (every circuit)",
    "panel": "Panel level (once)",
    "changed": "Edited or added",
    "removed": "Removed",
}


class ComponentFilter(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.side = "all"
        self.show = "all"
        self.text = ""
        self.setSortRole(SORT_ROLE)

    def _refilter(self, apply) -> None:
        # Qt 6.10 replaced invalidateFilter() with begin/endFilterChange().
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            apply()
            self.endFilterChange()
        else:
            apply()
            self.invalidateFilter()

    def set_side(self, side: str) -> None:
        self._refilter(lambda: setattr(self, "side", side))

    def set_show(self, show: str) -> None:
        self._refilter(lambda: setattr(self, "show", show))

    def set_text(self, text: str) -> None:
        self._refilter(lambda: setattr(self, "text", text.strip().lower()))

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if self.side != "all" and model.index(row, COL_SIDE, parent).data() != self.side:
            return False
        if self.show != "all":
            first = model.index(row, COL_DESIGNATOR, parent)
            level, state = first.data(KEY_ROLE)[0], first.data(STATE_ROLE)
            wanted = {
                "placed": state != "removed",
                "board": level == "board",
                "panel": level == "panel",
                "changed": state in ("edited", "added"),
                "removed": state == "removed",
            }
            if not wanted.get(self.show, True):
                return False
        if not self.text:
            return True
        return any(self.text in str(model.index(row, c, parent).data() or "").lower() for c in range(model.columnCount()))


class ComponentsPanel(QWidget):
    componentSelected = Signal(str, str)  # level, designator
    partNumberAttributeChanged = Signal(str)
    addRequested = Signal()
    editRequested = Signal(list)  # [(level, designator)]
    removeRequested = Signal(list)
    restoreRequested = Signal(list)
    revertRequested = Signal(list)
    suggestRequested = Signal(str)  # a key of analysis.edits.SUGGESTIONS

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search designator, part, package…")
        self.search.setClearButtonEnabled(True)
        self.side = QComboBox()
        self.side.addItems(["all", "top", "bottom"])
        self.show_filter = QComboBox()
        for key, label in SHOW.items():
            self.show_filter.addItem(label, key)
        self.mapping = QComboBox()
        self.mapping.setToolTip("Attribute or PRP property that holds the Detex part number")
        self.model = QStandardItemModel(0, len(COLUMNS))
        self.model.setHorizontalHeaderLabels(COLUMNS)
        self.proxy = ComponentFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.selectionModel().selectionChanged.connect(self._selected)
        self.table.doubleClicked.connect(lambda _i: self._emit(self.editRequested))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.count = QLabel("")
        self.count.setWordWrap(True)

        # Edit actions: buttons, the table's context menu and keys while the table has focus.
        self.act_add = self._action(
            "Add…", "Add a component the export does not have", QKeySequence(Qt.Key_Insert), self.addRequested.emit
        )
        self.act_edit = self._action(
            "Edit…",
            "Change part name, part number, package, side, position or rotation",
            QKeySequence(Qt.Key_F2),
            lambda: self._emit(self.editRequested),
        )
        self.act_remove = self._action(
            "Remove…",
            "Do not place the selected components (through-hole, not populated, …)",
            QKeySequence.Delete,
            lambda: self._emit(self.removeRequested),
        )
        self.act_restore = self._action(
            "Restore", "Place the selected removed components again", None, lambda: self._emit(self.restoreRequested)
        )
        self.act_revert = self._action(
            "Revert", "Back to the export's values for the selected components", None, lambda: self._emit(self.revertRequested)
        )
        self.suggest_menu = QMenu("Find", self)
        self.suggest_actions: dict[str, QAction] = {}
        for kind, label in SUGGESTIONS.items():
            act = self.suggest_menu.addAction(label + "…")
            act.triggered.connect(lambda _c=False, k=kind: self.suggestRequested.emit(k))
            self.suggest_actions[kind] = act
        self.suggest_btn = QToolButton()
        self.suggest_btn.setText("Find ▾")
        self.suggest_btn.setToolTip("Find components that are probably not machine-placed, review them and remove them")
        self.suggest_btn.setMenu(self.suggest_menu)
        self.suggest_btn.setPopupMode(QToolButton.InstantPopup)
        buttons = QHBoxLayout()
        for act in (self.act_add, self.act_edit, self.act_remove, self.act_restore, self.act_revert):
            btn = QToolButton()
            btn.setDefaultAction(act)
            buttons.addWidget(btn)
        buttons.addWidget(self.suggest_btn)
        buttons.addStretch(1)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(QLabel("Side"))
        top.addWidget(self.side)
        show = QHBoxLayout()
        show.addWidget(QLabel("Show"))
        show.addWidget(self.show_filter, 1)
        pn = QHBoxLayout()
        pn.addWidget(QLabel("Part number from"))
        pn.addWidget(self.mapping, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addLayout(show)
        layout.addLayout(pn)
        layout.addLayout(buttons)
        layout.addWidget(self.table)
        layout.addWidget(self.count)
        self.search.textChanged.connect(self.proxy.set_text)
        self.side.currentTextChanged.connect(self.proxy.set_side)
        self.show_filter.currentIndexChanged.connect(lambda _i: self.proxy.set_show(self.show_filter.currentData()))
        self.mapping.activated.connect(self._mapping_chosen)
        self._updating = False
        self._read_only = True
        self._update_actions()

    def _action(self, text: str, tip: str, shortcut, slot) -> QAction:
        act = QAction(text, self)
        act.setToolTip(tip)
        act.setStatusTip(tip)
        if shortcut is not None:
            act.setShortcut(QKeySequence(shortcut))
            act.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.table.addAction(act)
        act.triggered.connect(lambda _c=False: slot())
        return act

    def _emit(self, signal) -> None:
        keys = self.selected_keys()
        if keys and not self._read_only:
            signal.emit(keys)

    def _mapping_chosen(self, index: int) -> None:
        if not self._updating:
            self.partNumberAttributeChanged.emit(self.mapping.itemData(index) or "")

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        for act in (self.act_add, self.act_edit, self.act_remove, self.act_restore, self.act_revert):
            menu.addAction(act)
        menu.addSeparator()
        menu.addMenu(self.suggest_menu)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ selection
    def _selected(self) -> None:
        self._update_actions()
        if self._updating:
            return
        current = self.table.currentIndex()
        rows = self.table.selectionModel().selectedRows()
        if current.isValid() and self.table.selectionModel().isRowSelected(current.row(), QModelIndex()):
            index = current.siblingAtColumn(COL_DESIGNATOR)
        elif rows:
            index = rows[0]
        else:
            return
        level, designator = index.data(KEY_ROLE)
        self.componentSelected.emit(level, designator)

    def selected_keys(self) -> list[tuple[str, str]]:
        rows = sorted(self.table.selectionModel().selectedRows(), key=lambda i: i.row())
        return [tuple(i.data(KEY_ROLE)) for i in rows]

    def selected_designator(self) -> str | None:
        keys = self.selected_keys()
        return keys[0][1] if keys else None

    def selected_states(self) -> list[str]:
        return [i.data(STATE_ROLE) for i in self.table.selectionModel().selectedRows()]

    def select_designator(self, designator: str, level: str = "board") -> None:
        was = self._updating
        self._updating = True
        try:
            for r in range(self.proxy.rowCount()):
                idx = self.proxy.index(r, COL_DESIGNATOR)
                if tuple(idx.data(KEY_ROLE)) == (level, designator):
                    self.table.selectRow(r)
                    self.table.scrollTo(idx)
                    return
            self.table.clearSelection()
        finally:
            self._updating = was
            self._update_actions()

    def select_keys(self, keys: list[tuple[str, str]]) -> None:
        wanted = set(keys)
        was = self._updating
        self._updating = True
        try:
            selection = self.table.selectionModel()
            selection.clearSelection()
            first = None
            for r in range(self.proxy.rowCount()):
                idx = self.proxy.index(r, COL_DESIGNATOR)
                if tuple(idx.data(KEY_ROLE)) in wanted:
                    selection.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                    first = first or idx
            if first is not None:
                selection.setCurrentIndex(first, QItemSelectionModel.NoUpdate)
        finally:
            self._updating = was
            self._update_actions()

    def _update_actions(self) -> None:
        states = self.selected_states()
        editable = not self._read_only
        self.act_add.setEnabled(editable)
        self.act_edit.setEnabled(editable and bool(states))
        self.act_remove.setEnabled(editable and any(s != "removed" for s in states))
        self.act_restore.setEnabled(editable and "removed" in states)
        self.act_revert.setEnabled(editable and "edited" in states)
        self.suggest_btn.setEnabled(editable)

    # ------------------------------------------------------------------ content
    def set_analysis(self, a: PanelAnalysis | None, read_only: bool = False) -> None:
        self._updating = True
        try:
            keys = self.selected_keys()
            scroll = self.table.verticalScrollBar().value()
            self._read_only = a is None or read_only
            self.model.removeRows(0, self.model.rowCount())
            self.mapping.clear()
            self.mapping.setEnabled(not self._read_only)
            if a is None:
                self.count.setText("")
                return
            self.mapping.addItem("(none)", "")
            examples: dict[str, str] = {}
            for p in [*a.placements, *a.panel_parts]:
                for k, v in p.attributes.items():
                    if v and k not in examples:
                        examples[k] = v
            for key in a.attribute_keys:
                ex = examples.get(key, "")
                self.mapping.addItem(f"{key}  (e.g. {ex[:24]})" if ex else key, key)
            idx = self.mapping.findData(a.part_number_attribute)
            if idx < 0 and a.part_number_attribute:
                self.mapping.addItem(f"{a.part_number_attribute}  (not found)", a.part_number_attribute)
                idx = self.mapping.count() - 1
            self.mapping.setCurrentIndex(max(idx, 0))
            for level, part in all_parts(a):
                self.model.appendRow(self._row(a, level, part))
            self.table.resizeColumnsToContents()
            self.count.setText(self._count_text(a))
            if not self._read_only:
                found = suggest_removals(a)
                for kind, act in self.suggest_actions.items():
                    act.setText(f"{SUGGESTIONS[kind]} ({len(found[kind])})…")
                    act.setEnabled(bool(found[kind]))
            if keys:
                self.select_keys(keys)
            self.table.verticalScrollBar().setValue(scroll)
        finally:
            self._updating = False
            self._update_actions()

    def _row(self, a: PanelAnalysis, level: str, part) -> list[QStandardItem]:
        values = shown_values(a, part)
        export = shown_values(a, part, export=True) if part.export else {}
        cells: list[object] = [
            part.designator,
            level,
            values["part_name"],
            values["part_number"],
            values["package"],
            values["layer"],
            values["x"],
            values["y"],
            values["rotation"],
            (part.paste.describe() if part.paste else "-") if level == "board" else "",
            status_text(part),
        ]
        row = []
        for col, v in enumerate(cells):
            item = QStandardItem(f"{v:.3f}" if col in NUMERIC else str(v))
            item.setData(v if col in NUMERIC else _natural_key(str(v)), SORT_ROLE)
            if col in NUMERIC:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.append(item)
        row[COL_DESIGNATOR].setData((level, part.designator), KEY_ROLE)
        row[COL_DESIGNATOR].setData(part.state, STATE_ROLE)
        if part.state == "removed":
            for item in row:
                item.setForeground(QBrush(theme.REMOVED))
            font = row[COL_DESIGNATOR].font()
            font.setStrikeOut(True)
            row[COL_DESIGNATOR].setFont(font)
        elif part.state == "added":
            row[COL_DESIGNATOR].setForeground(QBrush(theme.ADDED))
            row[COL_STATUS].setForeground(QBrush(theme.ADDED))
        for f in part.export:  # only the fields an edit changed
            old = export[f]
            col = FIELD_COLUMNS[f]
            if part.state != "removed":
                row[col].setForeground(QBrush(theme.EDITED))
            shown = f"{old:.3f}" if col in NUMERIC else (old or "(empty)")
            row[col].setToolTip(f"Export: {shown}")
        if part.state == "edited":
            row[COL_STATUS].setForeground(QBrush(theme.EDITED))
        if part.edit is not None and part.edit.note:
            row[COL_STATUS].setToolTip(part.edit.note)
        return row

    @staticmethod
    def _count_text(a: PanelAnalysis) -> str:
        parts = all_parts(a)
        text = f"{len(a.placements)} placements per circuit ({len(a.circuits)} circuits)"
        if a.panel_parts:
            text += f" · {len(a.panel_parts)} panel-level"
        for state in ("removed", "added", "edited"):
            n = sum(1 for _lv, p in parts if p.state == state)
            if n:
                text += f" · {n} {state}"
        return text


def _natural_key(text: str) -> str:
    """Sort C2 before C10: pad digit runs."""
    out = []
    num = ""
    for ch in text:
        if ch.isdigit():
            num += ch
        else:
            if num:
                out.append(num.zfill(8))
                num = ""
            out.append(ch.lower())
    if num:
        out.append(num.zfill(8))
    return "".join(out)
