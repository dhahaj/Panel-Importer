"""A panel with about 2,000 placements loads in a few seconds."""

import time

import pytest

from panelimport.session import Session
from tests.synthetic.odbgen import sr_panel

LOAD_BUDGET_S = 6.0  # "a few seconds", with margin for slow CI machines


def big_panel():
    # 4 x 2 circuits x 250 parts = 2,000 placements on the panel.
    return sr_panel(nx=4, ny=2, dx=102, dy=77, board_w=100, board_h=75, n_parts=250)


@pytest.mark.slow
def test_2000_placements_load_quickly(tmp_path):
    src = big_panel().write_tgz(tmp_path / "big.tgz")
    t0 = time.perf_counter()
    s = Session()
    a = s.open_source(src)
    elapsed = time.perf_counter() - t0
    n_circuits, n_parts = len(a.circuits), len(a.placements)
    assert (n_circuits, n_parts) == (8, 250)
    assert not a.errors, [i.format() for i in a.errors]
    assert elapsed < LOAD_BUDGET_S, f"analysis took {elapsed:.2f} s"
