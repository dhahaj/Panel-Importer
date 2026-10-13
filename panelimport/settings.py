"""User settings: tolerances, patterns and defaults that are still to be confirmed.

Anything Phase 2 still has to confirm (circuit 1, reference point, numbering, the
part-number attribute, the STEP-REPEAT anchor) is a setting, never a constant.
Settings are plain JSON in the user's config directory; the GUI window layout is
stored separately by Qt.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from panelimport.model.serialize import SerializationError, from_jsonable, to_jsonable

CORNERS = ("lower-left", "lower-right", "upper-left", "upper-right")
ORDERS = ("row-major", "serpentine", "column-major", "column-serpentine")
REFERENCE_KINDS = ("profile-lower-left", "board-origin", "board-datum")
PANEL_ORIGINS = ("profile-lower-left", "odb-origin")
STEP_REPEAT_ANCHORS = ("datum", "origin")


@dataclass
class Tolerances:
    crosscheck: float = 0.01  # mm, step-repeat expansion vs flattened copies
    fit_residual: float = 0.01  # mm, fallback rigid-fit residual
    rotation: float = 0.05  # degrees, circuit rotated relative to circuit 1
    grid: float = 0.01  # mm, non-uniform grid
    centroid_on_pads: float = 0.25  # mm from the paste-pad cluster centre
    pattern_shift: float = 0.1  # mm, median centroid-vs-paste shift
    pad_match_radius: float = 1.0  # mm, toeprint to paste-pad matching radius
    fiducial_merge: float = 0.05  # mm, candidates closer than this are one fiducial


@dataclass
class FiducialSettings:
    patterns: list[str] = field(default_factory=lambda: ["FID*"])
    min_diameter: float = 0.5  # mm, round copper pad candidates
    max_diameter: float = 3.0  # mm
    clearance: float = 1.0  # mm of copper-free ring around an isolated pad
    mask_margin: float = 0.05  # mm, mask opening must exceed the copper pad by this


@dataclass
class Settings:
    tolerances: Tolerances = field(default_factory=Tolerances)
    fiducials: FiducialSettings = field(default_factory=FiducialSettings)
    # Regex with one group for the copy number, e.g. "_(\\d+)$"; empty = identical names.
    copy_suffix_regex: str = ""
    # Attribute/property holding the Detex part number; decided from a real export.
    part_number_attribute: str = ""
    circuit1_corner: str = "lower-left"
    numbering_order: str = "row-major"
    circuit_reference: str = "profile-lower-left"
    panel_origin: str = "profile-lower-left"
    # What STEP-REPEAT X/Y place: the child's datum (ODB++ spec) or its origin.
    step_repeat_anchor: str = "datum"

    def validate(self) -> list[str]:
        problems = []
        for name, allowed in (
            ("circuit1_corner", CORNERS),
            ("numbering_order", ORDERS),
            ("circuit_reference", REFERENCE_KINDS),
            ("panel_origin", PANEL_ORIGINS),
            ("step_repeat_anchor", STEP_REPEAT_ANCHORS),
        ):
            value = getattr(self, name)
            if value not in allowed:
                problems.append(f"{name}={value!r} is not one of {', '.join(allowed)}")
        if self.copy_suffix_regex:
            import re

            try:
                pattern = re.compile(self.copy_suffix_regex)
            except re.error as exc:
                problems.append(f"copy_suffix_regex is not a valid regex: {exc}")
            else:
                if pattern.groups < 1:
                    problems.append("copy_suffix_regex needs one group for the copy number")
        for name, value in vars(self.tolerances).items():
            if value < 0:
                problems.append(f"tolerances.{name} must not be negative")
        return problems

    def to_dict(self) -> dict:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        settings = from_jsonable(cls, data)
        problems = settings.validate()
        if problems:
            raise SerializationError("; ".join(problems))
        return settings

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> Settings:
        """Load settings; a missing file gives the defaults."""
        path = Path(path) if path else default_settings_path()
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def save(self, path: str | os.PathLike | None = None) -> Path:
        path = Path(path) if path else default_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return path


def user_config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "PanelImporter"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PanelImporter"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "panelimport"


def default_settings_path() -> Path:
    override = os.environ.get("PANELIMPORT_SETTINGS")
    if override:
        return Path(override)
    return user_config_dir() / "settings.json"
