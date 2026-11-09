"""Vues d'ensemble en cartes : outils du Diagnostic, collections de la Bibliothèque.

Pourquoi : les outils de maintenance (0.11 : six sous-onglets muets) et les
collections (0.11 : une simple liste latérale) gagnent une vue d'ensemble où
chaque élément dit ce qu'il est et ce qui mérite attention, avant d'ouvrir le
détail. Widgets passifs : ils émettent la clé de l'élément choisi.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..diagnostics import TOOLS, Status
from . import icons

CARD_MIN_W = 280


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _Grid(QWidget):
    """Grille de cartes dont le nombre de colonnes suit la largeur."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[QWidget] = []
        self._columns = 0
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        self._root = QVBoxLayout(content)
        self._root.setContentsMargins(20, 16, 20, 20)
        self._root.setSpacing(14)
        self.header = QHBoxLayout()
        titles = QVBoxLayout()
        t = QLabel(title, content)
        t.setProperty("role", "page-title")
        st = QLabel(subtitle, content)
        st.setProperty("role", "muted")
        st.setWordWrap(True)
        titles.addWidget(t)
        titles.addWidget(st)
        self.header.addLayout(titles, 1)
        self._root.addLayout(self.header)
        self._grid = QGridLayout()
        self._grid.setSpacing(14)
        self._root.addLayout(self._grid)
        self._root.addStretch(1)

    def _set_cards(self, cards: list[QWidget]) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = cards
        self._columns = 0
        self._relayout()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        columns = max(1, (self.width() - 40) // (CARD_MIN_W + 14))
        if columns == self._columns and self._grid.count() == len(self._cards):
            return
        self._columns = columns
        while self._grid.count():
            self._grid.takeAt(0)
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // columns, i % columns)
        for c in range(columns):
            self._grid.setColumnStretch(c, 1)


def _card(parent: QWidget) -> tuple[QWidget, QVBoxLayout]:
    card = QWidget(parent)
    card.setProperty("role", "card")
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    card.setMinimumWidth(CARD_MIN_W - 40)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(8)
    return card, lay


def _icon_title(card: QWidget, icon_name: str, title: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(12)
    badge = QLabel(card)
    badge.setProperty("role", "thumb")
    badge.setFixedSize(QSize(40, 40))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setPixmap(icons.pixmap(icon_name, None, 20))
    label = QLabel(title, card)
    label.setProperty("role", "card-title")
    row.addWidget(badge)
    row.addWidget(label, 1)
    return row


class DiagnosticHub(_Grid):
    """Six outils de maintenance en cartes, chacun avec son état."""

    open_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Diagnostic",
            "Les outils de maintenance au même endroit. Un point orange signale ce qui "
            "mérite un coup d'œil.",
            parent,
        )
        self.status_labels: dict[str, QLabel] = {}
        self.status_dots: dict[str, QLabel] = {}
        cards: list[QWidget] = []
        for tool in TOOLS:
            card, lay = _card(self)
            lay.addLayout(_icon_title(card, tool.icon, tool.title))
            desc = QLabel(tool.description, card)
            desc.setProperty("role", "muted")
            desc.setWordWrap(True)
            lay.addWidget(desc, 1)
            status = QHBoxLayout()
            dot = QLabel(card)
            dot.setProperty("role", "dot")
            dot.setFixedSize(9, 9)
            text = QLabel(card)
            text.setWordWrap(True)
            status.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
            status.addWidget(text, 1)
            lay.addLayout(status)
            open_btn = QPushButton("Ouvrir", card)
            open_btn.setAccessibleName(f"Ouvrir {tool.title}")
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.clicked.connect(lambda _c=False, k=tool.key: self.open_requested.emit(k))
            row = QHBoxLayout()
            row.addWidget(open_btn)
            row.addStretch(1)
            lay.addLayout(row)
            self.status_labels[tool.key] = text
            self.status_dots[tool.key] = dot
            cards.append(card)
        self._set_cards(cards)

    def set_status(self, key: str, status: Status) -> None:
        self.status_labels[key].setText(status.text)
        dot = self.status_dots[key]
        dot.setProperty("level", status.level)
        _repolish(dot)


class CollectionsOverview(_Grid):
    """Les collections en cartes : nombre de mods, profils qui les utilisent."""

    open_requested = Signal(str)  # slug
    new_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Collections",
            "Des mods installés souvent ensemble (viticole, forestier, indispensables…). "
            "Un profil reçoit une collection en la cochant dans sa page.",
            parent,
        )
        new_btn = QPushButton("Nouvelle collection", self)
        icons.bind(new_btn, "plus")
        new_btn.clicked.connect(self.new_requested.emit)
        self.header.addWidget(new_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self.empty_label = QLabel(
            "Aucune collection pour l'instant. Crée-en une pour regrouper les mods "
            "communs à plusieurs profils.",
            self,
        )
        self.empty_label.setProperty("role", "muted")
        self.empty_label.setWordWrap(True)
        self._root.insertWidget(1, self.empty_label)

    def set_collections(self, rows: list[tuple[str, str, int, list[str], str]]) -> None:
        """``rows`` : (slug, nom, nombre de mods, profils qui l'héritent, description)."""
        cards: list[QWidget] = []
        for slug, name, count, users, description in rows:
            card, lay = _card(self)
            lay.addLayout(_icon_title(card, "collection", name))
            text = description.strip()
            desc = QLabel(
                text or "Aucune description : « Modifier » pour en ajouter une.", card
            )
            desc.setProperty("role", "muted")
            desc.setWordWrap(True)
            if text:
                desc.setToolTip(text)
            lay.addWidget(desc)
            meta = QLabel(f"{count} mod" + ("s" if count > 1 else ""), card)
            meta.setProperty("role", "muted")
            used = QLabel(
                "Utilisée par : " + ", ".join(users) if users else "Utilisée par aucun profil",
                card,
            )
            used.setWordWrap(True)
            lay.addWidget(meta)
            lay.addWidget(used, 1)
            open_btn = QPushButton("Modifier", card)
            open_btn.setAccessibleName(f"Modifier la collection {name}")
            open_btn.clicked.connect(lambda _c=False, s=slug: self.open_requested.emit(s))
            row = QHBoxLayout()
            row.addWidget(open_btn)
            row.addStretch(1)
            lay.addLayout(row)
            cards.append(card)
        self.empty_label.setVisible(not rows)
        self._set_cards(cards)
