"""Embeddable panel presenting the FS25 log analysis as a filterable table."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..profiles.log_analyzer import (
    KIND_LABELS_FR,
    SEV_ERROR,
    LogIssue,
)

# Pale row backgrounds paired with an explicit dark text colour, so rows stay
# readable whatever the active (light/dark) theme: without forcing the
# foreground, a dark theme keeps light text that is invisible on these fills.
_ERROR_BG = QColor(255, 205, 205)
_ERROR_FG = QColor(120, 0, 0)
_WARNING_BG = QColor(255, 240, 196)
_WARNING_FG = QColor(120, 80, 0)


class LogReportPanel(QWidget):
    """Render a list of :class:`LogIssue` with a severity/kind filter."""

    def __init__(
        self,
        issues: list[LogIssue],
        *,
        log_path: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._issues = issues

        n_err = sum(i.count for i in issues if i.severity == SEV_ERROR)
        n_warn = sum(i.count for i in issues if i.severity != SEV_ERROR)
        if issues:
            intro = QLabel(
                f"<b>{n_err}</b> erreur(s) et <b>{n_warn}</b> avertissement(s) "
                f"détecté(s) dans le log de la dernière session."
            )
        else:
            intro = QLabel("✓ Aucune erreur ni avertissement détecté dans le log.")
        intro.setWordWrap(True)

        # ---- filter row
        self.kind_filter = QComboBox(self)
        self.kind_filter.addItem("Tous les types", userData=None)
        self.kind_filter.addItem("Erreurs uniquement", userData="__errors__")
        for key, label in KIND_LABELS_FR.items():
            self.kind_filter.addItem(label, userData=key)
        self.kind_filter.currentIndexChanged.connect(self._apply_filter)

        copy_btn = QPushButton("📋 Copier le rapport", self)
        copy_btn.clicked.connect(self._copy_report)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtre :", self))
        filter_row.addWidget(self.kind_filter)
        filter_row.addStretch(1)
        filter_row.addWidget(copy_btn)

        # ---- table
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Sévérité", "Type", "Mod", "Message (FR)", "Occ."]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(intro)
        if log_path:
            path_label = QLabel(f"<small>{log_path}</small>", self)
            path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(path_label)
        layout.addLayout(filter_row)
        layout.addWidget(self.table, 1)

        self._populate(self._issues)

    # ----------------------------------------------------------------- helpers

    def _filtered(self) -> list[LogIssue]:
        data = self.kind_filter.currentData()
        if data is None:
            return self._issues
        if data == "__errors__":
            return [i for i in self._issues if i.severity == SEV_ERROR]
        return [i for i in self._issues if i.kind == data]

    def _apply_filter(self) -> None:
        self._populate(self._filtered())

    def _populate(self, issues: list[LogIssue]) -> None:
        self.table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            is_error = issue.severity == SEV_ERROR
            bg = _ERROR_BG if is_error else _WARNING_BG
            fg = _ERROR_FG if is_error else _WARNING_FG
            cells = [
                issue.severity_label,
                issue.kind_label,
                issue.mod or "—",
                issue.message_fr,
                str(issue.count),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(QBrush(bg))
                item.setForeground(QBrush(fg))
                if col == 3:
                    tip = issue.raw
                    if issue.callstack:
                        tip += "\n\nPile d'appel :\n" + "\n".join(issue.callstack)
                    item.setToolTip(tip)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )

    def _copy_report(self) -> None:
        lines = ["Sévérité\tType\tMod\tMessage\tOcc."]
        for issue in self._filtered():
            lines.append(
                f"{issue.severity_label}\t{issue.kind_label}\t"
                f"{issue.mod or ''}\t{issue.message_fr}\t{issue.count}"
            )
        QGuiApplication.clipboard().setText("\n".join(lines))
