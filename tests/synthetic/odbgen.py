"""Builder for minimal synthetic ODB++ jobs, written for tests.

The builder writes the same files a real export has (matrix, misc/info, stephdr,
profile, layer features, components, eda/data) in MM or INCH, optionally with
``.Z``-compressed members, as a folder, ``.tgz`` or ``.zip``.

Geometry follows the ODB++ conventions independently of ``panelimport``: rotations
are clockwise, mirroring negates X and is applied after rotation, and STEP-REPEAT
places the child step's datum at ``X + i*DX, Y + j*DY``.
"""

from __future__ import annotations

import io
import math
import random
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from tests.synthetic.lzw import compress

MM_PER_INCH = 25.4


def fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def rot_cw(x: float, y: float, deg: float) -> tuple[float, float]:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return x * c + y * s, -x * s + y * c


def place(px: float, py: float, x: float, y: float, rot: float, mirror: bool) -> tuple[float, float]:
    """Package/child point -> parent: rotate clockwise, then mirror X, then translate."""
    rx, ry = rot_cw(px, py, rot)
    if mirror:
        rx = -rx
    return x + rx, y + ry


# ---------------------------------------------------------------------------- packages
@dataclass
class Land:
    name: str
    x: float
    y: float
    w: float
    h: float
    round: bool = False
    paste: bool = True  # SMT lands get paste; through-hole lands do not


@dataclass
class PackageDef:
    name: str
    lands: list[Land]
    body_w: float
    body_h: float


def _soic(name: str, n: int, pitch: float = 1.27, span: float = 5.4) -> PackageDef:
    half = n // 2
    lands = []
    for i in range(half):
        x = (i - (half - 1) / 2) * pitch
        lands.append(Land(str(i + 1), x, -span / 2, 0.6, 1.5))
    for i in range(half):
        x = ((half - 1) / 2 - i) * pitch
        lands.append(Land(str(half + i + 1), x, span / 2, 0.6, 1.5))
    return PackageDef(name, lands, (half - 1) * pitch + 1.5, span - 1.5)


PACKAGES: dict[str, PackageDef] = {
    "C0603": PackageDef("C0603", [Land("1", -0.8, 0, 0.9, 0.95), Land("2", 0.8, 0, 0.9, 0.95)], 1.6, 0.8),
    "R0402": PackageDef("R0402", [Land("1", -0.5, 0, 0.6, 0.6), Land("2", 0.5, 0, 0.6, 0.6)], 1.0, 0.5),
    "SOT23": PackageDef(
        "SOT23",
        [Land("1", -0.95, -1.0, 0.6, 0.7), Land("2", 0.95, -1.0, 0.6, 0.7), Land("3", 0.0, 1.0, 0.6, 0.7)],
        2.9,
        1.3,
    ),
    "SOIC8": _soic("SOIC8", 8),
    "HDR2": PackageDef(
        "HDR2",
        [Land("1", -1.27, 0, 1.7, 1.7, round=True, paste=False), Land("2", 1.27, 0, 1.7, 1.7, round=True, paste=False)],
        5.08,
        2.54,
    ),
    "FID1MM": PackageDef("FID1MM", [Land("1", 0, 0, 1.0, 1.0, round=True, paste=False)], 2.0, 2.0),
}


# ---------------------------------------------------------------------------- features
@dataclass
class PadF:
    x: float
    y: float
    shape: str  # "round" | "rect"
    w: float
    h: float
    rot: float = 0.0
    mirror: bool = False
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class LineF:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float


@dataclass
class SurfaceF:
    points: list[tuple[float, float]]


@dataclass
class CompDef:
    name: str
    pkg: str
    x: float
    y: float
    rot: float = 0.0
    side: str = "top"
    part: str = "PART"
    props: dict[str, str] = field(default_factory=dict)
    attrs: dict[str, str | bool] = field(default_factory=dict)


@dataclass
class Repeat:
    name: str
    x: float
    y: float
    dx: float
    dy: float
    nx: int
    ny: int
    angle: float = 0.0
    mirror: bool = False
    flip: bool = False


LAYERS: list[tuple[str, str, str]] = [
    # (name, type, context)
    ("comp_+_top", "COMPONENT", "BOARD"),
    ("top_paste", "SOLDER_PASTE", "BOARD"),
    ("top_mask", "SOLDER_MASK", "BOARD"),
    ("top_copper", "SIGNAL", "BOARD"),
    ("bottom_copper", "SIGNAL", "BOARD"),
    ("bottom_mask", "SOLDER_MASK", "BOARD"),
    ("bottom_paste", "SOLDER_PASTE", "BOARD"),
    ("comp_+_bot", "COMPONENT", "BOARD"),
    ("board_outline", "ROUT", "BOARD"),
]
# OPTION-type component attributes are written as option indices.
COMPONENT_OPTIONS = {".comp_mount_type": ["other", "smt", "thmt", "pressfit"]}
# FLOAT component attributes that are lengths: given in mm, written in the job's units.
COMPONENT_LENGTHS = {".comp_height"}
SIDE_LAYERS = {
    "top": ("top_paste", "top_copper", "top_mask"),
    "bottom": ("bottom_paste", "bottom_copper", "bottom_mask"),
}


class Step:
    def __init__(
        self,
        job: Job,
        name: str,
        profile: list[tuple[float, float]],
        datum: tuple[float, float] = (0.0, 0.0),
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.job = job
        self.name = name
        self.profile = profile
        self.datum = datum
        self.origin = origin
        self.components: list[CompDef] = []
        self.pads: dict[str, list[PadF]] = {}
        self.lines: dict[str, list[LineF]] = {}
        self.surfaces: dict[str, list[SurfaceF]] = {}
        self.repeats: list[Repeat] = []

    # -------------------------------------------------------------- primitives
    def pad(self, layer: str, x: float, y: float, shape: str, w: float, h: float | None = None, **kw) -> PadF:
        p = PadF(x, y, shape, w, w if h is None else h, **kw)
        self.pads.setdefault(layer, []).append(p)
        return p

    def line(self, layer: str, x1: float, y1: float, x2: float, y2: float, width: float) -> None:
        self.lines.setdefault(layer, []).append(LineF(x1, y1, x2, y2, width))

    def surface(self, layer: str, points: list[tuple[float, float]]) -> None:
        self.surfaces.setdefault(layer, []).append(SurfaceF(points))

    def outline_rect(self, layer: str, x0: float, y0: float, x1: float, y1: float, width: float = 0.2) -> None:
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            self.line(layer, a[0], a[1], b[0], b[1], width)

    def step_repeat(self, name: str, x: float, y: float, dx: float, dy: float, nx: int, ny: int, **kw) -> Repeat:
        rep = Repeat(name, x, y, dx, dy, nx, ny, **kw)
        self.repeats.append(rep)
        return rep

    # -------------------------------------------------------------- components
    def land_positions(self, comp: CompDef) -> list[tuple[Land, float, float]]:
        pkg = PACKAGES[comp.pkg]
        mirror = comp.side == "bottom"
        return [(land, *place(land.x, land.y, comp.x, comp.y, comp.rot, mirror)) for land in pkg.lands]

    def component(
        self,
        name: str,
        pkg: str,
        x: float,
        y: float,
        rot: float = 0.0,
        side: str = "top",
        part: str | None = None,
        *,
        paste: bool = True,
        copper: bool = True,
        mask: bool = True,
        paste_offset: tuple[float, float] = (0.0, 0.0),
        **kw,
    ) -> CompDef:
        comp = CompDef(name, pkg, x, y, rot, side, part or f"P-{pkg}", **kw)
        self.components.append(comp)
        paste_layer, copper_layer, mask_layer = SIDE_LAYERS[side]
        mirror = side == "bottom"
        for land, lx, ly in self.land_positions(comp):
            shape = "round" if land.round else "rect"
            if copper:
                self.pad(copper_layer, lx, ly, shape, land.w, land.h, rot=comp.rot, mirror=mirror)
            if mask:
                self.pad(mask_layer, lx, ly, shape, land.w + 0.1, land.h + 0.1, rot=comp.rot, mirror=mirror)
            if paste and land.paste:
                self.pad(
                    paste_layer,
                    lx + paste_offset[0],
                    ly + paste_offset[1],
                    shape,
                    land.w * 0.9,
                    land.h * 0.9,
                    rot=comp.rot,
                    mirror=mirror,
                )
        return comp

    def fiducial_feature(self, x: float, y: float, side: str = "top", attr: bool = True, d: float = 1.0) -> None:
        """A fiducial drawn only as copper + mask opening (no component)."""
        _paste, copper_layer, mask_layer = SIDE_LAYERS[side]
        attrs = {".pad_usage": "g_fiducial"} if attr else {}
        self.pad(copper_layer, x, y, "round", d, attrs=attrs)
        self.pad(mask_layer, x, y, "round", d * 2)


class Job:
    def __init__(
        self,
        name: str = "synthetic",
        units: str = "MM",
        version: tuple[int, int] = (8, 1),
        units_style: str = "UNITS=",  # "UNITS=" | "U" | "none"
        compress_members: bool = False,
        layers: list[tuple[str, str, str]] | None = None,
    ) -> None:
        assert units in ("MM", "INCH")
        self.name = name
        self.units = units
        self.version = version
        self.units_style = units_style
        self.compress_members = compress_members
        self.layers = list(layers or LAYERS)
        self.steps: dict[str, Step] = {}
        self.extra_files: dict[str, str] = {}

    # -------------------------------------------------------------- building
    def step(self, name: str, width: float, height: float, x0: float = 0.0, y0: float = 0.0, **kw) -> Step:
        profile = [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height)]
        st = Step(self, name, profile, **kw)
        self.steps[name] = st
        return st

    # -------------------------------------------------------------- units
    def c(self, v: float) -> str:
        """Coordinate in the job units."""
        return fmt(v / MM_PER_INCH if self.units == "INCH" else v)

    def sym_size(self, v: float) -> str:
        """Symbol dimension: microns (MM) or mils (INCH)."""
        return fmt(v * 1000.0 if self.units == "MM" else v / MM_PER_INCH * 1000.0)

    def units_line(self, kind: str) -> str:
        if self.units_style == "none":
            return ""
        if kind == "features" and self.units_style == "U":
            return f"U {self.units}\n"
        return f"UNITS={self.units}\n"

    # -------------------------------------------------------------- writers
    def _features_text(self, pads: list[PadF], lines: list[LineF], surfaces: list[SurfaceF]) -> str:
        symbols: dict[str, int] = {}

        def sym(name: str) -> int:
            return symbols.setdefault(name, len(symbols))

        attr_names: dict[str, int] = {}
        attr_texts: dict[str, int] = {}
        body = []
        for p in pads:
            if p.shape == "round":
                sname = f"r{self.sym_size(p.w)}"
            else:
                sname = f"rect{self.sym_size(p.w)}x{self.sym_size(p.h)}"
            orient = f"{9 if p.mirror else 8} {fmt(p.rot % 360)}"
            attrs = ""
            if p.attrs:
                parts = []
                for k, v in p.attrs.items():
                    idx = attr_names.setdefault(k, len(attr_names))
                    if k == ".pad_usage":
                        options = ["toeprint", "via", "g_fiducial", "l_fiducial", "tooling_hole", "bond_finger"]
                        parts.append(f"{idx}={options.index(v)}")
                    else:
                        parts.append(f"{idx}={attr_texts.setdefault(v, len(attr_texts))}")
                attrs = ";" + ",".join(parts)
            body.append(f"P {self.c(p.x)} {self.c(p.y)} {sym(sname)} P 0 {orient}{attrs}")
        for ln in lines:
            body.append(
                f"L {self.c(ln.x1)} {self.c(ln.y1)} {self.c(ln.x2)} {self.c(ln.y2)} "
                f"{sym('r' + self.sym_size(ln.width))} P 0"
            )
        for s in surfaces:
            pts = list(s.points)
            # islands are clockwise in ODB++
            area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
            if area > 0:
                pts = pts[::-1]
            body.append("S P 0")
            body.append(f"OB {self.c(pts[0][0])} {self.c(pts[0][1])} I")
            for x, y in pts[1:] + pts[:1]:
                body.append(f"OS {self.c(x)} {self.c(y)}")
            body.append("OE")
            body.append("SE")
        head = ["#", "#Units", "#", self.units_line("features").rstrip("\n")]
        head += ["#", "#Num Features", "#", f"F {len(pads) + len(lines) + len(surfaces)}", "#", "#Feature symbol names", "#"]
        head += [f"${i} {n}" for n, i in symbols.items()]
        if attr_names:
            head += ["#", "#Feature attribute names", "#"]
            head += [f"@{i} {n}" for n, i in attr_names.items()]
        if attr_texts:
            head += ["#", "#Feature attribute text strings", "#"]
            head += [f"&{i} {t}" for t, i in attr_texts.items()]
        head += ["#", "#Layer features", "#"]
        return "\n".join(line for line in head if line != "") + "\n" + "\n".join(body) + "\n"

    def _components_text(self, step: Step, side: str, pkg_index: dict[str, int]) -> str:
        comps = [c for c in step.components if c.side == side]
        attr_names: dict[str, int] = {}
        attr_texts: dict[str, int] = {}
        recs = []
        for i, comp in enumerate(comps):
            attrs = ""
            if comp.attrs:
                parts = []
                for k, v in comp.attrs.items():
                    idx = attr_names.setdefault(k, len(attr_names))
                    if v is True:  # boolean attribute: present, no value
                        parts.append(f"{idx}")
                    elif k in COMPONENT_OPTIONS:
                        parts.append(f"{idx}={COMPONENT_OPTIONS[k].index(v)}")
                    elif k in COMPONENT_LENGTHS:
                        parts.append(f"{idx}={self.c(float(v))}")
                    else:
                        parts.append(f"{idx}={attr_texts.setdefault(v, len(attr_texts))}")
                attrs = ";" + ",".join(parts)
            mirror = "M" if side == "bottom" else "N"
            recs.append(f"# CMP {i}")
            recs.append(
                f"CMP {pkg_index[comp.pkg]} {self.c(comp.x)} {self.c(comp.y)} {fmt(comp.rot % 360)} "
                f"{mirror} {comp.name} {comp.part}{attrs}"
            )
            for k, v in comp.props.items():
                recs.append(f"PRP {k} '{v}'")
            for n, (land, lx, ly) in enumerate(step.land_positions(comp)):
                recs.append(f"TOP {n} {self.c(lx)} {self.c(ly)} {fmt(comp.rot % 360)} {mirror} 0 {i * 10 + n} {land.name}")
            recs.append("#")
        head = [self.units_line("components").rstrip("\n"), "#", "#Component attribute names", "#"]
        head += [f"@{i} {n}" for n, i in attr_names.items()]
        if attr_texts:
            head += ["#", "#Component attribute text strings", "#"]
            head += [f"&{i} {t}" for t, i in attr_texts.items()]
        return "\n".join(line for line in head if line != "") + "\n" + "\n".join(recs) + "\n"

    def _eda_text(self, pkgs: list[str]) -> str:
        out = ["#", "HDR Synthetic test generator"]
        if self.units_style != "none":
            out.append(f"UNITS={self.units}")
        out.append("LYR " + " ".join(n for n, t, _c in self.layers if t in ("SIGNAL", "SOLDER_MASK", "SOLDER_PASTE")))
        out.append("#")
        out.append("NET $NONE$")
        for name in pkgs:
            pkg = PACKAGES[name]
            xs = [land.x - land.w / 2 for land in pkg.lands] + [land.x + land.w / 2 for land in pkg.lands]
            ys = [land.y - land.h / 2 for land in pkg.lands] + [land.y + land.h / 2 for land in pkg.lands]
            xmin = min(xs + [-pkg.body_w / 2])
            xmax = max(xs + [pkg.body_w / 2])
            ymin = min(ys + [-pkg.body_h / 2])
            ymax = max(ys + [pkg.body_h / 2])
            pitch = min(
                (math.hypot(a.x - b.x, a.y - b.y) for a in pkg.lands for b in pkg.lands if a is not b),
                default=0.0,
            )
            out.append(f"# PKG {name}")
            out.append(f"PKG {name} {self.c(pitch)} {self.c(xmin)} {self.c(ymin)} {self.c(xmax)} {self.c(ymax)}")
            out.append(
                f"RC {self.c(-pkg.body_w / 2)} {self.c(-pkg.body_h / 2)} {self.c(pkg.body_w)} {self.c(pkg.body_h)}"
            )
            for land in pkg.lands:
                ptype = "T" if not land.paste else "S"
                out.append(f"PIN {land.name} {ptype} {self.c(land.x)} {self.c(land.y)} 0 E {'T' if ptype == 'T' else 'S'}")
                if land.round:
                    out.append(f"CR {self.c(land.x)} {self.c(land.y)} {self.c(land.w / 2)}")
                else:
                    out.append(
                        f"RC {self.c(land.x - land.w / 2)} {self.c(land.y - land.h / 2)} {self.c(land.w)} {self.c(land.h)}"
                    )
        return "\n".join(out) + "\n"

    def files(self) -> dict[str, bytes]:
        """All job files keyed by job-relative path."""
        files: dict[str, str] = {}
        info = [
            f"JOB_NAME={self.name}",
            f"ODB_VERSION_MAJOR={self.version[0]}",
            f"ODB_VERSION_MINOR={self.version[1]}",
            "ODB_SOURCE=Synthetic",
            "CREATION_DATE=20261013.120000",
            "SAVE_DATE=20261013.120000",
            "SAVE_APP=panelimport test generator",
            "SAVE_USER=test",
        ]
        if self.version[0] >= 8 and self.units_style != "none":
            info.append(f"UNITS={self.units}")
        files["misc/info"] = "\n".join(info) + "\n"

        matrix = []
        for col, name in enumerate(self.steps, start=1):
            matrix += ["STEP {", f"   COL={col}", f"   NAME={name.upper()}", "}", ""]
        for row, (name, ltype, ctx) in enumerate(self.layers, start=1):
            matrix += [
                "LAYER {",
                f"   ROW={row}",
                f"   CONTEXT={ctx}",
                f"   TYPE={ltype}",
                f"   NAME={name.upper()}",
                "   POLARITY=POSITIVE",
                "   START_NAME=",
                "   END_NAME=",
                "   OLD_NAME=",
                "   ADD_TYPE=",
                "   COLOR=0",
                "}",
                "",
            ]
        files["matrix/matrix"] = "\n".join(matrix)

        for sname, st in self.steps.items():
            base = f"steps/{sname}"
            hdr = []
            if self.units_style != "none":
                hdr.append(f"UNITS={self.units}")
            hdr += [
                f"X_DATUM={self.c(st.datum[0])}",
                f"Y_DATUM={self.c(st.datum[1])}",
                f"X_ORIGIN={self.c(st.origin[0])}",
                f"Y_ORIGIN={self.c(st.origin[1])}",
            ]
            for rep in st.repeats:
                hdr += [
                    "STEP-REPEAT {",
                    f"   NAME={rep.name.upper()}",
                    f"   X={self.c(rep.x)}",
                    f"   Y={self.c(rep.y)}",
                    f"   DX={self.c(rep.dx)}",
                    f"   DY={self.c(rep.dy)}",
                    f"   NX={rep.nx}",
                    f"   NY={rep.ny}",
                    f"   ANGLE={fmt(rep.angle)}",
                    f"   FLIP={'YES' if rep.flip else 'NO'}",
                    f"   MIRROR={'YES' if rep.mirror else 'NO'}",
                    "}",
                ]
            hdr += ["TOP_ACTIVE=0", "BOTTOM_ACTIVE=0", "RIGHT_ACTIVE=0", "LEFT_ACTIVE=0", "AFFECTING_BOM=", "AFFECTING_BOM_CHANGED=0"]
            files[f"{base}/stephdr"] = "\n".join(hdr) + "\n"
            files[f"{base}/profile"] = self._features_text([], [], [SurfaceF(st.profile)])

            used_pkgs = sorted({c.pkg for c in st.components})
            pkg_index = {name: i for i, name in enumerate(used_pkgs)}
            files[f"{base}/eda/data"] = self._eda_text(used_pkgs)
            for lname, ltype, _ctx in self.layers:
                lbase = f"{base}/layers/{lname}"
                if ltype == "COMPONENT":
                    side = "top" if "top" in lname else "bottom"
                    files[f"{lbase}/components"] = self._components_text(st, side, pkg_index)
                    files[f"{lbase}/features"] = self._features_text([], [], [])
                else:
                    files[f"{lbase}/features"] = self._features_text(
                        st.pads.get(lname, []), st.lines.get(lname, []), st.surfaces.get(lname, [])
                    )
        files.update(self.extra_files)

        out: dict[str, bytes] = {}
        for rel, text in files.items():
            data = text.encode("utf-8")
            leaf = rel.rsplit("/", 1)[-1]
            if self.compress_members and leaf in ("features", "components", "data"):
                out[rel + ".Z"] = compress(data)
            else:
                out[rel] = data
        return out

    def write_folder(self, parent: Path) -> Path:
        root = Path(parent) / self.name
        for rel, data in self.files().items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return root

    def write_tgz(self, path: Path) -> Path:
        path = Path(path)
        with tarfile.open(path, "w:gz") as tar:
            for rel, data in self.files().items():
                ti = tarfile.TarInfo(f"{self.name}/{rel}")
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
        return path

    def write_zip(self, path: Path) -> Path:
        path = Path(path)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, data in self.files().items():
                zf.writestr(f"{self.name}/{rel}", data)
        return path

    # -------------------------------------------------------------- flattening
    def flatten(self, panel_name: str, *, suffix: str | None = None, keep_repeats: bool = False) -> None:
        """Copy every board instance's components and features into the panel step.

        ``suffix`` is a format string such as ``"_{n}"`` appended to designators (copy n
        counts instances in STEP-REPEAT order, starting at 1).
        """
        panel = self.steps[panel_name]
        n = 0
        for rep in list(panel.repeats):
            board = self.steps[rep.name]
            if board.repeats:
                raise NotImplementedError("flatten() handles one level of repeats")
            for j in range(rep.ny):
                for i in range(rep.nx):
                    n += 1
                    ox, oy = rep.x + i * rep.dx, rep.y + j * rep.dy

                    def tf(x: float, y: float) -> tuple[float, float]:
                        return place(x - board.datum[0], y - board.datum[1], ox, oy, rep.angle, rep.mirror)

                    for comp in board.components:
                        x, y = tf(comp.x, comp.y)
                        name = comp.name + (suffix.format(n=n) if suffix else "")
                        panel.components.append(
                            CompDef(
                                name,
                                comp.pkg,
                                x,
                                y,
                                (comp.rot + rep.angle) % 360,
                                comp.side,
                                comp.part,
                                dict(comp.props),
                                dict(comp.attrs),
                            )
                        )
                    for layer, pads in board.pads.items():
                        for p in pads:
                            x, y = tf(p.x, p.y)
                            panel.pads.setdefault(layer, []).append(
                                PadF(x, y, p.shape, p.w, p.h, (p.rot + rep.angle) % 360, p.mirror ^ rep.mirror, dict(p.attrs))
                            )
                    for layer, lines in board.lines.items():
                        for ln in lines:
                            a = tf(ln.x1, ln.y1)
                            b = tf(ln.x2, ln.y2)
                            panel.lines.setdefault(layer, []).append(LineF(a[0], a[1], b[0], b[1], ln.width))
                    # board outline drawn on the outline layer, as a flattened export would
                    pts = [tf(x, y) for x, y in board.profile]
                    for a, b in zip(pts, pts[1:] + pts[:1]):
                        panel.lines.setdefault("board_outline", []).append(LineF(a[0], a[1], b[0], b[1], 0.2))
        if not keep_repeats:
            panel.repeats = []


# ---------------------------------------------------------------------------- factories
def populate_board(step: Step, n_parts: int, seed: int = 0, bottom_every: int = 0, margin: float = 3.0) -> None:
    """Place ``n_parts`` parts on a grid inside the step profile (deterministic)."""
    rng = random.Random(seed)
    xs = [p[0] for p in step.profile]
    ys = [p[1] for p in step.profile]
    x0, x1, y0, y1 = min(xs) + margin, max(xs) - margin, min(ys) + margin, max(ys) - margin
    cell = 4.0
    cols = max(1, int((x1 - x0) // cell))
    rows = max(1, int((y1 - y0) // cell))
    if n_parts > cols * rows:
        cell = math.sqrt((x1 - x0) * (y1 - y0) / n_parts) * 0.98
        cols = max(1, int((x1 - x0) // cell))
        rows = max(1, int((y1 - y0) // cell))
    kinds = ["C0603", "R0402", "SOT23", "C0603", "R0402"]
    prefix = {"C0603": "C", "R0402": "R", "SOT23": "Q"}
    count = {"C": 0, "R": 0, "Q": 0}
    for c in step.components:
        for p in count:
            if c.name.startswith(p) and c.name[1:].isdigit():
                count[p] = max(count[p], int(c.name[1:]))
    occupied = [(c.x, c.y) for c in step.components]
    placed = 0
    for k in range(cols * rows):
        if placed >= n_parts:
            break
        cx = x0 + (k % cols + 0.5) * cell
        cy = y0 + (k // cols + 0.5) * cell
        if any(math.hypot(cx - ox, cy - oy) < 6.5 for ox, oy in occupied):
            continue
        pkg = kinds[rng.randrange(len(kinds))] if cell >= 3.5 else rng.choice(["C0603", "R0402"])
        p = prefix[pkg]
        count[p] += 1
        side = "bottom" if bottom_every and placed % bottom_every == bottom_every - 1 else "top"
        step.component(f"{p}{count[p]}", pkg, round(cx, 4), round(cy, 4), rot=rng.choice([0, 90, 180, 270]), side=side)
        placed += 1


def add_copper(step: Step, n_traces: int, seed: int = 0, pours: int = 2) -> None:
    """Realistic copper load: random short traces and a few large pours with many vertices."""
    rng = random.Random(seed)
    xs = [p[0] for p in step.profile]
    ys = [p[1] for p in step.profile]
    x0, x1, y0, y1 = min(xs) + 1, max(xs) - 1, min(ys) + 1, max(ys) - 1
    for _ in range(n_traces):
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        dx, dy = rng.choice([(1, 0), (0, 1), (1, 1), (1, -1)])
        length = rng.uniform(0.5, 4.0)
        step.line("top_copper", x, y, min(x1, x + dx * length), max(y0, min(y1, y + dy * length)), rng.choice([0.15, 0.2, 0.3]))
    for k in range(pours):
        cx, cy = rng.uniform(x0, x1), rng.uniform(y0, y1)
        r = min(x1 - x0, y1 - y0) * 0.2
        pts = []
        for i in range(400):
            t = 2 * math.pi * i / 400
            rr = r * (0.8 + 0.2 * math.sin(7 * t + k))
            pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
        step.surface("top_copper", pts)


def sr_panel(
    *,
    units: str = "MM",
    nx: int = 3,
    ny: int = 2,
    dx: float = 52.0,
    dy: float = 38.5,
    board_w: float = 50.0,
    board_h: float = 36.5,
    origin: tuple[float, float] = (5.0, 5.0),
    n_parts: int = 12,
    with_fiducials: bool = True,
    **job_kw,
) -> Job:
    """A panel step with one STEP-REPEAT block of a populated board step."""
    job = Job(units=units, **job_kw)
    board = job.step("pcb", board_w, board_h)
    board.component("U1", "SOIC8", 15.0, 18.0, rot=0, part="IC-555")
    board.component("C1", "C0603", 25.0, 10.0, rot=90, part="CAP-100N", props={"PART_NUMBER": "D-1001"})
    board.component("R1", "R0402", 30.0, 25.0, rot=0, part="RES-10K", props={"PART_NUMBER": "D-2002"})
    board.component("J1", "HDR2", 40.0, 30.0, rot=0, part="HDR-2")
    board.component("C2", "C0603", 10.0, 30.0, rot=180, side="bottom", part="CAP-1U")
    populate_board(board, max(0, n_parts - 5), seed=7)
    width = origin[0] * 2 + (nx - 1) * dx + board_w
    height = origin[1] * 2 + (ny - 1) * dy + board_h
    panel = job.step("panel", width, height)
    panel.step_repeat("pcb", origin[0], origin[1], dx, dy, nx, ny)
    if with_fiducials:
        panel.component("FID1", "FID1MM", 2.5, 2.5, part="FIDUCIAL")
        panel.component("FID2", "FID1MM", width - 2.5, 2.5, part="FIDUCIAL")
        panel.component("FID3", "FID1MM", 2.5, height - 2.5, part="FIDUCIAL")
    return job
