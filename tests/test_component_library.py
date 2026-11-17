"""The component database as records to edit: units, option names and unsaved changes
(no database needed; saving is in test_compolib.py)."""

from __future__ import annotations

import pytest

from panelimport.model.library import ADDED, DELETED, EDITED, FIELD, FIELDS, NAME, TABLES, Changes
from tests.synthetic.mdb import sample_library, values_of


def _id(lib, name: str) -> int:
    return next(r.compo_id for r in lib.records if r.name == name)


# ---------------------------------------------------------------------- units and names
def test_units_are_the_juki_editors():
    """What the Juki editor shows for 101672-10 of DETEX_New.mdb, from what is stored."""
    lib = sample_library()
    v = values_of("D-100")
    shown = {key: lib.text(key, v) for key in v}
    assert (shown["Compo.Width"], shown["Compo.Length"]) == ("4.814", "3.584")
    assert shown["Laser.LaserHeight"] == "-1.165"  # the editor cuts it to -1.16
    assert shown["Laser.GX4PreRotate"] == "30"  # 1/80 degree
    assert (shown["Expansion.OverPickGx10"], shown["Expansion.OverPlaceGx10"]) == ("0.2", "0.5")
    assert (shown["LaserGx10.PickZ2StepDown"], shown["LaserGx10.PickZ2StepUp"]) == ("2", "0.5")
    assert (shown["LaserGx10.PlaceZ2StepDown"], shown["LaserGx10.PlaceZ2StepUp"]) == ("0.7", "2")
    assert (shown["LaserGx10.SpdXY"], shown["LaserGx10.SpdTheta"]) == ("Fast 2", "Fast")
    assert (shown["Laser.LaserAlgo"], shown["LaserGx10.CompoShape"]) == ("Algorithm 1", "Corner square")
    assert (shown["Inspection.ChipStandCheck"], shown["Expansion.CompoLayer"]) == ("If possible", "Layer 4")
    assert (shown["Expansion.EtfPickPosAdjust"], shown["Expansion.PickPosAdjust"]) == ("Yes", "No")
    assert (shown["Compo.PkgClassID"], shown["Feeder.FdrTypeID"]) == ("Chip", "Tape")  # from the database's tables
    assert shown["Compo.PackageWidth"] == ""  # NULL
    assert lib.feeder_text(v) == "12mm emboss 8 mm (8 × 1)" and lib.centering_text(v) == "L(504)"
    assert lib.feeder_text(values_of("U-200")) == "MBF44 SOIC"
    assert lib.text("Feeder.TapeAngle", values_of("R-400")) == "270"


@pytest.mark.parametrize("f", [f for f in FIELDS if f.kind in ("number", "flag", "text")], ids=lambda f: f.key)
def test_shown_and_stored_round_trip(f):
    """A setting the user did not touch is stored exactly as it was."""
    for name in ("D-100", "U-200", "R-400"):
        raw = values_of(name)[f.key]
        if raw is not None:
            back = f.stored(f.shown(raw), raw)
            assert back == raw and type(back) is type(raw)


def test_stored_values():
    assert FIELD["Compo.Width"].stored(4.8151) == 48151
    assert FIELD["Feeder.TapeAngle"].stored(90.0) == 7200
    assert FIELD["Expansion.Test"].stored(True, False) is True  # a Yes/No column
    assert FIELD["Expansion.AutoTeach"].stored(True, 0) == 1  # a byte column
    assert FIELD["Compo.Description"].stored("  x  ", None) == "x"
    assert FIELD["Compo.Description"].stored("  ", None) is None  # an empty text stays NULL


def test_options_are_the_confirmed_and_the_used():
    lib = sample_library()
    assert lib.options(FIELD["LaserGx10.SpdPlaceUpZ"]) == [(0, "Fast"), (2, "Slow"), (4, "Fast 2")]
    # A name worked out but not seen in the Juki editor says so; it is offered once a component uses it.
    assert lib.options(FIELD["LaserGx10.SpdPlaceDownZ"])[1] == (1, "Medium (unconfirmed)")
    assert lib.options(FIELD["Laser.LaserAlgo"]) == [(1, "Algorithm 1"), (2, "Algorithm 2 (unconfirmed)")]
    assert lib.options(FIELD["LaserGx10.CompoShape"]) == [(2, "Corner square"), (4, "Code 4")]
    assert lib.options(FIELD["LaserGx10.NozzleNo"]) == [(503, "503"), (504, "504"), (506, "506")]
    assert lib.options(FIELD["Feeder.TapeTypeID"])[2] == (3, "12mm emboss")
    assert (201, "8 mm (4 × 2)") in lib.options(FIELD["Feeder.Pitch"])


# ---------------------------------------------------------------------- unsaved changes
def test_edit_keeps_only_real_changes():
    lib, ch = sample_library(), Changes()
    d = _id(lib, "D-100")
    lib.edit(ch, d, {"Compo.Width": 48150, "Compo.Height": 2, "Expansion.Test": True})
    assert ch.updates == {d: {"Compo.Width": 48150, "Expansion.Test": True}} and ch.summary() == "1 edited"
    c = lib.component(ch, d)
    assert c.state == EDITED and c.changed == {"Compo.Width", "Expansion.Test"} and c.values["Compo.Width"] == 48150
    lib.edit(ch, d, {"Compo.Width": 48140, "Expansion.Test": False})  # back to the database's
    assert not ch and lib.component(ch, d).state == ""
    with pytest.raises(ValueError, match="cannot be changed"):
        lib.edit(ch, d, {"Compo.PkgClassID": 101})  # read-only


def test_copy_delete_and_revert():
    lib, ch = sample_library(), Changes()
    d = _id(lib, "D-100")
    lib.edit(ch, d, {"Compo.Width": 50000})
    new = lib.add_copy(ch, d, " D-101 ")
    assert new == -1 and ch.added == {-1: d}
    c = lib.component(ch, new)
    # A copy of the component as it is shown: with its unsaved width.
    assert (c.name, c.state, c.values["Compo.Width"], c.values["Compo.Length"]) == ("D-101", ADDED, 50000, 35840)
    again = lib.add_copy(ch, new, "D-102")  # a copy of a copy is a copy of the same record
    assert again == -2 and ch.added[-2] == d and lib.component(ch, again).values["Compo.Width"] == 50000
    assert [c.name for c in lib.components(ch)] == ["D-100", "Q-300", "R-400", "U-200", "D-101", "D-102"]
    assert ch.summary() == "1 edited, 2 new"

    lib.edit(ch, new, {"Compo.Width": 48140})  # the copied record's own width: nothing to write for it
    assert "Compo.Width" not in ch.updates[new] and ch.updates[new][NAME] == "D-101"
    lib.delete(ch, again)  # a new component just goes
    assert again not in ch.added and again not in ch.updates and not ch.deleted
    lib.delete(ch, d)
    assert lib.component(ch, d).state == DELETED and d not in ch.updates and ch.summary() == "1 new, 1 deleted"
    lib.revert(ch, d)
    lib.revert(ch, new)
    assert not ch


def test_names_are_unique_ignoring_case():
    lib, ch = sample_library(), Changes()
    d, u = _id(lib, "D-100"), _id(lib, "U-200")
    assert lib.name_taken(ch, "d-100 ") and not lib.name_taken(ch, "d-100", but=d) and not lib.name_taken(ch, "X")
    lib.delete(ch, u)
    assert not lib.name_taken(ch, "U-200")  # a deleted component's name is free
    lib.edit(ch, d, {NAME: "u-200"})
    assert lib.problems(ch) == []
    lib.revert(ch, u)
    assert lib.problems(ch) == ["Two components are named U-200"]


def test_problems():
    lib, ch = sample_library(), Changes()
    d, q = _id(lib, "D-100"), _id(lib, "Q-300")
    lib.edit(ch, d, {NAME: "", "Compo.Width": -10000, "Expansion.Retry": 12})
    ch.updates[d]["LaserGx10.SpdXY"] = 9  # an option nothing uses
    assert lib.problems(ch) == [
        "A component has no name",
        f"component {d}: Width -1 is outside 0 to 999",
        f"component {d}: Retry times 12 is outside 0 to 9",
        f"component {d}: XY has no option 9",
    ]
    ch.clear()
    lib.edit(ch, d, {NAME: "X" * 61})
    assert lib.problems(ch) == [f"{'X' * 61}: the name is longer than 60 characters"]
    ch.clear()
    # Vision data is not copied or deleted here.
    lib.add_copy(ch, q, "Q-301")
    lib.delete(ch, q)
    assert lib.problems(ch) == [
        "Q-300 has ElementGroup data and cannot be deleted here",
        "Q-301 is a copy of Q-300, which has ElementGroup data and cannot be copied here",
    ]


def test_expected_is_the_database_after_saving():
    lib, ch = sample_library(), Changes()
    d, u = _id(lib, "D-100"), _id(lib, "U-200")
    lib.edit(ch, d, {"Compo.Width": 50000})
    new = lib.add_copy(ch, d, "D-101")
    lib.delete(ch, u)
    expected = lib.expected(ch, {new: 9})
    assert sorted(expected) == [d, _id(lib, "Q-300"), _id(lib, "R-400"), 9]
    assert expected[9] == {**values_of("D-100"), NAME: "D-101", "Compo.Width": 50000}
    assert expected[d]["Compo.Width"] == 50000


def test_tables_start_with_compo():
    assert TABLES[0] == "Compo" and set(TABLES) == {"Compo", "Feeder", "Laser", "LaserGx10", "Expansion", "Inspection"}
