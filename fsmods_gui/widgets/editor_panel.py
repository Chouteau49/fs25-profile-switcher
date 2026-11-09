"""Unified editor for a profile *or* a collection, on a single surface.

The same panel edits both: a header card (map thumbnail, name, map, notes and
the main window's « Jouer »), then a **Mods** tab showing the target's mods and
the library side by side (drag a mod from the library to add it), and, for a
profile, a **Collections héritées** tab. Dependencies and missing mods appear
as in-page notices instead of message boxes (0.13).

Replaces the old two-pane ``ProfileEditor`` and the modal
``CollectionsManagerDialog``.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..editor_notices import (
    ACTION_ADD,
    ACTION_REMOVE,
    Notice,
    dependency_notices,
    missing_notice,
)
from ..profiles.catalog import Catalog, CatalogEntry
from ..profiles.collection import Collection
from ..profiles.official_maps import OFFICIAL_MAPS
from ..profiles.profile import Profile
from . import icons
from .home_page import MapArt
from .library_table import LibraryTable
from .mod_gallery import (
    KIND_INHERITED,
    KIND_MAP,
    KIND_OWN,
    KIND_PLAIN,
    GalleryItem,
    ModContentPanel,
)
from .notice import NoticeBanner
from .toast import notify

_OFFICIAL = "official:"  # map combo data prefix for official (non-mod) maps


def _map_key(profile: Profile) -> str | None:
    """Map combo data of a profile: the map zip, or ``official:<mapId>``."""
    if profile.map_mod:
        return profile.map_mod
    return _OFFICIAL + profile.official_map if profile.official_map else None


class EditorPanel(QWidget):
    """Edit a :class:`Profile` or :class:`Collection` in place.

    Emits :attr:`changed` whenever the target is mutated (the owner persists it).
    """

    changed = Signal()  # target mutated → owner should save
    mod_delete_requested = Signal(list)  # list[CatalogEntry] — delete from library
    add_to_profile_requested = Signal(list)  # list[str] filenames — add to a chosen profile
    add_to_collection_requested = Signal(list)  # list[str] filenames — add to a chosen collection

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target: Profile | Collection | None = None
        self._catalog: Catalog | None = None
        # Thumbnail of an official map (set by the main window, which knows the paths).
        self._official_thumbnail: Callable[[str], Path | None] = lambda _map_id: None
        self._collections: list[Collection] = []
        self._last_items: list[GalleryItem] = []

        # ---- header card: map thumbnail · name / map / notes · actions
        self.name_input = QLineEdit(self)
        self.name_input.setProperty("role", "title-edit")
        self.name_input.setPlaceholderText("Nom du profil")
        self.name_input.setToolTip("Clique pour renommer.")
        self.name_input.editingFinished.connect(self._on_name_edited)

        self.description = QTextEdit(self)
        self.description.setPlaceholderText("Notes (optionnel) : pentes, DLC, règles de la partie…")
        self.description.setFixedHeight(54)
        self.description.textChanged.connect(self._on_description_changed)

        self.map_combo = QComboBox(self)
        self.map_combo.setMinimumWidth(260)
        self.map_combo.currentIndexChanged.connect(self._on_map_changed)
        self.map_art = MapArt("", None, 10, self)
        self.map_art.setFixedSize(220, 132)

        self._map_label = QLabel("Carte", self)
        self._map_label.setProperty("role", "muted")
        map_row = QHBoxLayout()
        map_row.setSpacing(8)
        map_row.addWidget(self._map_label)
        map_row.addWidget(self.map_combo, 1)

        info = QVBoxLayout()
        info.setSpacing(8)
        info.addWidget(self.name_input)
        info.addLayout(map_row)
        info.addWidget(self.description)

        #: Zone d'actions à droite de l'en-tête (la fenêtre y place « Jouer »).
        self.actions_box = QVBoxLayout()
        self.actions_box.setSpacing(8)

        self.header = QWidget(self)
        self.header.setProperty("role", "card")
        self.header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        head = QHBoxLayout(self.header)
        head.setContentsMargins(16, 16, 16, 16)
        head.setSpacing(18)
        head.addWidget(self.map_art, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(info, 1)
        head.addLayout(self.actions_box)

        # ---- notices (dépendances, mods absents) : encadrés dans la page
        self._dep_notices: list[Notice] = []
        self.notices = QWidget(self)
        self._notices_layout = QVBoxLayout(self.notices)
        self._notices_layout.setContentsMargins(0, 0, 0, 0)
        self._notices_layout.setSpacing(8)

        # ---- tab "Mods": contents (left) | library (right), side by side
        self.content = ModContentPanel(self)
        self.content.remove_requested.connect(self._remove_filenames)
        self.content.exclude_requested.connect(self._set_excluded)
        self.content.entry_double_clicked.connect(self._show_details)
        self.content.add_to_profile_requested.connect(self.add_to_profile_requested)
        self.content.add_to_collection_requested.connect(self.add_to_collection_requested)
        self.content.files_dropped.connect(self._add_filenames)

        self.library = LibraryTable(self)
        self.library.entry_double_clicked.connect(self._add_entry)
        # Library context-menu "Ajouter à une collection…" → pick a collection
        # (distinct from the "Ajouter →" button, which targets the current item).
        self.library.add_to_collection.connect(
            lambda entries: self.add_to_collection_requested.emit(
                [e.filename for e in entries]
            )
        )
        self.library.delete_requested.connect(self.mod_delete_requested)
        self.add_btn = QPushButton("Ajouter au profil", self)
        self.add_btn.setProperty("variant", "primary")
        icons.bind(self.add_btn, "plus", icons.ROLE_ON_ACCENT)
        self.add_btn.clicked.connect(self._add_selected)

        lib_panel = QWidget(self)
        lib_panel.setProperty("role", "card")
        lib_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lib_layout = QVBoxLayout(lib_panel)
        lib_layout.setContentsMargins(12, 12, 12, 12)
        lib_title = QLabel("Ajouter depuis la bibliothèque", lib_panel)
        lib_title.setProperty("role", "card-title")
        lib_hint = QLabel(
            "Glisse un mod vers la gauche, double-clique-le, ou sélectionne-le puis "
            "« Ajouter ».",
            lib_panel,
        )
        lib_hint.setProperty("role", "muted")
        lib_hint.setWordWrap(True)
        lib_layout.addWidget(lib_title)
        lib_layout.addWidget(lib_hint)
        lib_layout.addWidget(self.library, 1)
        add_row = QHBoxLayout()
        add_row.addStretch(1)
        add_row.addWidget(self.add_btn)
        lib_layout.addLayout(add_row)

        content_panel = QWidget(self)
        content_panel.setProperty("role", "card")
        content_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_title = QLabel("Dans ce profil", content_panel)
        self.content_title.setProperty("role", "card-title")
        content_layout.addWidget(self.content_title)
        content_layout.addWidget(self.content, 1)

        self.split = QSplitter(Qt.Orientation.Horizontal, self)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(content_panel)
        self.split.addWidget(lib_panel)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        lib_panel.setMinimumWidth(320)
        content_panel.setMinimumWidth(360)

        mods_page = QWidget(self)
        mods_layout = QVBoxLayout(mods_page)
        mods_layout.setContentsMargins(0, 10, 0, 0)
        mods_layout.setSpacing(10)
        mods_layout.addWidget(self.notices)
        mods_layout.addWidget(self.split, 1)

        # ---- tab "Collections héritées" (profiles only)
        self.collections_list = QListWidget(self)
        self.collections_list.itemChanged.connect(self._on_collection_toggled)
        cols_page = QWidget(self)
        cols_layout = QVBoxLayout(cols_page)
        cols_layout.setContentsMargins(0, 10, 0, 0)
        cols_hint = QLabel(
            "Les mods d'une collection cochée s'ajoutent à ce profil. Tu peux en exclure "
            "un seul (clic droit sur sa carte) sans toucher à la collection.",
            cols_page,
        )
        cols_hint.setProperty("role", "muted")
        cols_hint.setWordWrap(True)
        cols_layout.addWidget(cols_hint)
        cols_layout.addWidget(self.collections_list, 1)

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setProperty("role", "subtabs")
        self.tabs.addTab(mods_page, "Mods")
        self.tabs.addTab(cols_page, "Collections héritées")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(self.header)
        root.addWidget(self.tabs, 1)

        self._rebuild_map_combo()  # official maps are listed even before the library scan
        self.set_target(None)

    # ------------------------------------------------------------------ data

    def set_official_thumbnail_provider(self, provider: Callable[[str], Path | None]) -> None:
        self._official_thumbnail = provider
        self._update_map_icon()

    def set_catalog(self, catalog: Catalog | None) -> None:
        self._catalog = catalog
        self.library.set_catalog(catalog)
        self.content.set_catalog(catalog)
        self._rebuild_map_combo()

    def set_collections(self, collections: list[Collection]) -> None:
        self._collections = list(collections)
        self._rebuild_collections_list()

    def current_target(self) -> Profile | Collection | None:
        return self._target

    @property
    def _is_profile(self) -> bool:
        return isinstance(self._target, Profile)

    def _collection_mods_map(self) -> dict[str, list[str]]:
        return {c.slug: list(c.mods) for c in self._collections}

    def set_target(self, target: Profile | Collection | None) -> None:
        self._target = target
        is_profile = isinstance(target, Profile)

        block_name = self.name_input.blockSignals(True)
        block_desc = self.description.blockSignals(True)
        if target is None:
            self.name_input.clear()
            self.description.clear()
            self.setEnabled(False)
        else:
            self.setEnabled(True)
            self.name_input.setText(target.name)
            self.description.setPlainText(target.description)
        self.name_input.blockSignals(block_name)
        self.description.blockSignals(block_desc)

        # Map row + inherited collections are profile-only.
        self._map_label.setVisible(is_profile)
        self.map_combo.setVisible(is_profile)
        self.map_art.setVisible(is_profile)
        self.tabs.setTabVisible(1, is_profile)
        self.name_input.setPlaceholderText(
            "Nom du profil" if is_profile else "Nom de la collection"
        )
        self.description.setPlaceholderText(
            "Notes (optionnel) : pentes, DLC, règles de la partie…"
            if is_profile
            else "Ex. : à quoi sert la collection, pour quelles cartes ou quels types de partie."
        )
        self.content_title.setText("Dans ce profil" if is_profile else "Dans cette collection")
        self.add_btn.setText("Ajouter au profil" if is_profile else "Ajouter à la collection")
        self._dep_notices = []

        if isinstance(target, Profile):
            block_map = self.map_combo.blockSignals(True)
            self._select_map_in_combo(_map_key(target))
            self.map_combo.blockSignals(block_map)
            self._rebuild_collections_list()
            self._update_map_icon()
            self.library.set_profile(target)
        else:
            self.library.set_profile(None)

        # Always land on the Mods tab when switching target.
        self.tabs.setCurrentIndex(0)
        self._reload_content()

    # -------------------------------------------------------------- notices

    def _refresh_notices(self, items: list[GalleryItem] | None = None) -> None:
        """Encadrés : dépendances du dernier ajout, mods absents de la bibliothèque."""
        while self._notices_layout.count():
            item = self._notices_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)  # disparaît tout de suite, pas au prochain tour
                widget.deleteLater()
        notices = list(self._dep_notices)
        if isinstance(self._target, Profile) and self._catalog is not None and items:
            missing = [
                i.filename for i in items if i.entry is None and not i.excluded
            ]
            notice = missing_notice(missing)
            if notice is not None:
                notices.append(notice)
        for notice in notices:
            banner = NoticeBanner(notice, self.notices)
            banner.action_requested.connect(self._on_notice_action)
            banner.dismissed.connect(self._on_notice_dismissed)
            self._notices_layout.addWidget(banner)
        self.notices.setVisible(bool(notices))

    def _on_notice_action(self, notice: Notice) -> None:
        if notice in self._dep_notices:
            self._dep_notices.remove(notice)
        if notice.action == ACTION_ADD and isinstance(self._target, Profile):
            prof = self._target
            for fname in notice.filenames:
                if fname != prof.map_mod and fname not in prof.mods:
                    prof.mods.append(fname)
            self._reload_content()
            self.changed.emit()
        elif notice.action == ACTION_REMOVE:
            self._remove_filenames(list(notice.filenames))

    def _on_notice_dismissed(self, notice: Notice) -> None:
        if notice in self._dep_notices:
            self._dep_notices.remove(notice)
        self._refresh_notices(self._last_items)

    def _update_tab_labels(self, items: list[GalleryItem]) -> None:
        count = sum(1 for i in items if not i.excluded)
        self.tabs.setTabText(0, f"Mods ({count})")
        if isinstance(self._target, Profile):
            self.tabs.setTabText(1, f"Collections héritées ({len(self._target.collections)})")

    # ------------------------------------------------------- inherited cols

    def _rebuild_collections_list(self) -> None:
        self.collections_list.blockSignals(True)
        self.collections_list.clear()
        inherited = (
            set(self._target.collections)
            if isinstance(self._target, Profile)
            else set()
        )
        for col in self._collections:
            item = QListWidgetItem(f"{col.name}  ({len(col.mods)})")
            item.setData(Qt.ItemDataRole.UserRole, col.slug)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if col.slug in inherited
                else Qt.CheckState.Unchecked
            )
            self.collections_list.addItem(item)
        self.collections_list.blockSignals(False)

    def _on_collection_toggled(self, item: QListWidgetItem) -> None:
        if not isinstance(self._target, Profile):
            return
        slug = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        if checked and slug not in self._target.collections:
            self._target.collections.append(slug)
        elif not checked and slug in self._target.collections:
            self._target.collections = [
                s for s in self._target.collections if s != slug
            ]
        self._reload_content()
        self.changed.emit()

    # ------------------------------------------------------------------ map

    def _rebuild_map_combo(self) -> None:
        block = self.map_combo.blockSignals(True)
        self.map_combo.clear()
        self.map_combo.addItem("— Aucune —", userData=None)
        for m in OFFICIAL_MAPS:
            self.map_combo.addItem(m.label, userData=_OFFICIAL + m.map_id)
        if self._catalog is not None:
            for entry in sorted(
                self._catalog.maps(), key=lambda e: e.display_title.lower()
            ):
                self.map_combo.addItem(
                    f"{entry.display_title} ({entry.filename})", userData=entry.filename
                )
        if isinstance(self._target, Profile):
            self._select_map_in_combo(_map_key(self._target))
        self.map_combo.blockSignals(block)

    def _select_map_in_combo(self, filename: str | None) -> None:
        target = 0
        for i in range(self.map_combo.count()):
            if self.map_combo.itemData(i) == filename:
                target = i
                break
        self.map_combo.setCurrentIndex(target)

    def _on_map_changed(self) -> None:
        if not isinstance(self._target, Profile):
            return
        new_map = self.map_combo.currentData()
        if new_map == _map_key(self._target):
            return
        if isinstance(new_map, str) and new_map.startswith(_OFFICIAL):
            self._target.map_mod = None
            self._target.official_map = new_map[len(_OFFICIAL):]
        else:
            self._target.map_mod = new_map
            self._target.official_map = None
        self._reload_content()
        self._update_map_icon()
        self.changed.emit()

    def _update_map_icon(self) -> None:
        target = self._target
        if not isinstance(target, Profile):
            self.map_art.set_image("", None)
            return
        pix: QPixmap | None = None
        if target.official_map and not target.map_mod:
            thumb = self._official_thumbnail(target.official_map)
            pix = QPixmap(str(thumb)) if thumb else None
        elif target.map_mod and self._catalog:
            entry = self._catalog.entries.get(target.map_mod)
            if entry and entry.icon_cache_path:
                pix = QPixmap(entry.icon_cache_path)
        self.map_art.set_image(target.name, pix)
        caption = self.map_combo.currentText() if self.map_combo.currentIndex() > 0 else ""
        self.map_art.set_caption(caption.split(" (")[0])

    # -------------------------------------------------------------- content

    def _reload_content(self) -> None:
        if self._target is None:
            items: list[GalleryItem] = []
        elif isinstance(self._target, Profile):
            items = self._profile_items(self._target)
        else:
            items = self._collection_items(self._target)
        self.content.set_items(items)
        self._last_items = items
        self._update_tab_labels(items)
        self._refresh_notices(items)

    def _collection_items(self, col: Collection) -> list[GalleryItem]:
        items: list[GalleryItem] = []
        for fname in col.mods:
            entry = self._catalog.get(fname) if self._catalog else None
            items.append(GalleryItem(filename=fname, entry=entry, kind=KIND_PLAIN))
        return items

    def _profile_items(self, prof: Profile) -> list[GalleryItem]:
        inherited_sources = prof.inherited_mod_filenames(self._collection_mods_map())
        own = set(prof.mods)
        excluded = set(prof.excluded_mods)
        items: list[GalleryItem] = []

        def entry_of(fname: str) -> CatalogEntry | None:
            return self._catalog.get(fname) if self._catalog else None

        if prof.map_mod:
            items.append(
                GalleryItem(prof.map_mod, entry_of(prof.map_mod), kind=KIND_MAP)
            )
        for fname in prof.mods:
            items.append(GalleryItem(fname, entry_of(fname), kind=KIND_OWN))
        for fname in inherited_sources:
            if fname in own or fname == prof.map_mod:
                continue
            items.append(
                GalleryItem(
                    fname,
                    entry_of(fname),
                    kind=KIND_INHERITED,
                    excluded=fname in excluded,
                    sources=list(inherited_sources.get(fname, [])),
                )
            )
        return items

    # --------------------------------------------------------------- adding

    def _add_entry(self, entry: CatalogEntry) -> None:
        self._add_entries([entry])

    def _add_filenames(self, filenames: list[str]) -> None:
        """Mods déposés depuis la bibliothèque (glisser-déposer)."""
        if self._catalog is None:
            return
        entries = [e for e in (self._catalog.get(f) for f in filenames) if e is not None]
        self._add_entries(entries)

    def _add_selected(self) -> None:
        self._add_entries(self.library.selected_entries())

    def _add_entries(self, entries: list[CatalogEntry]) -> None:
        if self._target is None or not entries:
            return
        if isinstance(self._target, Profile):
            self._add_to_profile(entries)
        else:
            self._add_to_collection(entries)

    def _add_to_collection(self, entries: list[CatalogEntry]) -> None:
        col = self._target
        if not isinstance(col, Collection):
            return
        maps_skipped = 0
        changed = False
        for entry in entries:
            if entry.is_map:
                maps_skipped += 1
                continue
            if entry.filename not in col.mods:
                col.mods.append(entry.filename)
                changed = True
        if changed:
            self._reload_content()
            self.changed.emit()
        if maps_skipped:
            notify(
                self,
                "Cartes ignorées : une carte ne peut pas faire partie d'une collection "
                "(c'est un choix propre à chaque profil).",
            )

    def _add_to_profile(self, entries: list[CatalogEntry]) -> None:
        prof = self._target
        if not isinstance(prof, Profile):
            return
        changed = False
        map_changed = False
        added: list[str] = []
        for entry in entries:
            if entry.is_map:
                if prof.map_mod != entry.filename:
                    prof.map_mod = entry.filename
                    changed = True
                    map_changed = True
                continue
            if entry.filename in prof.mods:
                continue
            prof.mods.append(entry.filename)
            if entry.filename in prof.excluded_mods:
                prof.excluded_mods.remove(entry.filename)
            changed = True
            added.append(entry.filename)
        if changed:
            if map_changed:
                block = self.map_combo.blockSignals(True)
                self._select_map_in_combo(prof.map_mod)
                self.map_combo.blockSignals(block)
                self._update_map_icon()
            self._reload_content()
            self.changed.emit()
            self._handle_dependencies(added)

    def _handle_dependencies(self, seed_filenames: list[str]) -> None:
        if (
            not isinstance(self._target, Profile)
            or self._catalog is None
            or not seed_filenames
        ):
            return
        from ..profiles.dependencies import resolve_new_dependencies

        prof = self._target
        res = resolve_new_dependencies(
            seed_filenames, prof.all_mod_filenames(), self._catalog
        )
        titles = {
            f: (e.display_title if (e := self._catalog.get(f)) else f) for f in res.to_add
        }
        added_titles = [self._title_of(f) for f in seed_filenames]
        self._dep_notices = dependency_notices(res, titles, added_titles)
        self._refresh_notices(self._last_items)

    def _format_dep_list(self, filenames: list[str]) -> str:
        lines: list[str] = []
        for fname in filenames:
            entry = self._catalog.get(fname) if self._catalog else None
            label = f"{entry.display_title} ({fname})" if entry else fname
            lines.append(f"• {label}")
        return "\n".join(lines)

    # ------------------------------------------------------------- removing

    def _remove_filenames(self, filenames: list[str]) -> None:
        if self._target is None or not filenames:
            return
        snapshot = self._snapshot()
        changed = False
        if isinstance(self._target, Profile):
            prof = self._target
            for fname in filenames:
                if fname == prof.map_mod:
                    prof.map_mod = None
                    block = self.map_combo.blockSignals(True)
                    self._select_map_in_combo(None)
                    self.map_combo.blockSignals(block)
                    self._update_map_icon()
                    changed = True
                elif fname in prof.mods:
                    prof.mods.remove(fname)
                    changed = True
                elif fname not in prof.excluded_mods:
                    # Inherited from a collection — exclude it for this profile.
                    prof.excluded_mods.append(fname)
                    changed = True
        else:
            col = self._target
            for fname in filenames:
                if fname in col.mods:
                    col.mods.remove(fname)
                    changed = True
        if changed:
            self._reload_content()
            self.changed.emit()
            self._offer_undo(snapshot, self._removal_message(filenames))

    def _set_excluded(self, fname: str, excluded: bool) -> None:
        if not isinstance(self._target, Profile):
            return
        prof = self._target
        snapshot = self._snapshot()
        if excluded and fname not in prof.excluded_mods:
            prof.excluded_mods.append(fname)
        elif not excluded and fname in prof.excluded_mods:
            prof.excluded_mods.remove(fname)
        else:
            return
        self._reload_content()
        self.changed.emit()
        title = self._title_of(fname)
        self._offer_undo(
            snapshot,
            f"{title} exclu de ce profil (reste dans sa collection)."
            if excluded
            else f"{title} réintégré au profil.",
        )

    # ------------------------------------------------------------------ undo

    def _snapshot(self) -> tuple | None:
        """État modifiable de la cible, pour « Annuler »."""
        t = self._target
        if isinstance(t, Profile):
            return (t, list(t.mods), t.map_mod, t.official_map, list(t.excluded_mods))
        if isinstance(t, Collection):
            return (t, list(t.mods))
        return None

    def _restore(self, snapshot: tuple) -> None:
        target = snapshot[0]
        if isinstance(target, Profile):
            _, target.mods, target.map_mod, target.official_map, target.excluded_mods = snapshot
        else:
            _, target.mods = snapshot
        if target is self._target:
            if isinstance(target, Profile):
                block = self.map_combo.blockSignals(True)
                self._select_map_in_combo(_map_key(target))
                self.map_combo.blockSignals(block)
                self._update_map_icon()
            self._reload_content()
        self.changed.emit()

    def _offer_undo(self, snapshot: tuple | None, message: str) -> None:
        if snapshot is None:
            return
        notify(self, message, "Annuler", lambda: self._restore(snapshot))

    def _title_of(self, fname: str) -> str:
        entry = self._catalog.get(fname) if self._catalog else None
        return entry.display_title if entry else fname

    def _removal_message(self, filenames: list[str]) -> str:
        if len(filenames) == 1:
            return f"{self._title_of(filenames[0])} retiré."
        return f"{len(filenames)} mods retirés."

    def _show_details(self, filename: str) -> None:
        entry = self._catalog.get(filename) if self._catalog else None
        if entry is None:
            return
        from .mod_detail import ModDetailDialog

        ModDetailDialog(entry, self).exec()

    # ----------------------------------------------------------- form props

    def _on_name_edited(self) -> None:
        if self._target is None:
            return
        new = self.name_input.text().strip()
        if not new or new == self._target.name:
            return
        self._target.name = new
        self.changed.emit()

    def _on_description_changed(self) -> None:
        if self._target is None:
            return
        self._target.description = self.description.toPlainText()
        self.changed.emit()
