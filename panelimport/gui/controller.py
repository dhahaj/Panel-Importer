"""Connects the GUI to a :class:`~panelimport.session.Session`.

Every user edit (step and layer roles, numbering, fiducial picks, part-number mapping,
acknowledgements, panel-level confirmations, single-board setup, confirmation) is an
undoable command that swaps the immutable :class:`Decisions` and re-runs the analysis.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QUndoCommand, QUndoStack

from panelimport.analysis.pipeline import with_changes
from panelimport.analysis.result import PanelAnalysis
from panelimport.io.odb import OdbJob
from panelimport.model.panel import Decisions
from panelimport.session import ReopenResult, Session
from panelimport.settings import Settings


class DecisionCommand(QUndoCommand):
    def __init__(self, controller: Controller, text: str, old: Decisions, new: Decisions) -> None:
        super().__init__(text)
        self.controller = controller
        self.old = old
        self.new = new

    def redo(self) -> None:
        self.controller._set_decisions(self.new)

    def undo(self) -> None:
        self.controller._set_decisions(self.old)


class Controller(QObject):
    analysisChanged = Signal(object, bool)  # analysis, structure changed (re-fit view)
    dirtyChanged = Signal(bool)

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.session = Session(settings)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(lambda clean: self.dirtyChanged.emit(not clean))

    # ------------------------------------------------------------------ state
    @property
    def analysis(self) -> PanelAnalysis | None:
        return self.session.analysis

    @property
    def decisions(self) -> Decisions:
        return self.session.decisions

    @property
    def read_only(self) -> bool:
        return self.session.read_only

    def _busy(self):
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)

    def _idle(self):
        QGuiApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------ opening
    def open_job(self, job: OdbJob, decisions: Decisions) -> PanelAnalysis:
        self._busy()
        try:
            analysis = self.session.open_job(job, decisions)
        finally:
            self._idle()
        self.undo_stack.clear()
        self.analysisChanged.emit(analysis, True)
        return analysis

    def open_project(self, path: str) -> ReopenResult:
        self._busy()
        try:
            result = self.session.open_project(path)
        finally:
            self._idle()
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self.analysisChanged.emit(self.session.analysis, True)
        return result

    def save(self, path: str):
        project = self.session.save(path)
        self.undo_stack.setClean()
        return project

    def set_settings(self, settings: Settings) -> None:
        self._busy()
        try:
            self.session.set_settings(settings)
        finally:
            self._idle()
        self.analysisChanged.emit(self.session.analysis, False)

    # ------------------------------------------------------------------ edits
    def apply(self, text: str, **changes) -> None:
        if self.session.job is None:
            return
        old = self.session.decisions
        new = with_changes(old, **changes)
        if new == old:
            return
        self.undo_stack.push(DecisionCommand(self, text, old, new))

    def _set_decisions(self, decisions: Decisions) -> None:
        structural = (
            decisions.panel_step != self.session.decisions.panel_step
            or decisions.board_step != self.session.decisions.board_step
            or decisions.layer_roles != self.session.decisions.layer_roles
            or decisions.single_board != self.session.decisions.single_board
        )
        self._busy()
        try:
            self.session.set_decisions(decisions)
        finally:
            self._idle()
        self.analysisChanged.emit(self.session.analysis, structural)
