"""Cadre de la fenêtre : barre latérale de navigation et barre de session.

Pourquoi : remplacer les neuf onglets de 0.10 par quelques espaces clairs
(voir :mod:`fsmods_gui.navigation`) et donner en permanence l'état utile
(jeu lancé ou non, profil installé dans le dossier du jeu, bibliothèque,
sauvegarde de la config) au lieu de messages qui disparaissent après 5 s.

Ces widgets sont passifs : la fenêtre principale leur donne l'état et écoute
leurs signaux.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import navigation as nav
from . import icons


def _repolish(widget: QWidget) -> None:
    """Réapplique la feuille de style après un changement de propriété dynamique."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


class NavButton(QPushButton):
    """Entrée de la barre latérale : icône, libellé, pastille facultative."""

    def __init__(self, label: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setProperty("role", "nav")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(38)
        icons.bind(self, icon_name)
        self._badge = QLabel(self)
        self._badge.setProperty("role", "badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.hide()

    def set_badge(self, count: int) -> None:
        text = nav.badge_text(count)
        self._badge.setText(text)
        self._badge.setVisible(bool(text))
        self._badge.adjustSize()
        self._place_badge()

    def badge_text(self) -> str:
        return "" if self._badge.isHidden() else self._badge.text()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._place_badge()

    def _place_badge(self) -> None:
        b = self._badge
        w = max(20, b.sizeHint().width())
        b.resize(w, 18)
        b.move(self.width() - w - 10, (self.height() - 18) // 2)


class SideNav(QWidget):
    """Barre latérale : espaces de navigation, puis contenu libre (listes, actions)."""

    section_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(236)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 12, 10, 10)
        self._layout.setSpacing(2)

        self._buttons: dict[str, NavButton] = {}
        self._current: str | None = None
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for s in nav.nav_sections():
            btn = NavButton(s.label, s.icon, self)
            btn.setToolTip(s.tooltip)
            btn.clicked.connect(lambda _c=False, k=s.key: self.section_selected.emit(k))
            self._group.addButton(btn)
            self._buttons[s.key] = btn
            self._layout.addWidget(btn)
        self._layout.addSpacing(10)

    def button(self, key: str) -> NavButton:
        return self._buttons[key]

    def set_current(self, key: str) -> None:
        """Coche l'entrée ``key`` ; une page hors barre latérale ne coche rien."""
        self._current = key
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)
            return
        self._group.setExclusive(False)
        for b in self._buttons.values():
            b.setChecked(False)
        self._group.setExclusive(True)

    def current(self) -> str | None:
        return self._current

    def set_badge(self, key: str, count: int) -> None:
        self._buttons[key].set_badge(count)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_spacing(self, size: int) -> None:
        self._layout.addSpacing(size)


def section_header(title: str, actions: list[tuple[str, str, object]], parent: QWidget) -> QWidget:
    """Titre de section (« PROFILS ») suivi de petits boutons-icônes.

    ``actions`` : liste de ``(icône, info-bulle, slot)``.
    """
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(4, 8, 0, 2)
    lay.setSpacing(2)
    label = QLabel(title.upper(), row)
    label.setProperty("role", "section")
    lay.addWidget(label, 1)
    for icon_name, tip, slot in actions:
        btn = QToolButton(row)
        btn.setProperty("role", "icon")
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icons.bind(btn, icon_name, icons.ROLE_MUTED)
        btn.clicked.connect(slot)  # type: ignore[arg-type]
        lay.addWidget(btn)
    return row


class SessionBar(QWidget):
    """Barre du bas : état du jeu, profil installé, bibliothèque, sauvegarde, message."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "sessionbar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(20)

        game = QHBoxLayout()
        game.setSpacing(7)
        self.game_dot = QLabel(self)
        self.game_dot.setProperty("role", "dot")
        self.game_dot.setFixedSize(9, 9)
        self.game_label = QLabel(self)
        self.game_label.setProperty("role", "strong")
        game.addWidget(self.game_dot)
        game.addWidget(self.game_label)
        lay.addLayout(game)

        self.profile_label = QLabel(self)
        self.library_label = QLabel(self)
        self.backup_label = QLabel(self)
        for label in (self.profile_label, self.library_label, self.backup_label):
            label.setProperty("role", "muted")
            lay.addWidget(label)

        self.message_label = QLabel(self)
        self.message_label.setProperty("role", "muted")
        self.message_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.message_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.message_label, 1)

        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self.message_label.clear)

        self.set_game(nav.GAME_CLOSED)
        self.set_active_profile(None)
        self.set_library(None)
        self.backup_label.hide()

    def set_game(self, state: str) -> None:
        self.game_label.setText(nav.game_label(state))
        self.game_dot.setProperty("level", nav.game_level(state))
        _repolish(self.game_dot)

    def set_active_profile(self, name: str | None) -> None:
        self.profile_label.setText(nav.active_profile_label(name))

    def set_library(self, count: int | None) -> None:
        self.library_label.setText(nav.library_label(count))

    def set_backup(self, text: str, tooltip: str = "") -> None:
        self.backup_label.setText(text)
        self.backup_label.setToolTip(tooltip)
        self.backup_label.show()

    def flash(self, message: str, ms: int = 6000) -> None:
        """Message passager à droite (remplace l'ancienne barre d'état)."""
        self.message_label.setText(message)
        self.message_label.setToolTip(message)
        self._message_timer.start(ms)

    def message(self) -> str:
        return self.message_label.text()
