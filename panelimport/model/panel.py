"""Model dataclasses.  The project file (``<name>.panel.json``) is their direct serialization.

Units are mm, angles are degrees counter-clockwise, placements are circuit-relative.
Component sizes are the body's extent along the part's own X axis (``width``) and Y axis
(``length``) at rotation 0, and its ``height``; 0 means unknown.
Panel-level coordinates (outline, circuit reference, panel parts, fiducials) are in the
panel frame, whose origin is described by :class:`PanelOrigin`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from panelimport.settings import Settings

PROJECT_FORMAT = "panel-project"
PROJECT_VERSION = 3  # 2: component_edits, panel_parts[].part_number; 3: component sizes
READABLE_VERSIONS = (1, 2, 3)
#: The first version whose placements, panel parts and edits carry component sizes.
SIZES_VERSION = 3

#: Why a component is not placed.
REMOVAL_REASONS = ("through-hole", "not-populated", "mechanical", "other")


@dataclass
class SourceInfo:
    kind: str = "odb++"
    path: str = ""
    sha256: str = ""
    panel_step: str | None = None
    board_step: str | None = None
    container: str = ""  # "folder" | "tgz" | "zip"


@dataclass
class PanelOrigin:
    kind: str = "profile-lower-left"  # or "odb-origin"
    odb_x: float = 0.0  # where the panel origin sits in ODB++ panel-step coordinates
    odb_y: float = 0.0


@dataclass
class PanelOutline:
    width: float = 0.0
    height: float = 0.0
    outline: list[list[float]] = field(default_factory=list)
    origin: PanelOrigin = field(default_factory=PanelOrigin)


@dataclass
class Grid:
    cols: int = 0
    rows: int = 0
    pitch_x: float = 0.0
    pitch_y: float = 0.0
    uniform: bool = True
    source: str = ""  # "step-repeat" | "fitted" | "manual"


@dataclass
class Numbering:
    first: str = "lower-left"
    order: str = "row-major"


@dataclass
class CircuitReference:
    kind: str = "profile-lower-left"
    x: float = 0.0  # circuit 1 reference point, panel frame
    y: float = 0.0
    board_x: float = 0.0  # the same point in the board's own frame
    board_y: float = 0.0
    rotation: float = 0.0  # circuit 1 board frame relative to the panel, CCW
    mirror: bool = False


@dataclass
class Circuit:
    index: int = 0
    dx: float = 0.0
    dy: float = 0.0
    rotation: float = 0.0
    mirror: bool = False
    source: str = ""
    residual: float | None = None


@dataclass
class Placement:
    designator: str = ""
    part_name: str = ""
    part_number: str = ""
    package: str = ""
    layer: str = "top"
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    rotation_raw: float = 0.0
    attributes: dict[str, str] = field(default_factory=dict)
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0


@dataclass
class PanelPart:
    designator: str = ""
    x: float = 0.0
    y: float = 0.0
    layer: str = "top"
    part_name: str = ""
    part_number: str = ""
    package: str = ""
    rotation: float = 0.0
    rotation_raw: float = 0.0
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0


@dataclass
class Fiducial:
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    source: str = ""  # "component" | "attribute" | "copper" | "manual"
    layer: str = "top"
    diameter: float | None = None


@dataclass(frozen=True)
class Acknowledgement:
    code: str = ""
    designator: str | None = None
    circuit: int | None = None
    subject: str | None = None

    @property
    def key(self) -> tuple[str, str | None, int | None, str | None]:
        return (self.code, self.designator, self.circuit, self.subject)

    @classmethod
    def of(cls, issue) -> Acknowledgement:
        return cls(issue.code, issue.designator, issue.circuit, issue.subject)


@dataclass(frozen=True)
class ComponentEdit:
    """A user change to one component.  The export is never changed; edits are stored
    with the project and re-applied when it is reopened.

    * ``removed`` — the component is not placed (it still exists: a removed ``FID1`` is
      still a fiducial candidate).  ``reason`` says why.
    * ``added`` — a component the export does not have; every field below applies.
    * otherwise the fields that are not None override the export's values.

    ``level`` "board" components are placed in every circuit and their x/y are
    circuit-relative, like ``placements``; "panel" components are placed once and their
    x/y are in the panel frame, like ``panel_parts``.  Rotation is CCW degrees.  A size
    of 0 sets that dimension to unknown.
    """

    designator: str = ""
    level: Literal["board", "panel"] = "board"
    added: bool = False
    removed: bool = False
    reason: Literal["", "through-hole", "not-populated", "mechanical", "other"] = ""
    note: str = ""
    part_name: str | None = None
    part_number: str | None = None
    package: str | None = None
    layer: Literal["top", "bottom"] | None = None
    x: float | None = None
    y: float | None = None
    rotation: float | None = None
    width: float | None = None
    length: float | None = None
    height: float | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.level, self.designator)

    @property
    def overrides(self) -> dict[str, object]:
        """The fields this edit sets (all of them for an added component)."""
        return {f: getattr(self, f) for f in EDIT_FIELDS if getattr(self, f) is not None}

    @property
    def moves(self) -> bool:
        return any(getattr(self, f) is not None for f in ("x", "y", "rotation", "layer"))


#: Component fields an edit can set, in display order.
EDIT_FIELDS = ("part_name", "part_number", "package", "layer", "x", "y", "rotation", "width", "length", "height")
#: The size fields among them (mm, 0 = unknown).
SIZE_FIELDS = ("width", "length", "height")


@dataclass(frozen=True)
class EditFrame:
    """What component-edit coordinates were relative to when they were entered: the
    panel structure, the circuit reference, the numbering (which picks circuit 1 on a
    flattened panel) and the panel origin.  The analysis converts edits made in another
    frame, so changing the reference or the numbering never moves an edited part."""

    mode: str = "panel"
    reference: str = "profile-lower-left"
    first: str = "lower-left"
    order: str = "row-major"
    panel_origin: str = "profile-lower-left"


@dataclass
class SingleBoardSetup:
    """What the user enters for a single-board export."""

    cols: int = 1
    rows: int = 1
    pitch_x: float = 0.0
    pitch_y: float = 0.0
    # Optional per-circuit offsets [dx, dy] from circuit 1; overrides cols/rows/pitch.
    offsets: list[list[float]] | None = None
    # Where circuit 1's board origin sits, measured from the panel origin.
    origin_x: float = 0.0
    origin_y: float = 0.0
    panel_width: float = 0.0
    panel_height: float = 0.0
    panel_outline: list[list[float]] | None = None
    fiducials: list[Fiducial] = field(default_factory=list)
    # Optional panel ODB++ export used for the outline, paste and fiducials.
    panel_source: str | None = None

    def offsets_list(self) -> list[tuple[float, float]]:
        if self.offsets:
            return [(float(o[0]), float(o[1])) for o in self.offsets]
        return [
            (c * self.pitch_x, r * self.pitch_y) for r in range(max(self.rows, 1)) for c in range(max(self.cols, 1))
        ]


@dataclass
class Decisions:
    """User edits.  Never mutated in place: edits create a new object (undo-friendly)."""

    panel_step: str | None = None
    board_step: str | None = None
    layer_roles: dict[str, str] = field(default_factory=dict)
    numbering_first: str | None = None
    numbering_order: str | None = None
    circuit_reference: str | None = None
    part_number_attribute: str | None = None
    fiducials: list[str] = field(default_factory=list)
    acknowledged: list[Acknowledgement] = field(default_factory=list)
    panel_level: list[str] = field(default_factory=list)
    single_board: SingleBoardSetup | None = None
    bom_path: str | None = None
    component_edits: list[ComponentEdit] = field(default_factory=list)
    edit_frame: EditFrame | None = None  # None: the frame of the analysis itself
    confirmed: bool = False


@dataclass
class PanelProject:
    format: str = PROJECT_FORMAT
    version: int = PROJECT_VERSION
    generator: str = ""
    source: SourceInfo = field(default_factory=SourceInfo)
    mode: str = "panel"  # "panel" | "flattened" | "single-board"
    panel: PanelOutline = field(default_factory=PanelOutline)
    grid: Grid = field(default_factory=Grid)
    numbering: Numbering = field(default_factory=Numbering)
    circuit_reference: CircuitReference = field(default_factory=CircuitReference)
    # The board outline of one circuit, circuit-relative (like the placements).
    circuit_outline: list[list[float]] = field(default_factory=list)
    circuits: list[Circuit] = field(default_factory=list)
    part_number_attribute: str = ""
    placements: list[Placement] = field(default_factory=list)
    panel_parts: list[PanelPart] = field(default_factory=list)
    # What the user removed, added or changed (already applied to the lists above).
    component_edits: list[ComponentEdit] = field(default_factory=list)
    fiducials: list[Fiducial] = field(default_factory=list)
    acknowledged_warnings: list[Acknowledgement] = field(default_factory=list)
    layer_roles: dict[str, str] = field(default_factory=dict)
    panel_level_designators: list[str] = field(default_factory=list)
    single_board: SingleBoardSetup | None = None
    settings: Settings = field(default_factory=Settings)
