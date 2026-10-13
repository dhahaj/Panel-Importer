"""Import dialog: choose an ODB++ folder or archive and confirm step and layer roles."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from panelimport.analysis.roles import LAYER_ROLES, ROLE_LABELS, detect_layer_roles, detect_steps, has_components
from panelimport.io.odb import OdbJob, OdbOpenError

NONE = "—"
STEP_ROLES = [NONE, "Panel", "Board"]


def _ro(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


class ImportDialog(QDialog):
    def __init__(self, parent=None, job: OdbJob | None = None, decisions=None, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import ODB++" if job is None else "Edit step and layer roles")
        self.resize(820, 640)
        self.qsettings = settings or QSettings()
        self.job: OdbJob | None = None

        self.path = QLineEdit()
        self.path.setPlaceholderText("ODB++ export: folder, .tgz or .zip")
        self.folder_btn = QPushButton("Folder…")
        self.archive_btn = QPushButton("Archive…")
        self.load_btn = QPushButton("Load")
        self.folder_btn.clicked.connect(self._pick_folder)
        self.archive_btn.clicked.connect(self._pick_archive)
        self.load_btn.clicked.connect(lambda: self.load(self.path.text()))
        self.path.returnPressed.connect(lambda: self.load(self.path.text()))
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(self.folder_btn)
        path_row.addWidget(self.archive_btn)
        path_row.addWidget(self.load_btn)

        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #ffb000;")

        self.steps = QTableWidget(0, 5)
        self.steps.setHorizontalHeaderLabels(["Step", "STEP-REPEAT blocks", "Placed instances", "Components", "Role"])
        self.layers = QTableWidget(0, 5)
        self.layers.setHorizontalHeaderLabels(["Row", "Layer", "Type", "Context", "Role"])
        for t in (self.steps, self.layers):
            t.verticalHeader().setVisible(False)
            t.setSelectionMode(QAbstractItemView.NoSelection)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            t.horizontalHeader().setStretchLastSection(True)
        steps_box = QGroupBox("Steps")
        QVBoxLayout(steps_box).addWidget(self.steps)
        layers_box = QGroupBox("Layers")
        QVBoxLayout(layers_box).addWidget(self.layers)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Open" if job is None else "Apply")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(path_row)
        layout.addWidget(self.info)
        layout.addWidget(self.note)
        layout.addWidget(steps_box, 2)
        layout.addWidget(layers_box, 3)
        layout.addWidget(self.buttons)
        self._step_combos: list[tuple[str, QComboBox]] = []
        self._layer_combos: list[tuple[str, QComboBox]] = []
        self._updating = False
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)

        if job is not None:
            self.path.setText(str(job.path))
            for w in (self.path, self.folder_btn, self.archive_btn, self.load_btn):
                w.setEnabled(False)
            self._show(job, decisions)
        else:
            last = self.qsettings.value("import/last_path", "")
            if last:
                self.path.setText(str(last))

    # ------------------------------------------------------------------ choose
    def _start_dir(self) -> str:
        text = self.path.text().strip()
        if text:
            p = Path(text)
            return str(p if p.is_dir() else p.parent)
        return str(self.qsettings.value("import/last_dir", str(Path.home())))

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "ODB++ folder", self._start_dir())
        if d:
            self.path.setText(d)
            self.load(d)

    def _pick_archive(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "ODB++ archive", self._start_dir(), "ODB++ archives (*.tgz *.tar.gz *.tar *.zip);;All files (*)"
        )
        if f:
            self.path.setText(f)
            self.load(f)

    def load(self, path: str) -> bool:
        path = path.strip()
        if not path:
            return False
        try:
            job = OdbJob(path)
        except (OdbOpenError, OSError) as exc:
            QMessageBox.warning(self, "Cannot open export", str(exc))
            return False
        p = Path(path)
        self.qsettings.setValue("import/last_path", str(p))
        self.qsettings.setValue("import/last_dir", str(p if p.is_dir() else p.parent))
        self._show(job, None)
        return True

    # ------------------------------------------------------------------ show
    def _show(self, job: OdbJob, decisions) -> None:
        self.job = job
        det = detect_steps(job)
        roles, notes = detect_layer_roles(job.matrix)
        panel = det.panel_step
        board = det.board_step
        if decisions is not None:
            panel = decisions.panel_step or panel
            board = decisions.board_step or board
            for role, layer in decisions.layer_roles.items():
                if layer:
                    roles[role] = layer
                else:
                    roles.pop(role, None)
        self.info.setText(
            f"ODB++ {job.info.version} from {job.info.application}; default units {job.default_units.value}; "
            f"{len(job.matrix.steps)} steps, {len(job.matrix.layers)} layers ({job.source.kind})."
        )
        msgs = []
        if det.ambiguous:
            msgs.append(f"⚠ {det.reason}. Check the Panel and Board roles below.")
        if not det.has_repeats:
            msgs.append(
                "No STEP-REPEAT: the panel will be reconstructed from repeated designators, or treated as a "
                "single board after you confirm it."
            )
        msgs.extend(notes)
        self.note.setText("\n".join(msgs))

        self._updating = True
        self.steps.setRowCount(len(job.matrix.steps))
        self._step_combos = []
        for r, st in enumerate(job.matrix.steps):
            hdr = job.stephdr(st.name)
            blocks = len(hdr.repeats) if hdr else 0
            placed = det.instance_counts.get(st.name, 0)
            n_comps = 0
            if has_components(job, st.name):
                for layer in job.component_layers().values():
                    cf = job.components(st.name, layer.name)
                    n_comps += len(cf.components) if cf else 0
            self.steps.setItem(r, 0, _ro(st.name))
            self.steps.setItem(r, 1, _ro(str(blocks)))
            self.steps.setItem(r, 2, _ro(str(placed) if placed else "-"))
            self.steps.setItem(r, 3, _ro(str(n_comps)))
            combo = QComboBox()
            combo.addItems(STEP_ROLES)
            if panel and st.name.lower() == panel.lower():
                combo.setCurrentText("Panel")
            elif board and st.name.lower() == board.lower():
                combo.setCurrentText("Board")
            combo.currentTextChanged.connect(lambda text, name=st.name: self._step_role_changed(name, text))
            self.steps.setCellWidget(r, 4, combo)
            self._step_combos.append((st.name, combo))

        self.layers.setRowCount(len(job.matrix.layers))
        self._layer_combos = []
        role_of = {layer.lower(): role for role, layer in roles.items()}
        for r, layer in enumerate(job.matrix.layers):
            self.layers.setItem(r, 0, _ro(str(layer.row)))
            self.layers.setItem(r, 1, _ro(layer.name))
            self.layers.setItem(r, 2, _ro(layer.type))
            self.layers.setItem(r, 3, _ro(layer.context))
            combo = QComboBox()
            combo.addItem(NONE, "")
            for role in LAYER_ROLES:
                combo.addItem(ROLE_LABELS[role], role)
            role = role_of.get(layer.key)
            if role:
                combo.setCurrentIndex(combo.findData(role))
            combo.currentIndexChanged.connect(lambda _i, name=layer.name, c=combo: self._layer_role_changed(name, c))
            self.layers.setCellWidget(r, 4, combo)
            self._layer_combos.append((layer.name, combo))
        self._updating = False
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def _step_role_changed(self, name: str, text: str) -> None:
        if self._updating or text == NONE:
            return
        self._updating = True
        for other, combo in self._step_combos:
            if other != name and combo.currentText() == text:
                combo.setCurrentText(NONE)
        self._updating = False

    def _layer_role_changed(self, name: str, combo: QComboBox) -> None:
        if self._updating:
            return
        role = combo.currentData()
        if not role:
            return
        self._updating = True
        for other, c in self._layer_combos:
            if other != name and c.currentData() == role:
                c.setCurrentIndex(0)
        self._updating = False

    # ------------------------------------------------------------------ result
    def step_roles(self) -> tuple[str | None, str | None]:
        panel = next((n for n, c in self._step_combos if c.currentText() == "Panel"), None)
        board = next((n for n, c in self._step_combos if c.currentText() == "Board"), None)
        return panel, board

    def layer_roles(self) -> dict[str, str]:
        roles = {role: "" for role in LAYER_ROLES}
        for name, combo in self._layer_combos:
            role = combo.currentData()
            if role:
                roles[role] = name
        return roles

    def _accept(self) -> None:
        panel, _board = self.step_roles()
        if self.job is None:
            return
        if panel is None:
            QMessageBox.warning(self, "Choose the panel step", "Mark one step as the Panel.")
            return
        self.accept()
