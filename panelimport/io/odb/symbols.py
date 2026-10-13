"""ODB++ standard symbol names (spec chapter "Symbol Definitions").

A symbol name such as ``rect20x60`` describes the shape; its dimensions are in mils
or microns depending on the units in force (see :class:`~.common.Units`).  Names that
are not standard symbols refer to user-defined symbols stored under
``symbols/<name>/features``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

NUM = r"(\d+(?:\.\d*)?|\.\d+)"
_OPT_CORNERS = r"(?:x(\d+))?"


@dataclass
class SymbolShape:
    name: str
    kind: str
    width: float  # mm, extent along X before rotation
    height: float  # mm, extent along Y before rotation
    corner: float = 0.0  # mm: corner radius, chamfer or octagon corner size
    inner: float = 0.0  # mm: inner diameter/size of donuts and thermals
    rotation: float = 0.0  # degrees clockwise, for rotated standard symbols ``<name>_<angle>``
    standard: bool = True
    # User-defined symbols: extent relative to the insertion point, and their islands.
    extent: tuple[float, float, float, float] | None = None
    polygons: list[list[tuple[float, float]]] = field(default_factory=list)
    resolved: bool = True

    @property
    def is_round(self) -> bool:
        return self.kind == "round"

    def local_extent(self) -> tuple[float, float, float, float]:
        """Extent relative to the pad centre, before pad rotation (mm)."""
        if self.extent is not None:
            xmin, ymin, xmax, ymax = self.extent
        else:
            xmin, ymin, xmax, ymax = -self.width / 2, -self.height / 2, self.width / 2, self.height / 2
        if self.rotation:
            return rotate_extent((xmin, ymin, xmax, ymax), self.rotation)
        return xmin, ymin, xmax, ymax


def rotate_extent(
    ext: tuple[float, float, float, float], angle_cw: float
) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = ext
    t = math.radians(angle_cw)
    c, s = math.cos(t), math.sin(t)
    xs, ys = [], []
    for x, y in ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)):
        xs.append(x * c + y * s)
        ys.append(-x * s + y * c)
    return min(xs), min(ys), max(xs), max(ys)


def _f(v: str | None) -> float:
    return float(v) if v else 0.0


# (kind, regex, function(groups) -> (w, h, corner, inner)); first full match wins.
_RULES: list[tuple[str, re.Pattern, object]] = []


def _rule(kind: str, pattern: str):
    def deco(fn):
        _RULES.append((kind, re.compile(pattern), fn))
        return fn

    return deco


@_rule("round", rf"r{NUM}")
def _round(g):
    return _f(g[0]), _f(g[0]), 0.0, 0.0


@_rule("square", rf"s{NUM}")
def _square(g):
    return _f(g[0]), _f(g[0]), 0.0, 0.0


@_rule("rect", rf"rect{NUM}x{NUM}")
def _rect(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("rounded_rect", rf"rect{NUM}x{NUM}xr{NUM}{_OPT_CORNERS}")
def _rrect(g):
    return _f(g[0]), _f(g[1]), _f(g[2]), 0.0


@_rule("chamfered_rect", rf"rect{NUM}x{NUM}xc{NUM}{_OPT_CORNERS}")
def _crect(g):
    return _f(g[0]), _f(g[1]), _f(g[2]), 0.0


@_rule("oval", rf"oval{NUM}x{NUM}")
def _oval(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("diamond", rf"di{NUM}x{NUM}")
def _diamond(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("octagon", rf"oct{NUM}x{NUM}x{NUM}")
def _oct(g):
    return _f(g[0]), _f(g[1]), _f(g[2]), 0.0


@_rule("donut_r", rf"donut_r{NUM}x{NUM}")
def _donut_r(g):
    return _f(g[0]), _f(g[0]), 0.0, _f(g[1])


@_rule("donut_s", rf"donut_s{NUM}x{NUM}(?:xr{NUM}{_OPT_CORNERS})?")
def _donut_s(g):
    return _f(g[0]), _f(g[0]), _f(g[2]), _f(g[1])


@_rule("donut_sr", rf"donut_sr{NUM}x{NUM}")
def _donut_sr(g):
    return _f(g[0]), _f(g[0]), 0.0, _f(g[1])


@_rule("donut_rc", rf"donut_rc{NUM}x{NUM}x{NUM}(?:xr{NUM}{_OPT_CORNERS})?")
def _donut_rc(g):
    return _f(g[0]), _f(g[1]), _f(g[3]), 0.0


@_rule("donut_o", rf"donut_o{NUM}x{NUM}x{NUM}")
def _donut_o(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("hex_l", rf"hex_l{NUM}x{NUM}x{NUM}")
def _hex_l(g):
    return _f(g[0]), _f(g[1]), _f(g[2]), 0.0


@_rule("hex_s", rf"hex_s{NUM}x{NUM}x{NUM}")
def _hex_s(g):
    return _f(g[0]), _f(g[1]), _f(g[2]), 0.0


@_rule("butterfly", rf"bfr{NUM}")
def _bfr(g):
    return _f(g[0]), _f(g[0]), 0.0, 0.0


@_rule("square_butterfly", rf"bfs{NUM}")
def _bfs(g):
    return _f(g[0]), _f(g[0]), 0.0, 0.0


@_rule("triangle", rf"tri{NUM}x{NUM}")
def _tri(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("half_oval", rf"oval_h{NUM}x{NUM}")
def _oval_h(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("round_thermal", rf"th[rs]{NUM}x{NUM}x{NUM}x{NUM}x{NUM}")
def _thr(g):
    return _f(g[0]), _f(g[0]), 0.0, _f(g[1])


@_rule("square_thermal", rf"s_th[sor]{NUM}x{NUM}x{NUM}x{NUM}x{NUM}(?:xr{NUM}{_OPT_CORNERS})?")
def _s_ths(g):
    return _f(g[0]), _f(g[0]), _f(g[5]), _f(g[1])


@_rule("square_round_thermal", rf"sr_ths{NUM}x{NUM}x{NUM}x{NUM}x{NUM}")
def _sr_ths(g):
    return _f(g[0]), _f(g[0]), 0.0, _f(g[1])


@_rule(
    "rect_thermal",
    rf"rc_th[so]{NUM}x{NUM}x{NUM}x{NUM}x{NUM}x{NUM}(?:xr{NUM}{_OPT_CORNERS})?",
)
def _rc_ths(g):
    return _f(g[0]), _f(g[1]), _f(g[6]), 0.0


@_rule("oval_thermal", rf"o_th[so]{NUM}x{NUM}x{NUM}x{NUM}x{NUM}x{NUM}")
def _o_ths(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("oblong_thermal", rf"oblong_ths{NUM}x{NUM}x{NUM}x{NUM}x{NUM}x{NUM}x[rs]")
def _oblong(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("ellipse", rf"el{NUM}x{NUM}")
def _el(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


@_rule("moire", rf"moire{NUM}x{NUM}x{NUM}x{NUM}x{NUM}x{NUM}")
def _moire(g):
    rw, rg, nr, _lw, ll = (_f(v) for v in g[:5])
    d = max(ll, 2 * nr * (rw + rg))
    return d, d, 0.0, 0.0


@_rule("hole", rf"hole{NUM}x[pnv]x{NUM}x{NUM}")
def _hole(g):
    return _f(g[0]), _f(g[0]), 0.0, 0.0


@_rule("null", rf"null{NUM}")
def _null(g):
    return 0.0, 0.0, 0.0, 0.0


# Stencil-design symbols of ODB++ 8.x: only the outer width and height are used.
@_rule(
    "stencil",
    rf"(?:hplate|rhplate|fhplate|radhplate|dshape|cross|dogbone|dpack){NUM}x{NUM}(?:x.*)?",
)
def _stencil(g):
    return _f(g[0]), _f(g[1]), 0.0, 0.0


_ROTATED = re.compile(rf"(.+)_{NUM}")


def parse_standard_symbol(name: str, size_scale: float) -> SymbolShape | None:
    """Return the shape for a standard symbol name, or ``None`` if it is not one.

    ``size_scale`` converts the symbol's dimension units (mils or microns) to mm.
    """
    low = name.strip().lower()
    for kind, pattern, fn in _RULES:
        m = pattern.fullmatch(low)
        if m:
            w, h, corner, inner = fn(m.groups())  # type: ignore[operator]
            return SymbolShape(
                name=name,
                kind=kind,
                width=w * size_scale,
                height=h * size_scale,
                corner=corner * size_scale,
                inner=inner * size_scale,
            )
    m = _ROTATED.fullmatch(low)
    if m:
        base = parse_standard_symbol(m.group(1), size_scale)
        if base is not None:
            base.name = name
            base.rotation = float(m.group(2)) % 360.0
            return base
    return None
