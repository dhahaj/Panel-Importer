"""Toggleable, colour-coded canvas layers.  Double-click a layer (or use its context menu
or the Colour… button) to change its colour; Reset colours restores the defaults."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from panelimport.gui import theme


def swatch(color: QColor, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    c = QColor(color)
    c.setAlpha(255)
    pm.fill(c)
    return QIcon(pm)


class LayersPanel(QWidget):
    layerToggled = Signal(str, bool)
    colorChanged = Signal(str, QColor)

    def __init__(self, visible: dict[str, bool], colors: dict[str, QColor] | None = None, parent=None) -> None:
        super().__init__(parent)
        colors = colors or {}
        self.colors = {s.key: QColor(colors.get(s.key, s.color)) for s in theme.LAYERS}
        self.color_button = QPushButton("Colour…")
        self.color_button.setToolTip("Change the colour of the selected layer")
        self.color_button.setEnabled(False)
        self.color_button.clicked.connect(lambda: self.choose_color(self.current_key()))
        self.reset_button = QPushButton("Reset colours")
        self.reset_button.setToolTip("Restore every layer's default colour")
        self.reset_button.clicked.connect(self.reset_colors)
        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        for style in theme.LAYERS:
            item = QListWidgetItem(swatch(self.colors[style.key]), style.label)
            item.setData(Qt.UserRole, style.key)
            item.setToolTip("Double-click to change the colour")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if visible.get(style.key, style.visible) else Qt.Unchecked)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._changed)
        # Activation is a double-click outside the check box, or Enter.
        self.list.itemActivated.connect(lambda item: self.choose_color(item.data(Qt.UserRole)))
        self.list.currentItemChanged.connect(lambda item, _prev: self.color_button.setEnabled(item is not None))
        self.list.customContextMenuRequested.connect(self._context_menu)
        buttons = QHBoxLayout()
        buttons.addWidget(self.color_button)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.list)
        layout.addLayout(buttons)
        self._update_reset()

    def _changed(self, item: QListWidgetItem) -> None:
        self.layerToggled.emit(item.data(Qt.UserRole), item.checkState() == Qt.Checked)

    def _item(self, key: str) -> QListWidgetItem | None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.UserRole) == key:
                return item
        return None

    def current_key(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def set_checked(self, key: str, on: bool) -> None:
        item = self._item(key)
        if item is not None:
            item.setCheckState(Qt.Checked if on else Qt.Unchecked)

    # ------------------------------------------------------------------ colours
    def is_default(self, key: str) -> bool:
        return self.colors[key] == theme.STYLE[key].color

    def set_color(self, key: str, color: QColor) -> None:
        """Show ``color`` for a layer without announcing it."""
        self.colors[key] = QColor(color)
        item = self._item(key)
        if item is not None:
            item.setIcon(swatch(color))
        self._update_reset()

    def choose_color(self, key: str | None) -> None:
        if key is None:
            return
        color = QColorDialog.getColor(
            self.colors[key], self, f"{theme.STYLE[key].label} colour", QColorDialog.ShowAlphaChannel
        )
        if color.isValid() and color != self.colors[key]:
            self.set_color(key, color)
            self.colorChanged.emit(key, QColor(color))

    def reset_color(self, key: str) -> None:
        if not self.is_default(key):
            self.set_color(key, theme.STYLE[key].color)
            self.colorChanged.emit(key, QColor(theme.STYLE[key].color))

    def reset_colors(self) -> None:
        for style in theme.LAYERS:
            self.reset_color(style.key)

    def _update_reset(self) -> None:
        self.reset_button.setEnabled(not all(self.is_default(s.key) for s in theme.LAYERS))

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        item = self.list.itemAt(pos)
        if item is not None:
            key = item.data(Qt.UserRole)
            menu.addAction("Change colour…").triggered.connect(lambda: self.choose_color(key))
            reset = menu.addAction("Reset colour")
            reset.setEnabled(not self.is_default(key))
            reset.triggered.connect(lambda: self.reset_color(key))
            menu.addSeparator()
        reset_all = menu.addAction("Reset all colours")
        reset_all.setEnabled(self.reset_button.isEnabled())
        reset_all.triggered.connect(self.reset_colors)
        menu.exec(self.list.viewport().mapToGlobal(pos))
