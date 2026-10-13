"""Issues reported by parsing and analysis.

Every inconsistency is reported as an :class:`Issue` instead of being guessed away.
Errors block *Confirm panel*; warnings need an acknowledgement, which is saved with
the project; info items need nothing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]

    @property
    def label(self) -> str:
        return self.value.upper()


IssueKey = tuple[str, "str | None", "int | None", "str | None"]


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    designator: str | None = None
    circuit: int | None = None
    # Panel-frame location in mm, used by the GUI to zoom to the issue.
    location: tuple[float, float] | None = None
    # Source file inside the ODB++ export, when the issue comes from parsing.
    file: str | None = None
    # Extra identification for acknowledgement when designator/circuit are not enough.
    subject: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> IssueKey:
        """Identifies the issue across re-analysis and save/reopen (for acknowledgements)."""
        return (self.code, self.designator, self.circuit, self.subject)

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    @property
    def is_warning(self) -> bool:
        return self.severity is Severity.WARNING

    def where(self) -> str:
        parts = []
        if self.designator:
            parts.append(self.designator)
        if self.circuit is not None:
            parts.append(f"circuit {self.circuit}")
        if self.file:
            parts.append(self.file)
        return ", ".join(parts)

    def format(self) -> str:
        where = self.where()
        suffix = f"  [{where}]" if where else ""
        return f"{self.severity.label:<7} {self.code:<24} {self.message}{suffix}"


def error(code: str, message: str, **kw: Any) -> Issue:
    return Issue(Severity.ERROR, code, message, **kw)


def warning(code: str, message: str, **kw: Any) -> Issue:
    return Issue(Severity.WARNING, code, message, **kw)


def info(code: str, message: str, **kw: Any) -> Issue:
    return Issue(Severity.INFO, code, message, **kw)


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Stable order: severity, then circuit, then designator, then code."""

    def key(i: Issue) -> tuple:
        return (
            i.severity.rank,
            i.code,
            i.circuit if i.circuit is not None else -1,
            i.designator or "",
            i.subject or "",
            i.message,
        )

    return sorted(issues, key=key)
