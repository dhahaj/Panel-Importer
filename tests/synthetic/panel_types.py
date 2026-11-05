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


def fiducials(step, width: float, height: float, side: str = "top") -> None:
    for i, (x, y) in enumerate([(2.5, 2.5), (width - 2.5, 2.5), (2.5, height - 2.5)], start=1):
        step.component(f"FID{i}", "FID1MM", x, y, side=side, part="FIDUCIAL")


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
