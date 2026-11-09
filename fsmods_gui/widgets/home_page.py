"""Écran d'accueil : la dernière partie mise en avant, les autres profils en cartes.

Pourquoi : lancer une partie était caché dans l'onglet Éditeur. L'accueil (0.12)
met « Jouer » sur chaque profil, montre la carte du jeu et la progression de
l'activation dans la carte concernée, sans fenêtre modale.

Widget passif : il reçoit des :class:`fsmods_gui.home.ProfileCard` et émet des
signaux ; la fenêtre principale fait le reste.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..home import ProfileCard, art_palette
from . import icons

CARD_MIN_W = 250


class MapArt(QWidget):
    """Vignette de carte : image (recadrée) ou champs stylisés de secours."""

    def __init__(self, name: str, pixmap: QPixmap | None, radius: int, parent=None) -> None:
        super().__init__(parent)
        self._name = name
        self._pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self._radius = radius
        self._caption = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_caption(self, text: str) -> None:
        self._caption = text
        self.update()

    def has_image(self) -> bool:
        return self._pixmap is not None

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._radius, self._radius)
        p.setClipPath(clip)
        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            p.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        else:
            self._paint_fields(p, rect)
        if self._caption:
            self._paint_caption(p, rect)
        p.end()

    def _paint_fields(self, p: QPainter, r: QRectF) -> None:
        sky, horizon, f1, f2, f3 = (QColor(c) for c in art_palette(self._name))
        if theme.current().name == theme.MODE_DARK:
            for c in (sky, horizon, f1, f2, f3):
                c.setHsl(c.hue(), c.saturation(), int(c.lightness() * 0.78))
        w, h = r.width(), r.height()

        def pt(x: float, y: float) -> QPointF:
            return QPointF(r.left() + x * w, r.top() + y * h)

        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(r, sky)
        p.setBrush(horizon)
        p.drawPolygon(QPolygonF([pt(0, .5), pt(.38, .42), pt(.75, .47), pt(1, .44), pt(1, .55), pt(0, .6)]))
        for color, poly in (
            (f1, [pt(0, .56), pt(.38, .46), pt(.48, 1), pt(0, 1)]),
            (f2, [pt(.38, .46), pt(.75, .51), pt(.84, 1), pt(.48, 1)]),
            (f3, [pt(.75, .51), pt(1, .48), pt(1, 1), pt(.84, 1)]),
        ):
            p.setBrush(color)
            p.drawPolygon(QPolygonF(poly))
        line = QColor(0, 0, 0, 40)
        p.setPen(line)
        for i in range(3):
            y0 = .68 + i * .1
            p.drawLine(pt(.04, y0), pt(.38, y0 - .09))
            p.drawLine(pt(.52, y0 - .04), pt(.78, y0))

    def _paint_caption(self, p: QPainter, r: QRectF) -> None:
        font = p.font()
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1))
        font.setBold(True)
        p.setFont(font)
        m = p.fontMetrics()
        text = m.elidedText(self._caption, Qt.TextElideMode.ElideRight, int(r.width() - 40))
        pill = QRectF(r.left() + 12, r.bottom() - 12 - (m.height() + 8),
                      m.horizontalAdvance(text) + 20, m.height() + 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 26, 20, 185))
        p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        p.setPen(QColor("#F2F5EF"))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)


def _chip(text: str, parent: QWidget) -> QLabel:
    label = QLabel(text, parent)
    label.setProperty("role", "chip")
    return label


class _CardBase(QWidget):
    def __init__(self, card: ProfileCard, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.card = card
        self.setProperty("role", "card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.play_btn = QPushButton("Jouer", self)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setAccessibleName(f"Jouer à {card.name}")
        self.open_btn = QPushButton(self)
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.progress = QProgressBar(self)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress_label = QLabel(self)
        self.progress_label.setProperty("role", "muted")
        self.progress.hide()
        self.progress_label.hide()

    def set_state(self, *, activating: bool, running: bool, busy: bool) -> None:
        if running:
            self.play_btn.setText("En cours")
        elif activating:
            self.play_btn.setText("Activation…")
        else:
            self.play_btn.setText("Jouer")
        self.play_btn.setEnabled(not busy)
        self.progress.setVisible(activating)
        self.progress_label.setVisible(activating)
        if not activating:
            self.progress.setValue(0)

    def set_progress(self, percent: int, text: str) -> None:
        self.progress.setValue(max(0, min(100, percent)))
        self.progress_label.setText(text)


class HeroCard(_CardBase):
    """Grande carte de la dernière partie jouée."""

    def __init__(self, card: ProfileCard, pixmap: QPixmap | None, parent=None) -> None:
        super().__init__(card, parent)
        self.setProperty("hero", "true")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.art = MapArt(card.name, pixmap, 15, self)
        self.art.setMinimumSize(QSize(320, 230))
        self.art.set_caption(card.map_label)
        lay.addWidget(self.art, 1)

        info = QVBoxLayout()
        info.setContentsMargins(26, 22, 26, 22)
        info.setSpacing(10)
        kicker = QLabel(f"DERNIÈRE PARTIE · {card.last_played_label}", self)
        kicker.setProperty("role", "section")
        title = QLabel(card.name, self)
        title.setProperty("role", "hero-title")
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in (card.mods_label, card.collections_label):
            chips.addWidget(_chip(text, self))
        chips.addStretch(1)
        info.addWidget(kicker)
        info.addWidget(title)
        info.addLayout(chips)
        info.addWidget(self.progress)
        info.addWidget(self.progress_label)
        info.addStretch(1)
        buttons = QHBoxLayout()
        self.play_btn.setProperty("variant", "primary")
        self.play_btn.setMinimumHeight(46)
        self.play_btn.setIconSize(QSize(18, 18))
        icons.bind(self.play_btn, "play", icons.ROLE_ON_ACCENT)
        self.open_btn.setText("Modifier le profil")
        self.open_btn.setMinimumHeight(46)
        buttons.addWidget(self.play_btn)
        buttons.addWidget(self.open_btn)
        buttons.addStretch(1)
        info.addLayout(buttons)
        self.running_hint = QLabel(
            "FS25 est lancé : ferme le jeu pour changer de profil. Les mods "
            "téléchargés en jeu seront proposés à la fermeture.",
            self,
        )
        self.running_hint.setWordWrap(True)
        self.running_hint.setProperty("role", "muted")
        self.running_hint.hide()
        info.addWidget(self.running_hint)
        holder = QWidget(self)
        holder.setLayout(info)
        lay.addWidget(holder, 1)

    def set_state(self, *, activating: bool, running: bool, busy: bool) -> None:
        super().set_state(activating=activating, running=running, busy=busy)
        self.running_hint.setVisible(running)


class ProfileTile(_CardBase):
    """Carte compacte d'un autre profil."""

    def __init__(self, card: ProfileCard, pixmap: QPixmap | None, parent=None) -> None:
        super().__init__(card, parent)
        # La grille choisit le nombre de colonnes : une tuile ne doit jamais
        # imposer sa largeur (sinon la fenêtre s'élargit à chaque relayout).
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(CARD_MIN_W - 40)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 14)
        lay.setSpacing(3)
        self.art = MapArt(card.name, pixmap, 13, self)
        self.art.setFixedHeight(112)
        lay.addWidget(self.art)
        body = QVBoxLayout()
        body.setContentsMargins(16, 10, 16, 0)
        body.setSpacing(2)
        title = QLabel(card.name, self)
        title.setProperty("role", "card-title")
        map_label = QLabel(card.map_label, self)
        map_label.setProperty("role", "muted")
        meta = QLabel(f"{card.mods_label} · {card.last_played_label}", self)
        meta.setProperty("role", "muted")
        for w in (title, map_label, meta, self.progress, self.progress_label):
            body.addWidget(w)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 10, 0, 0)
        self.play_btn.setProperty("variant", "soft")
        self.play_btn.setMinimumHeight(38)
        icons.bind(self.play_btn, "play", icons.ROLE_ACCENT)
        self.open_btn.setText("Modifier")
        self.open_btn.setMinimumHeight(38)
        buttons.addWidget(self.play_btn, 1)
        buttons.addWidget(self.open_btn)
        body.addLayout(buttons)
        lay.addLayout(body)


class HomePage(QWidget):
    """Accueil : titre, bandeau « à ranger », dernière partie, autres profils."""

    play_requested = Signal(str)  # slug
    open_requested = Signal(str)  # slug
    new_requested = Signal()
    inbox_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: dict[str, _CardBase] = {}
        self._tiles: list[QWidget] = []
        self._columns = 0

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        content.setObjectName("homeContent")
        scroll.setWidget(content)
        self._root = QVBoxLayout(content)
        self._root.setContentsMargins(28, 24, 28, 28)
        self._root.setSpacing(18)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Tes parties", content)
        title.setProperty("role", "page-title")
        subtitle = QLabel("Choisis un profil : FS25 démarre avec exactement ses mods, rien de plus.")
        subtitle.setProperty("role", "muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles, 1)
        new_btn = QPushButton("Nouveau profil", content)
        icons.bind(new_btn, "plus")
        new_btn.setMinimumHeight(38)
        new_btn.clicked.connect(self.new_requested.emit)
        head.addWidget(new_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self._root.addLayout(head)

        self.banner = QWidget(content)
        self.banner.setProperty("role", "banner")
        self.banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        b_lay = QHBoxLayout(self.banner)
        b_lay.setContentsMargins(16, 12, 16, 12)
        self.banner_icon = QLabel(self.banner)
        self.banner_text = QLabel(self.banner)
        self.banner_text.setWordWrap(True)
        banner_btn = QPushButton("Ranger les mods", self.banner)
        banner_btn.setProperty("role", "banner-action")
        banner_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        banner_btn.clicked.connect(self.inbox_requested.emit)
        b_lay.addWidget(self.banner_icon)
        b_lay.addWidget(self.banner_text, 1)
        b_lay.addWidget(banner_btn)
        self.banner.hide()
        self._root.addWidget(self.banner)

        self._hero_slot = QVBoxLayout()
        self._root.addLayout(self._hero_slot)
        self.others_title = QLabel("Autres profils", content)
        self.others_title.setProperty("role", "card-title")
        self._root.addWidget(self.others_title)
        self._grid = QGridLayout()
        self._grid.setSpacing(16)
        self._root.addLayout(self._grid)
        self._root.addStretch(1)

        self.new_card = QPushButton("Nouveau profil\nNom, carte et carrière", content)
        self.new_card.setProperty("role", "newcard")
        self.new_card.setMinimumHeight(240)
        self.new_card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.new_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_card.clicked.connect(self.new_requested.emit)

        self.empty_label = QLabel(
            "Aucun profil pour l'instant : crée le premier avec « Nouveau profil ».", content
        )
        self.empty_label.setProperty("role", "muted")
        self._root.insertWidget(2, self.empty_label)

    # ------------------------------------------------------------------ data

    def set_cards(self, cards: list[ProfileCard], pixmaps: dict[str, QPixmap | None]) -> None:
        for widget in list(self._cards.values()):
            widget.setParent(None)
            widget.deleteLater()
        self._cards.clear()
        self._tiles = []
        self.empty_label.setVisible(not cards)

        hero = next((c for c in cards if c.is_last_played), None)
        if hero is None and cards:
            hero = cards[0]
        if hero is not None:
            hero_card = HeroCard(hero, pixmaps.get(hero.slug), self)
            self._wire(hero_card)
            self._hero_slot.addWidget(hero_card)
        others = [c for c in cards if hero is None or c.slug != hero.slug]
        self.others_title.setVisible(bool(cards))
        self.others_title.setText(
            "Autres profils" if others else "Autres profils : aucun pour l'instant"
        )
        for card in others:
            tile = ProfileTile(card, pixmaps.get(card.slug), self)
            self._wire(tile)
            self._tiles.append(tile)
        self._tiles.append(self.new_card)
        self._columns = 0
        self._relayout()

    def _wire(self, card: _CardBase) -> None:
        slug = card.card.slug
        card.play_btn.clicked.connect(lambda _c=False, s=slug: self.play_requested.emit(s))
        card.open_btn.clicked.connect(lambda _c=False, s=slug: self.open_requested.emit(s))
        self._cards[slug] = card

    def set_waiting(self, count: int) -> None:
        self.banner.setVisible(count > 0)
        if count > 0:
            t = theme.current()
            self.banner_icon.setPixmap(icons.pixmap("download", t.blue_text, 22))
            noun = "mod attend" if count == 1 else "mods attendent"
            self.banner_text.setText(
                f"<b>{count} {noun} d'être rangé{'s' if count > 1 else ''}</b><br>"
                "Téléchargés via ModHub en jeu, ou mis à l'abri lors d'une activation. "
                "Rien n'a été supprimé."
            )

    def set_activity(self, activating: str | None, running: str | None) -> None:
        """Profil en cours d'activation / en jeu : boutons et progression des cartes."""
        busy = activating is not None or running is not None
        for slug, card in self._cards.items():
            card.set_state(activating=slug == activating, running=slug == running, busy=busy)

    def set_progress(self, slug: str, percent: int, text: str) -> None:
        card = self._cards.get(slug)
        if card is not None:
            card.set_progress(percent, text)

    def card(self, slug: str) -> _CardBase | None:
        return self._cards.get(slug)

    # ---------------------------------------------------------------- layout

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        columns = max(1, (self.width() - 72) // (CARD_MIN_W + 16))
        if columns == self._columns and self._grid.count() == len(self._tiles):
            return
        self._columns = columns
        while self._grid.count():
            self._grid.takeAt(0)
        for i, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, i // columns, i % columns)
        for c in range(columns):
            self._grid.setColumnStretch(c, 1)
