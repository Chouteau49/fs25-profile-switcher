"""Navigation de la fenêtre et libellés de la barre de session."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fsmods_gui import navigation as nav

NOW = datetime(2026, 11, 9, 12, 0, 0)


def test_every_former_tab_has_a_place():
    keys = {f.key for f in nav.all_features()}
    assert keys == {
        "home", "editor", "newmods", "allmods", "collections", "career", "log", "audit",
        "duplicates", "autodrive", "testrunner", "stats",
    }


def test_feature_keys_are_unique():
    keys = [f.key for f in nav.all_features()]
    assert len(keys) == len(set(keys))


def test_home_first_and_editor_out_of_nav():
    keys = [s.key for s in nav.nav_sections()]
    assert keys[0] == nav.SECTION_HOME
    assert nav.SECTION_PROFILES not in keys


def test_section_of():
    assert nav.section_of(nav.FEATURE_LOG).key == nav.SECTION_DIAGNOSTIC
    assert nav.section_of(nav.FEATURE_NEWMODS).key == nav.SECTION_LIBRARY
    assert nav.section_of(nav.FEATURE_CAREER).key == nav.SECTION_CAREER
    with pytest.raises(KeyError):
        nav.section_of("inconnu")


def test_icons_exist():
    pytest.importorskip("PySide6")
    from fsmods_gui.widgets import icons

    known = set(icons.names())
    for s in nav.SECTIONS:
        assert s.icon in known, s.key
        for f in s.features:
            assert f.icon in known, f.key


@pytest.mark.parametrize(
    ("state", "label", "level"),
    [
        ("closed", "FS25 fermé", "off"),
        ("activating", "Activation en cours…", "warn"),
        ("running", "FS25 en cours", "ok"),
        ("bizarre", "FS25 fermé", "off"),
    ],
)
def test_game_label_and_level(state, label, level):
    assert nav.game_label(state) == label
    assert nav.game_level(state) == level


def test_active_profile_label():
    assert nav.active_profile_label("Montagne") == "Dans le dossier du jeu : Montagne"
    assert nav.active_profile_label(None).endswith("aucun profil")


def test_library_label():
    assert nav.library_label(None) == "Bibliothèque : scan en cours…"
    assert nav.library_label(1) == "Bibliothèque : 1 mod"
    assert nav.library_label(812) == "Bibliothèque : 812 mods"


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=5), "à l'instant"),
        (timedelta(minutes=2, seconds=30), "il y a 2 min"),
        (timedelta(hours=3), "il y a 3 h"),
        (timedelta(days=2), "le 07/11"),
    ],
)
def test_format_age(delta, expected):
    assert nav.format_age(NOW - delta, NOW) == expected


def test_format_age_never():
    assert nav.format_age(None, NOW) == "jamais"


def test_backup_label():
    assert "non configurée" in nav.backup_label(None, None, NOW)
    assert "échec" in nav.backup_label(False, NOW, NOW)
    assert nav.backup_label(True, NOW - timedelta(minutes=2), NOW) == (
        "Config sauvegardée · il y a 2 min"
    )


def test_badge_text():
    assert nav.badge_text(0) == ""
    assert nav.badge_text(-3) == ""
    assert nav.badge_text(4) == "4"
    assert nav.badge_text(250) == "99+"
