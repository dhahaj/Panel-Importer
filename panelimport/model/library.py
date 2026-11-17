"""The JaNets component database as records to browse and edit.

:mod:`panelimport.model.database` is the snapshot a project keeps (name, description,
package, size).  This is the database itself: every component with the settings the Juki
Component Database editor shows for it, and the changes the user has made here and not
saved yet (:class:`Changes`).  Reading and saving are in :mod:`panelimport.io.compolib`.

A component is one row of ``Compo`` plus one row in each per-machine table with the same
``CompoID`` (``Feeder``, ``Laser``, ``LaserGx10``, ``Expansion``, ``Inspection``, …).  The
machine sections are the KE-3010/3020's (``Gx10`` in the database) and the JM-10's
picking stroke, as the Juki editor shows them at Detex.

Only what is known is offered.  Every unit and option name below was checked against
the Juki editor showing the same record of ``DETEX_New.mdb`` (``101672-10`` and the
component list), and is marked where it was not:

* lengths are integers in 0.0001 mm (width 48140 = 4.814, picking stroke 2000 = 0.20,
  laser height -11650 = -1.16 on screen, where the editor cuts the third decimal);
* angles are integers in 1/80 degree (pre-rotate 2400 = 30; supply angles are 0, 7200
  and 21600);
* an option is offered when its name is confirmed or when some component of the
  database already uses it.  Names worked out but not seen on screen say
  "(unconfirmed)"; options with no known name are "Code n";
* settings whose unit or meaning could not be checked (offsets that are 0 everywhere,
  the vacuum, the gripper nozzle data, vision data) are shown read-only or left out.
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
    scale: int = 1  # stored units per shown unit (numbers)
    decimals: int = 0
    unit: str = ""
    lo: float = 0.0
    hi: float = 0.0
    max_length: int = 0
    choices: Mapping[int, str] = _field(default_factory=dict)  # names seen in the Juki editor
    unconfirmed: Mapping[int, str] = _field(default_factory=dict)  # names worked out, not seen
    lookup: str = ""  # names from a table of the database itself
    numbered: bool = False  # the options are numbers that are their own names (nozzles)
    read_only: bool = False
    when: tuple[str, int] | None = None  # only applies while that setting has that value
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.table}.{self.column}"

    def shown(self, raw):
        """The stored value as the editor shows it."""
        if self.kind == NUMBER:
            return 0.0 if raw is None else raw / self.scale
        if self.kind == FLAG:
            return bool(raw)
        if self.kind == TEXT:
            return "" if raw is None else str(raw)
        return raw

    def stored(self, shown, like=None):
        """A shown value as it is stored; ``like`` is the value it replaces (a Yes/No
        column holds a bool, a byte column 0 or 1; an empty text stays NULL)."""
        if self.kind == NUMBER:
            return round(float(shown) * self.scale)
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


def _speed(column: str, label: str) -> Field:
    # 4 = Fast 2 and 0 = Fast on the 3010-20 page, 2 = Slow on the fluxer's; 1 lies between.
    return Field(
        "LaserGx10", column, label, CHOICE, choices={0: "Fast", 2: "Slow", 4: "Fast 2"}, unconfirmed={1: "Medium"}
    )


_TAPE_ONLY = ("Feeder.FdrTypeID", TAPE)
#: Feed pitches: the pitch in mm; 201 is the 12 mm tape's "8mm(4*2)".
_PITCHES = {n: f"{n} mm ({n} × 1)" for n in (1, 2, 4, 8, 12, 16, 20, 24, 28, 32)} | {201: "8 mm (4 × 2)"}

FIELDS: tuple[Field, ...] = (
    # ------------------------------------------------------------------ component
    Field("Compo", "CompoName", "Component name", TEXT, max_length=NAME_MAX),
    Field("Compo", "Description", "Comment", TEXT, max_length=255),
    Field("Compo", "PkgType", "Package code", TEXT, read_only=True),
    Field("Compo", "PkgClassID", "Component type", CHOICE, lookup="pkg_class", read_only=True,
          note="Copy a component of the type you need; the type itself is changed in the Juki editor"),
    Field("Compo", "Rx7ComponentType", "Kind of shape", CHOICE, choices={1: "Chip component", 2: "Lead component"},
          read_only=True),
    Field("Feeder", "FdrTypeID", "Component packaging", CHOICE, lookup="feeder_type", read_only=True),
    _mm("Compo", "Width", "Width"),
    _mm("Compo", "Length", "Length"),
    _mm("Compo", "Height", "Height"),
    Field("Compo", "UsePackage", "Use", FLAG),
    _mm("Compo", "PackageWidth", "Width (PW)", when=("Compo.UsePackage", 1)),
    _mm("Compo", "PackageLength", "Length (PL)", when=("Compo.UsePackage", 1)),
    Field("Compo", "UseLaser", "Laser", FLAG, read_only=True),
    Field("Compo", "UseVision", "Vision", FLAG, read_only=True),
    Field("Compo", "GX4PriorityLV", "Centering preference", CHOICE, choices={0: "Auto"}),
    # ------------------------------------------------------------------ packaging style
    Field("Feeder", "TapeTypeID", "Tape width", CHOICE, lookup="tape_type", when=_TAPE_ONLY),
    Field("Feeder", "Pitch", "Feed pitch", CHOICE, choices=_PITCHES, when=_TAPE_ONLY,
          note="Which pitches a tape width allows is not checked here"),
    _degrees("Feeder", "TapeAngle", "Supply angle", when=_TAPE_ONLY),
    Field("Feeder", "SpliceSensorUse", "Use of a splice sensor", CHOICE, choices={0: "If possible"},
          unconfirmed={1: "No"}, when=_TAPE_ONLY),
    Field("Feeder", "StickTypeID", "Stick type", CHOICE, numbered=True, read_only=True),
    Field("Feeder", "StickChangerType", "Stick feeder", CHOICE, choices={221: "MBF44 SOIC", 223: "MBF44 SOL"},
          read_only=True),
    Field("Expansion", "ScrapTypeGx6", "2070-80", CHOICE, choices={0: "Trash box"}),
    Field("Expansion", "ScrapType", "Other machine types", CHOICE, choices={0: "Trash box"}),
    # ------------------------------------------------------------------ laser centering
    _mm("Laser", "LaserHeight", "Laser height", lo=-99.0, hi=99.0),
    Field("Laser", "LaserAlgo", "Laser algorithm", CHOICE, choices={1: "Algorithm 1"}, unconfirmed={2: "Algorithm 2"}),
    _degrees("Laser", "GX4PreRotate", "Pre-rotate"),
    Field("LaserGx10", "Gx10LA", "Use", FLAG),
    Field("LaserGx10", "NozzleNo", "Nozzle No.", CHOICE, numbered=True,
          note="The nozzles some component of the database already uses"),
    Field("LaserGx10", "PumpVacuum", "Vacuum pump (stored value)", NUMBER, read_only=True,
          note="The Juki editor shows this as a pressure (217 as -82.436); the conversion is not known"),
    _speed("SpdXY", "XY"),
    _speed("SpdPickDownZ", "Pick Z down"),
    _speed("SpdPickUpZ", "Pick Z up"),
    _speed("SpdPlaceDownZ", "3020/3020R place Z down"),
    _speed("SpdPlaceUpZ", "3020/3020R place Z up"),
    _speed("SpdPlaceDownZGx10V", "3010-20V/VA place Z down"),
    _speed("SpdPlaceUpZGx10V", "3010-20V/VA place Z up"),
    _speed("SpdThetaInLA", "Theta (measure)"),
    _speed("SpdTheta", "Theta (other)"),
    _mm("Laser", "Gx10LaserHeightLnc60", "Laser height", lo=-99.0, hi=99.0),
    Field("LaserGx10", "CompoShape", "Component shape", CHOICE, choices={2: "Corner square"}),
    # ------------------------------------------------------------------ pick conditions
    Field("Expansion", "Retry", "Retry times", NUMBER, lo=0, hi=9),
    Field("Expansion", "PickPosAdjust", "Auto correct pick: mechanical", FLAG),
    Field("Expansion", "EtfPickPosAdjust", "Auto correct pick: electric", FLAG),
    Field("Expansion", "AutoTeach", "Auto teaching", FLAG),
    Field("Expansion", "FCTypePickGx10", "Control mode", CHOICE, choices={0: "Stroke"}),
    _mm("Expansion", "OverPickGx10", "Picking stroke", hi=99.0),
    Field("LaserGx10", "PickZ2StepUse", "Z two-step speed control", FLAG),
    _mm("LaserGx10", "PickZ2StepDown", "Down speed change height", hi=99.0, when=("LaserGx10.PickZ2StepUse", 1)),
    _mm("LaserGx10", "PickZ2StepUp", "Up speed change height", hi=99.0, when=("LaserGx10.PickZ2StepUse", 1)),
    _mm("Expansion", "OverPickJM10", "Picking stroke", hi=99.0),
    # ------------------------------------------------------------------ placement conditions
    Field("Expansion", "Test", "Trial", FLAG),
    Field("Expansion", "CompoCheck", "Release check", FLAG),
    Field("Expansion", "CompoLayer", "Component layer", CHOICE, choices={4: "Layer 4"}),
    Field("Expansion", "FCTypePlaceGx10", "Length or weight", CHOICE, choices={0: "Stroke"}),
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
    def label(self, f: Field, code) -> str:
        if code is None:
            return ""
        names = self.lookups.get(f.lookup, {}) if f.lookup else f.choices
        if code in names:
            return names[code]
        if code in f.unconfirmed:
            return f"{f.unconfirmed[code]} (unconfirmed)"
        return str(code) if f.numbered else f"Code {code}"

    def options(self, f: Field) -> list[tuple[int, str]]:
        """What a choice can be set to: the options with a confirmed name and the ones
        some component of the database already uses."""
        named = self.lookups.get(f.lookup, {}) if f.lookup else f.choices
        codes = sorted(set(named) | set(self._codes.get(f.key, ())))
        return [(c, self.label(f, c)) for c in codes]

    def text(self, key: str, values: Mapping[str, object]) -> str:
        """A setting as text (for the list)."""
        f, raw = FIELD[key], values.get(key)
        if raw is None:
            return ""
        if f.kind == NUMBER:
            return number_text(raw / f.scale, f.decimals)
        if f.kind == FLAG:
            return "Yes" if raw else "No"
        if f.kind == CHOICE:
            return self.label(f, raw)
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
            for key in sorted(c.changed):
                f, value = FIELD.get(key), c.values[key]
                if f is None or key not in self.fields or f.read_only:
                    found.append(f"{label}: {key} cannot be changed here")
                elif key == NAME:
                    continue  # checked above
                elif f.kind == TEXT and f.max_length and len(str(value or "")) > f.max_length:
                    found.append(f"{label}: {f.label} is longer than {f.max_length} characters")
                elif f.kind == NUMBER and not f.lo * f.scale <= value <= f.hi * f.scale:
                    found.append(
                        f"{label}: {f.label} {number_text(value / f.scale, f.decimals)} is outside "
                        f"{number_text(f.lo, f.decimals)} to {number_text(f.hi, f.decimals)}"
                    )
                elif f.kind == CHOICE and value not in {code for code, _ in self.options(f)}:
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
