"""Collections : description à la création, affichage sur la carte, nom unique (0.17)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from fsmods_gui.config import Config, GameProfile
from fsmods_gui.state import AppState


@pytest.fixture(scope="module")
def app():
    QCoreApplication.setOrganizationName("fsmods-gui-tests")
    QCoreApplication.setApplicationName("fsmods-gui-tests")
    return QApplication.instance() or QApplication([])


def state(tmp_path: Path) -> AppState:
    library = tmp_path / "lib"
    (library / "mods").mkdir(parents=True)
    gp = GameProfile(name="fs25", mods_dir=tmp_path / "game" / "mods", library_dir=library)
    return AppState(cfg=Config(games={"fs25": gp}, default_game="fs25"), game_key="fs25")


def test_new_collection_keeps_description_on_disk(tmp_path):
    st = state(tmp_path)
    col = st.new_collection("Viticulture", "Tracteurs et outils de vigne")
    assert col.description == "Tracteurs et outils de vigne"
    reloaded = st.game.library_collections_dir
    assert reloaded is not None
    text = (reloaded / f"{col.slug}.json").read_text(encoding="utf-8")
    assert "Tracteurs et outils de vigne" in text


def test_new_collection_without_description_still_works(tmp_path):
    col = state(tmp_path).new_collection("Forestier")
    assert col.description == ""


def test_dialog_refuses_taken_name_and_returns_choice(app):
    from fsmods_gui.widgets.new_collection_dialog import NewCollectionDialog

    dlg = NewCollectionDialog({"Viticulture"})
    assert not dlg.create_btn.isEnabled()
    dlg.name_input.setText("viticulture")  # casse ignorée
    assert not dlg.create_btn.isEnabled()
    assert "déjà" in dlg.error.text()
    dlg.name_input.setText("Forestier")
    dlg.description.setPlainText("  Abatteuses et débardeurs  ")
    assert dlg.create_btn.isEnabled()
    assert dlg.choice() == ("Forestier", "Abatteuses et débardeurs")


def test_overview_card_shows_description_or_hint(app):
    from fsmods_gui.widgets.overview import CollectionsOverview

    panel = CollectionsOverview()
    panel.set_collections([
        ("viti", "Viticulture", 4, ["Montagne"], "Tracteurs de vigne"),
        ("base", "Base FS25", 2, [], ""),
    ])
    texts = [w.text() for w in panel.findChildren(type(panel.empty_label))]
    assert "Tracteurs de vigne" in texts
    assert any("Aucune description" in t for t in texts)
