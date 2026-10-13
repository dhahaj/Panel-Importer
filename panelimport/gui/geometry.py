"""Conversion of ODB++ layer features into Qt painter paths, cached per step layer.

A step's layer is converted once and shared by every instance of the step on the
panel (each instance only has its own item transform).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPolygonF, QTransform

from panelimport.io.odb.features import FeatureFile, arc_points
from panelimport.io.odb.symbols import SymbolShape


@dataclass
class LayerGeometry:
    pads: QPainterPath
    surfaces: QPainterPath
    lines: list[tuple[float, list[QLineF]]] = field(default_factory=list)  # (width mm, segments)
    rect: QRectF = field(default_factory=QRectF)
    count: int = 0


def _symbol_path(shape: SymbolShape) -> QPainterPath:
    """The symbol outline centred on 0,0 (before pad rotation)."""
    path = QPainterPath()
    w, h = shape.width, shape.height
    if shape.kind == "user" and shape.polygons:
        for poly in shape.polygons:
            path.addPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
            path.closeSubpath()
    elif w <= 0 and h <= 0:
        return path
    elif shape.kind in ("round", "donut_r", "round_thermal", "butterfly", "hole", "moire"):
        path.addEllipse(QPointF(0, 0), w / 2, w / 2)
    elif shape.kind in ("oval", "half_oval", "oval_thermal", "oblong_thermal"):
        r = min(w, h) / 2
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
    elif shape.kind == "ellipse":
        path.addEllipse(QPointF(0, 0), w / 2, h / 2)
    elif shape.kind == "rounded_rect":
        path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), shape.corner, shape.corner)
    elif shape.kind == "diamond":
        path.addPolygon(QPolygonF([QPointF(0, -h / 2), QPointF(w / 2, 0), QPointF(0, h / 2), QPointF(-w / 2, 0)]))
        path.closeSubpath()
    elif shape.kind in ("octagon", "chamfered_rect"):
        c = min(shape.corner, w / 2, h / 2)
        pts = [(-w / 2 + c, -h / 2), (w / 2 - c, -h / 2), (w / 2, -h / 2 + c), (w / 2, h / 2 - c),
               (w / 2 - c, h / 2), (-w / 2 + c, h / 2), (-w / 2, h / 2 - c), (-w / 2, -h / 2 + c)]
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        path.closeSubpath()
    elif shape.kind == "triangle":
        path.addPolygon(QPolygonF([QPointF(-w / 2, -h / 2), QPointF(w / 2, -h / 2), QPointF(0, h / 2)]))
        path.closeSubpath()
    else:
        path.addRect(QRectF(-w / 2, -h / 2, w, h))
    if shape.rotation:
        path = QTransform().rotate(-shape.rotation).map(path)
    return path


def build_layer_geometry(ff: FeatureFile) -> LayerGeometry:
    pads = QPainterPath()
    pads.setFillRule(Qt.WindingFill)
    surfaces = QPainterPath()
    surfaces.setFillRule(Qt.OddEvenFill)
    symbol_paths: dict[tuple[int, float, bool], QPainterPath] = {}
    count = 0
    for p in ff.pads:
        if not p.positive:
            continue
        key = (p.sym, p.rotation, p.mirror)
        base = symbol_paths.get(key)
        if base is None:
            base = _symbol_path(ff.symbol(p.sym))
            t = QTransform()
            if p.mirror:
                t.scale(-1, 1)
            # ODB++ rotation is clockwise in a Y-up frame: rotate by -angle.
            t.rotate(-p.rotation)
            base = t.map(base)
            symbol_paths[key] = base
        if base.isEmpty():
            continue
        pads.addPath(base.translated(p.x, p.y))
        count += 1
    by_width: dict[float, list[QLineF]] = {}
    for ln in ff.lines:
        if ln.positive:
            by_width.setdefault(round(ff.symbol(ln.sym).width, 4), []).append(QLineF(ln.x1, ln.y1, ln.x2, ln.y2))
            count += 1
    for a in ff.arcs:
        if not a.positive:
            continue
        w = round(ff.symbol(a.sym).width, 4)
        prev = QPointF(a.x1, a.y1)
        for x, y in arc_points(a.x1, a.y1, a.x2, a.y2, a.xc, a.yc, a.cw, step_deg=10.0):
            cur = QPointF(x, y)
            by_width.setdefault(w, []).append(QLineF(prev, cur))
            prev = cur
        count += 1
    for s in ff.surfaces:
        if not s.positive:
            continue
        for c in s.contours:
            if len(c.points) >= 3:
                surfaces.addPolygon(QPolygonF([QPointF(x, y) for x, y in c.points]))
                surfaces.closeSubpath()
        count += 1
    rect = pads.boundingRect().united(surfaces.boundingRect())
    for w, segs in by_width.items():
        xs = [v for s in segs for v in (s.x1(), s.x2())]
        ys = [v for s in segs for v in (s.y1(), s.y2())]
        rect = rect.united(QRectF(min(xs) - w, min(ys) - w, max(xs) - min(xs) + 2 * w, max(ys) - min(ys) + 2 * w))
    return LayerGeometry(pads, surfaces, sorted(by_width.items()), rect, count)


def polygon_path(points, close: bool = True) -> QPainterPath:
    path = QPainterPath()
    if len(points) >= 2:
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        if close:
            path.closeSubpath()
    return path


def qtransform(t) -> QTransform:
    """analysis.transforms.Transform -> QTransform (row-vector convention)."""
    return QTransform(t.a, t.c, t.b, t.d, t.tx, t.ty)
