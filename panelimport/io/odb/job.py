"""High-level access to one ODB++ export.

Files are parsed on first use and cached.  Parse issues of every file that was read
are collected in :attr:`OdbJob.issues`; whether a *missing* file is an error depends on
what the analysis needs it for, so missing files are reported by the caller.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from panelimport.io.odb.archive import OdbOpenError, OdbReadError, OdbSource
from panelimport.io.odb.attributes import ATTRIBUTE_DEF_FILES, AttrDefs
from panelimport.io.odb.common import Units, UnitsDirective, parse_units
from panelimport.io.odb.components import ComponentFile, parse_components
from panelimport.io.odb.eda import EdaData, parse_eda
from panelimport.io.odb.features import FeatureFile, parse_features
from panelimport.io.odb.matrix import Matrix, MatrixLayer, parse_matrix
from panelimport.io.odb.stephdr import StepHeader, parse_stephdr
from panelimport.io.odb.structured import parse_structured
from panelimport.io.odb.symbols import SymbolShape
from panelimport.model.issues import Issue, error, info, warning

log = logging.getLogger("panelimport.odb")

__all__ = ["OdbJob", "OdbOpenError", "Profile", "JobInfo"]

INFO_FIELDS = frozenset(
    (
        "JOB_NAME",
        "ODB_VERSION_MAJOR",
        "ODB_VERSION_MINOR",
        "ODB_SOURCE",
        "CREATION_DATE",
        "SAVE_DATE",
        "SAVE_APP",
        "SAVE_USER",
        "UNITS",
        "MAX_UID",
    )
)


@dataclass
class JobInfo:
    fields: dict[str, str] = field(default_factory=dict)
    units: Units | None = None

    @property
    def version(self) -> str:
        major = self.fields.get("ODB_VERSION_MAJOR", "")
        minor = self.fields.get("ODB_VERSION_MINOR", "")
        return f"{major}.{minor}" if major else "unknown"

    @property
    def application(self) -> str:
        return self.fields.get("SAVE_APP") or self.fields.get("ODB_SOURCE") or "unknown"


@dataclass
class Profile:
    path: str
    outline: list[tuple[float, float]]  # largest island, mm
    islands: list[list[tuple[float, float]]]
    holes: list[list[tuple[float, float]]]

    @property
    def extent(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.outline]
        ys = [p[1] for p in self.outline]
        return min(xs), min(ys), max(xs), max(ys)


def polygon_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


_MISSING = object()


class OdbJob:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.source = OdbSource(self.path)
        self.issues: list[Issue] = []
        self.units_used: dict[str, UnitsDirective] = {}
        self._noted: set[str] = set()
        self._cache: dict[tuple, object] = {}
        self._sha256: str | None = None
        self._symbol_depth = 0

        self.info = self._read_info()
        self.default_units = self.info.units or Units.INCH
        matrix_text = self._read_text("matrix/matrix")
        if matrix_text is None:
            raise OdbOpenError(f"{self.path}: missing required file matrix/matrix")
        self.matrix, matrix_issues = parse_matrix(matrix_text, self.source.display_name("matrix/matrix"))
        self._note("matrix/matrix", matrix_issues)
        self.attr_defs = self._read_attr_defs()
        log.info(
            "Opened %s (%s): ODB++ %s from %s, default units %s, %d steps, %d layers",
            self.path,
            self.source.kind,
            self.info.version,
            self.info.application,
            self.default_units.value,
            len(self.matrix.steps),
            len(self.matrix.layers),
        )

    # ------------------------------------------------------------------ basics
    @property
    def name(self) -> str:
        return self.info.fields.get("JOB_NAME") or self.source.job_name

    @property
    def sha256(self) -> str:
        if self._sha256 is None:
            self._sha256 = self.source.sha256()
        return self._sha256

    @property
    def step_names(self) -> list[str]:
        return [s.name for s in self.matrix.steps]

    def _note(self, key: str, issues: list[Issue]) -> None:
        if key in self._noted:
            return
        self._noted.add(key)
        for issue in issues:
            log.warning("%s: %s", issue.file or key, issue.message)
        self.issues.extend(issues)

    def _read_text(self, rel: str) -> str | None:
        try:
            return self.source.read_text(rel)
        except OdbReadError as exc:
            self._note(
                f"read:{rel}",
                [error("read_error", f"Cannot read file: {exc.message}", file=exc.path, subject=exc.path)],
            )
            return None

    def _track_units(self, path: str, units: UnitsDirective) -> None:
        self.units_used[path] = units

    def _read_info(self) -> JobInfo:
        text = self._read_text("misc/info")
        if text is None:
            self._note(
                "misc/info",
                [error("missing_file", "Missing required file misc/info", file="misc/info", subject="misc/info")],
            )
            return JobInfo()
        doc = parse_structured(text)
        job_info = JobInfo(fields=dict(doc.fields))
        issues: list[Issue] = []
        if "UNITS" in doc.fields:
            u = parse_units(doc.fields["UNITS"])
            if u is None:
                issues.append(
                    error(
                        "unknown_units",
                        f"Unrecognized units '{doc.fields['UNITS']}'",
                        file="misc/info",
                        subject="misc/info:units",
                    )
                )
            job_info.units = u
        unknown = [k for k in doc.fields if k not in INFO_FIELDS]
        if unknown:
            issues.append(
                info(
                    "unknown_field",
                    f"Unrecognized field(s) in misc/info: {', '.join(sorted(unknown))}",
                    file="misc/info",
                    subject="misc/info",
                )
            )
        self._note("misc/info", issues)
        return job_info

    def _read_attr_defs(self) -> AttrDefs:
        files = []
        for rel in ATTRIBUTE_DEF_FILES:
            text = self._read_text(rel)
            if text is not None:
                files.append((self.source.display_name(rel), text))
        defs, issues = AttrDefs.parse(files)
        self._note("attrdefs", issues)
        return defs

    def _cached(self, key: tuple, loader):
        value = self._cache.get(key, _MISSING)
        if value is _MISSING:
            value = loader()
            self._cache[key] = value
        return value

    # ------------------------------------------------------------------ steps
    def step_exists(self, step: str) -> bool:
        return self.source.exists(f"steps/{step}/stephdr") or bool(self.source.listdir(f"steps/{step}"))

    def stephdr(self, step: str) -> StepHeader | None:
        def load() -> StepHeader | None:
            rel = f"steps/{step}/stephdr"
            text = self._read_text(rel)
            if text is None:
                return None
            path = self.source.display_name(rel)
            hdr, issues = parse_stephdr(text, path, self.default_units)
            self._track_units(path, hdr.units)
            self._note(rel, issues)
            return hdr

        return self._cached(("stephdr", step.lower()), load)

    def profile(self, step: str) -> Profile | None:
        def load() -> Profile | None:
            rel = f"steps/{step}/profile"
            text = self._read_text(rel)
            if text is None:
                return None
            path = self.source.display_name(rel)
            ff, problems = parse_features(text, path, self.default_units, self.user_symbol)
            self._track_units(path, ff.units)
            issues = problems.to_issues()
            islands = [c.points for s in ff.surfaces for c in s.contours if c.island and len(c.points) >= 3]
            holes = [c.points for s in ff.surfaces for c in s.contours if not c.island and len(c.points) >= 3]
            if not islands:
                issues.append(
                    error(
                        "empty_profile",
                        f"Profile of step '{step}' has no closed outline",
                        file=path,
                        subject=path,
                    )
                )
                self._note(rel, issues)
                return None
            islands.sort(key=polygon_area, reverse=True)
            if len(islands) > 1:
                issues.append(
                    info(
                        "profile_islands",
                        f"Profile of step '{step}' has {len(islands)} islands; the largest is the outline",
                        file=path,
                        subject=path,
                    )
                )
            self._note(rel, issues)
            return Profile(path=path, outline=islands[0], islands=islands, holes=holes)

        return self._cached(("profile", step.lower()), load)

    # ------------------------------------------------------------------ layers
    def layer_exists(self, step: str, layer: str) -> bool:
        return self.source.exists(f"steps/{step}/layers/{layer}/features")

    def features(self, step: str, layer: str) -> FeatureFile | None:
        def load() -> FeatureFile | None:
            rel = f"steps/{step}/layers/{layer}/features"
            text = self._read_text(rel)
            if text is None:
                return None
            path = self.source.display_name(rel)
            ff, problems = parse_features(text, path, self.default_units, self.user_symbol)
            self._track_units(path, ff.units)
            self._note(rel, problems.to_issues())
            log.info("Read %s: %d features", path, ff.feature_count)
            return ff

        return self._cached(("features", step.lower(), layer.lower()), load)

    def component_layers(self) -> dict[str, MatrixLayer]:
        """The matrix COMPONENT layers keyed by side ("top"/"bottom")."""
        comps = [layer for layer in self.matrix.layers if layer.type == "COMPONENT"]
        out: dict[str, MatrixLayer] = {}
        for layer in comps:
            if layer.key == "comp_+_top":
                out["top"] = layer
            elif layer.key == "comp_+_bot":
                out["bottom"] = layer
        rest = [layer for layer in comps if layer not in out.values()]
        if rest and ("top" not in out or "bottom" not in out):
            # Fall back to stack-up order: the first component layer is the top side.
            for layer in rest:
                side = "top" if "top" not in out else "bottom" if "bottom" not in out else None
                if side:
                    out[side] = layer
        return out

    def components(self, step: str, layer: str) -> ComponentFile | None:
        def load() -> ComponentFile | None:
            rel = f"steps/{step}/layers/{layer}/components"
            text = self._read_text(rel)
            if text is None:
                return None
            path = self.source.display_name(rel)
            cf, problems = parse_components(text, path, self.default_units, self.attr_defs)
            self._track_units(path, cf.units)
            self._note(rel, problems.to_issues())
            log.info("Read %s: %d components", path, len(cf.components))
            return cf

        return self._cached(("components", step.lower(), layer.lower()), load)

    def eda(self, step: str) -> EdaData | None:
        def load() -> EdaData | None:
            rel = f"steps/{step}/eda/data"
            text = self._read_text(rel)
            if text is None:
                return None
            path = self.source.display_name(rel)
            data, problems = parse_eda(text, path, self.default_units)
            self._track_units(path, data.units)
            self._note(rel, problems.to_issues())
            log.info("Read %s: %d packages", path, len(data.packages))
            return data

        return self._cached(("eda", step.lower()), load)

    # ------------------------------------------------------------------ symbols
    def user_symbol(self, name: str) -> SymbolShape | None:
        """A user-defined symbol from ``symbols/<name>/features``."""

        def load() -> SymbolShape | None:
            rel = f"symbols/{name}/features"
            if not self.source.exists(rel) or self._symbol_depth > 4:
                return None
            text = self._read_text(rel)
            if text is None:
                return None
            path = self.source.display_name(rel)
            self._symbol_depth += 1
            try:
                ff, problems = parse_features(text, path, self.default_units, self.user_symbol)
            finally:
                self._symbol_depth -= 1
            self._track_units(path, ff.units)
            self._note(rel, problems.to_issues())
            extent = ff.extent()
            if extent is None:
                return SymbolShape(name=name, kind="user", width=0.0, height=0.0, standard=False, extent=(0, 0, 0, 0))
            polygons = [c.points for s in ff.surfaces if s.positive for c in s.contours if c.island]
            for p in ff.pads:
                ex = ff.symbol(p.sym).local_extent()
                polygons.append(
                    [
                        (p.x + ex[0], p.y + ex[1]),
                        (p.x + ex[2], p.y + ex[1]),
                        (p.x + ex[2], p.y + ex[3]),
                        (p.x + ex[0], p.y + ex[3]),
                    ]
                )
            return SymbolShape(
                name=name,
                kind="user",
                width=extent[2] - extent[0],
                height=extent[3] - extent[1],
                standard=False,
                extent=extent,
                polygons=polygons,
            )

        return self._cached(("symbol", name.lower()), load)

    # ------------------------------------------------------------------ units summary
    def units_issues(self) -> list[Issue]:
        """One issue summarising files that relied on the default units."""
        assumed = sorted(p for p, u in self.units_used.items() if not u.declared)
        if not assumed:
            return []
        declared_units = {u.units for u in self.units_used.values() if u.declared}
        default = self.default_units
        source = "misc/info UNITS" if self.info.units else "ODB++ default for files without a UNITS directive"
        listed = ", ".join(assumed[:5]) + (f" and {len(assumed) - 5} more" if len(assumed) > 5 else "")
        if declared_units - {default}:
            return [
                warning(
                    "units_assumed",
                    f"{len(assumed)} file(s) declare no units and were read as {default.value} ({source}), "
                    f"while other files declare {', '.join(sorted(u.value for u in declared_units))}: {listed}",
                    subject="units",
                    data={"files": assumed},
                )
            ]
        return [
            info(
                "units_assumed",
                f"{len(assumed)} file(s) declare no units and were read as {default.value} ({source}): {listed}",
                subject="units",
                data={"files": assumed},
            )
        ]
