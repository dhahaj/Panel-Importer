"""Toggleable, colour-coded canvas layers."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from panelimport.gui import theme


def swatch(color: QColor, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    c = QColor(color)
    c.setAlpha(255)
    pm.fill(c)
    return QIcon(pm)


class LayersPanel(QWidget):
    layerToggled = Signal(str, bool)

    def __init__(self, visible: dict[str, bool], parent=None) -> None:
        super().__init__(parent)
        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        for style in theme.LAYERS:
            item = QListWidgetItem(swatch(style.color), style.label)
            item.setData(Qt.UserRole, style.key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if visible.get(style.key, style.visible) else Qt.Unchecked)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.list)

    def _changed(self, item: QListWidgetItem) -> None:
        self.layerToggled.emit(item.data(Qt.UserRole), item.checkState() == Qt.Checked)

    def set_checked(self, key: str, on: bool) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.UserRole) == key:
                item.setCheckState(Qt.Checked if on else Qt.Unchecked)
