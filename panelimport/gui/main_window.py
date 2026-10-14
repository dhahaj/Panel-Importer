"""Main window: canvas in the centre, layers and tables on the left, inspector on the
right, issues along the bottom.  Workflow: import → detection → review issues →
confirm panel → pick fiducials → (add, edit or remove components) → save project.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from panelimport import __version__
from panelimport.analysis import edits
from panelimport.analysis.fiducials import MAX_PANEL_FIDUCIALS
from panelimport.analysis.result import PanelAnalysis
from panelimport.components_csv import COMPONENTS_SUFFIX, write_components_csv
from panelimport.gui.canvas import PanelCanvas
from panelimport.gui.component_dialog import ComponentDialog, RemoveDialog
from panelimport.gui.controller import Controller
from panelimport.gui.import_dialog import ImportDialog
from panelimport.gui.panels.circuits import CircuitsPanel
from panelimport.gui.panels.components import ComponentsPanel
from panelimport.gui.panels.fiducials import FiducialsPanel
from panelimport.gui.panels.inspector import Inspector
from panelimport.gui.panels.issues import IssuesPanel
from panelimport.gui.panels.layers import LayersPanel
from panelimport.gui.panels.summary import SummaryBar
from panelimport.gui.settings_dialog import SettingsDialog
from panelimport.gui.single_board_dialog import SingleBoardDialog
from panelimport.io.bom import BomError, read_bom
from panelimport.io.odb import OdbJob, OdbOpenError
from panelimport.model.issues import Issue
from panelimport.model.panel import Acknowledgement, Decisions
from panelimport.model.project_file import PROJECT_SUFFIX, ProjectFileError, default_project_path
from panelimport.session import SessionError
from panelimport.settings import Settings


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, qsettings: QSettings | None = None) -> None:
        super().__init__()
        self.qsettings = qsettings or QSettings()
        self.settings = settings
        self.controller = Controller(settings, self)
        self.setWindowTitle("Panel Importer")
        self.resize(1400, 900)

        # ---------------------------------------------------------- widgets
        self.canvas = PanelCanvas()
        for key in list(self.canvas.visible):
            stored = self.qsettings.value(f"layers/{key}")
            if stored is not None:
                self.canvas.visible[key] = str(stored).lower() in ("true", "1")
        self.summary = SummaryBar()
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.summary)
        v.addWidget(self.canvas, 1)
        self.setCentralWidget(central)

        self.layers_panel = LayersPanel(self.canvas.visible)
        self.circuits_panel = CircuitsPanel()
        self.components_panel = ComponentsPanel()
        self.fiducials_panel = FiducialsPanel()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.layers_panel, "Layers")
        self.tabs.addTab(self.circuits_panel, "Circuits")
        self.tabs.addTab(self.components_panel, "Components")
        self.tabs.addTab(self.fiducials_panel, "Fiducials")
        self.left_dock = self._dock("Panel", "leftDock", self.tabs, Qt.LeftDockWidgetArea)
        self.inspector = Inspector()
        self.right_dock = self._dock("Inspector", "inspectorDock", self.inspector, Qt.RightDockWidgetArea)
        self.issues_panel = IssuesPanel()
        self.bottom_dock = self._dock("Issues", "issuesDock", self.issues_panel, Qt.BottomDockWidgetArea)

        self.coord_label = QLabel("")
        self.measure_label = QLabel("")
        self.zoom_label = QLabel("")
        self.statusBar().addPermanentWidget(self.measure_label)
        self.statusBar().addPermanentWidget(self.coord_label)
        self.statusBar().addPermanentWidget(self.zoom_label)

        self._create_actions()
        self._connect()
        geometry = self.qsettings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.qsettings.value("window/state")
        if state is not None:
            self.restoreState(state)
        self._update_actions()

    def _dock(self, title: str, name: str, widget: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    # ------------------------------------------------------------------ actions
    def _action(self, text: str, slot, shortcut=None, checkable: bool = False, tip: str = "") -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.setCheckable(checkable)
        if tip:
            act.setStatusTip(tip)
            act.setToolTip(tip)
        act.triggered.connect(slot)
        return act

    def _create_actions(self) -> None:
        self.act_import = self._action("&Import ODB++…", self.import_odb, QKeySequence.New, tip="Open an ODB++ folder or archive")
        self.act_open = self._action("&Open project…", self.open_project, QKeySequence.Open)
        self.act_save = self._action("&Save project", lambda: self.save_project(False), QKeySequence.Save)
        self.act_save_as = self._action("Save project &as…", lambda: self.save_project(True), QKeySequence.SaveAs)
        self.act_bom = self._action("Load &BOM CSV…", self.load_bom, tip="Cross-check designators against a BOM")
        self.act_export_components = self._action(
            "&Export components CSV…", self.export_components, tip="Write every component in the Components tab to a CSV file"
        )
        self.act_quit = self._action("&Quit", self.close, QKeySequence.Quit)
        self.act_undo = self.controller.undo_stack.createUndoAction(self, "&Undo")
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_redo = self.controller.undo_stack.createRedoAction(self, "&Redo")
        self.act_redo.setShortcut(QKeySequence.Redo)
        self.act_roles = self._action("Step and layer &roles…", self.edit_roles)
        self.act_settings = self._action("&Settings…", self.edit_settings)
        self.act_fit = self._action("&Fit to panel", self.canvas.fit, "F")
        self.act_bottom = self._action("View from &bottom", self.canvas.set_view_from_bottom, "B", checkable=True)
        self.act_measure = self._action("&Measure", self._toggle_measure, "M", checkable=True, tip="Two clicks give ΔX, ΔY and distance")
        self.act_confirm = self._action("&Confirm panel", self.confirm_panel, "Ctrl+Return")
        self.act_add_component = self._action(
            "&Add component…", lambda: self.add_component(), tip="Add a component the export does not have"
        )
        self.suggest_menu = QMenu("Remove &suggested components", self)
        self.suggest_actions: dict[str, QAction] = {}
        for kind, label in edits.SUGGESTIONS.items():
            act = self.suggest_menu.addAction(label + "…")
            act.triggered.connect(lambda _c=False, k=kind: self.suggest_removals(k))
            self.suggest_actions[kind] = act
        self.act_reset_layout = self._action("Reset window layout", self.reset_layout)
        self.act_about = self._action("&About", self.about)

        m = self.menuBar().addMenu("&File")
        for a in (self.act_import, self.act_open, None, self.act_save, self.act_save_as, None, self.act_bom, self.act_export_components, None, self.act_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = self.menuBar().addMenu("&Edit")
        for a in (self.act_undo, self.act_redo, None, self.act_roles, self.act_confirm, None, self.act_add_component):
            m.addSeparator() if a is None else m.addAction(a)
        m.addMenu(self.suggest_menu)
        m.addSeparator()
        m.addAction(self.act_settings)
        m = self.menuBar().addMenu("&View")
        for a in (self.act_fit, self.act_bottom, self.act_measure, None, self.act_reset_layout):
            m.addSeparator() if a is None else m.addAction(a)
        m.addSeparator()
        for dock in (self.left_dock, self.right_dock, self.bottom_dock):
            m.addAction(dock.toggleViewAction())
        self.menuBar().addMenu("&Help").addAction(self.act_about)

        tb = QToolBar("Main")
        tb.setObjectName("mainToolbar")
        for a in (self.act_import, self.act_open, self.act_save, None, self.act_undo, self.act_redo, None, self.act_fit, self.act_measure, self.act_bottom):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(tb)

    def _connect(self) -> None:
        c = self.controller
        c.analysisChanged.connect(self._on_analysis)
        c.dirtyChanged.connect(lambda _d: self._update_title())
        self.canvas.cursorMoved.connect(self._on_cursor)
        self.canvas.measured.connect(lambda dx, dy, d: self.measure_label.setText(f"ΔX {dx:.3f}  ΔY {dy:.3f}  D {d:.3f} mm"))
        self.canvas.itemPicked.connect(self._on_picked)
        self.canvas.selectionCleared.connect(self.inspector.clear)
        self.canvas.contextRequested.connect(self._canvas_context)
        self.canvas.editRequested.connect(
            lambda k: self.edit_components([("board" if k[0] == "placement" else "panel", k[1][0])])
        )
        self.canvas.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{z:.1f} px/mm"))
        self.layers_panel.layerToggled.connect(self._toggle_layer)
        self.circuits_panel.numberingChanged.connect(
            lambda first, order: c.apply("Change circuit numbering", numbering_first=first, numbering_order=order)
        )
        self.circuits_panel.referenceChanged.connect(lambda kind: c.apply("Change circuit reference", circuit_reference=kind))
        self.circuits_panel.circuitActivated.connect(self._show_circuit)
        self.components_panel.componentSelected.connect(lambda level, d: self._component_selected(d, level))
        self.components_panel.partNumberAttributeChanged.connect(
            lambda key: c.apply("Map part number", part_number_attribute=key)
        )
        self.components_panel.addRequested.connect(lambda: self.add_component())
        self.components_panel.editRequested.connect(self.edit_components)
        self.components_panel.removeRequested.connect(self.remove_components)
        self.components_panel.restoreRequested.connect(self.restore_components)
        self.components_panel.revertRequested.connect(self.revert_components)
        self.components_panel.suggestRequested.connect(self.suggest_removals)
        self.fiducials_panel.acceptRequested.connect(self.accept_fiducial)
        self.fiducials_panel.removeRequested.connect(self.remove_fiducial)
        self.fiducials_panel.fiducialSelected.connect(self._fiducial_selected)
        self.issues_panel.issueActivated.connect(self._show_issue)
        self.issues_panel.acknowledgeRequested.connect(self.acknowledge)
        self.issues_panel.unacknowledgeRequested.connect(self.unacknowledge)
        self.issues_panel.panelLevelRequested.connect(self.confirm_panel_level)
        self.issues_panel.removePartsRequested.connect(self.remove_from_issues)
        self.summary.confirmRequested.connect(self.confirm_panel)
        self.summary.editRequested.connect(self.edit_roles)
        self.summary.singleBoardRequested.connect(self.single_board_setup)

    # ------------------------------------------------------------------ state
    @property
    def analysis(self) -> PanelAnalysis | None:
        return self.controller.analysis

    def _update_title(self) -> None:
        a = self.analysis
        name = ""
        if a is not None and a.job is not None:
            name = a.job.name
        elif self.controller.session.project_path is not None:
            name = self.controller.session.project_path.name
        dirty = not self.controller.undo_stack.isClean()
        self.setWindowTitle(f"Panel Importer — {name}{' *' if dirty else ''}" if name else "Panel Importer")

    def _update_actions(self) -> None:
        a = self.analysis
        ro = self.controller.read_only
        has = a is not None and not ro
        self.act_save.setEnabled(has and a.confirmed)
        self.act_save_as.setEnabled(has and a.confirmed)
        self.act_roles.setEnabled(has)
        self.act_bom.setEnabled(has)
        self.act_export_components.setEnabled(a is not None)  # also from a read-only project
        self.act_confirm.setEnabled(has and a.can_confirm()[0] and not a.confirmed)
        self.act_add_component.setEnabled(has)
        self.suggest_menu.setEnabled(has)
        if has:
            found = edits.suggest_removals(a)
            for kind, act in self.suggest_actions.items():
                act.setText(f"{edits.SUGGESTIONS[kind]} ({len(found[kind])})…")
                act.setEnabled(bool(found[kind]))

    def _on_analysis(self, a: PanelAnalysis | None, structural: bool) -> None:
        ro = self.controller.read_only
        keys = self.components_panel.selected_keys()
        self.canvas.set_analysis(a, keep_view=not structural)
        self.summary.set_analysis(a, ro)
        self.circuits_panel.set_analysis(a, ro)
        self.components_panel.set_analysis(a, ro)
        self.fiducials_panel.set_analysis(a, ro)
        self.issues_panel.set_analysis(a, ro)
        if a is not None and keys and edits.find_part(a, *keys[0]) is not None:
            level, designator = keys[0]
            self.canvas.select_designator(designator, level=level)
            self._inspect(level, designator)
        else:
            self.inspector.clear()
        self._update_actions()
        self._update_title()

    # ------------------------------------------------------------------ canvas events
    def _on_cursor(self, x: float, y: float) -> None:
        text = f"Panel X {x:9.3f}  Y {y:9.3f} mm"
        a = self.analysis
        if a is not None:
            rel = a.circuit_relative(x, y)
            if rel is not None:
                text += f"   |   Circuit {rel[0]}: X {rel[1]:8.3f}  Y {rel[2]:8.3f}"
        self.coord_label.setText(text)

    def _on_picked(self, kind: str, key) -> None:
        a = self.analysis
        if a is None:
            return
        if kind == "placement":
            self.components_panel.select_designator(key[0], "board")
            self.inspector.show_placement(a, key[0], key[1])
        elif kind == "panel_part":
            self.components_panel.select_designator(key[0], "panel")
            self.inspector.show_panel_part(a, key[0])
        elif kind == "fiducial":
            self.fiducials_panel.select(key[0])
            self.inspector.show_fiducial(a, key[0])
        elif kind == "fiducial_click":
            cand = next((f for f in a.fiducial_candidates if f.name == key[0]), None)
            if cand is None or not cand.selectable or self.controller.read_only:
                return
            if key[0] in [f.name for f in a.fiducials]:
                self.remove_fiducial(key[0])
            else:
                self.accept_fiducial(key[0])

    def _toggle_layer(self, key: str, on: bool) -> None:
        self.canvas.set_layer_visible(key, on)
        self.qsettings.setValue(f"layers/{key}", on)

    def _toggle_measure(self, on: bool) -> None:
        self.canvas.set_measure_mode(on)
        if not on:
            self.measure_label.setText("")

    def _component_selected(self, designator: str, level: str = "board") -> None:
        a = self.analysis
        if a is None:
            return
        self.canvas.select_designator(designator, 1, center=True, level=level)
        self._inspect(level, designator, 1)

    def _inspect(self, level: str, designator: str, circuit: int | None = None) -> None:
        if level == "panel":
            self.inspector.show_panel_part(self.analysis, designator)
        else:
            self.inspector.show_placement(self.analysis, designator, circuit)

    def _fiducial_selected(self, name: str) -> None:
        if self.analysis is not None:
            self.canvas.select_fiducial(name, center=True)
            self.inspector.show_fiducial(self.analysis, name)

    def _show_circuit(self, index: int) -> None:
        a = self.analysis
        c = next((c for c in a.circuits if c.index == index), None) if a else None
        if c is None:
            return
        self.canvas.zoom_to(c.center[0], c.center[1], max(c.size) * 0.6)
        self.inspector.show_circuit(a, index)

    def _show_issue(self, issue: Issue) -> None:
        a = self.analysis
        if a is None:
            return
        if issue.location is not None:
            self.canvas.show_location(issue.location[0], issue.location[1], 5.0)
        elif issue.circuit is not None:
            self._show_circuit(issue.circuit)
        if issue.designator:
            self.canvas.select_designator(issue.designator, issue.circuit)
            for level in ("board", "panel"):
                if edits.find_part(a, level, issue.designator) is not None:
                    self.components_panel.select_designator(issue.designator, level)
                    self._inspect(level, issue.designator, issue.circuit)
                    break

    # ------------------------------------------------------------------ edits
    def confirm_panel(self) -> None:
        a = self.analysis
        if a is None:
            return
        ok, why = a.can_confirm()
        if not ok:
            QMessageBox.information(self, "Confirm panel", f"The panel cannot be confirmed yet: {why}.")
            return
        self.controller.apply("Confirm panel", confirmed=True)
        self.tabs.setCurrentWidget(self.fiducials_panel)
        self.statusBar().showMessage("Panel confirmed. Pick up to 3 panel fiducials, then save the project.", 8000)

    def accept_fiducial(self, name: str) -> None:
        a = self.analysis
        if a is None or self.controller.read_only:
            return
        if not a.confirmed:
            QMessageBox.information(self, "Fiducials", "Confirm the panel first; fiducials are picked after confirmation.")
            return
        cand = next((f for f in a.fiducial_candidates if f.name == name), None)
        if cand is None or not cand.selectable:
            QMessageBox.information(self, "Fiducials", "Circuit-level fiducials are shown but cannot be picked.")
            return
        current = list(self.controller.decisions.fiducials)
        if name in current:
            return
        if len(current) >= MAX_PANEL_FIDUCIALS:
            QMessageBox.warning(
                self,
                "Fiducials",
                f"At most {MAX_PANEL_FIDUCIALS} panel fiducials can be picked. Remove one before adding {name}.",
            )
            return
        self.controller.apply(f"Pick fiducial {name}", fiducials=current + [name])

    def remove_fiducial(self, name: str) -> None:
        current = list(self.controller.decisions.fiducials)
        if name in current:
            current.remove(name)
            self.controller.apply(f"Remove fiducial {name}", fiducials=current)

    def acknowledge(self, issues: list[Issue]) -> None:
        acks = list(self.controller.decisions.acknowledged)
        known = {a.key for a in acks}
        added = [Acknowledgement.of(i) for i in issues if i.key not in known]
        if added:
            self.controller.apply(f"Acknowledge {len(added)} issue(s)", acknowledged=acks + added)

    def unacknowledge(self, issues: list[Issue]) -> None:
        keys = {i.key for i in issues}
        acks = [a for a in self.controller.decisions.acknowledged if a.key not in keys]
        self.controller.apply(f"Un-acknowledge {len(issues)} issue(s)", acknowledged=acks)

    def confirm_panel_level(self, designators: list[str]) -> None:
        current = list(self.controller.decisions.panel_level)
        new = current + [d for d in designators if d not in current]
        self.controller.apply(f"Confirm {', '.join(designators)} as panel-level", panel_level=new)

    def edit_roles(self) -> None:
        job = self.controller.session.job
        if job is None:
            return
        dlg = ImportDialog(self, job=job, decisions=self.controller.decisions, settings=self.qsettings)
        if dlg.exec():
            panel, board = dlg.step_roles()
            self.controller.apply("Change step and layer roles", panel_step=panel, board_step=board, layer_roles=dlg.layer_roles())

    def single_board_setup(self) -> None:
        dlg = SingleBoardDialog(self, self.controller.decisions.single_board)
        if dlg.exec() and dlg.result_setup is not None:
            if dlg.result_setup.panel_source:
                try:
                    OdbJob(dlg.result_setup.panel_source)  # validate before it becomes an undoable edit
                except (OdbOpenError, OSError) as exc:
                    QMessageBox.warning(self, "Panel export", str(exc))
                    return
            self.controller.apply("Single-board setup", single_board=dlg.result_setup)

    # ------------------------------------------------------------------ component edits
    def _set_component_edits(self, text: str, new: list) -> None:
        a = self.analysis
        if a is None or self.controller.read_only or new == a.component_edits:
            return
        self.controller.apply(text, component_edits=new, edit_frame=a.edit_frame)

    @staticmethod
    def _names(keys) -> str:
        names = [d for _lv, d in keys]
        return ", ".join(names) if len(names) <= 3 else f"{len(names)} components"

    def add_component(self, level: str = "board", position: dict | None = None) -> None:
        a = self.analysis
        if a is None or self.controller.read_only:
            return
        dlg = ComponentDialog(self, a, level=level, position=position)
        if not dlg.exec() or dlg.validate():
            return
        new = edits.added_edit(dlg.chosen_level(), dlg.chosen_designator(), dlg.values(), dlg.note_text())
        self._set_component_edits(f"Add {new.designator}", edits.set_edits(a.component_edits, [new]))
        self.tabs.setCurrentWidget(self.components_panel)
        self.components_panel.select_designator(new.designator, new.level)
        self._component_selected(new.designator, new.level)

    def edit_components(self, keys: list) -> None:
        a = self.analysis
        keys = [tuple(k) for k in keys if edits.find_part(a, *k) is not None] if a is not None else []
        if not keys or self.controller.read_only:
            return
        dlg = ComponentDialog(self, a, keys)
        if not dlg.exec() or dlg.validate():
            return
        values, note = dlg.values(), dlg.note_text()
        new, drop = [], []
        for key in keys:
            part = edits.find_part(a, *key)
            if part.state == "added" and dlg.mode == "one":
                renamed = edits.added_edit(key[0], dlg.chosen_designator(), values, note)
                new.append(renamed)
                if renamed.key != key:
                    drop.append(key)
                continue
            merged = {**edits.shown_values(a, part), **values}
            e = edits.edit_from_values(a, key[0], key[1], merged, note if dlg.mode == "one" else None)
            if e is None:
                drop.append(key)
            else:
                new.append(e)
        self._set_component_edits(f"Edit {self._names(keys)}", edits.set_edits(a.component_edits, new, drop))

    def remove_components(self, keys: list, reason: str = "through-hole", why: dict | None = None, title: str = "") -> None:
        """Review and remove (not place) components; ``why`` explains each one in the dialog."""
        a = self.analysis
        if a is None or self.controller.read_only:
            return
        rows = []
        for key in keys:
            part = edits.find_part(a, *key)
            if part is None or part.state == "removed":
                continue
            what = " · ".join(x for x in (part.part_name, part.package) if x)
            rows.append((tuple(key), what, (why or {}).get(tuple(key), "added by hand" if part.state == "added" else "")))
        if not rows:
            return
        dlg = RemoveDialog(self, rows, reason, title or "Remove components")
        if not dlg.exec() or not dlg.chosen():
            return
        chosen = dlg.chosen()
        new = edits.remove_parts(a.component_edits, chosen, dlg.chosen_reason(), dlg.note_text())
        label = edits.REASON_LABELS.get(dlg.chosen_reason(), "")
        self._set_component_edits(f"Remove {self._names(chosen)} ({label})", new)

    def restore_components(self, keys: list) -> None:
        a = self.analysis
        if a is not None:
            keys = [tuple(k) for k in keys]
            self._set_component_edits(f"Restore {self._names(keys)}", edits.restore_parts(a.component_edits, keys))

    def revert_components(self, keys: list) -> None:
        a = self.analysis
        if a is not None:
            keys = [tuple(k) for k in keys]
            self._set_component_edits(f"Revert {self._names(keys)} to the export", edits.revert_parts(a.component_edits, keys))

    def suggest_removals(self, kind: str) -> None:
        a = self.analysis
        if a is None:
            return
        found = edits.suggest_removals(a).get(kind, [])
        if not found:
            QMessageBox.information(self, "Remove components", f"No {edits.SUGGESTIONS[kind].lower()} found.")
            return
        self.remove_components(
            [s.key for s in found],
            edits.SUGGESTED_REASON[kind],
            {s.key: s.why for s in found},
            f"Remove {edits.SUGGESTIONS[kind].lower()}",
        )

    def remove_from_issues(self, issues: list[Issue]) -> None:
        a = self.analysis
        if a is None:
            return
        keys, why = [], {}
        reason = "other"
        for issue in issues:
            for level in ("board", "panel"):
                part = edits.find_part(a, level, issue.designator or "")
                if part is not None and part.state != "removed":
                    key = (level, part.designator)
                    if key not in keys:
                        keys.append(key)
                        why[key] = issue.code
                    break
            if issue.code == "no_paste":
                reason = "through-hole"
            elif issue.code in ("bom_not_in_bom", "copy_count") and reason == "other":
                reason = "not-populated"
        self.remove_components(keys, reason, why)

    def canvas_menu(self, key, x: float, y: float) -> QMenu:
        """The canvas's right-click menu: actions on the component under the cursor, and
        adding a component at the clicked point (board-level inside a circuit)."""
        a = self.analysis
        menu = QMenu(self)
        if a is None:
            return menu
        ro = self.controller.read_only
        if key is not None:
            kind, k = key
            level = "board" if kind == "placement" else "panel"
            part = edits.find_part(a, level, k[0])
            if part is not None:
                title = menu.addAction(f"{part.designator} — {part.part_name or part.package or level}")
                title.setEnabled(False)
                cmp_key = (level, part.designator)
                menu.addAction(f"Edit {part.designator}…", lambda: self.edit_components([cmp_key])).setEnabled(not ro)
                if part.state == "removed":
                    menu.addAction(f"Restore {part.designator}", lambda: self.restore_components([cmp_key])).setEnabled(not ro)
                else:
                    menu.addAction(f"Remove {part.designator}…", lambda: self.remove_components([cmp_key])).setEnabled(not ro)
                if part.state == "edited":
                    menu.addAction(f"Revert {part.designator} to the export", lambda: self.revert_components([cmp_key])).setEnabled(not ro)
                menu.addSeparator()
        rel = a.circuit_relative(x, y)
        position = {"panel": (x, y), "board": (rel[1], rel[2]) if rel else None}
        where = f"circuit {rel[0]}, X {rel[1]:.3f} Y {rel[2]:.3f}" if rel else f"panel X {x:.3f} Y {y:.3f}"
        level = "board" if rel else "panel"
        add = menu.addAction(f"Add component here ({where})…", lambda: self.add_component(level, position))
        add.setEnabled(not ro)
        return menu

    def _canvas_context(self, key, x: float, y: float, global_pos) -> None:
        self.canvas_menu(key, x, y).exec(global_pos)

    # ------------------------------------------------------------------ files
    def _discard_ok(self) -> bool:
        if self.analysis is None or self.controller.undo_stack.isClean():
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Discard the changes to the current panel?")
        return r == QMessageBox.Yes

    def import_odb(self) -> None:
        if not self._discard_ok():
            return
        dlg = ImportDialog(self, settings=self.qsettings)
        if dlg.exec() and dlg.job is not None:
            panel, board = dlg.step_roles()
            self.open_job(dlg.job, Decisions(panel_step=panel, board_step=board, layer_roles=dlg.layer_roles()))

    def open_job(self, job: OdbJob, decisions: Decisions) -> None:
        self.controller.open_job(job, decisions)
        self.statusBar().showMessage(f"Imported {job.path}", 5000)

    def open_path(self, path: str) -> None:
        """Open an ODB++ export or a project file given on the command line."""
        if path.endswith(PROJECT_SUFFIX):
            self._open_project_file(path)
            return
        try:
            self.open_job(OdbJob(path), Decisions())
        except (OdbOpenError, OSError) as exc:
            QMessageBox.warning(self, "Cannot open export", str(exc))

    def open_project(self) -> None:
        if not self._discard_ok():
            return
        start = str(self.qsettings.value("project/last_dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start, f"Panel projects (*{PROJECT_SUFFIX});;All files (*)")
        if path:
            self._open_project_file(path)

    def _open_project_file(self, path: str) -> None:
        try:
            result = self.controller.open_project(path)
        except (ProjectFileError, OdbOpenError, OSError) as exc:
            QMessageBox.warning(self, "Cannot open project", str(exc))
            return
        self.qsettings.setValue("project/last_dir", str(Path(path).parent))
        if result.source_issue is not None:
            QMessageBox.warning(self, "Project source", result.source_issue.message)
        elif result.differences:
            QMessageBox.warning(
                self,
                "Project",
                "Re-analysing the unchanged export gives a different result than the saved project "
                f"({', '.join(result.differences)}). Review and confirm again.",
            )
        else:
            self.statusBar().showMessage(f"Opened {path}: the export is unchanged and reproduces the project", 8000)

    def save_project(self, save_as: bool = False) -> None:
        a = self.analysis
        if a is None or self.controller.read_only:
            return
        if not a.confirmed:
            QMessageBox.information(self, "Save project", "Confirm the panel before saving the project.")
            return
        if len(a.fiducials) < 2:
            r = QMessageBox.question(
                self, "Save project", f"Only {len(a.fiducials)} panel fiducial(s) picked. Save anyway?"
            )
            if r != QMessageBox.Yes:
                return
        path = self.controller.session.project_path
        if save_as or path is None:
            default = str(default_project_path(a.job.path))
            name, _ = QFileDialog.getSaveFileName(self, "Save project", default, f"Panel projects (*{PROJECT_SUFFIX})")
            if not name:
                return
            if not name.endswith(PROJECT_SUFFIX):
                name += PROJECT_SUFFIX
            path = Path(name)
        try:
            self.controller.save(str(path))
        except (SessionError, OSError) as exc:
            QMessageBox.warning(self, "Save project", str(exc))
            return
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}", 5000)

    def load_bom(self) -> None:
        start = str(self.qsettings.value("bom/last_dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(self, "BOM CSV", start, "CSV files (*.csv *.txt);;All files (*)")
        if not path:
            return
        self.qsettings.setValue("bom/last_dir", str(Path(path).parent))
        try:
            read_bom(path)  # validate before it becomes an undoable edit
        except (BomError, OSError) as exc:
            QMessageBox.warning(self, "BOM", str(exc))
            return
        self.controller.apply("Load BOM", bom_path=path)

    def export_components(self) -> None:
        a = self.analysis
        if a is None:
            return
        project = self.controller.session.project_path or default_project_path(a.job.path)
        default = project.with_name(project.name.removesuffix(PROJECT_SUFFIX) + COMPONENTS_SUFFIX)
        name, _ = QFileDialog.getSaveFileName(self, "Export components", str(default), "CSV files (*.csv);;All files (*)")
        if not name:
            return
        if not Path(name).suffix:
            name += ".csv"
        try:
            count = write_components_csv(a, name)
        except OSError as exc:
            QMessageBox.warning(self, "Export components", str(exc))
            return
        self.statusBar().showMessage(f"Exported {count} components to {name}", 5000)

    def edit_settings(self) -> None:
        dlg = SettingsDialog(self.controller.session.settings, self)
        if dlg.exec():
            self.settings = dlg.settings
            try:
                dlg.settings.save()
            except OSError as exc:
                QMessageBox.warning(self, "Settings", f"Settings applied but not saved: {exc}")
            if self.controller.session.job is not None:
                self.controller.set_settings(dlg.settings)
            else:
                self.controller.session.settings = dlg.settings

    # ------------------------------------------------------------------ window
    def reset_layout(self) -> None:
        for dock, area in ((self.left_dock, Qt.LeftDockWidgetArea), (self.right_dock, Qt.RightDockWidgetArea), (self.bottom_dock, Qt.BottomDockWidgetArea)):
            dock.setFloating(False)
            dock.show()
            self.addDockWidget(area, dock)

    def about(self) -> None:
        QMessageBox.about(
            self,
            "Panel Importer",
            f"<b>Panel Importer</b> {__version__}<br>Phase 1: identifies an Altium panel exported as ODB++ "
            "and saves it as a .panel.json project. It writes no machine program.",
        )

    def closeEvent(self, event) -> None:
        if not self._discard_ok():
            event.ignore()
            return
        self.qsettings.setValue("window/geometry", self.saveGeometry())
        self.qsettings.setValue("window/state", self.saveState())
        super().closeEvent(event)
