"""Widgets et thème : régressions visuelles corrigées en 0.10.0.

- le titre du détail d'un mod était forcé en blanc (invisible en thème clair) ;
- les cartes de la galerie étaient peintes en gris foncé sur une fenêtre claire.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QStyleOptionViewItem, QWidget

from fsmods_gui import theme
from fsmods_gui.profiles.catalog import CatalogEntry
from fsmods_gui.widgets import icons, theming
from fsmods_gui.widgets.library_table import CARD_H, CARD_W, CatalogTableModel, ModCardDelegate


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def light(app):
    previous = theme.current()
    theming.apply_tokens(app, theme.LIGHT)
    yield theme.LIGHT
    theming.apply_tokens(app, previous)


def entry() -> CatalogEntry:
    return CatalogEntry(filename="FS25_Test.zip", title="Mod de test", version="1.0.0.0")


def test_mod_detail_title_is_not_forced_white(light):
    from fsmods_gui.widgets.mod_detail import ModDetailDialog

    dlg = ModDetailDialog(entry())
    for label in dlg.findChildren(QLabel):
        assert "#fff" not in label.styleSheet().lower()
    dlg.deleteLater()


def test_library_card_is_light_in_light_theme(light):
    model = CatalogTableModel()
    from pathlib import Path

    from fsmods_gui.profiles.catalog import Catalog

    cat = Catalog(mods_dir=Path("."), entries={"FS25_Test.zip": entry()})
    model.set_catalog(cat)
    delegate = ModCardDelegate()
    image = QImage(QSize(CARD_W, CARD_H), QImage.Format.Format_ARGB32)
    image.fill(QColor(light.bg))
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, CARD_W, CARD_H)
    option.widget = QWidget()
    delegate.paint(painter, option, model.index(0, 0))
    painter.end()
    # Un point du fond de la carte, sous la vignette, à côté du texte.
    pixel = image.pixelColor(6, CARD_H - 6)
    assert pixel.lightness() > 200, pixel.name()


def test_icons_render_in_theme_color(app):
    icon = icons.icon("home", "#2E7A3A", 24)
    assert not icon.isNull()
    pix = icon.pixmap(24, 24)
    assert not pix.isNull()


def test_unknown_icon_raises(app):
    with pytest.raises(KeyError):
        icons.icon("nexiste-pas")


def test_apply_tokens_sets_current_and_stylesheet(app):
    previous = theme.current()
    try:
        theming.apply_tokens(app, theme.DARK)
        assert theme.current() is theme.DARK
        assert theme.DARK.surface in app.styleSheet()
    finally:
        theming.apply_tokens(app, previous)


def test_card_painter_has_no_hardcoded_dark_fill(app):
    # Garde-fou simple : les anciennes couleurs en dur ne doivent pas revenir.
    import inspect

    from fsmods_gui.widgets import library_table, mod_gallery

    for module in (library_table, mod_gallery):
        source = inspect.getsource(module)
        for old in ("#2a2a2a", "#22293a", "#2a2424", "#e6e6e6"):
            assert old not in source, (module.__name__, old)
