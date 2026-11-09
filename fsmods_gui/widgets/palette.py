"""Palette de commandes (Ctrl+K) : chercher un profil, un mod, une action, et l'exécuter.

La liste et la recherche viennent de :mod:`fsmods_gui.commands` ; ce dialogue
ne gère que la saisie au clavier (↑ ↓ Entrée Échap) et la souris.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..commands import Command, search
from . import icons

_GROUP_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class CommandPalette(QDialog):
    command_chosen = Signal(str)  # Command.key

    def __init__(self, commands: list[Command], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rechercher ou lancer")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setModal(True)
        self.setProperty("role", "palette")
        self.setMinimumWidth(620)
        self._commands = commands

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(14, 10, 14, 10)
        glass = QLabel(self)
        glass.setPixmap(icons.pixmap("search", None, 18))
        self.input = QLineEdit(self)
        self.input.setProperty("role", "palette-input")
        self.input.setPlaceholderText("Profil, mod ou action… (ex. jouer, courseplay, rescanner)")
        self.input.textChanged.connect(self._refresh)
        self.input.installEventFilter(self)
        hint = QLabel("Échap pour fermer", self)
        hint.setProperty("role", "muted")
        top.addWidget(glass)
        top.addWidget(self.input, 1)
        top.addWidget(hint)
        lay.addLayout(top)

        self.list = QListWidget(self)
        self.list.setProperty("role", "palette-list")
        self.list.setMinimumHeight(360)
        self.list.itemActivated.connect(self._choose_item)
        self.list.itemClicked.connect(self._choose_item)
        lay.addWidget(self.list, 1)
        self.empty = QLabel("Aucun résultat.", self)
        self.empty.setProperty("role", "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty)
        self._refresh("")

    # ------------------------------------------------------------------ data

    def results(self) -> list[str]:
        """Clés des commandes affichées (sans les en-têtes de groupe)."""
        out = []
        for i in range(self.list.count()):
            key = self.list.item(i).data(Qt.ItemDataRole.UserRole)
            if key:
                out.append(key)
        return out

    def _refresh(self, text: str) -> None:
        self.list.clear()
        found = search(self._commands, text)
        group = None
        for c in found:
            if c.group != group:
                group = c.group
                head = QListWidgetItem(group.upper())
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                head.setData(_GROUP_ROLE, True)
                self.list.addItem(head)
            item = QListWidgetItem(f"{c.label}    {c.hint}" if c.hint else c.label)
            item.setData(Qt.ItemDataRole.UserRole, c.key)
            item.setToolTip(c.hint)
            self.list.addItem(item)
        self.empty.setVisible(not found)
        self._select_first()

    def _select_first(self) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole):
                self.list.setCurrentRow(i)
                return

    def _move(self, step: int) -> None:
        row = self.list.currentRow()
        n = self.list.count()
        for _ in range(n):
            row = (row + step) % max(1, n)
            if self.list.item(row).data(Qt.ItemDataRole.UserRole):
                self.list.setCurrentRow(row)
                return

    def _choose_item(self, item: QListWidgetItem | None) -> None:
        key = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if key:
            self.accept()
            self.command_chosen.emit(key)

    def choose_current(self) -> None:
        self._choose_item(self.list.currentItem())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()  # type: ignore[attr-defined]
            if key == Qt.Key.Key_Down:
                self._move(1)
                return True
            if key == Qt.Key.Key_Up:
                self._move(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.choose_current()
                return True
        return super().eventFilter(watched, event)
