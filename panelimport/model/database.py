"""Component records from the JaNets component database (table ``Compo``).

The database is read in Phase 1 (:mod:`panelimport.io.compodb`); the project keeps a
snapshot of what it said about the project's components, so Phase 2 never opens it.
A component is looked up by the name JaNets looks up: its part number, else its part
name, stripped and compared case-insensitively (as Jet compares text).

Sizes are in mm in the machine's frame (as JaNets turns the part); 0 means unknown.
Per dimension, a size edited in Phase 1 wins, then the database's, then the export's.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property

#: Component size fields (mm, 0 = unknown); :mod:`panelimport.model.panel` uses them too.
SIZE_FIELDS = ("width", "length", "height")
#: What the database says about a component name.
FOUND, MISSING, NOT_LOOKED_UP = "found", "missing", "not looked up"


@dataclass
class DatabasePart:
    """One ``Compo`` record."""

    name: str = ""  # CompoName: the Detex part number
    description: str = ""
    pkg_type: str = ""  # Juki package (tape) name, e.g. "1206"; not the footprint
    width: float = 0.0
    length: float = 0.0
    height: float = 0.0


@dataclass
class ComponentDatabase:
    """The component database as read at ``read_at``.

    ``whole`` (right after a read, never saved): ``parts`` is every record, so any other
    name is missing.  Otherwise (saved in a project) ``parts`` are the records found
    for the project's components and ``missing`` the names not found; a name in
    neither was not looked up."""

    path: str = ""
    read_at: str = ""  # ISO 8601, local time
    parts: list[DatabasePart] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    whole: bool = False

    @cached_property
    def _index(self) -> dict[str, DatabasePart]:
        index: dict[str, DatabasePart] = {}
        for p in self.parts:
            index.setdefault(name_key(p.name), p)
        return index

    @cached_property
    def _missing(self) -> frozenset[str]:
        return frozenset(name_key(n) for n in self.missing)

    def find(self, name: str) -> DatabasePart | None:
        return self._index.get(name_key(name)) if name_key(name) else None

    def state(self, name: str) -> str:
        key = name_key(name)
        if key in self._index:
            return FOUND
        return MISSING if self.whole or key in self._missing else NOT_LOOKED_UP

    def for_names(self, names: Iterable[str]) -> ComponentDatabase:
        """What this database says about ``names``: their records and the names it
        does not have (names it never looked up are left out)."""
        parts: dict[str, DatabasePart] = {}
        missing: dict[str, str] = {}
        for name in names:
            key = name_key(name)
            if not key:
                continue
            part = self._index.get(key)
            if part is not None:
                parts.setdefault(key, part)
            elif self.whole or key in self._missing:
                missing.setdefault(key, name.strip())
        return ComponentDatabase(
            path=self.path,
            read_at=self.read_at,
            parts=sorted(parts.values(), key=lambda p: name_key(p.name)),
            missing=sorted(missing.values(), key=name_key),
        )

    @property
    def label(self) -> str:
        """The database's file name and when it was read, for messages."""
        name = self.path.replace("\\", "/").rsplit("/", 1)[-1] or "the component database"
        return f"{name}, read {self.read_at.replace('T', ' ')}" if self.read_at else name


def name_key(name: str) -> str:
    return (name or "").strip().upper()


def component_name(part) -> str:
    """The component name a program carries for ``part`` (and JaNets looks up): its
    part number, else its part name."""
    return (part.part_number or "").strip() or (part.part_name or "").strip()


def with_database(
    size: tuple[float, float, float], edited: Iterable[str], record: DatabasePart | None
) -> tuple[tuple[float, float, float], set[str]]:
    """``size`` with the database's dimensions, and which dimensions came from it.

    Per dimension: an edited value (> 0) stays, else the database's (> 0), else the
    value given (the export's, or an edit's 0)."""
    edited = set(edited)
    out, used = [], set()
    for f, value in zip(SIZE_FIELDS, size):
        db = getattr(record, f) if record is not None else 0.0
        if (f in edited and value > 0) or not db > 0:
            out.append(value)
        else:
            out.append(db)
            used.add(f)
    return (out[0], out[1], out[2]), used
