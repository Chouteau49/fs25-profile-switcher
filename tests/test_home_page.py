"""Accueil, notifications et « Annuler » dans l'éditeur (0.12)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QWidget

from fsmods_gui.home import ProfileCard
from fsmods_gui.profiles.collection import Collection
from fsmods_gui.profiles.profile import Profile
from fsmods_gui.widgets.home_page import HomePage
from fsmods_gui.widgets.toast import Toast, notify


@pytest.fixture(scope="module")
def app():
    QCoreApplication.setOrganizationName("fsmods-gui-tests")
    QCoreApplication.setApplicationName("fsmods-gui-tests")
    return QApplication.instance() or QApplication([])


def card(slug: str, last: bool = False) -> ProfileCard:
    return ProfileCard(slug, slug.title(), "Alpenland · carte mod", 10, 1, "hier, 21:40", last)


# ------------------------------------------------------------------ toast


def test_toast_shows_message_and_runs_action_once(app):
    parent = QWidget()
    parent.resize(800, 600)
    toast = Toast(parent)
    calls: list[int] = []
    toast.show_message("Mod retiré.", "Annuler", lambda: calls.append(1))
    assert toast.message() == "Mod retiré."
    assert not toast.action_btn.isHidden()
    toast.trigger_action()
    toast.trigger_action()  # déjà fermée : l'action ne se rejoue pas
    assert calls == [1]
    assert toast.message() == ""


def test_toast_without_action_hides_button(app):
    parent = QWidget()
    toast = Toast(parent)
    toast.show_message("Export terminé.")
    assert toast.action_btn.isHidden()


def test_notify_uses_window_notify(app):
    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.got: list[str] = []

        def notify(self, message, action_label=None, action=None, *, error=False):
            self.got.append(message)

    win = Window()
    child = QWidget(win)
    notify(child, "Bonjour")
    assert win.got == ["Bonjour"]


# ------------------------------------------------------------------ home


def test_home_hero_is_last_played_and_tiles_for_others(app):
    page = HomePage()
    page.resize(1100, 800)
    page.set_cards([card("montagne", last=True), card("plaines"), card("rizieres")], {})
    from fsmods_gui.widgets.home_page import HeroCard, ProfileTile

    assert isinstance(page.card("montagne"), HeroCard)
    assert isinstance(page.card("plaines"), ProfileTile)
    assert page.card("inconnu") is None


def test_home_play_and_open_signals(app):
    page = HomePage()
    page.set_cards([card("montagne", last=True), card("plaines")], {})
    played: list[str] = []
    opened: list[str] = []
    page.play_requested.connect(played.append)
    page.open_requested.connect(opened.append)
    page.card("plaines").play_btn.click()
    page.card("montagne").open_btn.click()
    assert played == ["plaines"]
    assert opened == ["montagne"]


def test_home_activity_disables_play_and_shows_progress(app):
    page = HomePage()
    page.set_cards([card("montagne", last=True), card("plaines")], {})
    page.set_activity("plaines", None)
    plaines, montagne = page.card("plaines"), page.card("montagne")
    assert plaines.play_btn.text() == "Activation…"
    assert not plaines.progress.isHidden()
    assert not montagne.play_btn.isEnabled()
    page.set_progress("plaines", 40, "Liens des mods : 4 / 10")
    assert plaines.progress.value() == 40
    page.set_activity(None, "plaines")
    assert plaines.play_btn.text() == "En cours"
    page.set_activity(None, None)
    assert montagne.play_btn.isEnabled() and plaines.play_btn.text() == "Jouer"


def test_home_banner_and_empty_state(app):
    page = HomePage()
    page.set_cards([], {})
    assert not page.empty_label.isHidden()
    page.set_waiting(0)
    assert page.banner.isHidden()
    page.set_waiting(3)
    assert not page.banner.isHidden()
    assert "3 mods attendent" in page.banner_text.text()


# --------------------------------------------------------- editor undo


def _editor_with(target):
    from fsmods_gui.widgets.editor_panel import EditorPanel

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.last = None

        def notify(self, message, action_label=None, action=None, *, error=False):
            self.last = (message, action_label, action)

    win = Window()
    editor = EditorPanel(win)
    editor.set_target(target)
    return win, editor


def test_remove_mod_then_undo_restores_profile(app):
    prof = Profile(name="Montagne", mods=["a.zip", "b.zip"], map_mod="map.zip")
    win, editor = _editor_with(prof)
    changes: list[int] = []
    editor.changed.connect(lambda: changes.append(1))
    editor._remove_filenames(["a.zip", "map.zip"])
    assert prof.mods == ["b.zip"] and prof.map_mod is None
    message, label, undo = win.last
    assert label == "Annuler" and message == "2 mods retirés."
    undo()
    assert prof.mods == ["a.zip", "b.zip"] and prof.map_mod == "map.zip"
    assert len(changes) == 2  # retrait + annulation : chacun est sauvegardé


def test_exclude_then_undo(app):
    prof = Profile(name="Montagne", collections=["base"])
    win, editor = _editor_with(prof)
    editor._set_excluded("x.zip", True)
    assert prof.excluded_mods == ["x.zip"]
    assert "exclu" in win.last[0]
    win.last[2]()
    assert prof.excluded_mods == []


def test_collection_remove_undo(app):
    col = Collection(name="Base", mods=["a.zip", "b.zip"])
    win, editor = _editor_with(col)
    editor._remove_filenames(["b.zip"])
    assert col.mods == ["a.zip"]
    win.last[2]()
    assert col.mods == ["a.zip", "b.zip"]


# ---------------------------------------------------------- main window


@pytest.fixture
def window(app, tmp_path: Path):
    from fsmods_gui.config import Config, GameProfile
    from fsmods_gui.main_window import MainWindow
    from fsmods_gui.state import AppState

    library = tmp_path / "lib"
    (library / "mods").mkdir(parents=True)
    gp = GameProfile(name="fs25", mods_dir=tmp_path / "game" / "mods", library_dir=library)
    state = AppState(cfg=Config(games={"fs25": gp}, default_game="fs25"), game_key="fs25")
    played = state.new_profile("Montagne")
    played.last_played = datetime(2026, 11, 8, 21, 40).isoformat()
    played.save()
    state.new_profile("Plaines")
    win = MainWindow(state)
    win._refresh_home()
    yield win
    win._watcher.stop()
    win.close()
    win.deleteLater()


def test_window_home_lists_profiles_with_last_played_as_hero(window):
    from fsmods_gui.widgets.home_page import HeroCard

    assert isinstance(window.home.card("montagne"), HeroCard)
    assert window.home.card("plaines") is not None


def test_home_open_goes_to_editor_of_that_profile(window):
    from fsmods_gui import navigation as nav

    window._on_home_open("plaines")
    assert window.sidebar.current() == nav.SECTION_PROFILES
    assert window.editor.current_target().slug == "plaines"


def test_home_play_selects_profile_and_activates(window, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        window, "_on_activate", lambda: calls.append(window.state.current_profile.slug)
    )
    window._on_home_play("plaines")
    assert calls == ["plaines"]


def test_window_notify_shows_toast(window):
    window.notify("Export terminé.")
    assert window.toast.message() == "Export terminé."
