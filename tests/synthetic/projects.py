"""Synthetic panel projects for the ISS tests, built directly from the model.

``truth_position`` and ``machine_point`` compute where a part should end up with plain
geometry, independently of :mod:`panelimport.iss.mapping`.
"""

from __future__ import annotations

import math

from panelimport.model.panel import (
    Circuit,
    CircuitReference,
    Fiducial,
    PanelOutline,
    PanelPart,
    PanelProject,
    Placement,
)

PARTS = [
    # designator, x, y (circuit-relative), rotation CCW, part number
    ("R1", 10.0, 20.0, 30.0, "107522-31-1001"),
    ("C1", 25.5, 7.25, 90.0, "107523-3156-1003"),
    ("U1", 33.3333, 41.1, 270.5, "109826"),
    ("R2", 3.0, 3.0, 0.0, "107522-31-1001"),
]


def placements(layer: str = "top", parts=PARTS) -> list[Placement]:
    return [
        Placement(
            designator=d,
            part_name=f"NAME-{d}",
            part_number=pn,
            package="0603",
            layer=layer,
            x=x,
            y=y,
            rotation=rot,
            rotation_raw=(360.0 - rot) % 360.0,
            attributes={"DSC": f"Description of {d}"},
            width=1.6,
            length=0.8,
            height=0.55,
        )
        for d, x, y, rot, pn in parts
    ]


def make_project(
    *,
    width: float = 100.0,
    height: float = 70.0,
    ref: tuple[float, float] = (5.0, 5.0),
    ref_rotation: float = 0.0,
    ref_mirror: bool = False,
    kind: str = "profile-lower-left",
    outline: tuple[float, float, float, float] = (0.0, 0.0, 40.0, 50.0),
    circuits: list[tuple[float, float, float]] | None = None,
    layer: str = "top",
    parts=PARTS,
    fiducials: list[tuple[float, float, str]] | None = None,
    panel_parts: list[PanelPart] | None = None,
) -> PanelProject:
    """``outline`` is the circuit outline's bbox relative to the reference point;
    ``circuits`` lists (dx, dy, rotation) of every circuit relative to circuit 1."""
    x0, y0, x1, y1 = outline
    circuits = circuits if circuits is not None else [(0.0, 0.0, 0.0), (45.0, 0.0, 0.0)]
    if fiducials is None:
        fiducials = [(2.0, 2.0, layer), (width - 2.0, 2.0, layer), (2.0, height - 2.0, layer)]
    return PanelProject(
        panel=PanelOutline(width=width, height=height, outline=[[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]]),
        circuit_reference=CircuitReference(kind=kind, x=ref[0], y=ref[1], rotation=ref_rotation, mirror=ref_mirror),
        circuit_outline=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        circuits=[Circuit(index=i, dx=dx, dy=dy, rotation=rot) for i, (dx, dy, rot) in enumerate(circuits, start=1)],
        placements=placements(layer, parts),
        fiducials=[Fiducial(name=f"FID{i}", x=x, y=y, source="component", layer=side) for i, (x, y, side) in enumerate(fiducials, 1)],
        panel_parts=panel_parts or [],
    )


def truth_position(project: PanelProject, circuit: int, p: Placement) -> tuple[float, float, float]:
    """Panel position and CCW angle of ``p`` in circuit ``circuit`` (1-based):
    circuit k's reference point is ref + (dx, dy), turned by ref.rotation + rotation_k."""
    ref = project.circuit_reference
    c = project.circuits[circuit - 1]
    a = math.radians(ref.rotation + c.rotation)
    x = ref.x + c.dx + math.cos(a) * p.x - math.sin(a) * p.y
    y = ref.y + c.dy + math.sin(a) * p.x + math.cos(a) * p.y
    return x, y, (p.rotation + ref.rotation + c.rotation) % 360.0


def machine_point(x: float, y: float, width: float, height: float, flip: str | None, rotation: int) -> tuple[float, float]:
    """A panel point (lower-left 0,0, size width × height) as the machine sees it."""
    if flip == "left-right":
        x = width - x
    elif flip == "front-back":
        y = height - y
    w, h = width, height
    for _ in range((rotation // 90) % 4):  # 90° CCW, keeping the lower-left at 0,0
        x, y = h - y, x
        w, h = h, w
    return x, y


def machine_angle(theta: float, flip: str | None, rotation: int) -> float:
    if flip == "left-right":
        theta = 180.0 - theta
    elif flip == "front-back":
        theta = -theta
    return (theta + rotation) % 360.0
