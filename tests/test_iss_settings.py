"""ISS settings live in the Phase 1 settings file under ``iss``."""

from __future__ import annotations

import json

import pytest

from panelimport.iss.settings import IssSettings
from panelimport.model.serialize import SerializationError
from panelimport.settings import Settings


def test_defaults_are_the_brief():
    s = IssSettings()
    assert s.validate() == []
    assert (s.panel_rotation, s.bottom_flip, s.clamp_offset_y, s.circuit_layout) == ("auto", "left-right", "auto", "nonmatrix")
    assert (s.pwb_thickness, s.back_height, s.angle_direction, s.angle_offset) == (1.6, 37.0, "ccw", 0.0)
    assert (s.header_completion, s.model_component_stubs, s.component_size) == ("zero", False, "zero")
    assert s.comment_attributes == ["DSC", "Description", "Comment"]
    assert (s.line_name, s.line_id, s.mark_name, s.traceability) == ("Line", 1, "BOCMARK01", "TwoDimensions")


def test_shared_file_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    phase1 = Settings(part_number_attribute="Detex_P/N")
    phase1.save(path)
    IssSettings(panel_rotation=90, clamp_offset_y=91.313, comment_attributes=["DSC"]).save(path)
    data = json.loads(path.read_text())
    assert data["part_number_attribute"] == "Detex_P/N" and data["iss"]["panel_rotation"] == 90
    # Phase 1 reads past the iss section and keeps it when it saves.
    loaded = Settings.load(path)
    assert loaded.part_number_attribute == "Detex_P/N"
    loaded.numbering_order = "serpentine"
    loaded.save(path)
    iss = IssSettings.load(path)
    assert (iss.panel_rotation, iss.clamp_offset_y, iss.comment_attributes) == (90, 91.313, ["DSC"])
    assert Settings.load(path).numbering_order == "serpentine"


def test_missing_file_or_section_gives_defaults(tmp_path):
    assert IssSettings.load(tmp_path / "none.json") == IssSettings()
    path = tmp_path / "settings.json"
    Settings().save(path)
    assert IssSettings.load(path) == IssSettings()


@pytest.mark.parametrize(
    "data, message",
    [
        ({"panel_rotation": 45}, "panel_rotation"),
        ({"panel_rotation": True}, "panel_rotation"),
        ({"bottom_flip": "up-down"}, "bottom_flip"),
        ({"clamp_offset_y": "half"}, "clamp_offset_y"),
        ({"clamp_offset_y": -1}, "clamp_offset_y"),
        ({"circuit_layout": "grid"}, "circuit_layout"),
        ({"traceability": "x"}, "traceability"),
        ({"pwb_thickness": 0}, "pwb_thickness"),
        ({"surprise": 1}, "unknown keys"),
    ],
)
def test_invalid_values_are_refused(data, message):
    with pytest.raises(SerializationError, match=message):
        IssSettings.from_dict(data)


def test_overrides():
    s = IssSettings().with_overrides(
        [
            "panel_rotation=270",
            "clamp_offset_y=auto",
            "model-component-stubs=yes",
            "line_id=2",
            "angle_offset=-1.5",
            "comment_attributes=Description, DSC",
            "pwb_id=ER F8",
        ]
    )
    assert (s.panel_rotation, s.clamp_offset_y, s.model_component_stubs, s.line_id) == (270, "auto", True, 2)
    assert (s.angle_offset, s.comment_attributes, s.pwb_id) == (-1.5, ["Description", "DSC"], "ER F8")
    assert IssSettings().with_overrides(["panel_rotation=auto"]).panel_rotation == "auto"
    assert IssSettings().with_overrides(["clamp_offset_y=91.313"]).clamp_offset_y == 91.313
    with pytest.raises(SerializationError, match="not a valid bool"):
        IssSettings().with_overrides(["model_component_stubs=maybe"])


def test_describe_lists_every_setting():
    keys = [k for k, _v in IssSettings().describe()]
    assert keys[0] == "pwb_id" and "traceability" in keys and len(keys) == 18
