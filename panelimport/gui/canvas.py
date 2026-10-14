"""The panel canvas: a QGraphicsView in panel coordinates (mm, Y up).

* Pan with the middle mouse button, zoom with the wheel towards the cursor, ``F`` fits.
* Layers are toggleable; a step's layer is drawn once per instance via item transforms.
* Centroid and fiducial markers keep a constant pixel size; hovering shows details.
* Measure tool: two clicks give ΔX, ΔY and the distance (snapping to markers).
* "View from bottom" mirrors the display only.
* Right-click asks the main window for a menu (edit, remove or add components);
  double-clicking a component asks to edit it.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QStyleOptionGraphicsItem,
)

from panelimport.analysis.edits import status_text
from panelimport.analysis.result import PanelAnalysis
from panelimport.gui import theme
from panelimport.gui.geometry import LayerGeometry, build_layer_geometry, polygon_path, qtransform

LABEL_ZOOM = 6.0  # pixels per mm above which designator labels are drawn


class FeatureLayerItem(QGraphicsItem):
    """One layer of one step instance (pads, lines, surfaces)."""

    def __init__(self, geo: LayerGeometry, color: QColor, transform: QTransform) -> None:
        super().__init__()
        self.geo = geo
        self.color = color
        self.setTransform(transform)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:
        return self.geo.rect

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        if not self.geo.surfaces.isEmpty():
            painter.drawPath(self.geo.surfaces)
        if not self.geo.pads.isEmpty():
            painter.drawPath(self.geo.pads)
        for width, lines in self.geo.lines:
            pen = QPen(self.color, max(width, 0.0), Qt.SolidLine, Qt.RoundCap)
            if width <= 0:
                pen.setCosmetic(True)
                pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.drawLines(lines)


class MarkerItem(QGraphicsItem):
    """A constant-size marker for a centroid, panel part or fiducial."""

    show_labels = False
    view_mirrored = False

    def __init__(
        self, kind: str, key: tuple, color: QColor, label: str, rotation: float | None = None, state: str = ""
    ) -> None:
        super().__init__()
        self.kind = kind  # "placement" | "panel_part" | "fiducial"
        self.key = key
        self.color = color
        self.label = label
        self.rotation_ccw = rotation
        self.state = state  # "" | "edited" | "added" | "removed" (component edits)
        self.selected_number: int | None = None
        self.selectable_fiducial = True
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self._hover = False

    def boundingRect(self) -> QRectF:
        return QRectF(-10, -10, 20 + 90, 20)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(QRectF(-7, -7, 14, 14))
        return p

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = theme.HIGHLIGHT if (self.isSelected() or self._hover) else self.color
        pen = QPen(color, 2.0 if self.isSelected() else 1.3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if self.kind == "fiducial":
            r = 7.0 if self.selectable_fiducial else 5.0
            if self.selected_number is not None:
                painter.setBrush(QBrush(theme.SELECTED_FIDUCIAL))
                painter.setPen(QPen(theme.HIGHLIGHT if self.isSelected() else theme.SELECTED_FIDUCIAL, 2.0))
            painter.drawEllipse(QPointF(0, 0), r, r)
            painter.drawLine(QPointF(-r - 3, 0), QPointF(r + 3, 0))
            painter.drawLine(QPointF(0, -r - 3), QPointF(0, r + 3))
            if self.selected_number is not None:
                painter.setPen(QPen(theme.HIGHLIGHT))
                f = QFont(painter.font())
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(QPointF(10, -8), str(self.selected_number))
        elif self.state == "removed":  # not placed: a grey cross, no rotation
            s = 3.5
            painter.drawLine(QPointF(-s, -s), QPointF(s, s))
            painter.drawLine(QPointF(-s, s), QPointF(s, -s))
        else:
            s = 4.0 if self.kind == "placement" else 5.0
            painter.drawLine(QPointF(-s, 0), QPointF(s, 0))
            painter.drawLine(QPointF(0, -s), QPointF(0, s))
            if self.state == "added":  # added by hand: a green diamond
                d = s + 1.5
                painter.setPen(QPen(theme.HIGHLIGHT if self.isSelected() else theme.ADDED, pen.widthF()))
                painter.drawPolygon(QPolygonF([QPointF(0, -d), QPointF(d, 0), QPointF(0, d), QPointF(-d, 0)]))
                painter.setPen(pen)
            elif self.kind == "panel_part":
                painter.drawRect(QRectF(-s, -s, 2 * s, 2 * s))
            else:
                painter.drawEllipse(QPointF(0, 0), 2.2, 2.2)
            if self.state == "edited":  # edited by hand: an amber centre
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(theme.EDITED))
                painter.drawEllipse(QPointF(0, 0), 2.6, 2.6)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)
            if self.rotation_ccw is not None:
                t = math.radians(self.rotation_ccw)
                dx, dy = math.cos(t), -math.sin(t)  # device Y points down
                if MarkerItem.view_mirrored:
                    dx = -dx
                painter.drawLine(QPointF(0, 0), QPointF(dx * 7, dy * 7))
        if MarkerItem.show_labels or self.isSelected() or self._hover:
            label_color = {"edited": theme.EDITED, "added": theme.ADDED, "removed": theme.REMOVED}.get(
                self.state, theme.STYLE["labels"].color
            )
            painter.setPen(QPen(label_color))
            painter.drawText(QPointF(9, 4), self.label)


class PanelCanvas(QGraphicsView):
    cursorMoved = Signal(float, float)
    measured = Signal(float, float, float)
    itemPicked = Signal(str, object)  # kind, key
    selectionCleared = Signal()
    zoomChanged = Signal(float)
    # (kind, key) of the component under the cursor or None, panel x, y, global position
    contextRequested = Signal(object, float, float, object)
    editRequested = Signal(object)  # (kind, key) of a double-clicked component

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(theme.CANVAS_BACKGROUND)
        self.setRenderHints(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setOptimizationFlags(QGraphicsView.DontSavePainterState)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.analysis: PanelAnalysis | None = None
        self.layers: dict[str, list[QGraphicsItem]] = {s.key: [] for s in theme.LAYERS}
        self.visible: dict[str, bool] = {s.key: s.visible for s in theme.LAYERS}
        self._geo_cache: dict[tuple, LayerGeometry] = {}
        self._geo_job = None
        self._markers: list[MarkerItem] = []
        self._snap = np.zeros((0, 2))
        self._pan_last = None
        self._measure = False
        self._measure_pts: list[QPointF] = []
        self._measure_items: list[QGraphicsItem] = []
        self._issue_items: list[QGraphicsItem] = []
        self._mirrored = False
        self._suppress_selection = False
        self.scene().selectionChanged.connect(self._on_selection_changed)
        self.setTransform(QTransform.fromScale(4, -4))

    # ------------------------------------------------------------------ content
    def clear(self) -> None:
        self.scene().clear()
        self.layers = {s.key: [] for s in theme.LAYERS}
        self._markers = []
        self._measure_items = []
        self._issue_items = []
        self._measure_pts = []
        self.analysis = None

    def set_analysis(self, analysis: PanelAnalysis | None, keep_view: bool = False) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        transform = self.transform()
        self._suppress_selection = True
        self.clear()
        self.analysis = analysis
        if analysis is None:
            self._suppress_selection = False
            return
        if analysis.job is not self._geo_job:
            self._geo_cache = {}
            self._geo_job = analysis.job
        self._build(analysis)
        self._apply_visibility()
        rect = self._content_rect()
        self.scene().setSceneRect(rect.adjusted(-rect.width(), -rect.height(), rect.width(), rect.height()))
        if keep_view:
            self.setTransform(transform)
            self.centerOn(center)
        else:
            self.fit()
        self._suppress_selection = False

    def _add(self, layer: str, item: QGraphicsItem) -> QGraphicsItem:
        item.setZValue(theme.STYLE[layer].z)
        self.scene().addItem(item)
        self.layers[layer].append(item)
        return item

    def _geometry(self, draw) -> LayerGeometry | None:
        key = (id(draw.job), draw.step.lower(), draw.layer.lower())
        if key not in self._geo_cache:
            ff = draw.job.features(draw.step, draw.layer)
            self._geo_cache[key] = build_layer_geometry(ff) if ff is not None else None
        return self._geo_cache[key]

    def _build(self, a: PanelAnalysis) -> None:
        # Feature layers
        for draw in a.layer_draws():
            if draw.role not in self.layers:
                continue
            geo = self._geometry(draw)
            if geo is None or geo.count == 0:
                continue
            self._add(draw.role, FeatureLayerItem(geo, theme.STYLE[draw.role].color, qtransform(draw.transform)))

        # Outlines
        if a.panel_outline:
            item = QGraphicsPathItem(polygon_path(a.panel_outline))
            pen = QPen(theme.STYLE["panel_outline"].color, 1.5)
            pen.setCosmetic(True)
            item.setPen(pen)
            self._add("panel_outline", item)
        font = QFont()
        font.setBold(True)
        font.setPointSize(14)
        for c in a.circuits:
            item = QGraphicsPathItem(polygon_path(c.outline))
            pen = QPen(theme.STYLE["circuit_outlines"].color, 1.2, Qt.DashLine)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setToolTip(self._circuit_tip(c))
            self._add("circuit_outlines", item)
            label = QGraphicsSimpleTextItem(str(c.index))
            label.setFont(font)
            label.setBrush(theme.STYLE["circuit_outlines"].color)
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            br = label.boundingRect()
            label.setPos(QPointF(*c.center))
            label.setTransformOriginPoint(br.center())
            label.setTransform(QTransform.fromTranslate(-br.width() / 2, -br.height() / 2))
            self._add("circuit_outlines", label)

        # Component bodies, one path per circuit and side
        for c in a.circuits:
            for side in ("top", "bottom"):
                path = QPainterPath()
                for p in a.placements:
                    if p.layer != side:
                        continue
                    for poly in p.body:
                        path.addPath(polygon_path(poly))
                if path.isEmpty():
                    continue
                item = QGraphicsPathItem(path)
                item.setTransform(qtransform(c.transform))
                color = QColor(theme.STYLE["bodies"].color)
                if side == "bottom":
                    color = QColor(theme.STYLE["centroids_bottom"].color)
                    color.setAlpha(110)
                pen = QPen(color, 1.0)
                pen.setCosmetic(True)
                item.setPen(pen)
                item.setAcceptedMouseButtons(Qt.NoButton)
                self._add("bodies", item)

        # Centroids per circuit
        snap = []
        for c in a.circuits:
            for p in a.placements:
                x, y, rot = a.circuit_position(p, c)
                layer = "centroids_top" if p.layer == "top" else "centroids_bottom"
                m = MarkerItem("placement", (p.designator, c.index), theme.STYLE[layer].color, p.designator, rot, p.state)
                m.setPos(x, y)
                m.setToolTip(self._placement_tip(a, p, c, x, y, rot))
                self._add(layer, m)
                self._markers.append(m)
                snap.append((x, y))
            for p in a.removed_placements:
                x, y, rot = a.circuit_position(p, c)
                m = MarkerItem("placement", (p.designator, c.index), theme.STYLE["removed"].color, p.designator, None, "removed")
                m.setPos(x, y)
                m.setToolTip(self._placement_tip(a, p, c, x, y, rot))
                self._add("removed", m)
                self._markers.append(m)
        for pp in [*a.panel_parts, *a.removed_panel_parts]:
            removed = pp.state == "removed"
            color = theme.STYLE["removed" if removed else "panel_parts"].color
            m = MarkerItem("panel_part", (pp.designator,), color, pp.designator, None if removed else pp.rotation, pp.state)
            m.setPos(pp.x, pp.y)
            status = status_text(pp)
            pn = f"<br>Part number {pp.part_number}" if pp.part_number else ""
            m.setToolTip(
                f"<b>{pp.designator}</b> — panel-level part<br>{pp.part_name}{pn}<br>Layer {pp.layer}<br>"
                f"Rotation {pp.rotation:.3f}° (raw {pp.rotation_raw:.3f}° CW)<br>Panel X {pp.x:.3f} Y {pp.y:.3f}"
                + (f"<br><i>{status}</i>" if status else "")
            )
            self._add("removed" if removed else "panel_parts", m)
            self._markers.append(m)
            if not removed:
                snap.append((pp.x, pp.y))

        # Fiducials
        chosen = {f.name: i + 1 for i, f in enumerate(a.fiducials)}
        for f in a.fiducial_candidates:
            color = theme.STYLE["fiducials"].color if f.selectable else theme.CIRCUIT_FIDUCIAL
            m = MarkerItem("fiducial", (f.name,), color, f.name if f.selectable else "")
            m.selectable_fiducial = f.selectable
            m.selected_number = chosen.get(f.name)
            m.setPos(f.x, f.y)
            level = "panel fiducial" if f.selectable else f"circuit-level fiducial (circuit {f.circuit})"
            d = f"<br>Diameter {f.diameter:.3f} mm" if f.diameter else ""
            hint = "<br><i>Click to accept or remove</i>" if f.selectable else "<br><i>Shown only; not selectable</i>"
            m.setToolTip(
                f"<b>{f.name}</b> — {level}<br>Source: {', '.join(f.sources)}<br>Side {f.side}"
                f"<br>Panel X {f.x:.3f} Y {f.y:.3f}{d}{hint}"
            )
            self._add("fiducials", m)
            self._markers.append(m)
            snap.append((f.x, f.y))
        self._snap = np.array(snap, dtype=float).reshape(-1, 2)

    @staticmethod
    def _circuit_tip(c) -> str:
        res = "" if c.residual is None else f"<br>Fit residual {c.residual:.4f} mm"
        return (
            f"<b>Circuit {c.index}</b><br>ΔX {c.dx:.3f}  ΔY {c.dy:.3f} mm<br>Rotation {c.rotation:.3f}°"
            f"{' (mirrored)' if c.mirror else ''}<br>Source {c.source}{res}"
        )

    @staticmethod
    def _placement_tip(a: PanelAnalysis, p, c, x: float, y: float, rot: float) -> str:
        rx, ry = a.reference_board
        pn = f"<br>Part number {p.part_number}" if p.part_number else ""
        status = status_text(p)
        return (
            f"<b>{p.designator}</b> — {p.part_name}{pn}<br>Package {p.package or '?'} · {p.layer}"
            f"<br>Rotation {p.rotation:.3f}° (raw {p.rotation_raw:.3f}° CW)"
            f"<br>Panel X {x:.3f}  Y {y:.3f}"
            f"<br>Circuit {c.index}: X {p.x - rx:.3f}  Y {p.y - ry:.3f}"
            + (f"<br><i>{status}</i>" if status else "")
        )

    def _content_rect(self) -> QRectF:
        if self.analysis and self.analysis.panel_outline:
            return polygon_path(self.analysis.panel_outline).boundingRect()
        rect = QRectF()
        for c in self.analysis.circuits if self.analysis else []:
            rect = rect.united(polygon_path(c.outline).boundingRect())
        return rect if not rect.isNull() else QRectF(0, 0, 100, 100)

    # ------------------------------------------------------------------ layers
    def set_layer_visible(self, key: str, visible: bool) -> None:
        self.visible[key] = visible
        if key == "labels":
            MarkerItem.show_labels = visible and self.zoom() >= LABEL_ZOOM
            self.viewport().update()
            return
        for item in self.layers.get(key, []):
            item.setVisible(visible)

    def _apply_visibility(self) -> None:
        for key, items in self.layers.items():
            for item in items:
                item.setVisible(self.visible.get(key, True))
        MarkerItem.show_labels = self.visible.get("labels", True) and self.zoom() >= LABEL_ZOOM

    # ------------------------------------------------------------------ view
    def zoom(self) -> float:
        t = self.transform()
        return math.hypot(t.m11(), t.m12())

    def fit(self) -> None:
        rect = self._content_rect()
        if rect.isEmpty():
            return
        m = max(rect.width(), rect.height()) * 0.03
        self.fitInView(rect.adjusted(-m, -m, m, m), Qt.KeepAspectRatio)
        self._zoom_changed()

    def zoom_to(self, x: float, y: float, radius: float = 4.0) -> None:
        self.fitInView(QRectF(x - radius, y - radius, 2 * radius, 2 * radius), Qt.KeepAspectRatio)
        self._zoom_changed()

    def set_view_from_bottom(self, on: bool) -> None:
        if on == self._mirrored:
            return
        self._mirrored = on
        MarkerItem.view_mirrored = on
        center = self.mapToScene(self.viewport().rect().center())
        self.setTransform(self.transform() * QTransform.fromScale(-1, 1))
        self.centerOn(center)
        self.viewport().update()

    def _zoom_changed(self) -> None:
        show = self.visible.get("labels", True) and self.zoom() >= LABEL_ZOOM
        if show != MarkerItem.show_labels:
            MarkerItem.show_labels = show
            self.viewport().update()
        self.zoomChanged.emit(self.zoom())

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if not delta:
            return
        factor = 1.25 ** (delta / 120.0)
        new_zoom = self.zoom() * factor
        if 0.05 < new_zoom < 5000:
            self.scale(factor, factor)
            self._zoom_changed()

    # ------------------------------------------------------------------ selection
    def _on_selection_changed(self) -> None:
        if self._suppress_selection:
            return
        items = [i for i in self.scene().selectedItems() if isinstance(i, MarkerItem)]
        if not items:
            self.selectionCleared.emit()
            return
        item = items[0]
        self.itemPicked.emit(item.kind, item.key)

    def select_designator(
        self, designator: str, circuit: int | None = None, center: bool = False, level: str | None = None
    ) -> None:
        """Select a component's markers (``level`` "board", "panel" or None for both)."""
        self._suppress_selection = True
        self.scene().clearSelection()
        target = None
        for m in self._markers:
            if m.kind == "placement" and m.key[0] == designator and level != "panel":
                m.setSelected(True)
                if circuit is None or m.key[1] == circuit:
                    target = target or m
            elif m.kind == "panel_part" and m.key[0] == designator and level != "board":
                m.setSelected(True)
                target = target or m
        self._suppress_selection = False
        if center and target is not None:
            self.centerOn(target.pos())

    def select_fiducial(self, name: str, center: bool = False) -> None:
        self._suppress_selection = True
        self.scene().clearSelection()
        for m in self._markers:
            if m.kind == "fiducial" and m.key[0] == name:
                m.setSelected(True)
                if center:
                    self.centerOn(m.pos())
        self._suppress_selection = False

    def show_location(self, x: float, y: float, radius: float = 4.0) -> None:
        for item in self._issue_items:
            self.scene().removeItem(item)
        self._issue_items = []
        path = QPainterPath()
        path.addEllipse(QPointF(x, y), radius * 0.4, radius * 0.4)
        item = QGraphicsPathItem(path)
        pen = QPen(theme.ISSUE_MARK, 2.0)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setZValue(100)
        self.scene().addItem(item)
        self._issue_items.append(item)
        self.zoom_to(x, y, radius)

    # ------------------------------------------------------------------ measure
    def set_measure_mode(self, on: bool) -> None:
        self._measure = on
        self._clear_measure()
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def _clear_measure(self) -> None:
        for item in self._measure_items:
            self.scene().removeItem(item)
        self._measure_items = []
        self._measure_pts = []

    def _snapped(self, pos) -> QPointF:
        p = self.mapToScene(pos)
        if len(self._snap) == 0:
            return p
        d = np.hypot(self._snap[:, 0] - p.x(), self._snap[:, 1] - p.y())
        i = int(np.argmin(d))
        if d[i] * self.zoom() <= 10:  # within 10 pixels
            return QPointF(*self._snap[i])
        return p

    def _draw_measure(self, a: QPointF, b: QPointF) -> None:
        for item in self._measure_items:
            self.scene().removeItem(item)
        self._measure_items = []
        path = QPainterPath(a)
        path.lineTo(b)
        line = QGraphicsPathItem(path)
        pen = QPen(theme.MEASURE, 1.5)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(90)
        self.scene().addItem(line)
        dx, dy = b.x() - a.x(), b.y() - a.y()
        text = QGraphicsSimpleTextItem(f"ΔX {dx:.3f}  ΔY {dy:.3f}  D {math.hypot(dx, dy):.3f} mm")
        text.setBrush(theme.MEASURE)
        text.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        text.setPos(b)
        text.setZValue(91)
        self.scene().addItem(text)
        self._measure_items = [line, text]

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if self._measure and event.button() == Qt.LeftButton:
            p = self._snapped(event.position().toPoint())
            if len(self._measure_pts) != 1:
                self._clear_measure()
                self._measure_pts = [p]
            else:
                a = self._measure_pts[0]
                self._measure_pts.append(p)
                self._draw_measure(a, p)
                dx, dy = p.x() - a.x(), p.y() - a.y()
                self.measured.emit(dx, dy, math.hypot(dx, dy))
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if isinstance(item, MarkerItem) and item.kind == "fiducial":
                super().mousePressEvent(event)
                self.itemPicked.emit("fiducial_click", item.key)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_last is not None:
            pos = event.position().toPoint()
            delta = pos - self._pan_last
            self._pan_last = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        p = self.mapToScene(event.position().toPoint())
        self.cursorMoved.emit(p.x(), p.y())
        if self._measure and len(self._measure_pts) == 1:
            self._draw_measure(self._measure_pts[0], self._snapped(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.setCursor(Qt.CrossCursor if self._measure else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if (
            event.button() == Qt.LeftButton
            and not self._measure
            and isinstance(item, MarkerItem)
            and item.kind in ("placement", "panel_part")
        ):
            self.editRequested.emit((item.kind, item.key))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self.analysis is None:
            return
        item = self.itemAt(event.pos())
        key = None
        if isinstance(item, MarkerItem) and item.kind in ("placement", "panel_part"):
            key = (item.kind, item.key)
        p = self.mapToScene(event.pos())
        self.contextRequested.emit(key, p.x(), p.y(), event.globalPos())
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_F:
            self.fit()
            return
        if event.key() == Qt.Key_Escape and self._measure:
            self._clear_measure()
            return
        super().keyPressEvent(event)
