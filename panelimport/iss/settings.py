"""ISS output settings: every switch and constant Phase 2 has not confirmed in JaNets.

Anything that is a guess is a setting, so a JaNets problem can be tried around without
changing code.  The settings live in the Phase 1 settings file under the ``iss`` key;
``panelimport iss --set key=value`` overrides one value for one run, and the report
lists every value used.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from panelimport.model.serialize import SerializationError, from_jsonable, to_jsonable

#: Key of the ISS section in the settings file.
ISS_KEY = "iss"

PANEL_ROTATIONS = ("auto", 0, 90, 180, 270)
BOTTOM_FLIPS = ("left-right", "front-back")
CIRCUIT_LAYOUTS = ("nonmatrix", "matrix")
ANGLE_DIRECTIONS = ("ccw", "cw")
HEADER_COMPLETIONS = ("zero", "total")
COMPONENT_SIZES = ("zero", "body")
TRACEABILITIES = ("TwoDimensions", "NOUSE")


@dataclass
class IssSettings:
    # pwbId in core and model; empty = the project file name stem.
    pwb_id: str = ""
    # "auto" (portrait -> 90 CCW, landscape -> 0) or 0/90/180/270 CCW, after the bottom flip.
    panel_rotation: str | int = "auto"
    # How a bottom-layer panel is turned over: "left-right" (x -> W - x) or "front-back" (y -> H - y).
    bottom_flip: str = "left-right"
    # Added to bottom-layer angles after mirroring (degrees).
    bottom_angle_offset: float = 0.0
    pwb_thickness: float = 1.6  # mm
    back_height: float = 37.0  # mm, as in every real program
    # "auto" = program panel height / 2, else mm.
    clamp_offset_y: str | float = "auto"
    # "nonmatrix" lists every allocation; "matrix" writes divideNumber/pitch (uniform grids only).
    circuit_layout: str = "nonmatrix"
    # "cw" negates every angle written; project angles are CCW.
    angle_direction: str = "ccw"
    # Added to every placement angle, then normalized to [0, 360).
    angle_offset: float = 0.0
    # Header completion counts: "zero" (CircuitCAM, issgen) or "total" (T3, JaNets).
    header_completion: str = "zero"
    # Test switch: stub model/componentData records (known to hang JaNets when its database lock is held).
    model_component_stubs: bool = False
    # componentSize: "body" writes each component's body size and height from the project
    # (package outline and .comp_height, or as edited in Phase 1; 0 where unknown);
    # "zero" writes witdh/length/height 0 for every component.
    component_size: str = "body"
    # Placement attributes tried, in order, for the component comment.
    comment_attributes: list[str] = field(default_factory=lambda: ["DSC", "Description", "Comment"])
    line_name: str = "Line"
    line_id: int = 1
    mark_name: str = "BOCMARK01"
    traceability: str = "TwoDimensions"

    # ------------------------------------------------------------------ validation
    def validate(self) -> list[str]:
        problems = []
        if self.panel_rotation not in PANEL_ROTATIONS or isinstance(self.panel_rotation, bool):
            problems.append(f"panel_rotation={self.panel_rotation!r} is not one of auto, 0, 90, 180, 270")
        for name, allowed in (
            ("bottom_flip", BOTTOM_FLIPS),
            ("circuit_layout", CIRCUIT_LAYOUTS),
            ("angle_direction", ANGLE_DIRECTIONS),
            ("header_completion", HEADER_COMPLETIONS),
            ("component_size", COMPONENT_SIZES),
            ("traceability", TRACEABILITIES),
        ):
            value = getattr(self, name)
            if value not in allowed:
                problems.append(f"{name}={value!r} is not one of {', '.join(allowed)}")
        if isinstance(self.clamp_offset_y, str):
            if self.clamp_offset_y != "auto":
                problems.append(f"clamp_offset_y={self.clamp_offset_y!r} must be 'auto' or a number of mm")
        elif not self.clamp_offset_y > 0:
            problems.append("clamp_offset_y must be positive")
        for name in ("pwb_thickness", "back_height"):
            if not getattr(self, name) > 0:
                problems.append(f"{name} must be positive")
        if self.line_id < 0:
            problems.append("line_id must not be negative")
        if not self.line_name.strip():
            problems.append("line_name must not be empty")
        if not self.mark_name.strip():
            problems.append("mark_name must not be empty")
        return problems

    # ------------------------------------------------------------------ (de)serialization
    def to_dict(self) -> dict:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict) -> IssSettings:
        settings = from_jsonable(cls, data, f"${ISS_KEY}")
        problems = settings.validate()
        if problems:
            raise SerializationError("; ".join(problems))
        return settings

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> IssSettings:
        """The ``iss`` section of the settings file; a missing file or section gives the defaults."""
        from panelimport.settings import default_settings_path

        path = Path(path) if path else default_settings_path()
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise SerializationError(f"{path}: invalid JSON: {exc}") from None
        section = data.get(ISS_KEY) if isinstance(data, dict) else None
        return cls() if section is None else cls.from_dict(section)

    def save(self, path: str | os.PathLike | None = None) -> Path:
        """Write the ``iss`` section, keeping the rest of the settings file as it is."""
        from panelimport.settings import default_settings_path, write_settings_file

        path = Path(path) if path else default_settings_path()
        data = {}
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        data[ISS_KEY] = self.to_dict()
        return write_settings_file(path, data)

    # ------------------------------------------------------------------ overrides
    def with_overrides(self, pairs: list[str]) -> IssSettings:
        """A copy with ``key=value`` overrides applied (``--set`` on the command line)."""
        data = self.to_dict()
        kinds = {f.name: f.type for f in fields(self)}
        for pair in pairs:
            key, sep, text = pair.partition("=")
            key = key.strip().replace("-", "_")
            if not sep or not key:
                raise SerializationError(f"--set {pair!r}: expected key=value")
            if key not in kinds:
                raise SerializationError(f"--set {pair!r}: unknown ISS setting {key!r} (known: {', '.join(kinds)})")
            data[key] = _parse_value(key, kinds[key], text.strip())
        return IssSettings.from_dict(data)

    def describe(self) -> list[tuple[str, str]]:
        """Every setting and its value, for the report."""
        out = []
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, list):
                text = ", ".join(value) or "-"
            elif isinstance(value, bool):
                text = "true" if value else "false"
            else:
                text = str(value) if value != "" else "-"
            out.append((f.name, text))
        return out


def _parse_value(key: str, kind: str, text: str):
    """Convert ``--set`` text to the setting's JSON type."""
    try:
        if kind == "bool":
            low = text.lower()
            if low in ("1", "true", "yes", "on"):
                return True
            if low in ("0", "false", "no", "off"):
                return False
            raise ValueError
        if kind == "int":
            return int(text)
        if kind == "float":
            return float(text)
        if kind == "str | int":
            return text if not text.lstrip("-").isdigit() else int(text)
        if kind == "str | float":
            return text if text == "auto" else float(text)
        if kind == "list[str]":
            return [t.strip() for t in text.split(",") if t.strip()]
    except ValueError:
        raise SerializationError(f"--set {key}={text!r}: not a valid {kind.replace(' | ', ' or ')}") from None
    return text
