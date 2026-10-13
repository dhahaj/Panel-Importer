"""Parser for ``matrix/matrix``: the steps (columns) and layers (rows) of the job."""

from __future__ import annotations

from dataclasses import dataclass

from panelimport.io.odb.common import unknown_field_issue
from panelimport.io.odb.structured import parse_structured
from panelimport.model.issues import Issue, error, warning

STEP_FIELDS = frozenset(("COL", "NAME", "ID"))
LAYER_FIELDS = frozenset(
    (
        "ROW",
        "CONTEXT",
        "TYPE",
        "NAME",
        "POLARITY",
        "START_NAME",
        "END_NAME",
        "OLD_NAME",
        "ADD_TYPE",
        "COLOR",
        "ID",
        "REF",
        "FORM",
        "DIELECTRIC_TYPE",
        "DIELECTRIC_NAME",
        "CU_TOP",
        "CU_BOTTOM",
    )
)
LAYER_TYPES = frozenset(
    (
        "SIGNAL",
        "POWER_GROUND",
        "DIELECTRIC",
        "MIXED",
        "SOLDER_MASK",
        "SOLDER_PASTE",
        "SILK_SCREEN",
        "DRILL",
        "ROUT",
        "DOCUMENT",
        "COMPONENT",
        "MASK",
        "CONDUCTIVE_PASTE",
    )
)
COPPER_TYPES = frozenset(("SIGNAL", "POWER_GROUND", "MIXED"))


@dataclass
class MatrixStep:
    col: int
    name: str
    id: str | None = None

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass
class MatrixLayer:
    row: int
    name: str
    type: str
    context: str
    polarity: str
    add_type: str = ""
    id: str | None = None
    ref: str | None = None

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def is_board(self) -> bool:
        return self.context == "BOARD"

    @property
    def is_copper(self) -> bool:
        return self.type in COPPER_TYPES


@dataclass
class Matrix:
    steps: list[MatrixStep]
    layers: list[MatrixLayer]

    def step(self, name: str) -> MatrixStep | None:
        key = name.lower()
        return next((s for s in self.steps if s.key == key), None)

    def layer(self, name: str) -> MatrixLayer | None:
        key = name.lower()
        return next((layer for layer in self.layers if layer.key == key), None)


def parse_matrix(text: str, path: str = "matrix/matrix") -> tuple[Matrix, list[Issue]]:
    doc = parse_structured(text)
    issues: list[Issue] = []
    steps: list[MatrixStep] = []
    layers: list[MatrixLayer] = []
    unknown: dict[str, list[str]] = {}

    for line_no, line, reason in doc.problems:
        issues.append(
            error("parse_error", f"line {line_no}: {reason}: {line.strip()[:60]!r}", file=path, subject=f"{path}:{line_no}")
        )

    for block in doc.blocks:
        f = block.fields
        if block.name == "STEP":
            unknown.setdefault("STEP", []).extend(k for k in f if k not in STEP_FIELDS)
            try:
                steps.append(MatrixStep(int(f.get("COL", "0")), f["NAME"], f.get("ID")))
            except (KeyError, ValueError) as exc:
                issues.append(error("parse_error", f"STEP array at line {block.line}: {exc}", file=path))
        elif block.name == "LAYER":
            unknown.setdefault("LAYER", []).extend(k for k in f if k not in LAYER_FIELDS)
            try:
                layer = MatrixLayer(
                    row=int(f.get("ROW", "0")),
                    name=f["NAME"],
                    type=f.get("TYPE", "").upper(),
                    context=f.get("CONTEXT", "").upper(),
                    polarity=f.get("POLARITY", "POSITIVE").upper(),
                    add_type=f.get("ADD_TYPE", ""),
                    id=f.get("ID") or None,
                    ref=f.get("REF") or None,
                )
            except (KeyError, ValueError) as exc:
                issues.append(error("parse_error", f"LAYER array at line {block.line}: {exc}", file=path))
                continue
            if layer.type not in LAYER_TYPES:
                issues.append(
                    warning(
                        "unknown_layer_type",
                        f"Layer '{layer.name}' has unrecognized TYPE '{layer.type}'",
                        file=path,
                        subject=layer.name,
                    )
                )
            layers.append(layer)
        else:
            issues.append(
                warning(
                    "unknown_field",
                    f"Unrecognized array '{block.name}' at line {block.line}",
                    file=path,
                    subject=f"{path}:{block.name}",
                )
            )
    for block_name, names in unknown.items():
        if names:
            issues.append(unknown_field_issue(path, block_name, names, blocking=False))
    if doc.fields:
        issues.append(unknown_field_issue(path, "top level", list(doc.fields), blocking=False))

    steps.sort(key=lambda s: s.col)
    layers.sort(key=lambda layer: layer.row)
    return Matrix(steps, layers), issues
