"""Colours and layer definitions for the canvas."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

CANVAS_BACKGROUND = QColor("#16181d")


@dataclass(frozen=True)
class LayerStyle:
    key: str
    label: str
    color: QColor
    visible: bool = True
    z: float = 0.0


def _c(hex_rgb: str, alpha: int = 255) -> QColor:
    c = QColor(hex_rgb)
    c.setAlpha(alpha)
    return c


LAYERS: list[LayerStyle] = [
    LayerStyle("panel_outline", "Panel outline", _c("#e8e8e8"), True, 1),
    LayerStyle("circuit_outlines", "Circuit outlines and numbers", _c("#f2c94c"), True, 2),
    LayerStyle("copper_top", "Top copper", _c("#c8823c", 150), True, 10),
    LayerStyle("copper_bottom", "Bottom copper", _c("#3c78d0", 110), False, 9),
    LayerStyle("mask_top", "Top mask openings", _c("#3fb950", 70), False, 11),
    LayerStyle("mask_bottom", "Bottom mask openings", _c("#2aa198", 70), False, 8),
    LayerStyle("paste_top", "Top paste", _c("#d0d4dc", 210), True, 12),
    LayerStyle("paste_bottom", "Bottom paste", _c("#9fa8ff", 180), True, 7),
    LayerStyle("bodies", "Component bodies", _c("#b0b8c8", 170), True, 20),
    LayerStyle("centroids_top", "Centroids (top)", _c("#00e5ff"), True, 30),
    LayerStyle("centroids_bottom", "Centroids (bottom)", _c("#ff5fd2"), True, 29),
    LayerStyle("panel_parts", "Panel-level parts", _c("#a6ff00"), True, 31),
    LayerStyle("labels", "Designator labels (when zoomed in)", _c("#e6edf3"), True, 32),
    LayerStyle("fiducials", "Fiducials", _c("#ffb000"), True, 40),
]
STYLE = {s.key: s for s in LAYERS}

SELECTED_FIDUCIAL = _c("#ff453a")
CIRCUIT_FIDUCIAL = _c("#8b949e")
HIGHLIGHT = _c("#ffffff")
MEASURE = _c("#d4ff4f")
ISSUE_MARK = _c("#ff453a")

SEVERITY_COLOR = {"error": _c("#ff453a"), "warning": _c("#ffb000"), "info": _c("#58a6ff")}
