"""Application du thème (clair / sombre / système) à l'application Qt.

Les couleurs viennent de :mod:`fsmods_gui.theme` (pur) ; ce module les pose sur
l'application : style Fusion (rendu identique partout, entièrement piloté par la
palette et la feuille de style), palette, police, feuille de style, puis
recoloration des icônes déjà affichées. Le choix est mémorisé dans ``QSettings``.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from .. import theme
from . import icons

SETTINGS_KEY = "ui/theme"


def saved_mode() -> str:
    return theme.normalize_mode(QSettings().value(SETTINGS_KEY, theme.MODE_SYSTEM))


def save_mode(mode: str) -> None:
    QSettings().setValue(SETTINGS_KEY, theme.normalize_mode(mode))


def system_is_dark(app: QApplication) -> bool:
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def _palette(t: theme.Tokens) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.surface2,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.surface,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.ToolTipBase: t.surface,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_text,
        QPalette.ColorRole.Link: t.blue,
        QPalette.ColorRole.Light: t.surface,
        QPalette.ColorRole.Midlight: t.surface2,
        QPalette.ColorRole.Mid: t.border_strong,
        QPalette.ColorRole.Dark: t.border_strong,
        QPalette.ColorRole.Shadow: t.border,
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return p


def _font() -> QFont:
    available = set(QFontDatabase.families())
    family = next((f for f in theme.FONT_FAMILIES if f in available), None)
    font = QFont(family) if family else QApplication.font()
    font.setPointSizeF(10)
    return font


def refresh_icons(app: QApplication) -> None:
    """Recolore toutes les icônes posées via :func:`icons.bind`."""
    for widget in app.allWidgets():
        icons.apply_bound(widget)
        for action in widget.actions():
            icons.apply_bound(action)


def apply_tokens(app: QApplication, tokens: theme.Tokens) -> None:
    theme.set_current(tokens)
    app.setPalette(_palette(tokens))
    app.setStyleSheet(theme.build_stylesheet(tokens))
    refresh_icons(app)
    for widget in app.allWidgets():
        widget.update()


def apply_mode(app: QApplication, mode: str) -> theme.Tokens:
    tokens = theme.resolve(mode, system_is_dark(app))
    apply_tokens(app, tokens)
    return tokens


def install(app: QApplication) -> None:
    """Thème au démarrage + suivi du thème de Windows en mode « système »."""
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)
    app.setFont(_font())
    apply_mode(app, saved_mode())

    def on_system_change(_scheme) -> None:
        if saved_mode() == theme.MODE_SYSTEM:
            apply_mode(app, theme.MODE_SYSTEM)

    app.styleHints().colorSchemeChanged.connect(on_system_change)


def set_mode(app: QApplication, mode: str) -> None:
    """Changement de thème choisi par l'utilisateur (mémorisé)."""
    save_mode(mode)
    apply_mode(app, mode)
