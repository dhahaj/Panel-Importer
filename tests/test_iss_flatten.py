"""Flatten output: one allocation holding every placement of every circuit.

Positions are checked against coordinates worked out by hand, and a grid forced into
flatten must put every part exactly where its per-circuit program does.
"""

from __future__ import annotations

import pytest

from panelimport.analysis.pipeline import analyze
from panelimport.analysis.transforms import angle_diff
from panelimport.io.odb import OdbJob
from panelimport.iss.checks import prepare
from panelimport.iss.compare import panel_geometry
from panelimport.iss.reader import read_iss_bytes, read_program
from panelimport.iss.settings import IssSettings
from panelimport.iss.writer import encode, render, write_iss
from panelimport.model.panel import Decisions
from panelimport.settings import REFERENCE_KINDS, Settings
from tests.synthetic.panel_types import FIDS, IRREGULAR, IRREGULAR_SIZE, irregular_job
from tests.synthetic.projects import machine_angle, make_project

#: Circuits: P + allocation + position, three 4-decimal roundings; flatten: one.
EXPANDED_TOL = 2e-4


def program_of(project, settings: IssSettings):
    prepared = prepare(project, settings, pwb_id="T")
    assert prepared.can_write, [i.format() for i in prepared.errors]
    return prepared, read_iss_bytes(encode(render(prepared.layout, settings)))


# -------------------------------------------------------------------- by hand
def test_bottom_rotated_circuit_by_hand():
    """Panel 150 × 150, circuit 1's reference at (20, 20), circuit 2 at +(100, 100) turned
    90° CCW, R1 at (10, 20) in the circuit at 30°, bottom side, turned over left-right.

    Circuit 1: (30, 40) → (120, 40), 180° − 30° = 150°.
    Circuit 2: (10, 20) turned 90° = (−20, 10), + (120, 120) = (100, 130) → (50, 130);
    30° + 90° = 120° → 180° − 120° = 60°.  P is the panel's lower-left corner."""
    project = make_project(
        width=150,
        height=150,
        ref=(20.0, 20.0),
        circuits=[(0, 0, 0), (100.0, 100.0, 90.0)],
        layer="bottom",
        parts=[("R1", 10.0, 20.0, 30.0, "P-1")],
    )
    prepared, prog = program_of(project, IssSettings(panel_rotation=0))
    assert prepared.layout.output == "flatten"
    assert (prog.width, prog.height, prog.circuit_width, prog.circuit_height) == (150, 150, 150, 150)
    assert prog.pwb_layout_offset == (150, 0) and prog.circuit_layout_offset == (0, 0) and prog.origin == (0, 0)
    assert [(c.number, c.x, c.y, c.angle) for c in prog.circuits] == [(1, 0, 0, 0)]
    assert [(p.designator, p.component, p.x, p.y, p.angle) for p in prog.placements] == [
        ("R1_1", "P-1", 120, 40, 150),
        ("R1_2", "P-1", 50, 130, 60),
    ]
    # Fiducials (2, 2), (148, 2), (2, 148) turned over left-right; P is (0, 0).
    assert [(f.x, f.y) for f in prog.fiducials] == [(148, 2), (2, 2), (148, 148)]
    assert prog.clamp_offset == 75


def test_angle_settings_apply_to_every_circuit():
    project = make_project(
        width=150, height=150, ref=(20.0, 20.0), circuits=[(0, 0, 0), (100.0, 100.0, 90.0)], parts=[("R1", 10.0, 20.0, 30.0, "P")]
    )
    _p, prog = program_of(project, IssSettings(panel_rotation=0, angle_direction="cw", angle_offset=10))
    assert [p.angle for p in prog.placements] == [340, 250]  # −30° + 10°, −120° + 10°


def test_components_and_sizes_as_in_circuits_output():
    project = make_project()
    _a, circuits = program_of(project, IssSettings())
    _b, flat = program_of(project, IssSettings(circuit_output="flatten"))
    assert [(c.name, c.comment, c.width, c.length, c.height) for c in flat.components] == [
        (c.name, c.comment, c.width, c.length, c.height) for c in circuits.components
    ]
    assert [p.designator for p in flat.placements] == [f"{p.designator}_{k}" for k in (1, 2) for p in project.placements]


def test_written_file_reads_back(tmp_path):
    project = make_project(circuits=[(0, 0, 0), (90.0, 55.0, 180.0)])  # circuit 2 turned about (95, 60)
    prepared = prepare(project, IssSettings(), pwb_id="T")
    out = write_iss(prepared, tmp_path / "flat.iss")  # the writer's self-test reads it back
    text = out.read_bytes().decode("utf-8-sig")
    assert '<totalCount count="1" />' in text and text.count("<allocation ") == 1
    assert read_program(out).placements[0].designator == "R1_1"


# -------------------------------------------------------------------- grid forced into flatten
def assert_flatten_matches_circuits(project, settings: IssSettings) -> None:
    """Every part of every circuit lands at the same machine position, at the same angle."""
    a, circuits = program_of(project, settings)
    flat_settings = IssSettings(**{**settings.to_dict(), "circuit_output": "flatten", "circuit_layout": "nonmatrix"})
    b, flat = program_of(project, flat_settings)
    assert a.layout.output == "circuits" and b.layout.output == "flatten"
    assert (flat.width, flat.height, flat.clamp_offset) == (circuits.width, circuits.height, circuits.clamp_offset)
    expanded = {}
    for p in panel_geometry(circuits).placements:
        expanded[f"{p.designator}_{a.layout.circuit_numbers[p.circuit - 1]}"] = p
    flattened = {p.designator: p for p in panel_geometry(flat).placements}
    assert set(flattened) == set(expanded)
    for name, f in flattened.items():
        e = expanded[name]
        assert abs(f.x - e.x) <= EXPANDED_TOL and abs(f.y - e.y) <= EXPANDED_TOL, (name, (f.x, f.y), (e.x, e.y))
        assert angle_diff(f.angle, e.angle) <= 1e-3, name
        assert f.component == e.component
    marks = sorted((x, y) for _n, x, y in panel_geometry(flat).fiducials)
    assert marks == pytest.approx(sorted((x, y) for _n, x, y in panel_geometry(circuits).fiducials), abs=EXPANDED_TOL)


GRID = [(0, 0, 0), (45.0, 0, 0), (0, 55.0, 0), (45.0, 55.0, 0)]


@pytest.mark.parametrize(
    "settings",
    [
        IssSettings(),
        IssSettings(panel_rotation=90),
        IssSettings(panel_rotation=270, angle_direction="cw", angle_offset=-45),
        IssSettings(circuit_layout="matrix"),
    ],
    ids=["plain", "rotated", "cw-offset", "matrix"],
)
@pytest.mark.parametrize("layer", ["top", "bottom"])
def test_grid_forced_into_flatten(settings, layer):
    project = make_project(width=100, height=120, circuits=GRID, layer=layer)
    assert_flatten_matches_circuits(project, settings)


@pytest.mark.parametrize("flip", ["left-right", "front-back"])
def test_grid_forced_into_flatten_bottom_flips(flip):
    project = make_project(width=100, height=120, circuits=GRID, layer="bottom", ref=(50.0, 3.25), ref_rotation=90.0)
    assert_flatten_matches_circuits(project, IssSettings(bottom_flip=flip))


@pytest.mark.parametrize("kind", REFERENCE_KINDS)
def test_grid_forced_into_flatten_through_phase1(tmp_path, kind):
    from tests.test_iss_mapping import _pipeline_project

    for side in ("top", "bottom"):
        project, _truth = _pipeline_project(tmp_path, "upper-right", kind, side=side)
        assert_flatten_matches_circuits(project, IssSettings())


# -------------------------------------------------------------------- irregular ODB++ panel
def _irregular_project(tmp_path, side: str):
    src = irregular_job(side).write_folder(tmp_path / side)
    a = analyze(OdbJob(src), Settings(part_number_attribute="PART_NUMBER"), Decisions(fiducials=list(FIDS), confirmed=True))
    assert a.mode == "panel" and not a.errors, [i.format() for i in a.errors]
    return a.to_project()


def test_irregular_panel_flattened_by_hand(tmp_path):
    """Top side, 230 × 70 landscape: the program frame is the panel frame, so each
    flattened part sits at the position worked out by hand for its copy."""
    prepared, prog = program_of(_irregular_project(tmp_path, "top"), IssSettings())
    assert prepared.layout.output == "flatten"
    assert prepared.layout.output_reason == "circuits 2, 3, 4 rotated relative to circuit 1"
    got = {}
    for p in prog.placements:
        got.setdefault(p.designator.rsplit("_", 1)[0], set()).add((p.x, p.y, p.angle))
    assert got == IRREGULAR


def test_irregular_bottom_panel_flattened_by_hand(tmp_path):
    """The same panel with its parts on the bottom, turned over left-right: x → 230 − x,
    angles θ → 180° − θ (positions are where the parts are; the side only flips them)."""
    project = _irregular_project(tmp_path, "bottom")
    prepared, prog = program_of(project, IssSettings())
    m = prepared.layout.machine
    assert (m.side, m.flip, m.rotation) == ("bottom", "left-right", 0)
    width = IRREGULAR_SIZE[0]
    got = {}
    for p in prog.placements:
        got.setdefault(p.designator.rsplit("_", 1)[0], set()).add((p.x, p.y))
    assert got == {name: {(width - x, y) for x, y, _a in where} for name, where in IRREGULAR.items()}
    # Angles: Phase 1's own rotation of each copy, mirrored by the flip.
    by_name = {p.designator: p for p in prog.placements}
    for p in project.placements:
        for c in project.circuits:
            written = by_name[f"{p.designator}_{c.index}"]
            panel_angle = (p.rotation + project.circuit_reference.rotation + c.rotation) % 360
            assert angle_diff(written.angle, machine_angle(panel_angle, "left-right", 0)) <= 1e-3
