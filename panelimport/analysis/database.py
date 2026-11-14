"""What the component database says about an analysis's components.

Free of Qt, so the components table, the CSV, the inspector and the report show the
same values: each part's record, whether the database has it, and its size by the
precedence of :func:`panelimport.model.database.with_database`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from panelimport.analysis.edits import Part, shown_values
from panelimport.analysis.result import PanelAnalysis
from panelimport.model.database import FOUND, MISSING, NOT_LOOKED_UP, DatabasePart, component_name, with_database
from panelimport.model.issues import Issue, info
from panelimport.model.panel import SIZE_FIELDS


@dataclass
class PartDatabase:
    record: DatabasePart | None = None
    state: str = ""  # "" (no database read), FOUND, MISSING or NOT_LOOKED_UP
    sizes: dict[str, float] = field(default_factory=dict)  # as written: edit > database > export
    from_database: set[str] = field(default_factory=set)  # the sizes taken from the database


def part_database(a: PanelAnalysis, part: Part) -> PartDatabase:
    values = shown_values(a, part)
    size = tuple(values[f] for f in SIZE_FIELDS)
    db = a.decisions.component_database
    name = component_name(part)
    if db is None or not name:
        return PartDatabase(sizes=dict(zip(SIZE_FIELDS, size)))
    record = db.find(name)
    edited = [f for f in SIZE_FIELDS if part.edit is not None and getattr(part.edit, f) is not None]
    sized, used = with_database(size, edited, record)
    return PartDatabase(record, db.state(name), dict(zip(SIZE_FIELDS, sized)), used)


def placed_names(a: PanelAnalysis) -> dict[str, list[str]]:
    """Each component name the program places, with its designators."""
    users: dict[str, list[str]] = {}
    for p in a.placements:
        name = component_name(p)
        if name:
            users.setdefault(name, []).append(p.designator)
    return users


def database_summary(a: PanelAnalysis) -> str:
    """"DETEX.mdb, read 2026-11-14 10:02:00: 19 of 35 components found", or "" without one."""
    db = a.decisions.component_database
    if db is None:
        return ""
    names = placed_names(a)
    found = sum(1 for name in names if db.state(name) == FOUND)
    return f"{db.label}: {found} of {len(names)} components found"


def database_issues(a: PanelAnalysis) -> list[Issue]:
    """The components the program places that the database does not have (JaNets needs
    a record for each), and those it was never asked about."""
    db = a.decisions.component_database
    if db is None:
        return []
    issues = []
    unchecked = []
    for name, designators in placed_names(a).items():
        state = db.state(name)
        if state == MISSING:
            listed = ", ".join(designators[:6]) + (", …" if len(designators) > 6 else "")
            issues.append(
                info(
                    "not_in_database",
                    f"{name} ({listed}) is not in the component database ({db.label}); JaNets needs a record for it",
                    designator=designators[0],
                    subject=name,
                )
            )
        elif state == NOT_LOOKED_UP:
            unchecked.append(name)
    if unchecked:
        issues.append(
            info(
                "database_not_looked_up",
                f"{len(unchecked)} component(s) were not looked up in the component database ({db.label}): "
                f"{', '.join(unchecked[:8])}{', …' if len(unchecked) > 8 else ''}. Update from the database",
                subject="database",
            )
        )
    return issues
