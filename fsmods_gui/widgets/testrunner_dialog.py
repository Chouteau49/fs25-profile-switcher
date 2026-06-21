"""Embeddable panel: validate mods (OK / WARN / KO) before playing.

Built-in static checks always run; if a path to Giants ``TestRunner.exe`` is
provided, its verdict is folded in too. Heavy work runs in a worker owned by the
main window — this panel only collects the request and renders results.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..profiles.testrunner import (
    LEVEL_ERROR,
    LEVEL_OK,
    LEVEL_WARN,
    STATUS_KO,
    STATUS_LABELS_FR,
    STATUS_OK,
    STATUS_WARN,
    ModTestResult,
)

SCOPE_PROFILE = "profile"
SCOPE_LIBRARY = "library"

# ---- result filters (which statuses to show in the table)
FILTER_ALL = "all"
FILTER_PROBLEMS = "problems"  # KO + à vérifier
_FILTER_STATUSES = {
    FILTER_ALL: {STATUS_OK, STATUS_WARN, STATUS_KO},
    FILTER_PROBLEMS: {STATUS_WARN, STATUS_KO},
    STATUS_KO: {STATUS_KO},
    STATUS_WARN: {STATUS_WARN},
    STATUS_OK: {STATUS_OK},
}

_STATUS_BG = {
    STATUS_OK: QColor(214, 245, 214),
    STATUS_WARN: QColor(255, 240, 196),
    STATUS_KO: QColor(255, 205, 205),
}
_STATUS_FG = {
    STATUS_OK: QColor(0, 90, 0),
    STATUS_WARN: QColor(120, 80, 0),
    STATUS_KO: QColor(120, 0, 0),
}
_LEVEL_PREFIX = {LEVEL_OK: "✅", LEVEL_WARN: "⚠", LEVEL_ERROR: "❌"}


class TestRunnerPanel(QWidget):
    """Pick a scope, validate the mods, browse per-mod findings."""

    # Emitted on "Lancer les tests": (scope, testrunner_exe_path_or_empty).
    run_requested = Signal(str, str)

    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._results: list[ModTestResult] = []

        intro = QLabel(
            "Valide les mods avant de jouer. Les <b>contrôles intégrés</b> "
            "(intégrité du zip, modDesc.xml, icône, textures, taille…) tournent "
            "toujours. Indique le chemin de <b>Giants TestRunner.exe</b> (GDN) "
            "pour ajouter son verdict officiel."
        )
        intro.setWordWrap(True)

        # ---- TestRunner.exe path (optional)
        self.exe_edit = QLineEdit(self)
        default_exe = getattr(state.game, "testrunner_exe", None)
        if default_exe is not None:
            self.exe_edit.setText(str(default_exe))
        self.exe_edit.setPlaceholderText(
            "Optionnel — laisser vide pour n'utiliser que les contrôles intégrés"
        )
        browse_btn = QPushButton("📁 Parcourir…", self)
        browse_btn.clicked.connect(self._browse_exe)
        exe_row = QHBoxLayout()
        exe_row.addWidget(QLabel("TestRunner.exe :", self))
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(browse_btn)

        # ---- scope + run
        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem("Mods du profil courant", userData=SCOPE_PROFILE)
        self.scope_combo.addItem("Toute la bibliothèque", userData=SCOPE_LIBRARY)
        self.run_btn = QPushButton("▶ Lancer les tests", self)
        self.run_btn.clicked.connect(self._emit_run)
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Portée :", self))
        scope_row.addWidget(self.scope_combo, 1)
        scope_row.addWidget(self.run_btn)

        self.progress = QProgressBar(self)
        self.progress.setVisible(False)

        # ---- summary + status filter
        self.summary = QLabel("", self)
        self.summary.setWordWrap(True)
        self.filter_combo = QComboBox(self)
        self.filter_combo.addItem("Tous", userData=FILTER_ALL)
        self.filter_combo.addItem("⚠❌ Problèmes (KO + à vérifier)", userData=FILTER_PROBLEMS)
        self.filter_combo.addItem("❌ KO seulement", userData=STATUS_KO)
        self.filter_combo.addItem("⚠ À vérifier seulement", userData=STATUS_WARN)
        self.filter_combo.addItem("✅ OK seulement", userData=STATUS_OK)
        self.filter_combo.currentIndexChanged.connect(self._populate_table)
        filter_row = QHBoxLayout()
        filter_row.addWidget(self.summary, 1)
        filter_row.addWidget(QLabel("Afficher :", self))
        filter_row.addWidget(self.filter_combo)

        # ---- results table + per-mod detail
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Statut", "Mod", "Résumé"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.currentCellChanged.connect(self._on_row_changed)

        self.detail = QPlainTextEdit(self)
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Sélectionne un mod pour voir le détail des contrôles.")

        split = QSplitter(Qt.Orientation.Vertical, self)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(intro)
        layout.addLayout(exe_row)
        layout.addLayout(scope_row)
        layout.addWidget(self.progress)
        layout.addLayout(filter_row)
        layout.addWidget(split, 1)

    # ------------------------------------------------------------------ actions

    def _browse_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner Giants TestRunner.exe", self.exe_edit.text(),
            "Exécutables (*.exe);;Tous les fichiers (*)",
        )
        if path:
            self.exe_edit.setText(path)

    def _emit_run(self) -> None:
        scope = self.scope_combo.currentData()
        self.run_requested.emit(scope, self.exe_edit.text().strip())

    # ----------------------------------------------------- driven by main window

    def set_running(self, running: bool) -> None:
        self.run_btn.setEnabled(not running)
        self.scope_combo.setEnabled(not running)
        self.progress.setVisible(running)
        if running:
            self.progress.setRange(0, 0)  # busy until first progress tick
            self.summary.setText("Validation en cours…")

    def set_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        if name:
            self.summary.setText(f"Validation… ({done}/{total}) {name}")

    def set_results(self, results: list[ModTestResult]) -> None:
        self._results = results
        self.progress.setVisible(False)
        self._update_summary()
        self._populate_table()

    def _update_summary(self) -> None:
        ok = sum(1 for r in self._results if r.status == STATUS_OK)
        warn = sum(1 for r in self._results if r.status == STATUS_WARN)
        ko = sum(1 for r in self._results if r.status == STATUS_KO)
        self.summary.setText(
            f"{len(self._results)} mod(s) testé(s) — "
            f"✅ {ok} OK  ·  ⚠ {warn} à vérifier  ·  ❌ {ko} KO."
        )

    def _populate_table(self) -> None:
        allowed = _FILTER_STATUSES.get(self.filter_combo.currentData(), _FILTER_STATUSES[FILTER_ALL])
        rows = [(i, r) for i, r in enumerate(self._results) if r.status in allowed]
        self.table.setRowCount(len(rows))
        for row, (idx, res) in enumerate(rows):
            bg = _STATUS_BG.get(res.status)
            fg = _STATUS_FG.get(res.status)
            status_item = QTableWidgetItem(STATUS_LABELS_FR.get(res.status, res.status))
            status_item.setData(Qt.ItemDataRole.UserRole, idx)
            mod_item = QTableWidgetItem(f"{res.title}  ({res.filename})")
            summary_item = QTableWidgetItem(res.summary())
            for col, item in enumerate((status_item, mod_item, summary_item)):
                if bg is not None:
                    item.setBackground(QBrush(bg))
                if fg is not None:
                    item.setForeground(QBrush(fg))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # Refresh the selection + detail for the new row set (the row index may
        # be unchanged after a filter switch, so force the detail to follow).
        if rows:
            self.table.setCurrentCell(0, 0)
            self._on_row_changed(0)
        else:
            self.table.clearSelection()
            self.detail.clear()

    def _on_row_changed(self, row: int, *_args) -> None:
        item = self.table.item(row, 0) if row >= 0 else None
        idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if idx is None or idx >= len(self._results):
            self.detail.clear()
            return
        res = self._results[idx]
        lines = [f"{res.title}  ({res.filename})", ""]
        for chk in res.checks:
            prefix = _LEVEL_PREFIX.get(chk.level, "•")
            line = f"{prefix} {chk.label}"
            if chk.detail:
                line += f" — {chk.detail}"
            lines.append(line)
        if res.testrunner_returncode is not None or res.testrunner_output:
            lines.append("")
            lines.append("── Giants TestRunner ──")
            if res.testrunner_returncode is not None:
                lines.append(f"Code de sortie : {res.testrunner_returncode}")
            if res.testrunner_output:
                lines.append(res.testrunner_output)
        self.detail.setPlainText("\n".join(lines))
