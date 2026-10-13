"""An import session: one ODB++ export, the settings, the user's decisions and the result.

Used by both the CLI and the GUI, so both show exactly the same analysis.  Never
imports Qt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from panelimport.analysis.pipeline import analyze, decisions_from_project, with_changes
from panelimport.analysis.result import PanelAnalysis
from panelimport.analysis.snapshot import snapshot_from_project
from panelimport.io.bom import Bom, read_bom
from panelimport.io.odb import OdbJob
from panelimport.model.issues import Issue, Severity, sort_issues, warning
from panelimport.model.panel import Decisions, PanelProject
from panelimport.model.project_file import check_source, diff_projects, load_project, save_project
from panelimport.settings import Settings


class SessionError(Exception):
    pass


@dataclass
class ReopenResult:
    project: PanelProject
    source: Path
    source_issue: Issue | None
    differences: list[str]


class Session:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.job: OdbJob | None = None
        self.decisions = Decisions()
        self.analysis: PanelAnalysis | None = None
        self.bom: Bom | None = None
        self.panel_job: OdbJob | None = None
        self.project_path: Path | None = None
        self.saved_project: PanelProject | None = None
        self.extra_issues: list[Issue] = []

    @property
    def read_only(self) -> bool:
        """True when showing a saved project whose source export is missing."""
        return self.job is None and self.analysis is not None

    # ------------------------------------------------------------------ source
    def open_source(self, path: str | os.PathLike, decisions: Decisions | None = None) -> PanelAnalysis:
        return self.open_job(OdbJob(path), decisions)

    def open_job(self, job: OdbJob, decisions: Decisions | None = None) -> PanelAnalysis:
        self.job = job
        self.decisions = decisions or Decisions()
        self.project_path = None
        self.saved_project = None
        self.extra_issues = []
        self.bom = read_bom(self.decisions.bom_path) if self.decisions.bom_path else None
        self.panel_job = self._panel_job_for(self.decisions)
        return self.reanalyze()

    def reanalyze(self) -> PanelAnalysis:
        if self.job is None:
            raise SessionError("no export is open")
        self.analysis = analyze(self.job, self.settings, self.decisions, bom=self.bom, panel_job=self.panel_job)
        if self.extra_issues:
            self.analysis.issues = sort_issues(self.analysis.issues + self.extra_issues)
            acks = {a.key for a in self.decisions.acknowledged}
            self.analysis.acknowledged |= {
                i.key for i in self.extra_issues if i.severity is not Severity.ERROR and i.key in acks
            }
        return self.analysis

    def set_decisions(self, decisions: Decisions) -> PanelAnalysis:
        """Apply new decisions.  Inputs they name (BOM, panel export) are loaded first, so a
        file that cannot be read leaves the session unchanged."""
        bom = self.bom
        if not decisions.bom_path:
            bom = None
        elif bom is None or bom.path != decisions.bom_path:
            bom = read_bom(decisions.bom_path)
        panel_job = self.panel_job
        if self._panel_source(decisions) != self._panel_source(self.decisions):
            panel_job = self._panel_job_for(decisions)
        self.decisions, self.bom, self.panel_job = decisions, bom, panel_job
        return self.reanalyze()

    def update(self, **changes) -> PanelAnalysis:
        return self.set_decisions(with_changes(self.decisions, **changes))

    def set_settings(self, settings: Settings) -> PanelAnalysis | None:
        self.settings = settings
        return self.reanalyze() if self.job else None

    @staticmethod
    def _panel_source(decisions: Decisions) -> str | None:
        return decisions.single_board.panel_source if decisions.single_board else None

    def _panel_job_for(self, decisions: Decisions) -> OdbJob | None:
        source = self._panel_source(decisions)
        return OdbJob(source) if source else None

    # ------------------------------------------------------------------ project
    def save(self, path: str | os.PathLike) -> PanelProject:
        if self.analysis is None:
            raise SessionError("nothing to save")
        if not self.analysis.confirmed:
            ok, why = self.analysis.can_confirm()
            raise SessionError("Confirm the panel before saving" + (f": {why}" if why else ""))
        project = self.analysis.to_project(path)
        save_project(project, path)
        self.project_path = Path(path)
        self.saved_project = project
        return project

    def open_project(self, path: str | os.PathLike) -> ReopenResult:
        """Reopen a project: re-analyse its source with the saved decisions.

        When the source is missing nothing is analysed; when its hash changed the new
        export is analysed with the saved decisions but needs confirming again.  When
        the source is unchanged, the re-analysis is compared with the saved model.
        """
        project = load_project(path)
        src, issue = check_source(project, path)
        result = ReopenResult(project, src, issue, [])
        self.project_path = Path(path)
        self.saved_project = project
        self.settings = project.settings
        if issue is not None and issue.code == "source_missing":
            # Read-only view of the saved model; nothing can be re-analysed.
            self.job = None
            self.extra_issues = [issue]
            self.analysis = snapshot_from_project(project, [issue])
            return result
        decisions = decisions_from_project(project)
        self.extra_issues = []
        if issue is not None:
            # The saved project stays valid; the changed export is re-analysed with the
            # saved decisions and must be reviewed and confirmed again before saving.
            decisions = with_changes(decisions, confirmed=False)
            self.extra_issues.append(
                warning(
                    "source_changed",
                    issue.message + "; the new export was analysed with the saved decisions: review and confirm again",
                    subject="source",
                    data=issue.data,
                )
            )
        self.job = OdbJob(src)
        self.decisions = decisions
        self.bom = None
        self.panel_job = self._panel_job_for(decisions)
        self.reanalyze()
        if issue is None and self.analysis is not None:
            rebuilt = self.analysis.to_project(path)
            result.differences = diff_projects(rebuilt, project)
            if result.differences:
                self.extra_issues.append(
                    warning(
                        "reopen_differs",
                        "Re-analysing the unchanged export gives a different result than the saved project "
                        f"({', '.join(result.differences)}); check and confirm again",
                        subject="reopen",
                    )
                )
                self.decisions = with_changes(self.decisions, confirmed=False)
                self.reanalyze()
        return result
