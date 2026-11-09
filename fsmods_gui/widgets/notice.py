"""Encadré d'information dans une page (dépendance à ajouter, mods absents…).

Remplace les fenêtres « Oui / Non » de la page Profil : le message reste visible
dans la page, avec un bouton d'action et une croix pour l'écarter.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QWidget

from .. import theme
from ..editor_notices import KIND_ERROR, Notice
from . import icons


class NoticeBanner(QWidget):
    action_requested = Signal(object)  # Notice
    dismissed = Signal(object)  # Notice

    def __init__(self, notice: Notice, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.notice = notice
        error = notice.kind == KIND_ERROR
        self.setProperty("role", "notice")
        self.setProperty("level", "error" if error else "info")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        t = theme.current()
        fg = t.red_text if error else t.blue_text

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 8, 10)
        lay.setSpacing(10)
        icon = QLabel(self)
        icon.setPixmap(icons.pixmap("alert" if error else "link", fg, 20))
        self.label = QLabel(notice.text, self)
        self.label.setWordWrap(True)
        self.label.setProperty("role", "notice-text")
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.label, 1)
        self.action_btn: QPushButton | None = None
        if notice.action:
            self.action_btn = QPushButton(notice.action_label, self)
            self.action_btn.setProperty("role", "notice-action")
            self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_btn.clicked.connect(lambda: self.action_requested.emit(self.notice))
            lay.addWidget(self.action_btn)
        close = QToolButton(self)
        close.setProperty("role", "icon")
        close.setAccessibleName("Écarter ce message")
        close.setToolTip("Écarter")
        close.setIcon(icons.icon("x", fg, 16))
        close.setIconSize(QSize(16, 16))
        close.clicked.connect(lambda: self.dismissed.emit(self.notice))
        lay.addWidget(close)
