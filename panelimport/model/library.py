"""The JaNets component database as records to browse and edit.

:mod:`panelimport.model.database` is the snapshot a project keeps (name, description,
package, size).  This is the database itself: every component with the settings the Juki
Component Database editor shows for it, and the changes the user has made here and not
saved yet (:class:`Changes`).  Reading and saving are in :mod:`panelimport.io.compolib`.

A component is one row of ``Compo`` plus one row in each per-machine table with the same
``CompoID`` (``Feeder``, ``Laser``, ``LaserGx10``, ``Expansion``, ``Inspection``, …).  The
machine sections are the KE-3010/3020's (``Gx10`` in the database) and the JM-10's
picking stroke, as the Juki editor shows them at Detex.

Only what is known is offered.  The units were checked against the Juki editor showing
the same record of ``DETEX_New.mdb`` (``101672-10`` and the component list):

* lengths are integers in 0.0001 mm (width 48140 = 4.814, picking stroke 2000 = 0.20,
  laser height -11650 = -1.16 on screen, where the editor cuts the third decimal);
* angles are integers in 1/80 degree (pre-rotate 2400 = 30; supply angles are 0, 7200
  and 21600).

The options are JaNets's own (version 1.4 of the Component Database, read 2026-11-17):
the lists its editor shows, in their order, the English names of
``Languages/en-US.xml``, and the value each one is stored as, from the tables JaNets
converts with (``Juki.Iss.Extension.Defines``) and how it reads and writes each column
(``Juki.Msdb.DatabaseAccess``).  They agree with every option seen in the editor's
screenshots.  Where JaNets stores a value it does not offer for the KE-3010/3020 (load
control, tray restore, RX-7 vision), the value keeps its name but is not offered;
a value JaNets has no name for is "Code n".  The nozzles are the KE-3010/3020's of
the Juki editor's nozzle table at Detex; :func:`nozzle_for` is JaNets's rule for the
nozzle of a size (``NozzleData.GetDefault``), and the vacuum is converted as JaNets does.

Settings whose unit or meaning could not be checked (offsets that are 0 everywhere, the
gripper nozzle data, vision data) are shown read-only or left out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from dataclasses import field as _field
from functools import cached_property

from panelimport.model.database import name_key

TEXT, NUMBER, CHOICE, FLAG = "text", "number", "choice", "flag"
EDITED, ADDED, DELETED = "edited", "new", "deleted"

#: Stored units per mm and per degree.
PER_MM = 10000
PER_DEGREE = 80
#: ``Feeder.FdrTypeID`` of tape.
TAPE = 1

NAME = "Compo.CompoName"
DESCRIPTION = "Compo.Description"
NAME_MAX = 60


@dataclass(frozen=True)
class Field:
    """One setting of a component: a column of a per-component table."""

    table: str
    column: str
    label: str
    kind: str = NUMBER
    scale: float = 1  # stored units per shown unit (numbers) …
    offset: float = 0  # … counted from this stored value
    decimals: int = 0
    unit: str = ""
    lo: float = 0.0
    hi: float = 0.0
    max_length: int = 0
    choices: Mapping[int, str] = _field(default_factory=dict)  # the options, in the Juki editor's order
    known: Mapping[int, str] = _field(default_factory=dict)  # named, kept, but not offered here
    lookup: str = ""  # names from a table of the database itself
    numbered: bool = False  # the options are numbers that are their own names (nozzles)
    per: str = ""  # the options depend on that setting's value …
    by: Mapping[object, Mapping[int, str]] = _field(default_factory=dict)  # … as given here
    read_only: bool = False
    when: tuple[str, int] | None = None  # only applies while that setting has that value
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.table}.{self.column}"

    def shown(self, raw):
        """The stored value as the editor shows it."""
        if self.kind == NUMBER:
            return 0.0 if raw is None else (raw - self.offset) / self.scale
        if self.kind == FLAG:
            return bool(raw)
        if self.kind == TEXT:
            return "" if raw is None else str(raw)
        return raw

    def stored(self, shown, like=None):
        """A shown value as it is stored; ``like`` is the value it replaces (a Yes/No
        column holds a bool, a byte column 0 or 1; an empty text stays NULL)."""
        if self.kind == NUMBER:
            return round(float(shown) * self.scale + self.offset)
        if self.kind == FLAG:
            return bool(shown) if isinstance(like, bool) else int(bool(shown))
        if self.kind == TEXT:
            text = str(shown).strip()
            return None if not text and like is None else text
        return shown


def number_text(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _mm(table: str, column: str, label: str, lo: float = 0.0, hi: float = 999.0, **kw) -> Field:
    return Field(table, column, label, NUMBER, scale=PER_MM, decimals=4, unit="mm", lo=lo, hi=hi, **kw)


def _degrees(table: str, column: str, label: str, **kw) -> Field:
    return Field(table, column, label, NUMBER, scale=PER_DEGREE, decimals=2, unit="°", lo=0.0, hi=359.99, **kw)


#: Axis speeds (JaNets's ``SpeedStandard``), in the order the Juki editor lists them.
_SPEEDS = {
    4: "Fast 2", 0: "Fast", 1: "Medium", 2: "Slow", 3: "Slow 2", 7: "FC speed",
    8: "Fast V1", 9: "Fast V2", 10: "Fast V3",
}  # fmt: skip
#: The speeds each list of the 3010-20 page offers (Fast V1-V3 only the 3010-20V/VA's).
_XY, _Z, _Z_V = (4, 0, 1, 2), (4, 0, 1, 2, 3, 7), (4, 0, 1, 2, 3, 7, 8, 9, 10)
_THETA_MEASURE, _THETA = (0, 1, 2), (0, 1, 2, 3)


def _speed(column: str, label: str, codes: tuple[int, ...]) -> Field:
    choices = {c: _SPEEDS[c] for c in codes}
    known = {c: name for c, name in _SPEEDS.items() if c not in choices}
    return Field("LaserGx10", column, label, CHOICE, choices=choices, known=known)


_TAPE_ONLY = ("Feeder.FdrTypeID", TAPE)
#: Feed pitches by tape width (``Feeder.TapeTypeID``): stored value → (pitch in mm, feeds
#: per component), as JaNets reads them.  A value means another feed on another tape:
#: 12 is 12 mm on 12 and 16 mm tape but 6 mm twice on 24 mm tape.  32 mm paper (6) has none.
_FEEDS: dict[int, dict[int, tuple[float, int]]] = {
    1: {50: (0.5, 1), 1: (1, 1), 2: (2, 1), 4: (4, 1), 8: (8, 1)},
    2: {50: (0.5, 1), 1: (1, 1), 2: (2, 1), 4: (4, 1), 8: (8, 1)},
    3: {2: (2, 1), 4: (4, 1), 8: (8, 1), 201: (4, 2), 12: (12, 1), 202: (6, 2), 206: (16, 1)},
    4: {4: (4, 1), 8: (8, 1), 201: (4, 2), 12: (12, 1), 202: (6, 2), 16: (8, 2), 208: (20, 1), 205: (24, 1),
        203: (28, 1), 207: (32, 1)},
    5: {4: (4, 1), 8: (8, 1), 204: (12, 1), 12: (6, 2), 16: (8, 2), 20: (10, 2), 24: (12, 2), 203: (28, 1),
        207: (32, 1)},
    7: {4: (4, 1), 8: (8, 1), 204: (12, 1), 12: (6, 2), 206: (16, 1), 16: (8, 2), 20: (10, 2), 205: (12, 2),
        24: (8, 3), 203: (14, 2), 28: (4, 7), 207: (16, 2), 32: (8, 4)},
    8: {4: (4, 1), 8: (8, 1), 12: (12, 1), 206: (16, 1), 208: (20, 1), 24: (12, 2), 28: (14, 2), 32: (16, 2),
        36: (18, 2), 40: (20, 2), 44: (22, 2)},
    9: {4: (4, 1), 8: (8, 1), 12: (12, 1), 206: (16, 1), 208: (20, 1), 24: (12, 2), 203: (14, 2), 32: (16, 2),
        36: (18, 2), 40: (20, 2), 209: (10, 4), 44: (22, 2), 48: (16, 3), 52: (13, 4), 56: (14, 4)},
    11: {50: (0.5, 1), 1: (1, 1), 2: (2, 1)},
    12: {4: (4, 1), 8: (8, 1), 12: (12, 1), 206: (16, 1), 208: (20, 1), 24: (12, 2), 203: (14, 2), 32: (16, 2),
         36: (18, 2), 40: (20, 2), 44: (22, 2), 48: (16, 3), 52: (13, 4), 56: (14, 4)},
}  # fmt: skip


def _pitch_text(pitch: float, feeds: int) -> str:
    """``8 mm (4 × 2)``: the feed per component, and the pitch fed that many times."""
    return f"{pitch * feeds:g} mm" if feeds == 1 else f"{pitch * feeds:g} mm ({pitch:g} × {feeds})"


_PITCHES = {tape: {code: _pitch_text(*feed) for code, feed in codes.items()} for tape, codes in _FEEDS.items()}
_REJECT = {0: "Trash box", 2: "IC collection belt", 3: "Protect"}
_REJECT_NOTE = "JaNets offers the IC collection belt for components with vision centering"
_LOAD_NOTE = "Load control also needs a load, which is set in the Juki Component Database"
#: The vacuum is stored as a count where 51 is 0 kPa (JaNets's ``VacuumConvertDbToIs``:
#: ``(stored − 51) × −760/204 × 0.1333`` kPa); 217 is the -82.437 kPa of most components.
_KPA_PER_STEP = -760 / 204 * 0.1333
#: The KE-3010/3020's laser nozzles and the component sizes they are for, in mm (the
#: nozzle table of the Juki editor at Detex).
NOZZLES: dict[int, tuple[float, float | None]] = {
    500: (0.45, 1.45), 501: (0.0, 0.45), 502: (0.45, 0.75), 503: (0.75, 1.45), 504: (1.1, 2.5), 505: (2.5, 4.0),
    506: (4.0, 7.0), 507: (7.0, 10.0), 508: (10.0, None), 509: (0.0, 0.3), 510: (0.75, 2.5), 511: (2.0, 4.0),
    512: (1.6, None), 521: (0.8, None),
}  # fmt: skip


def _nozzle_name(nozzle: int, low: float, high: float | None) -> str:
    if high is None:
        return f"{nozzle} ({low:g} mm and more)"
    return f"{nozzle} (up to {high:g} mm)" if not low else f"{nozzle} ({low:g}–{high:g} mm)"


_NOZZLE_NAMES = {nozzle: _nozzle_name(nozzle, *size) for nozzle, size in NOZZLES.items()}

FIELDS: tuple[Field, ...] = (
    # ------------------------------------------------------------------ component
    Field("Compo", "CompoName", "Component name", TEXT, max_length=NAME_MAX),
    Field("Compo", "Description", "Comment", TEXT, max_length=255),
    Field("Compo", "PkgType", "Package code", TEXT, read_only=True),
    Field("Compo", "PkgClassID", "Component type", CHOICE, lookup="pkg_class", read_only=True,
          known={120: "QFN", 601: "Insert", 602: "INS electrolytic capacitor", 700: "Odd shape"},
          note="Copy a component of the type you need; the type itself is changed in the Juki editor"),
    Field("Compo", "Rx7ComponentType", "Kind of shape", CHOICE, read_only=True, choices={
        1: "Chip component", 2: "Lead component", 3: "BGA component", 4: "Odd shape (without leads)",
        5: "Odd shape (with leads)", 6: "Odd shape (with balls)",
    }),  # fmt: skip
    Field("Feeder", "FdrTypeID", "Component packaging", CHOICE, lookup="feeder_type", read_only=True),
    _mm("Compo", "Width", "Width"),
    _mm("Compo", "Length", "Length"),
    _mm("Compo", "Height", "Height"),
    Field("Compo", "UsePackage", "Use", FLAG),
    _mm("Compo", "PackageWidth", "Width (PW)", when=("Compo.UsePackage", 1)),
    _mm("Compo", "PackageLength", "Length (PL)", when=("Compo.UsePackage", 1)),
    Field("Compo", "UseLaser", "Laser", FLAG, read_only=True),
    Field("Compo", "UseVision", "Vision", FLAG, read_only=True),
    Field("Compo", "GX4PriorityLV", "Centering preference", CHOICE,
          choices={0: "Auto", 1: "Laser priority", 2: "Vision priority"}, known={3: "RX-7 vision only"}),
    # ------------------------------------------------------------------ packaging style
    Field("Feeder", "TapeTypeID", "Tape width", CHOICE, lookup="tape_type", when=_TAPE_ONLY),
    Field("Feeder", "Pitch", "Feed pitch", CHOICE, per="Feeder.TapeTypeID", by=_PITCHES, when=_TAPE_ONLY,
          note="The pitches JaNets offers for the tape width"),
    _degrees("Feeder", "TapeAngle", "Supply angle", when=_TAPE_ONLY),
    Field("Feeder", "SpliceSensorUse", "Use of a splice sensor", CHOICE, choices={0: "If possible", 1: "No"},
          when=_TAPE_ONLY),
    Field("Feeder", "StickTypeID", "Stick type", CHOICE, numbered=True, read_only=True),
    Field("Feeder", "StickChangerType", "Stick feeder", CHOICE, read_only=True,
          choices={0: "None", 221: "MBF44 SOIC", 223: "MBF44 SOL"}),  # None: the stick type is used
    Field("Expansion", "ScrapTypeGx6", "2070-80", CHOICE, choices=_REJECT, known={1: "Tray restore"},
          note=_REJECT_NOTE),
    Field("Expansion", "ScrapType", "Other machine types", CHOICE, choices=_REJECT, known={1: "Tray restore"},
          note=_REJECT_NOTE),
    # ------------------------------------------------------------------ laser centering
    _mm("Laser", "LaserHeight", "Laser height", lo=-99.0, hi=99.0),
    # JaNets turns the 3 of Algorithm 3 into 101 when it reads it, and back when it writes.
    Field("Laser", "LaserAlgo", "Laser algorithm", CHOICE,
          choices={100: "Algorithm 0", 1: "Algorithm 1", 2: "Algorithm 2", 3: "Algorithm 3"}),
    _degrees("Laser", "GX4PreRotate", "Pre-rotate"),
    Field("LaserGx10", "Gx10LA", "Use", FLAG),
    Field("LaserGx10", "NozzleNo", "Nozzle No.", CHOICE, numbered=True, choices=_NOZZLE_NAMES,
          note="Picked from the size when the size changes, as the Juki editor does; it can then be changed"),
    Field("LaserGx10", "PumpVacuum", "Vacuum pump", NUMBER, scale=1 / _KPA_PER_STEP, offset=51, decimals=3,
          unit="kPa", lo=-101.308, hi=0.0),
    _speed("SpdXY", "XY", _XY),
    _speed("SpdPickDownZ", "Pick Z down", _Z),
    _speed("SpdPickUpZ", "Pick Z up", _Z),
    _speed("SpdPlaceDownZ", "3020/3020R place Z down", _Z),
    _speed("SpdPlaceUpZ", "3020/3020R place Z up", _Z),
    _speed("SpdPlaceDownZGx10V", "3010-20V/VA place Z down", _Z_V),
    _speed("SpdPlaceUpZGx10V", "3010-20V/VA place Z up", _Z_V),
    _speed("SpdThetaInLA", "Theta (measure)", _THETA_MEASURE),
    _speed("SpdTheta", "Theta (other)", _THETA),
    _mm("Laser", "Gx10LaserHeightLnc60", "Laser height", lo=-99.0, hi=99.0),
    Field("LaserGx10", "CompoShape", "Component shape", CHOICE, choices={
        0: "No definition", 2: "Corner square", 4: "Corner cut", 9: "PLCC", 99: "Cylinder", 10: "Flexible",
        7: "Flexible 2", 6: "Flexible 3",
    }),  # fmt: skip
    # ------------------------------------------------------------------ pick conditions
    Field("Expansion", "Retry", "Retry times", NUMBER, lo=0, hi=9),
    Field("Expansion", "PickPosAdjust", "Auto correct pick: mechanical", FLAG),
    Field("Expansion", "EtfPickPosAdjust", "Auto correct pick: electric", FLAG),
    Field("Expansion", "AutoTeach", "Auto teaching", FLAG),
    Field("Expansion", "FCTypePickGx10", "Control mode", CHOICE, choices={0: "Stroke"}, known={1: "Load"},
          note=_LOAD_NOTE),
    _mm("Expansion", "OverPickGx10", "Picking stroke", hi=99.0),
    Field("LaserGx10", "PickZ2StepUse", "Z two-step speed control", FLAG),
    _mm("LaserGx10", "PickZ2StepDown", "Down speed change height", hi=99.0, when=("LaserGx10.PickZ2StepUse", 1)),
    _mm("LaserGx10", "PickZ2StepUp", "Up speed change height", hi=99.0, when=("LaserGx10.PickZ2StepUse", 1)),
    _mm("Expansion", "OverPickJM10", "Picking stroke", hi=99.0),
    # ------------------------------------------------------------------ placement conditions
    Field("Expansion", "Test", "Trial", FLAG),
    Field("Expansion", "CompoCheck", "Release check", FLAG),
    Field("Expansion", "CompoLayer", "Component layer", CHOICE, choices={n: f"Layer {n}" for n in range(1, 8)}),
    Field("Expansion", "FCTypePlaceGx10", "Length or weight", CHOICE, choices={0: "Stroke"}, known={1: "Load"},
          note=_LOAD_NOTE),
    _mm("Expansion", "OverPlaceGx10", "Placing stroke", hi=99.0),
    Field("LaserGx10", "PlaceZ2StepUse", "Z two-step speed control", FLAG),
    _mm("LaserGx10", "PlaceZ2StepDown", "Down speed change height", hi=99.0, when=("LaserGx10.PlaceZ2StepUse", 1)),
    _mm("LaserGx10", "PlaceZ2StepUp", "Up speed change height", hi=99.0, when=("LaserGx10.PlaceZ2StepUse", 1)),
    # ------------------------------------------------------------------ check
    Field("Inspection", "ChipStandCheck", "Tombstone detection", CHOICE,
          choices={0: "No", 1: "Yes", 2: "If possible"}),
)
FIELD = {f.key: f for f in FIELDS}
#: Tables the settings are in, ``Compo`` first.
TABLES = tuple(dict.fromkeys(f.table for f in FIELDS))
#: Names read from the database: lookup → (table, id column, name column).
LOOKUPS = {
    "pkg_class": ("PkgClass", "PkgClassID", "EngClass"),
    "feeder_type": ("FeederType", "FdrTypeID", "FdrTypeEng"),
    "tape_type": ("Lookup", "TapeTypeID", "TapeType"),
}


@dataclass
class ComponentRecord:
    """A component as the database has it: stored values by ``Table.Column``."""

    compo_id: int
    values: dict[str, object] = _field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.values.get(NAME) or "").strip()


@dataclass
class Component:
    """A component as the window shows it: the record with the unsaved changes."""

    compo_id: int  # negative: not in the database yet
    values: dict[str, object]
    state: str = ""  # "", EDITED, ADDED or DELETED
    changed: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        return str(self.values.get(NAME) or "").strip()


@dataclass
class Changes:
    """What the user changed and has not saved."""

    updates: dict[int, dict[str, object]] = _field(default_factory=dict)  # id → stored values
    added: dict[int, int] = _field(default_factory=dict)  # new (negative) id → id of the record copied
    deleted: set[int] = _field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.updates or self.added or self.deleted)

    @property
    def edited(self) -> list[int]:
        return [i for i in self.updates if i not in self.added and i not in self.deleted]

    def summary(self) -> str:
        parts = [(len(self.edited), "edited"), (len(self.added), "new"), (len(self.deleted), "deleted")]
        return ", ".join(f"{n} {what}" for n, what in parts if n) or "no changes"

    def clear(self) -> None:
        self.updates.clear()
        self.added.clear()
        self.deleted.clear()


@dataclass
class ComponentLibrary:
    """Every component of the database at ``path`` as read at ``read_at``."""

    path: str = ""
    read_at: str = ""  # ISO 8601, local time
    records: list[ComponentRecord] = _field(default_factory=list)
    lookups: dict[str, dict[int, str]] = _field(default_factory=dict)
    fields: frozenset[str] = frozenset(FIELD)  # the settings this database has
    #: Components with data this program cannot copy or delete (vision elements, …): id → tables.
    nested: dict[int, list[str]] = _field(default_factory=dict)

    @cached_property
    def _by_id(self) -> dict[int, ComponentRecord]:
        return {r.compo_id: r for r in self.records}

    def record(self, compo_id: int) -> ComponentRecord | None:
        return self._by_id.get(compo_id)

    @cached_property
    def _codes(self) -> dict[str, list[int]]:
        codes: dict[str, set[int]] = {}
        for f in FIELDS:
            if f.kind == CHOICE:
                codes[f.key] = {v for r in self.records if isinstance(v := r.values.get(f.key), int)}
        return {key: sorted(found) for key, found in codes.items()}

    # ------------------------------------------------------------------ names of options
    def _named(self, f: Field, values: Mapping[str, object] | None) -> Mapping[int, str]:
        """The options of ``f`` with their names; ``values`` are the component's, for a
        choice whose options depend on another setting."""
        if f.per:
            return f.by.get((values or {}).get(f.per), {})
        return self.lookups.get(f.lookup, {}) if f.lookup else f.choices

    def label(self, f: Field, code, values: Mapping[str, object] | None = None) -> str:
        if code is None:
            return ""
        names = self._named(f, values)
        if code in names:
            return names[code]
        if code in f.known:
            return f.known[code]
        return str(code) if f.numbered else f"Code {code}"

    def options(self, f: Field, values: Mapping[str, object] | None = None) -> list[tuple[int, str]]:
        """What a choice can be set to: JaNets's options in its order, then the values
        without a name that some component of the database already uses.  ``values`` are
        the component's (a feed pitch's options are its tape width's)."""
        named = self._named(f, values)
        if f.per:
            codes = list(named)
        else:
            used = set(self._codes.get(f.key, ())) - set(named) - set(f.known)
            codes = sorted(set(named) | used) if f.lookup else [*named, *sorted(used)]
        return [(c, self.label(f, c, values)) for c in codes]

    def text(self, key: str, values: Mapping[str, object]) -> str:
        """A setting as text (for the list)."""
        f, raw = FIELD[key], values.get(key)
        if raw is None:
            return ""
        if f.kind == NUMBER:
            return number_text(f.shown(raw), f.decimals)
        if f.kind == FLAG:
            return "Yes" if raw else "No"
        if f.kind == CHOICE:
            return self.label(f, raw, values)
        return str(raw).strip()

    def feeder_text(self, values: Mapping[str, object]) -> str:
        """The feeder as the Juki list shows it: tape and pitch, or the stick feeder."""
        if values.get("Feeder.FdrTypeID") == TAPE:
            return " ".join(t for t in (self.text("Feeder.TapeTypeID", values), self.text("Feeder.Pitch", values)) if t)
        return self.text("Feeder.StickChangerType", values) if values.get("Feeder.StickChangerType") else ""

    @staticmethod
    def centering_text(values: Mapping[str, object]) -> str:
        """Laser centering on the 3010-20 and its nozzle, e.g. ``L(504)``."""
        if not values.get("LaserGx10.Gx10LA"):
            return ""
        nozzle = values.get("LaserGx10.NozzleNo")
        return f"L({nozzle})" if nozzle is not None else "L"

    # ------------------------------------------------------------------ unsaved changes
    def base(self, changes: Changes, compo_id: int) -> dict[str, object]:
        """The values ``compo_id`` has without its own unsaved edits: the record's, or
        for a new component the record's it is a copy of."""
        record = self.record(changes.added.get(compo_id, compo_id))
        return dict(record.values) if record is not None else {}

    def component(self, changes: Changes, compo_id: int) -> Component | None:
        base = self.base(changes, compo_id)
        if not base:
            return None
        updates = changes.updates.get(compo_id, {})
        if compo_id in changes.added:
            state = ADDED
        elif compo_id in changes.deleted:
            state = DELETED
        else:
            state = EDITED if updates else ""
        return Component(compo_id, {**base, **updates}, state, frozenset(updates))

    def components(self, changes: Changes) -> list[Component]:
        """Every component as it is with the unsaved changes; new ones last."""
        ids = [r.compo_id for r in self.records] + sorted(changes.added, reverse=True)
        return [c for c in (self.component(changes, i) for i in ids) if c is not None]

    def edit(self, changes: Changes, compo_id: int, values: Mapping[str, object]) -> None:
        """Set stored values of ``compo_id``; a value equal to the database's is no change."""
        base = self.base(changes, compo_id)
        updates = dict(changes.updates.get(compo_id, {}))
        for key, value in values.items():
            if key not in self.fields or FIELD[key].read_only:
                raise ValueError(f"{key} cannot be changed here")
            # A new component always carries its name (the record it copies has another).
            if value == base.get(key) and not (key == NAME and compo_id in changes.added):
                updates.pop(key, None)
            else:
                updates[key] = value
        if updates:
            changes.updates[compo_id] = updates
        else:
            changes.updates.pop(compo_id, None)

    def add_copy(self, changes: Changes, source_id: int, name: str) -> int:
        """A new component named ``name`` that is a copy of ``source_id`` as it is shown
        (with its unsaved edits); its id is negative until it is saved."""
        if self.component(changes, source_id) is None:
            raise ValueError(f"There is no component {source_id} to copy")
        new_id = min(changes.added, default=0) - 1
        changes.added[new_id] = changes.added.get(source_id, source_id)
        changes.updates[new_id] = {**changes.updates.get(source_id, {}), NAME: name.strip()}
        return new_id

    def apply_defaults(self, changes: Changes, compo_id: int) -> None:
        """Give ``compo_id`` the :data:`DEFAULTS` and the nozzle JaNets picks for its size
        (the settings this database has and that apply to its packaging)."""
        values = self.component(changes, compo_id).values
        stored = {
            key: FIELD[key].stored(shown, values.get(key))
            for key, shown in DEFAULTS.items()
            if key in self.fields and _applies(FIELD[key], values)
        }
        picked = nozzle_for(values)
        if picked is not None:
            stored |= {k: v for k, v in zip(("LaserGx10.NozzleNo", "LaserGx10.PumpVacuum"), picked) if k in self.fields}
        self.edit(changes, compo_id, stored)

    def delete(self, changes: Changes, compo_id: int) -> None:
        """Delete ``compo_id`` when the changes are saved; a new component just goes."""
        changes.updates.pop(compo_id, None)
        if changes.added.pop(compo_id, None) is None:
            changes.deleted.add(compo_id)

    @staticmethod
    def revert(changes: Changes, compo_id: int) -> None:
        """Drop the unsaved changes to ``compo_id`` (a new component goes)."""
        changes.updates.pop(compo_id, None)
        changes.added.pop(compo_id, None)
        changes.deleted.discard(compo_id)

    def name_taken(self, changes: Changes, name: str, but: int | None = None) -> bool:
        """Whether another component will have ``name`` (ignoring case, as Jet does)."""
        key = name_key(name)
        return any(
            c.compo_id != but and c.state != DELETED and name_key(c.name) == key for c in self.components(changes)
        )

    def problems(self, changes: Changes) -> list[str]:
        """Why ``changes`` cannot be saved; empty when they can."""
        found: list[str] = []
        seen: dict[str, str] = {}
        for c in self.components(changes):
            if c.state == DELETED:
                if c.compo_id in self.nested:
                    found.append(f"{c.name} has {_tables(self.nested[c.compo_id])} data and cannot be deleted here")
                continue
            label = c.name or f"component {c.compo_id}"
            if not c.name:
                found.append("A component has no name")
            elif len(c.name) > NAME_MAX:
                found.append(f"{c.name}: the name is longer than {NAME_MAX} characters")
            if name_key(c.name) in seen:
                found.append(f"Two components are named {c.name}")
            seen.setdefault(name_key(c.name), c.name)
            if c.state == ADDED and changes.added[c.compo_id] in self.nested:
                source = self.record(changes.added[c.compo_id])
                found.append(
                    f"{label} is a copy of {source.name}, which has {_tables(self.nested[source.compo_id])} data "
                    "and cannot be copied here"
                )
            # A choice whose options depend on a changed setting is checked again.
            dependent = {f.key for f in FIELDS if f.per in c.changed and f.key in self.fields and _applies(f, c.values)}
            for key in sorted(c.changed | dependent):
                f, value = FIELD.get(key), c.values.get(key)
                if key not in c.changed and value is None:
                    continue
                if f is None or key not in self.fields or f.read_only:
                    found.append(f"{label}: {key} cannot be changed here")
                elif key == NAME:
                    continue  # checked above
                elif f.kind == TEXT and f.max_length and len(str(value or "")) > f.max_length:
                    found.append(f"{label}: {f.label} is longer than {f.max_length} characters")
                elif f.kind == NUMBER and not f.lo <= round(f.shown(value), f.decimals) <= f.hi:
                    found.append(
                        f"{label}: {f.label} {number_text(f.shown(value), f.decimals)} is outside "
                        f"{number_text(f.lo, f.decimals)} to {number_text(f.hi, f.decimals)}"
                    )
                elif f.kind == CHOICE and value not in {code for code, _ in self.options(f, c.values)}:
                    found.append(f"{label}: {f.label} has no option {value}")
        return found

    def expected(self, changes: Changes, ids: Mapping[int, int]) -> dict[int, dict[str, object]]:
        """What the database must hold once ``changes`` are saved: stored values by the
        component's id, ``ids`` giving the ids the new components got."""
        return {
            ids.get(c.compo_id, c.compo_id): c.values for c in self.components(changes) if c.state != DELETED
        }


def _tables(names: Iterable[str]) -> str:
    return ", ".join(sorted(names))


# ---------------------------------------------------------------------- the nozzle for a size
#: What JaNets adds to the shorter side for some component types (``ComponentData.ContactSize``),
#: in 0.0001 mm: a MELF touches the nozzle 0.5 mm wider, an SOP 1 mm narrower, …
_CONTACT = {
    3: 5000, 6: -7000, 11: 2500, 12: -23000, 101: -10000, 102: -30000, 103: -23000, 105: -20000, 106: -50000,
    107: -30000, 109: -10000, 110: -10000, 251: -30000, 301: -130000, 302: -130000, 303: -130000,
}  # fmt: skip
#: The default nozzle for 0.45 to 1.45 mm is 500 (JaNets can also be set to 502/503 instead);
#: Detex has it on 500: 84 components of that size are on 500, one on 503 and none on 502.
NOZZLE_500 = True
_MELF, _GAASFET, _OTHER, _INSERT = 3, 13, 999, (601, 602)


def _short_side(width, length) -> int:
    return min(width, length) if width is not None and length is not None else 0


def nozzle_for(values: Mapping[str, object]) -> tuple[int, int] | None:
    """The laser nozzle JaNets picks for a component of this size on the KE-3010/3020,
    with its pump vacuum as stored: ``NozzleData.GetDefault`` for laser centering.
    ``None`` when it picks none (a GaAsFET, "Other") or the size it needs is not all
    there yet (JaNets would take a missing package size as 0 mm)."""
    width, length = values.get("Compo.Width"), values.get("Compo.Length")
    kind = values.get("Compo.PkgClassID")
    if not width or not length or kind in (_GAASFET, _OTHER):
        return None
    package = _short_side(values.get("Compo.PackageWidth"), values.get("Compo.PackageLength"))
    if not package and (kind in _INSERT or values.get("Compo.UsePackage") == 1):
        return None
    short = package if kind in _INSERT else min(width, length)
    contact = package if kind in _INSERT or values.get("Compo.UsePackage") == 1 else min(width, length)
    contact += _CONTACT.get(kind, 0)
    vacuum, melf_vacuum = _vacuum(-82.437), _vacuum(-78.464)
    if short < 2500:
        return 509, vacuum
    if kind == _MELF and 7500 <= short < 20000:
        return 510, melf_vacuum
    if kind == _MELF and 20000 <= short < 40000:
        return 511, melf_vacuum
    if 4500 <= contact < 14500:
        return (500 if NOZZLE_500 else 502 if contact < 7500 else 503), vacuum
    below = ((4500, 501), (25000, 504), (40000, 505), (70000, 506), (100000, 507))
    return next((nozzle for top, nozzle in below if contact < top), 508), vacuum


def _vacuum(kpa: float) -> int:
    return FIELD["LaserGx10.PumpVacuum"].stored(kpa)


def _fastest(key: str) -> int:
    """A speed's fastest option: the first the Juki editor lists."""
    return next(iter(FIELD[key].choices))


_SPEED_KEYS = [f.key for f in FIELDS if f.table == "LaserGx10" and f.column.startswith("Spd")]
#: Detex's settings for a new component, as shown (mm, degrees, kPa, option codes).
DEFAULTS: dict[str, object] = {
    "Expansion.ScrapType": 0, "Expansion.ScrapTypeGx6": 0,  # rejects to the trash box
    "Feeder.TapeAngle": 0.0,
    "LaserGx10.Gx10LA": True, "Laser.LaserHeight": -0.5, "Laser.Gx10LaserHeightLnc60": -0.5,
    "Laser.LaserAlgo": 1, "Laser.GX4PreRotate": 30.0, "LaserGx10.PumpVacuum": -82.437,
    **{key: _fastest(key) for key in _SPEED_KEYS},
    "LaserGx10.CompoShape": 2,  # corner square
    "Expansion.Retry": 1, "Expansion.OverPickGx10": 0.2,
    "Expansion.PickPosAdjust": False, "Expansion.EtfPickPosAdjust": True,  # auto correct pick: electric
    "Expansion.CompoLayer": 4, "Expansion.OverPlaceGx10": 0.5,
}  # fmt: skip


def _applies(f: Field, values: Mapping[str, object]) -> bool:
    """Whether ``f`` is a setting of a component with ``values`` (see ``Field.when``)."""
    return f.when is None or values.get(f.when[0]) == f.when[1]
