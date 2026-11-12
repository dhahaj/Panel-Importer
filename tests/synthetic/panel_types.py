"""Small synthetic ODB++ panels, one per panel type, with positions worked out by hand.

Every board is 50 × 36.5 with its profile at (−8, −6) and its datum at (4, 3), so a
STEP-REPEAT copy turns the board clockwise about (4, 3) and puts that point on X, Y.
Parts are on one side only (``side``), like every panel the machine places.
"""

from __future__ import annotations

from tests.synthetic.odbgen import Job

DATUM = (4.0, 3.0)


def board(job: Job, name: str = "pcb", side: str = "top"):
    """U1 (7, 12) at 0° and C1 (17, 4) at 90° clockwise: (3, 9) and (13, 1) from the datum."""
    b = job.step(name, 50.0, 36.5, x0=-8.0, y0=-6.0, datum=DATUM)
    b.component("U1", "SOIC8", 7.0, 12.0, rot=0, side=side, part="IC", props={"PART_NUMBER": "D-1"})
    b.component("C1", "C0603", 17.0, 4.0, rot=90, side=side, part="CAP", props={"PART_NUMBER": "D-2"})
    return b


def fiducials(step, width: float, height: float, side: str = "top", x0: float = 0.0, y0: float = 0.0) -> None:
    for i, (x, y) in enumerate([(2.5, 2.5), (width - 2.5, 2.5), (2.5, height - 2.5)], start=1):
        step.component(f"FID{i}", "FID1MM", x0 + x, y0 + y, side=side, part="FIDUCIAL")


FIDS = ["FID1", "FID2", "FID3"]


# -------------------------------------------------------------------- irregular
IRREGULAR_SIZE = (230.0, 70.0)
# (x, y, CCW rotation) of each part in each copy: (3, 9) and (13, 1) turned clockwise by
# 0/90/180/270° — (x, y) → (x, y), (y, −x), (−x, −y), (−y, x) — plus the copy's X, Y.
IRREGULAR = {
    "U1": {(18.0, 21.0, 0.0), (84.0, 47.0, 270.0), (157.0, 36.0, 180.0), (206.0, 23.0, 90.0)},
    "C1": {(28.0, 13.0, 270.0), (76.0, 37.0, 180.0), (147.0, 44.0, 90.0), (214.0, 33.0, 0.0)},
}


def irregular_job(side: str = "top") -> Job:
    """One board, four copies at uneven offsets turned 0, 90, 180 and 270° clockwise."""
    job = Job()
    board(job, side=side)
    panel = job.step("panel", *IRREGULAR_SIZE)
    panel.step_repeat("pcb", 15.0, 12.0, 0.0, 0.0, 1, 1)
    panel.step_repeat("pcb", 75.0, 50.0, 0.0, 0.0, 1, 1, angle=90)
    panel.step_repeat("pcb", 160.0, 45.0, 0.0, 0.0, 1, 1, angle=180)
    panel.step_repeat("pcb", 215.0, 20.0, 0.0, 0.0, 1, 1, angle=270)
    fiducials(panel, *IRREGULAR_SIZE, side=side)
    return job


# -------------------------------------------------------------------- mixed designs
MIXED_SIZE = (200.0, 80.0)
AUX_DATUM = (1.0, 1.0)


def aux_board(job: Job, name: str = "aux", side: str = "top"):
    """A second, smaller design: U1 (3, 4) at 0° and R1 (8, 2) at 180° clockwise, (2, 3) and
    (7, 1) from its datum (1, 1); its profile is 20 × 15 from (−2, −1).  It shares the
    designator U1 with ``board``."""
    b = job.step(name, 20.0, 15.0, x0=-2.0, y0=-1.0, datum=AUX_DATUM)
    b.component("U1", "SOT23", 3.0, 4.0, rot=0, side=side, part="REG", props={"PART_NUMBER": "D-5"})
    b.component("R1", "R0402", 8.0, 2.0, rot=180, side=side, part="RES", props={"PART_NUMBER": "D-3"})
    return b


# Flattened designator -> (x, y, CCW rotation).  Circuits are numbered from the lower left,
# row by row: the main board at (15, 12) and (75, 12), then aux at (150, 15) turned 0° and
# aux at (150, 50) turned 90° clockwise — (x, y) → (y, −x), rotation − 90°.
MIXED = {
    "U1_1": (18.0, 21.0, 0.0),
    "C1_1": (28.0, 13.0, 270.0),
    "U1_2": (78.0, 21.0, 0.0),
    "C1_2": (88.0, 13.0, 270.0),
    "U1_3": (152.0, 18.0, 0.0),
    "R1_3": (157.0, 16.0, 180.0),
    "U1_4": (153.0, 48.0, 270.0),
    "R1_4": (151.0, 43.0, 90.0),
}


def mixed_job(side: str = "top") -> Job:
    """Two copies of the main board and two of a smaller design, one of them turned."""
    job = Job()
    board(job, "main", side=side)
    aux_board(job, side=side)
    panel = job.step("panel", *MIXED_SIZE)
    panel.step_repeat("main", 15.0, 12.0, 60.0, 0.0, 2, 1)
    panel.step_repeat("aux", 150.0, 15.0, 0.0, 0.0, 1, 1)
    panel.step_repeat("aux", 150.0, 50.0, 0.0, 0.0, 1, 1, angle=90)
    fiducials(panel, *MIXED_SIZE, side=side)
    return job


# -------------------------------------------------------------------- flat (no STEP-REPEAT)
FLAT_SIZE = (120.0, 60.0)
# Panel-frame (x, y, CCW rotation): the panel profile starts at (−10, −5), so each part
# sits at its ODB++ position + (10, 5).
FLAT = {
    "U1": (20.0, 15.0, 0.0),
    "C1": (30.0, 7.0, 270.0),
    "R1": (70.0, 40.0, 180.0),
}
# With ``duplicate``: a second U1, numbered after the first (lower-left first, row by row).
FLAT_DUPLICATE = {"U1_1": (20.0, 15.0, 0.0), "U1_2": (80.0, 15.0, 270.0), "C1": FLAT["C1"], "R1": FLAT["R1"]}


def flat_job(side: str = "top", duplicate: bool = False) -> Job:
    """One step, the panel itself, with its parts placed directly in it."""
    job = Job()
    panel = job.step("panel", *FLAT_SIZE, x0=-10.0, y0=-5.0)
    panel.component("U1", "SOIC8", 10.0, 10.0, rot=0, side=side, part="IC", props={"PART_NUMBER": "D-1"})
    panel.component("C1", "C0603", 20.0, 2.0, rot=90, side=side, part="CAP", props={"PART_NUMBER": "D-2"})
    panel.component("R1", "R0402", 60.0, 35.0, rot=180, side=side, part="RES", props={"PART_NUMBER": "D-3"})
    if duplicate:
        panel.component("U1", "SOIC8", 70.0, 10.0, rot=90, side=side, part="IC", props={"PART_NUMBER": "D-1"})
    fiducials(panel, *FLAT_SIZE, side=side, x0=-10.0, y0=-5.0)
    return job
