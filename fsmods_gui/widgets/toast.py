"""Notifications non bloquantes en bas à droite de la fenêtre (« toasts »).

Pourquoi : jusqu'en 0.11, chaque information (activation réussie, mods ajoutés,
export terminé…) ouvrait une fenêtre modale à fermer. Une notification passe
toute seule, n'interrompt pas, et peut porter une action (« Annuler »,
« Ranger »). Les confirmations d'actions destructrices restent des modales.

Les widgets qui ne connaissent pas la fenêtre principale passent par
:func:`notify`, qui trouve la fenêtre et se rabat sur une modale si besoin.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QWidget,
)

from . import icons

DEFAULT_MS = 7000


class Toast(QWidget):
    """Bandeau posé au-dessus de son parent, ancré en bas à droite."""

    def __init__(self, parent: QWidget, bottom_margin: int = 56) -> None:
        super().__init__(parent)
        self.setProperty("role", "toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._bottom_margin = bottom_margin
        self._action: Callable[[], None] | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 8, 10)
        lay.setSpacing(10)
        self.icon = QLabel(self)
        self.icon.setFixedSize(18, 18)
        self.label = QLabel(self)
        self.label.setProperty("role", "toast-text")
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.action_btn = QPushButton(self)
        self.action_btn.setProperty("role", "toast-action")
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.clicked.connect(self._on_action)
        self.close_btn = QToolButton(self)
        self.close_btn.setProperty("role", "toast-close")
        self.close_btn.setAccessibleName("Fermer la notification")
        self.close_btn.setToolTip("Fermer")
        self.close_btn.clicked.connect(self.dismiss)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        parent.installEventFilter(self)
        self.hide()

    # ------------------------------------------------------------------ API

    def show_message(
        self,
        message: str,
        action_label: str | None = None,
        action: Callable[[], None] | None = None,
        *,
        error: bool = False,
        ms: int = DEFAULT_MS,
    ) -> None:
        from .. import theme

        t = theme.current()
        self.setProperty("level", "error" if error else "ok")
        self.style().unpolish(self)
        self.style().polish(self)
        self.label.setText(message)
        longest = max((self.label.fontMetrics().horizontalAdvance(line)
                       for line in message.splitlines() or [""]), default=0)
        self.label.setMinimumWidth(min(longest + 4, 340))
        # Le bandeau est foncé en thème clair et clair en thème sombre.
        fg = t.surface if t.name == theme.MODE_LIGHT else t.bg
        self.icon.setPixmap(icons.pixmap("alert" if error else "check", fg, 18, stroke=2.2))
        self.close_btn.setIcon(icons.icon("x", fg, 16))
        self._action = action
        self.action_btn.setVisible(bool(action_label and action))
        self.action_btn.setText(action_label or "")
        parent = self.parentWidget()
        width = parent.width() if parent is not None else 520
        self.setMaximumWidth(min(480, max(260, width - 48)))
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._timer.start(ms)

    def dismiss(self) -> None:
        self._timer.stop()
        self._action = None
        self.hide()

    def message(self) -> str:
        return self.label.text() if not self.isHidden() else ""

    def trigger_action(self) -> None:
        """Comme un clic sur le bouton d'action (utile aux tests)."""
        self._on_action()

    # ------------------------------------------------------------ internals

    def _on_action(self) -> None:
        action = self._action
        self.dismiss()
        if action is not None:
            action()

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(
            max(8, parent.width() - self.width() - 20),
            max(8, parent.height() - self.height() - self._bottom_margin),
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._place()
        return False


def notify(
    widget: QWidget,
    message: str,
    action_label: str | None = None,
    action: Callable[[], None] | None = None,
    *,
    error: bool = False,
) -> None:
    """Notification depuis n'importe quel widget : passe par la fenêtre principale
    (méthode ``notify``) ou, à défaut, par une petite modale."""
    window = widget.window()
    target = getattr(window, "notify", None)
    if callable(target):
        target(message, action_label, action, error=error)
        return
    if error:
        QMessageBox.warning(widget, "Information", message)
    else:
        QMessageBox.information(widget, "Information", message)
