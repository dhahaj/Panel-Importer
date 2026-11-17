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
    assert lib.feeder_text(v) == "12mm emboss 8 mm" and lib.centering_text(v) == "L(504)"
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


def _codes(lib, key: str, values=None) -> list[int]:
    return [code for code, _label in lib.options(FIELD[key], values)]


def test_options_are_janets():
    """The options of JaNets's Component Database editor, in its order, with the values it stores."""
    lib = sample_library()
    assert lib.options(FIELD["LaserGx10.SpdXY"]) == [(4, "Fast 2"), (0, "Fast"), (1, "Medium"), (2, "Slow")]
    assert _codes(lib, "LaserGx10.SpdPickDownZ") == _codes(lib, "LaserGx10.SpdPlaceUpZ") == [4, 0, 1, 2, 3, 7]
    assert _codes(lib, "LaserGx10.SpdPlaceUpZGx10V") == [4, 0, 1, 2, 3, 7, 8, 9, 10]  # Fast V1-V3: 3010-20V/VA
    assert _codes(lib, "LaserGx10.SpdThetaInLA") == [0, 1, 2] and _codes(lib, "LaserGx10.SpdTheta") == [0, 1, 2, 3]
    assert dict(lib.options(FIELD["LaserGx10.SpdPickUpZ"]))[3] == "Slow 2"
    assert lib.options(FIELD["Laser.LaserAlgo"]) == [
        (100, "Algorithm 0"), (1, "Algorithm 1"), (2, "Algorithm 2"), (3, "Algorithm 3"),
    ]  # fmt: skip
    shapes = dict(lib.options(FIELD["LaserGx10.CompoShape"]))
    assert (shapes[2], shapes[4], shapes[99]) == ("Corner square", "Corner cut", "Cylinder") and len(shapes) == 8
    assert lib.options(FIELD["Compo.GX4PriorityLV"]) == [(0, "Auto"), (1, "Laser priority"), (2, "Vision priority")]
    assert lib.options(FIELD["Feeder.SpliceSensorUse"]) == [(0, "If possible"), (1, "No")]
    assert lib.options(FIELD["Expansion.ScrapType"]) == [(0, "Trash box"), (2, "IC collection belt"), (3, "Protect")]
    assert _codes(lib, "Expansion.ScrapTypeGx6") == [0, 2, 3]
    assert _codes(lib, "Expansion.CompoLayer") == [1, 2, 3, 4, 5, 6, 7]
    assert lib.options(FIELD["Inspection.ChipStandCheck"]) == [(0, "No"), (1, "Yes"), (2, "If possible")]
    assert lib.options(FIELD["LaserGx10.NozzleNo"]) == [(503, "503"), (504, "504"), (506, "506")]  # the ones in use
    assert lib.options(FIELD["Feeder.TapeTypeID"])[2] == (3, "12mm emboss")  # from the database's table
    # Names JaNets has for values that are kept here but not offered.
    assert lib.label(FIELD["Compo.PkgClassID"], 120) == "QFN"  # not in the database's PkgClass table
    assert lib.label(FIELD["Compo.Rx7ComponentType"], 4) == "Odd shape (without leads)"
    assert lib.label(FIELD["Compo.GX4PriorityLV"], 3) == "RX-7 vision only"
    assert lib.label(FIELD["Expansion.ScrapType"], 1) == "Tray restore"
    assert lib.label(FIELD["Feeder.StickChangerType"], 0) == "None"
    assert lib.label(FIELD["LaserGx10.CompoShape"], 5) == "Code 5"  # a value JaNets has no name for


def test_load_is_named_but_not_offered():
    """Load control needs a load this program does not show: a component that has it keeps it."""
    lib = sample_library()
    lib.record(_id(lib, "U-200")).values["Expansion.FCTypePickGx10"] = 1
    assert lib.options(FIELD["Expansion.FCTypePickGx10"]) == [(0, "Stroke")]
    assert lib.label(FIELD["Expansion.FCTypePickGx10"], 1) == "Load"
    assert lib.text("Expansion.FCTypePickGx10", values_of("U-200") | {"Expansion.FCTypePickGx10": 1}) == "Load"


def test_feed_pitches_depend_on_the_tape_width():
    """A stored pitch means another feed on another tape width (JaNets's MdbFeederInfo)."""
    lib = sample_library()
    pitch = FIELD["Feeder.Pitch"]

    def on(tape):
        return lib.options(pitch, {"Feeder.TapeTypeID": tape})

    assert on(1) == [(50, "0.5 mm"), (1, "1 mm"), (2, "2 mm"), (4, "4 mm"), (8, "8 mm")]  # 8mm paper
    assert dict(on(3))[201] == "8 mm (4 × 2)" and dict(on(3))[12] == "12 mm"
    assert dict(on(5))[12] == "12 mm (6 × 2)" and dict(on(5))[204] == "12 mm" and dict(on(5))[24] == "24 mm (12 × 2)"
    assert dict(on(4))[16] == "16 mm (8 × 2)" and on(6) == [] and on(None) == []
    assert lib.text("Feeder.Pitch", {"Feeder.TapeTypeID": 5, "Feeder.Pitch": 16}) == "16 mm (8 × 2)"
    assert lib.feeder_text({"Feeder.FdrTypeID": 1, "Feeder.TapeTypeID": 3, "Feeder.Pitch": 201}) == "12mm emboss 8 mm (4 × 2)"


def test_a_pitch_must_be_one_of_its_tape_width():
    lib, ch = sample_library(), Changes()
    d = _id(lib, "D-100")  # 12mm emboss, 8 mm
    lib.edit(ch, d, {"Feeder.TapeTypeID": 1})  # 8 mm is a pitch of 8mm paper too
    assert lib.problems(ch) == []
    lib.edit(ch, d, {"Feeder.Pitch": 201})  # 4 × 2 is not
    assert lib.problems(ch) == ["D-100: Feed pitch has no option 201"]
    ch.clear()
    lib.record(d).values["Feeder.Pitch"] = 201  # stored: only the tape width changes
    lib.edit(ch, d, {"Feeder.TapeTypeID": 1})
    assert lib.problems(ch) == ["D-100: Feed pitch has no option 201"]


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
