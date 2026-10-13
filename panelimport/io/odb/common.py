"""Shared helpers for ODB++ files: units, record splitting and problem aggregation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from panelimport.model.issues import Issue, error, warning

MM_PER_INCH = 25.4


class Units(str, enum.Enum):
    MM = "MM"
    INCH = "INCH"

    @property
    def coord_scale(self) -> float:
        """Factor converting coordinates in these units to mm."""
        return 1.0 if self is Units.MM else MM_PER_INCH

    @property
    def symbol_scale(self) -> float:
        """Factor converting symbol dimensions (microns or mils) to mm."""
        return 0.001 if self is Units.MM else MM_PER_INCH / 1000.0


def parse_units(token: str) -> Units | None:
    t = token.strip().upper()
    if t == "MM":
        return Units.MM
    if t == "INCH":
        return Units.INCH
    return None


def split_record(line: str) -> tuple[str, str, str | None]:
    """Split ``<main> ; <attributes> ; ID=<id>`` into its three parts."""
    main, sep, rest = line.partition(";")
    if not sep:
        return main, "", None
    attrs = []
    rec_id = None
    for part in rest.split(";"):
        p = part.strip()
        if p.upper().startswith("ID="):
            rec_id = p[3:].strip()
        elif p:
            attrs.append(p)
    return main, ",".join(attrs), rec_id


def split_quoted(line: str) -> tuple[str, str, str]:
    """Split a line at its first and last single quote: (before, inside, after)."""
    first = line.find("'")
    last = line.rfind("'")
    if first < 0 or last <= first:
        return line, "", ""
    return line[:first], line[first + 1 : last], line[last + 1 :]


def yes_no(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().upper()
    if v in ("YES", "Y", "1", "TRUE"):
        return True
    if v in ("NO", "N", "0", "FALSE", ""):
        return False
    return None


@dataclass
class UnitsDirective:
    """The units a file declared, or the default that was assumed for it."""

    units: Units
    declared: bool


@dataclass
class FileProblems:
    """Aggregates repetitive problems in one file into a handful of issues."""

    path: str
    unknown: dict[str, list[int]] = field(default_factory=dict)
    malformed: list[tuple[int, str, str]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def unknown_record(self, record: str, line_no: int) -> None:
        self.unknown.setdefault(record, []).append(line_no)

    def bad_line(self, line_no: int, line: str, reason: str) -> None:
        self.malformed.append((line_no, line, reason))

    def add(self, issue: Issue) -> None:
        if issue.file is None:
            issue.file = self.path
        self.issues.append(issue)

    def bad_units(self, line_no: int, value: str) -> None:
        self.add(
            error(
                "unknown_units",
                f"Unrecognized units '{value}' at line {line_no}",
                file=self.path,
                subject=f"{self.path}:units",
            )
        )

    def to_issues(self) -> list[Issue]:
        out = list(self.issues)
        for record, lines in sorted(self.unknown.items()):
            count = len(lines)
            out.append(
                error(
                    "unknown_record",
                    f"Unknown record type '{record}' ({count} line{'s' if count != 1 else ''}, "
                    f"first at line {lines[0]})",
                    file=self.path,
                    subject=f"{self.path}:{record}",
                    data={"record": record, "count": count, "lines": lines[:20]},
                )
            )
        if self.malformed:
            line_no, line, reason = self.malformed[0]
            count = len(self.malformed)
            out.append(
                error(
                    "parse_error",
                    f"{count} malformed line{'s' if count != 1 else ''}; first at line {line_no}: "
                    f"{reason}: {line.strip()[:80]!r}",
                    file=self.path,
                    subject=f"{self.path}:parse",
                    data={"count": count},
                )
            )
        return out


def unknown_field_issue(path: str, block: str, names: list[str], *, blocking: bool) -> Issue:
    text = ", ".join(sorted(set(names)))
    make = error if blocking else warning
    return make(
        "unknown_field",
        f"Unrecognized field(s) in {block}: {text}",
        file=path,
        subject=f"{path}:{block}",
        data={"fields": sorted(set(names))},
    )
