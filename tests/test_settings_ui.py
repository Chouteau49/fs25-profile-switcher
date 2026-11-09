"""Paramètres, assistant, palette Ctrl+K et formulaire « Nouveau profil » (0.16)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
import yaml
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from fsmods_gui import config_setup as cs
from fsmods_gui import navigation as nav
from fsmods_gui.commands import build_commands


@pytest.fixture(scope="module")
def app():
    QCoreApplication.setOrganizationName("fsmods-gui-tests")
    QCoreApplication.setApplicationName("fsmods-gui-tests")
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------ palette


def test_palette_filters_and_enter_runs_first_result(app):
    from fsmods_gui.widgets.palette import CommandPalette

    palette = CommandPalette(build_commands([("montagne", "Montagne", 3)], [], []))
    got: list[str] = []
    palette.command_chosen.connect(got.append)
    QTest.keyClicks(palette.input, "jouer mont")
    assert palette.results() == ["play:montagne"]
    QTest.keyClick(palette.input, Qt.Key.Key_Return)
    assert got == ["play:montagne"]


def test_palette_arrow_keys_skip_group_headers(app):
    from fsmods_gui.widgets.palette import CommandPalette

    palette = CommandPalette(build_commands([("a", "A", 1)], [], []))
    first = palette.list.currentItem().data(Qt.ItemDataRole.UserRole)
    QTest.keyClick(palette.input, Qt.Key.Key_Down)
    second = palette.list.currentItem().data(Qt.ItemDataRole.UserRole)
    assert first and second and first != second


# --------------------------------------------------------- new profile dialog


def test_new_profile_dialog_validates_and_returns_choice(app):
    from fsmods_gui.widgets.new_profile_dialog import NewProfileDialog

    dlg = NewProfileDialog(
        [("— Aucune —", None), ("Riverbend Springs (carte officielle)", "official:MapUS")],
        [("base", "Base FS25", 38)],
        [("Aucune", None), ("Agriculture classique", "classic")],
        {"Montagne"},
    )
    assert not dlg.create_btn.isEnabled()
    dlg.name_input.setText("montagne")
    assert not dlg.create_btn.isEnabled() and "déjà" in dlg.error.text()
    dlg.name_input.setText("Plaines")
    assert dlg.create_btn.isEnabled()
    dlg.map_combo.setCurrentIndex(1)
    dlg.collection_boxes[0][1].setChecked(True)
    dlg.scenario_group.button(1).setChecked(True)
    choice = dlg.choice()
    assert choice.name == "Plaines"
    assert choice.map_data == "official:MapUS"
    assert choice.collections == ("base",)
    assert choice.scenario == "classic"


# -------------------------------------------------------------- settings page


def settings(tmp_path: Path) -> cs.GameSettings:
    return cs.GameSettings("fs25", tmp_path / "game" / "mods", tmp_path / "lib", 2300320)


def test_settings_page_save_only_when_dirty_and_valid(app, tmp_path):
    from fsmods_gui.widgets.settings_page import SettingsPage

    page = SettingsPage()
    page.set_settings(settings(tmp_path), tmp_path / "config.yaml", "dark")
    assert not page.save_btn.isEnabled()
    assert page.theme_group.checkedId() == 2
    saved: list[cs.GameSettings] = []
    page.save_requested.connect(saved.append)
    page.library_field.set_path(tmp_path / "autre")
    assert page.save_btn.isEnabled()
    page.save_btn.click()
    assert saved and saved[0].library_dir == tmp_path / "autre"
    page.library_field.set_path(None)
    assert not page.save_btn.isEnabled()


def test_settings_page_backups_and_steam(app, tmp_path):
    from fsmods_gui.widgets.settings_page import SettingsPage

    page = SettingsPage()
    s = cs.GameSettings("fs25", tmp_path / "m", tmp_path / "l", None, (tmp_path / "drive",))
    page.set_settings(s, None, "system")
    assert page.backup_list.count() == 1
    page.backup_list.setCurrentRow(0)
    page.remove_backup_btn.click()
    page.steam_edit.setText("abc")
    assert not page.save_btn.isEnabled()  # identifiant Steam invalide
    page.steam_edit.setText("2300320")
    current = page.current_settings()
    assert current is not None and current.backup_dirs == () and current.steam_app_id == 2300320


# ------------------------------------------------------------------- wizard


def test_wizard_prefills_detected_folders_and_counts_mods(app, tmp_path):
    from fsmods_gui.widgets.settings_page import FirstRunWizard

    mods = tmp_path / "Documents" / "My Games" / "FarmingSimulator2025" / "mods"
    mods.mkdir(parents=True)
    (mods / "a.zip").write_bytes(b"x")
    (mods / "b.zip").write_bytes(b"x")
    wizard = FirstRunWizard(tmp_path, [])
    wizard.next_btn.click()  # étape 2
    assert wizard.mods_field.path() == mods
    assert wizard.library_field.path() is not None
    wizard.library_field.set_path(tmp_path / "lib")
    wizard.next_btn.click()  # étape 3
    assert "2 mods" in wizard.import_summary.text()
    assert wizard.next_btn.text() == "Terminer"
    wizard.next_btn.click()
    assert wizard.result() == wizard.DialogCode.Accepted
    assert wizard.import_requested() and wizard.profile_requested()
    result = wizard.settings()
    assert result is not None and result.steam_app_id == 2300320
    assert result.library_dir == tmp_path / "lib"


def test_wizard_without_mods_to_import(app, tmp_path):
    from fsmods_gui.widgets.settings_page import FirstRunWizard

    wizard = FirstRunWizard(tmp_path, [])
    wizard.next_btn.click()
    wizard.mods_field.set_path(tmp_path / "vide")
    wizard.library_field.set_path(tmp_path / "lib")
    wizard.next_btn.click()
    assert "Aucun mod" in wizard.import_summary.text()
    wizard.next_btn.click()
    assert not wizard.import_requested()


# -------------------------------------------------------------- main window


@pytest.fixture
def window(app, tmp_path):
    from fsmods_gui import config as cfgmod
    from fsmods_gui.main_window import MainWindow
    from fsmods_gui.state import AppState

    path = tmp_path / "config.yaml"
    path.write_text(cs.updated_config_text(
        "# commentaire\ngames:\n  fs25:\n    mods_dir: x\n    testrunner_exe: C:/tr.exe\n",
        cs.GameSettings("fs25", tmp_path / "game" / "mods", tmp_path / "lib", 2300320),
    ), encoding="utf-8")
    (tmp_path / "lib" / "mods").mkdir(parents=True)
    state = AppState(cfg=cfgmod.load(path), game_key="fs25")
    win = MainWindow(state)
    yield win
    win._watcher.stop()
    win.close()
    win.deleteLater()


def test_settings_section_saves_config_with_backup(window, tmp_path):
    window._show_section(nav.SECTION_SETTINGS)
    page = window._feature_panels[nav.FEATURE_SETTINGS]
    new_lib = tmp_path / "lib2"
    page.library_field.set_path(new_lib)
    page.save_btn.click()
    data = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert data["games"]["fs25"]["library_dir"] == new_lib.as_posix()
    assert data["games"]["fs25"]["testrunner_exe"] == "C:/tr.exe"  # clé inconnue gardée
    assert (tmp_path / "config.yaml.bak").is_file()
    assert window.state.game.library_dir == new_lib
    assert (new_lib / "profiles").is_dir()
    assert "Paramètres enregistrés" in window.toast.message()


def test_run_command_navigation(window):
    window._run_command("go:diagnostic")
    assert window.sidebar.current() == nav.SECTION_DIAGNOSTIC
    window._run_command("go:allmods")
    assert window._visible_feature() == nav.FEATURE_ALLMODS
    window._run_command("go:settings")
    assert window.sidebar.current() == nav.SECTION_SETTINGS
    window._run_command("action:inconnue")  # ignorée sans erreur


def test_initial_import_creates_profile(window, tmp_path, qtbot=None):
    mods = tmp_path / "game" / "mods"
    mods.mkdir(parents=True)
    (mods / "x.zip").write_bytes(b"x")
    from fsmods_gui.config_setup import ImportResult

    window._on_initial_import_done(ImportResult(["x.zip"], []), ["x.zip"], True)
    prof = next(p for p in window.state.profiles if p.name == "Partie actuelle")
    assert prof.mods == ["x.zip"] and prof.last_played
