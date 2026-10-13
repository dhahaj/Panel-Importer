"""Components of circuit 1: sortable, filterable, searchable; part-number mapping."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from panelimport.analysis.result import PanelAnalysis

COLUMNS = ["Designator", "Part name", "Part number", "Package", "Layer", "X (mm)", "Y (mm)", "Rotation (°)", "Paste check"]
NUMERIC = {5, 6, 7}
SORT_ROLE = Qt.UserRole + 1


class ComponentFilter(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.side = "all"
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

    def set_text(self, text: str) -> None:
        self._refilter(lambda: setattr(self, "text", text.strip().lower()))

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if self.side != "all" and model.index(row, 4, parent).data() != self.side:
            return False
        if not self.text:
            return True
        return any(self.text in str(model.index(row, c, parent).data() or "").lower() for c in range(model.columnCount()))


class ComponentsPanel(QWidget):
    componentSelected = Signal(str)
    partNumberAttributeChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search designator, part, package…")
        self.search.setClearButtonEnabled(True)
        self.side = QComboBox()
        self.side.addItems(["all", "top", "bottom"])
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
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.selectionModel().selectionChanged.connect(self._selected)
        self.count = QLabel("")
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(QLabel("Side"))
        top.addWidget(self.side)
        pn = QHBoxLayout()
        pn.addWidget(QLabel("Part number from"))
        pn.addWidget(self.mapping, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(top)
        layout.addLayout(pn)
        layout.addWidget(self.table)
        layout.addWidget(self.count)
        self.search.textChanged.connect(self.proxy.set_text)
        self.side.currentTextChanged.connect(self.proxy.set_side)
        self.mapping.activated.connect(self._mapping_chosen)
        self._updating = False

    def _mapping_chosen(self, index: int) -> None:
        if not self._updating:
            self.partNumberAttributeChanged.emit(self.mapping.itemData(index) or "")

    def _selected(self) -> None:
        if self._updating:
            return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.componentSelected.emit(rows[0].data())

    def set_analysis(self, a: PanelAnalysis | None, read_only: bool = False) -> None:
        self._updating = True
        try:
            selected = self.selected_designator()
            self.model.removeRows(0, self.model.rowCount())
            self.mapping.clear()
            self.mapping.setEnabled(a is not None and not read_only)
            if a is None:
                self.count.setText("")
                return
            self.mapping.addItem("(none)", "")
            examples: dict[str, str] = {}
            for p in a.placements:
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
            rx, ry = a.reference_board
            for p in a.placements:
                values = [
                    p.designator,
                    p.part_name,
                    p.part_number,
                    p.package,
                    p.layer,
                    p.x - rx,
                    p.y - ry,
                    p.rotation,
                    p.paste.describe() if p.paste else "-",
                ]
                row = []
                for col, v in enumerate(values):
                    item = QStandardItem(f"{v:.3f}" if col in NUMERIC else str(v))
                    item.setData(v if col in NUMERIC else _natural_key(str(v)), SORT_ROLE)
                    if col in NUMERIC:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    row.append(item)
                self.model.appendRow(row)
            self.table.resizeColumnsToContents()
            self.count.setText(f"{len(a.placements)} placements per circuit ({len(a.circuits)} circuits)")
            if selected:
                self.select_designator(selected)
        finally:
            self._updating = False

    def selected_designator(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].data() if rows else None

    def select_designator(self, designator: str) -> None:
        was = self._updating
        self._updating = True
        try:
            for r in range(self.proxy.rowCount()):
                idx = self.proxy.index(r, 0)
                if idx.data() == designator:
                    self.table.selectRow(r)
                    self.table.scrollTo(idx)
                    return
            self.table.clearSelection()
        finally:
            self._updating = was


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
