"""Objectifs de carrière en cartes, regroupées par statut.

Remplace le tableau de neuf colonnes de la vue Objectifs (0.15) : chaque carte
montre le nom, la catégorie et la difficulté, la récompense, la progression et,
pour un objectif terminé avec de l'argent, la case « Versé ». Un clic sélectionne
la carte (détail et actions sous la liste).
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..career import presentation as pr
from ..career.objectives import ST_COMPLETED, ST_LOCKED, Objective, can_mark_paid

CARD_MIN_W = 300


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ObjectiveCard(QWidget):
    clicked = Signal(str)  # id
    paid_toggled = Signal(str, bool)

    def __init__(self, o: Objective, subtitle: str, requires: str, parent=None) -> None:
        super().__init__(parent)
        self.objective_id = o.id
        self.setProperty("role", "card")
        self.setProperty("selected", "false")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(CARD_MIN_W - 40)
        if o.description:
            self.setToolTip(o.description)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel(self)
        dot.setProperty("role", "dot")
        dot.setProperty("level", pr.STATUS_LEVEL.get(o.status, "off"))
        dot.setFixedSize(9, 9)
        dot.setToolTip(o.status)
        title = QLabel(o.name, self)
        title.setProperty("role", "card-title")
        title.setWordWrap(True)
        head.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(title, 1)
        reward = pr.reward_text(o)
        if reward:
            pill = QLabel(reward, self)
            pill.setProperty("role", "reward")
            head.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        sub = QLabel(subtitle, self)
        sub.setProperty("role", "muted")
        lay.addWidget(sub)

        if o.status == ST_LOCKED:
            req = QLabel(f"Requiert : {requires}" if requires else "Verrouillé", self)
            req.setProperty("role", "muted")
            req.setWordWrap(True)
            lay.addWidget(req)
        else:
            self.bar = QProgressBar(self)
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(8)
            self.bar.setRange(0, 1000)
            self.bar.setValue(round(o.progress * 1000))
            lay.addWidget(self.bar)
            row = QHBoxLayout()
            progress = QLabel(pr.progress_text(o), self)
            percent = QLabel(pr.percent_text(o), self)
            percent.setProperty("role", "strong")
            row.addWidget(progress, 1)
            row.addWidget(percent)
            lay.addLayout(row)

        self.paid_box: QCheckBox | None = None
        if o.status == ST_COMPLETED and o.reward.money:
            self.paid_box = QCheckBox("Versé", self)
            self.paid_box.setChecked(o.reward_state == "claimed")
            self.paid_box.setEnabled(can_mark_paid(o))
            self.paid_box.setToolTip(
                "Coche quand tu as ajouté l'argent sur ta ferme (PowerTools, F12)."
            )
            self.paid_box.toggled.connect(
                lambda checked: self.paid_toggled.emit(self.objective_id, checked)
            )
            state = QLabel(pr.reward_state_text(o), self)
            state.setProperty("role", "muted")
            row = QHBoxLayout()
            row.addWidget(self.paid_box)
            row.addWidget(state, 1)
            lay.addLayout(row)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        _repolish(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self.objective_id)
        super().mousePressEvent(event)


class ObjectiveCards(QWidget):
    """Groupes d'objectifs (« En cours », « Terminés »…) en grilles de cartes."""

    selected = Signal(str)  # id
    paid_toggled = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: dict[str, ObjectiveCard] = {}
        self._grids: list[tuple[QGridLayout, list[ObjectiveCard]]] = []
        self._columns = 0
        self._selected: str | None = None
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self._content = QWidget()
        scroll.setWidget(self._content)
        self._root = QVBoxLayout(self._content)
        self._root.setContentsMargins(0, 0, 8, 0)
        self._root.setSpacing(10)
        self.empty_label = QLabel(
            "Aucun objectif ici. Ajoute un modèle ou un objectif perso.", self._content
        )
        self.empty_label.setProperty("role", "muted")

    def set_groups(
        self,
        groups: list[tuple[str, list[Objective]]],
        subtitle: Callable[[Objective], str],
        requires: Callable[[Objective], str],
    ) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None and w is not self.empty_label:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()
        self._grids = []
        self._root.addWidget(self.empty_label)
        self.empty_label.setVisible(not groups)
        for title, objectives in groups:
            heading = QLabel(f"{title.upper()} · {len(objectives)}", self._content)
            heading.setProperty("role", "section")
            self._root.addWidget(heading)
            holder = QWidget(self._content)
            grid = QGridLayout(holder)
            grid.setContentsMargins(0, 0, 0, 6)
            grid.setSpacing(12)
            cards = []
            for o in objectives:
                card = ObjectiveCard(o, subtitle(o), requires(o), holder)
                card.clicked.connect(self._on_clicked)
                card.paid_toggled.connect(self.paid_toggled)
                self._cards[o.id] = card
                cards.append(card)
            self._grids.append((grid, cards))
            self._root.addWidget(holder)
        self._root.addStretch(1)
        self._columns = 0
        self._relayout()
        if self._selected in self._cards:
            self._cards[self._selected].set_selected(True)

    def card(self, objective_id: str) -> ObjectiveCard | None:
        return self._cards.get(objective_id)

    def select(self, objective_id: str | None) -> None:
        for oid, card in self._cards.items():
            card.set_selected(oid == objective_id)
        self._selected = objective_id

    def _on_clicked(self, objective_id: str) -> None:
        self.select(objective_id)
        self.selected.emit(objective_id)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        columns = max(1, (self.width() - 20) // (CARD_MIN_W + 12))
        if columns == self._columns:
            return
        self._columns = columns
        for grid, cards in self._grids:
            while grid.count():
                grid.takeAt(0)
            for i, card in enumerate(cards):
                grid.addWidget(card, i // columns, i % columns)
            for c in range(columns):
                grid.setColumnStretch(c, 1)
