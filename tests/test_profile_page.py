"""Page Profil (0.13) : glisser-déposer, encadrés de dépendances et de mods absents."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QWidget

from fsmods_gui.editor_notices import ACTION_ADD, ACTION_REMOVE
from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.collection import Collection
from fsmods_gui.profiles.profile import Profile
from fsmods_gui.widgets.library_table import (
    MODS_MIME,
    CatalogTableModel,
    decode_filenames,
    encode_filenames,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def catalog() -> Catalog:
    entries = [
        CatalogEntry("FS25_Silo.zip", "Silo modulable", "1.0", requires=["FS25_Lights"]),
        CatalogEntry("FS25_Lights.zip", "Lumières de ferme", "1.0"),
        CatalogEntry("FS25_Needy.zip", "Mod exigeant", "1.0", requires=["FS25_Absent"]),
        CatalogEntry("FS25_Plain.zip", "Mod simple", "1.0"),
    ]
    return Catalog(mods_dir=Path("."), entries={e.filename: e for e in entries})


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.notes: list[str] = []

    def notify(self, message, action_label=None, action=None, *, error=False):
        self.notes.append(message)


def editor_for(target, cat: Catalog | None = None):
    from fsmods_gui.widgets.editor_panel import EditorPanel

    win = Window()
    editor = EditorPanel(win)
    editor.set_catalog(cat or catalog())
    editor.set_target(target)
    return win, editor


def banners(editor):
    from fsmods_gui.widgets.notice import NoticeBanner

    return [b for b in editor.notices.findChildren(NoticeBanner) if b.parent() is editor.notices]


# ------------------------------------------------------------- drag & drop


def test_mime_roundtrip():
    mime = encode_filenames(["a.zip", "b.zip"])
    assert mime.hasFormat(MODS_MIME)
    assert decode_filenames(mime) == ["a.zip", "b.zip"]


def test_library_model_drags_filenames(app):
    model = CatalogTableModel()
    model.set_catalog(catalog())
    index = model.index(0, 2)
    assert model.flags(index) & Qt.ItemFlag.ItemIsDragEnabled
    names = decode_filenames(model.mimeData([index, model.index(0, 1)]))
    assert len(names) == 1 and names[0].endswith(".zip")


def test_drop_on_content_adds_to_profile(app):
    prof = Profile(name="Montagne")
    win, editor = editor_for(prof)
    win.resize(1200, 800)
    win.show()  # Qt ne livre pas un dépôt à un widget invisible
    QApplication.processEvents()
    mime = encode_filenames(["FS25_Plain.zip"])  # l'événement ne garde qu'un pointeur
    event = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    editor.content.view.dropEvent(event)
    assert prof.mods == ["FS25_Plain.zip"]
    assert editor.tabs.tabText(0) == "Mods (1)"


# ------------------------------------------------------------- notices


def test_dependency_notice_then_add(app):
    prof = Profile(name="Montagne")
    _win, editor = editor_for(prof)
    editor._add_filenames(["FS25_Silo.zip"])
    (banner,) = banners(editor)
    assert banner.notice.action == ACTION_ADD
    assert "Silo modulable a besoin de Lumières de ferme" in banner.notice.text
    banner.action_btn.click()
    assert prof.mods == ["FS25_Silo.zip", "FS25_Lights.zip"]
    QApplication.processEvents()
    assert banners(editor) == []


def test_missing_dependency_notice_has_no_action(app):
    prof = Profile(name="Montagne")
    _win, editor = editor_for(prof)
    editor._add_filenames(["FS25_Needy.zip"])
    (banner,) = banners(editor)
    assert banner.action_btn is None
    assert "FS25_Absent" in banner.notice.text


def test_missing_mod_notice_removes_them(app):
    prof = Profile(name="Montagne", mods=["FS25_Plain.zip", "FS25_Gone.zip"])
    _win, editor = editor_for(prof)
    (banner,) = banners(editor)
    assert banner.notice.action == ACTION_REMOVE
    banner.action_btn.click()
    assert prof.mods == ["FS25_Plain.zip"]


def test_dismissing_dependency_notice(app):
    prof = Profile(name="Montagne")
    _win, editor = editor_for(prof)
    editor._add_filenames(["FS25_Silo.zip"])
    (banner,) = banners(editor)
    banner.dismissed.emit(banner.notice)
    QApplication.processEvents()
    assert banners(editor) == []


def test_no_message_box_left_in_dependency_handling():
    import inspect

    from fsmods_gui.widgets import editor_panel

    assert "QMessageBox" not in inspect.getsource(editor_panel)


# ---------------------------------------------------------------- layout


def test_collection_hides_map_and_collections_tab(app):
    col = Collection(name="Base", mods=["FS25_Plain.zip"])
    _win, editor = editor_for(col)
    assert not editor.tabs.isTabVisible(1)
    assert editor.map_art.isHidden()
    assert editor.add_btn.text() == "Ajouter à la collection"


def test_profile_tabs_show_counts(app):
    prof = Profile(name="Montagne", mods=["FS25_Plain.zip"], collections=["base"])
    _win, editor = editor_for(prof)
    editor.set_collections([Collection(name="base", mods=["FS25_Lights.zip"])])
    editor.set_target(prof)
    assert editor.tabs.tabText(0) == "Mods (2)"
    assert editor.tabs.tabText(1) == "Collections héritées (1)"
    assert editor.tabs.isTabVisible(1)
