"""A uniform-grid spatial index for point and box queries."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np


class BoxIndex:
    """Index of axis-aligned boxes ``(xmin, ymin, xmax, ymax)`` with a centre point each."""

    def __init__(self, boxes: np.ndarray, centres: np.ndarray, cell: float = 2.0) -> None:
        self.boxes = np.asarray(boxes, dtype=float).reshape(-1, 4)
        self.centres = np.asarray(centres, dtype=float).reshape(-1, 2)
        self.cell = max(cell, 1e-6)
        self._grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (x0, y0, x1, y1) in enumerate(self.boxes):
            for gx in range(self._c(x0), self._c(x1) + 1):
                for gy in range(self._c(y0), self._c(y1) + 1):
                    self._grid[(gx, gy)].append(i)

    def __len__(self) -> int:
        return len(self.boxes)

    def _c(self, v: float) -> int:
        return math.floor(v / self.cell)

    def candidates(self, x0: float, y0: float, x1: float, y1: float) -> set[int]:
        out: set[int] = set()
        for gx in range(self._c(x0), self._c(x1) + 1):
            for gy in range(self._c(y0), self._c(y1) + 1):
                out.update(self._grid.get((gx, gy), ()))
        return out

    def containing(self, x: float, y: float, slack: float = 0.0) -> list[int]:
        """Boxes that contain the point (grown by ``slack``)."""
        hits = []
        for i in self.candidates(x - slack, y - slack, x + slack, y + slack):
            bx0, by0, bx1, by1 = self.boxes[i]
            if bx0 - slack <= x <= bx1 + slack and by0 - slack <= y <= by1 + slack:
                hits.append(i)
        return hits

    def within(self, x: float, y: float, radius: float) -> list[int]:
        """Boxes whose centre lies within ``radius`` of the point, nearest first."""
        cand = self.candidates(x - radius, y - radius, x + radius, y + radius)
        found = []
        for i in cand:
            cx, cy = self.centres[i]
            d = math.hypot(cx - x, cy - y)
            if d <= radius:
                found.append((d, i))
        found.sort()
        return [i for _d, i in found]

    def overlapping(self, x0: float, y0: float, x1: float, y1: float) -> list[int]:
        hits = []
        for i in self.candidates(x0, y0, x1, y1):
            bx0, by0, bx1, by1 = self.boxes[i]
            if bx0 <= x1 and bx1 >= x0 and by0 <= y1 and by1 >= y0:
                hits.append(i)
        return hits
