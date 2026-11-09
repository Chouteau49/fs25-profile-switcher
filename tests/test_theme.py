"""Thème : contrastes lisibles, résolution du mode, feuille de style, cartes."""
from __future__ import annotations

import re

import pytest

from fsmods_gui import theme
from fsmods_gui.theme import DARK, LIGHT


@pytest.mark.parametrize("tokens", [LIGHT, DARK], ids=["clair", "sombre"])
@pytest.mark.parametrize("pair", theme.TEXT_PAIRS, ids=lambda p: f"{p[0]}/{p[1]}")
def test_text_pairs_are_readable(tokens, pair):
    fg, bg = (getattr(tokens, name) for name in pair)
    assert theme.contrast(fg, bg) >= 4.5, f"{tokens.name} {pair}"


def test_both_themes_define_every_token_as_hex():
    for tokens in (LIGHT, DARK):
        for key, value in tokens.as_dict().items():
            if key != "name":
                assert re.fullmatch(r"#[0-9A-F]{6}", value), (tokens.name, key)


def test_contrast_extremes():
    assert theme.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert theme.contrast("#777777", "#777777") == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("mode", "system_dark", "expected"),
    [
        ("system", False, LIGHT),
        ("system", True, DARK),
        ("light", True, LIGHT),
        ("dark", False, DARK),
        ("n'importe quoi", True, DARK),
        (None, False, LIGHT),
    ],
)
def test_resolve(mode, system_dark, expected):
    assert theme.resolve(mode, system_dark) is expected


def test_normalize_mode():
    assert theme.normalize_mode("dark") == "dark"
    assert theme.normalize_mode(3) == "system"


def test_stylesheet_uses_tokens_and_has_no_unformatted_braces():
    for tokens in (LIGHT, DARK):
        qss = theme.build_stylesheet(tokens)
        assert tokens.accent in qss and tokens.surface in qss
        assert "{t." not in qss
        assert qss.count("{") == qss.count("}")


def test_card_style_follows_theme():
    # Régression : les cartes étaient peintes en #2a2a2a même en thème clair.
    assert theme.card_style(LIGHT).bg == LIGHT.surface
    assert theme.card_style(DARK).bg == DARK.surface
    assert theme.card_style(LIGHT, missing=True).border == LIGHT.red
    assert theme.card_style(LIGHT, selected=True).bg == LIGHT.accent_soft


def test_current_defaults_to_light_and_can_change():
    previous = theme.current()
    try:
        theme.set_current(DARK)
        assert theme.current() is DARK
    finally:
        theme.set_current(previous)
