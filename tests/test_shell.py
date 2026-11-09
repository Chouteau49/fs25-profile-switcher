"""Barre latérale, barre de session et navigation de la fenêtre principale (0.11)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from fsmods_gui import navigation as nav
from fsmods_gui.config import Config, GameProfile
from fsmods_gui.state import AppState
from fsmods_gui.widgets.shell import SessionBar, SideNav


@pytest.fixture(scope="module")
def app():
    QCoreApplication.setOrganizationName("fsmods-gui-tests")
    QCoreApplication.setApplicationName("fsmods-gui-tests")
    return QApplication.instance() or QApplication([])


def test_sidenav_lists_every_section_and_tracks_current(app):
    side = SideNav()
    for s in nav.nav_sections():
        assert side.button(s.key).text() == s.label
    side.set_current(nav.SECTION_DIAGNOSTIC)
    assert side.current() == nav.SECTION_DIAGNOSTIC
    side.set_current(nav.SECTION_CAREER)
    assert side.current() == nav.SECTION_CAREER
    side.set_current(nav.SECTION_PROFILES)  # hors barre : plus rien de coché
    assert side.current() == nav.SECTION_PROFILES
    assert not any(side.button(s.key).isChecked() for s in nav.nav_sections())


def test_sidenav_emits_section_on_click(app):
    side = SideNav()
    got: list[str] = []
    side.section_selected.connect(got.append)
    side.button(nav.SECTION_LIBRARY).click()
    assert got == [nav.SECTION_LIBRARY]


def test_badge_shows_count_and_hides_at_zero(app):
    side = SideNav()
    side.set_badge(nav.SECTION_LIBRARY, 3)
    assert side.button(nav.SECTION_LIBRARY).badge_text() == "3"
    side.set_badge(nav.SECTION_LIBRARY, 0)
    assert side.button(nav.SECTION_LIBRARY).badge_text() == ""


def test_session_bar_texts(app):
    bar = SessionBar()
    assert bar.game_label.text() == "FS25 fermé"
    bar.set_game(nav.GAME_RUNNING)
    assert bar.game_label.text() == "FS25 en cours"
    assert bar.game_dot.property("level") == "ok"
    bar.set_active_profile("Montagne")
    assert bar.profile_label.text().endswith("Montagne")
    bar.set_library(9)
    assert bar.library_label.text() == "Bibliothèque : 9 mods"
    bar.flash("Profil enregistré")
    assert bar.message() == "Profil enregistré"


# ---------------------------------------------------------------- fenêtre


def _state(tmp_path: Path) -> AppState:
    library = tmp_path / "lib"
    (library / "mods").mkdir(parents=True)
    gp = GameProfile(name="fs25", mods_dir=tmp_path / "game" / "mods", library_dir=library)
    return AppState(cfg=Config(games={"fs25": gp}, default_game="fs25"), game_key="fs25")


@pytest.fixture
def window(app, tmp_path):
    from fsmods_gui.main_window import MainWindow

    state = _state(tmp_path)
    state.new_profile("Montagne")
    (state.game.inbox_dir_effective).mkdir(parents=True, exist_ok=True)
    (state.game.inbox_dir_effective / "nouveau.zip").write_bytes(b"x")
    win = MainWindow(state)
    yield win
    win._watcher.stop()
    win.close()
    win.deleteLater()


def test_window_has_no_tab_bar_or_toolbar_anymore(window):
    from PySide6.QtWidgets import QToolBar

    assert not window.findChildren(QToolBar)
    assert not hasattr(window, "tabs")


def test_window_starts_on_home_with_badge(window):
    assert window.sidebar.current() == nav.SECTION_HOME
    assert window.sidebar.button(nav.SECTION_LIBRARY).badge_text() == "1"


def test_show_feature_opens_section_and_subtab(window):
    window._show_feature_tab(nav.FEATURE_LOG)
    assert window.sidebar.current() == nav.SECTION_DIAGNOSTIC
    assert window._visible_feature() == nav.FEATURE_LOG
    window._show_feature_tab(nav.FEATURE_STATS)
    assert window._visible_feature() == nav.FEATURE_STATS


def test_every_view_builds_without_error(window):
    for feature in nav.all_features():
        if feature.key in (nav.FEATURE_EDITOR, nav.FEATURE_HOME):
            continue
        window._show_feature_tab(feature.key)
        assert feature.key in window._feature_panels, feature.key


def test_status_goes_to_session_bar(window):
    window._status("Bonjour")
    assert window.session.message() == "Bonjour"


def test_no_screen_forces_a_wide_window(window):
    # Régression 0.12/0.13 : une rangée de boutons ou de filtres trop longue
    # imposait sa largeur minimale et la fenêtre s'élargissait toute seule.
    for section in nav.SECTIONS:
        window._show_section(section.key)
        for feature in section.features:
            if len(section.features) > 1:
                window._show_feature_tab(feature.key)
            assert window.minimumSizeHint().width() <= 1280, (section.key, feature.key)
