"""Unified editor for a profile *or* a collection, on a single surface.

The same panel edits both: a list on the left of the main window selects the
target (profile or collection), and this panel shows two pages toggled by a
segmented control — **📦 Contenu** (the target's mods as a gallery) and
**➕ Bibliothèque** (the full library, to add mods). A profile additionally gets
a map picker and an inherited-collections checklist; a collection hides those.

Replaces the old two-pane ``ProfileEditor`` and the modal
``CollectionsManagerDialog``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileIconProvider,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog, CatalogEntry
from ..profiles.collection import Collection
from ..profiles.profile import Profile
from .library_table import LibraryTable
from .mod_gallery import (
    KIND_INHERITED,
    KIND_MAP,
    KIND_OWN,
    KIND_PLAIN,
    GalleryItem,
    ModContentPanel,
)

_PAGE_CONTENT = 0
_PAGE_LIBRARY = 1


class EditorPanel(QWidget):
    """Edit a :class:`Profile` or :class:`Collection` in place.

    Emits :attr:`changed` whenever the target is mutated (the owner persists it).
    """

    changed = Signal()  # target mutated → owner should save
    mod_delete_requested = Signal(list)  # list[CatalogEntry] — delete from library

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target: Profile | Collection | None = None
        self._catalog: Catalog | None = None
        self._collections: list[Collection] = []

        # ---- header: name + description (+ map for profiles)
        self.name_input = QLineEdit(self)
        self.name_input.editingFinished.connect(self._on_name_edited)

        self.description = QTextEdit(self)
        self.description.setMaximumHeight(60)
        self.description.textChanged.connect(self._on_description_changed)

        self.map_combo = QComboBox(self)
        self.map_combo.setMinimumWidth(280)
        self.map_combo.currentIndexChanged.connect(self._on_map_changed)
        self.map_icon = QLabel(self)
        self.map_icon.setFixedSize(72, 72)
        self.map_icon.setScaledContents(True)
        self.map_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_icon.setStyleSheet(
            "border: 1px solid #555; background: #111; border-radius: 4px;"
        )

        self._form = QFormLayout()
        self._form.addRow("Nom", self.name_input)
        self._map_label = QLabel("Carte", self)
        self._form.addRow(self._map_label, self.map_combo)
        self._form.addRow("Notes", self.description)

        form_widget = QWidget(self)
        top_layout = QHBoxLayout(form_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(self._form, 1)
        top_layout.addWidget(self.map_icon)

        # ---- inherited collections (profiles only)
        self.collections_list = QListWidget(self)
        self.collections_list.setMaximumHeight(90)
        self.collections_list.itemChanged.connect(self._on_collection_toggled)
        self._coll_box = QGroupBox("Collections héritées", self)
        coll_layout = QVBoxLayout(self._coll_box)
        coll_layout.setContentsMargins(6, 4, 6, 4)
        coll_layout.addWidget(self.collections_list)

        # ---- segmented toggle: Contenu / Bibliothèque
        self.content_btn = QToolButton(self)
        self.content_btn.setText("📦 Contenu")
        self.content_btn.setCheckable(True)
        self.content_btn.setChecked(True)
        self.library_btn = QToolButton(self)
        self.library_btn.setText("➕ Bibliothèque")
        self.library_btn.setCheckable(True)
        for b in (self.content_btn, self.library_btn):
            b.setMinimumHeight(28)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._toggle_group = QButtonGroup(self)
        self._toggle_group.setExclusive(True)
        self._toggle_group.addButton(self.content_btn, _PAGE_CONTENT)
        self._toggle_group.addButton(self.library_btn, _PAGE_LIBRARY)
        self.content_btn.clicked.connect(lambda: self._set_page(_PAGE_CONTENT))
        self.library_btn.clicked.connect(lambda: self._set_page(_PAGE_LIBRARY))

        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self.content_btn)
        toggle_row.addWidget(self.library_btn)
        toggle_row.addStretch(1)

        # ---- page 0: contents gallery
        self.content = ModContentPanel(self)
        self.content.remove_requested.connect(self._remove_filenames)
        self.content.exclude_requested.connect(self._set_excluded)
        self.content.entry_double_clicked.connect(self._show_details)

        # ---- page 1: library picker + add button
        self.library = LibraryTable(self)
        self.library.entry_double_clicked.connect(self._add_entry)
        self.library.add_to_collection.connect(self._add_entries)
        self.library.delete_requested.connect(self.mod_delete_requested)
        self.add_btn = QPushButton("Ajouter →", self)
        self.add_btn.clicked.connect(self._add_selected)
        lib_page = QWidget(self)
        lib_layout = QVBoxLayout(lib_page)
        lib_layout.setContentsMargins(0, 0, 0, 0)
        lib_layout.addWidget(self.library, 1)
        add_row = QHBoxLayout()
        add_row.addStretch(1)
        add_row.addWidget(self.add_btn)
        lib_layout.addLayout(add_row)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.content)  # _PAGE_CONTENT
        self.stack.addWidget(lib_page)  # _PAGE_LIBRARY

        root = QVBoxLayout(self)
        root.addWidget(form_widget)
        root.addWidget(self._coll_box)
        root.addLayout(toggle_row)
        root.addWidget(self.stack, 1)

        self.set_target(None)

    # ------------------------------------------------------------------ data

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
        self.map_icon.setVisible(is_profile)
        self._coll_box.setVisible(is_profile)

        if is_profile:
            block_map = self.map_combo.blockSignals(True)
            self._select_map_in_combo(target.map_mod)
            self.map_combo.blockSignals(block_map)
            self._rebuild_collections_list()
            self._update_map_icon()
            self.library.set_profile(target)
        else:
            self.library.set_profile(None)

        # Always land on the Contenu page when switching target.
        self._set_page(_PAGE_CONTENT)
        self._reload_content()

    # --------------------------------------------------------------- paging

    def _set_page(self, page: int) -> None:
        self.stack.setCurrentIndex(page)
        self.content_btn.setChecked(page == _PAGE_CONTENT)
        self.library_btn.setChecked(page == _PAGE_LIBRARY)
        self.add_btn.setText(
            "Ajouter à la collection →" if not self._is_profile else "Ajouter au profil →"
        )

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
        if self._catalog is not None:
            for entry in sorted(
                self._catalog.maps(), key=lambda e: e.display_title.lower()
            ):
                self.map_combo.addItem(
                    f"{entry.display_title} ({entry.filename})", userData=entry.filename
                )
        if isinstance(self._target, Profile):
            self._select_map_in_combo(self._target.map_mod)
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
        if new_map == self._target.map_mod:
            return
        self._target.map_mod = new_map
        self._reload_content()
        self._update_map_icon()
        self.changed.emit()

    def _update_map_icon(self) -> None:
        if not isinstance(self._target, Profile) or not self._catalog:
            self.map_icon.setPixmap(QPixmap())
            return
        entry = (
            self._catalog.entries.get(self._target.map_mod)
            if self._target.map_mod
            else None
        )
        if entry and entry.icon_cache_path:
            pix = QPixmap(entry.icon_cache_path)
            if not pix.isNull():
                self.map_icon.setPixmap(pix)
                return
        provider = QFileIconProvider()
        self.map_icon.setPixmap(
            provider.icon(QFileIconProvider.IconType.Computer).pixmap(72, 72)
        )

    # -------------------------------------------------------------- content

    def _reload_content(self) -> None:
        if self._target is None:
            self.content.set_items([])
            return
        if isinstance(self._target, Profile):
            self.content.set_items(self._profile_items(self._target))
        else:
            self.content.set_items(self._collection_items(self._target))

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
            QMessageBox.information(
                self,
                "Cartes ignorées",
                "Les cartes ne peuvent pas faire partie d'une collection "
                "(la carte est un choix propre à chaque profil).",
            )

    def _add_to_profile(self, entries: list[CatalogEntry]) -> None:
        prof = self._target
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
        if not res.has_any:
            return

        added_any = False
        if res.to_add:
            ans = QMessageBox.question(
                self,
                "Dépendances requises",
                f"{len(res.to_add)} dépendance(s) requise(s) sont présentes dans "
                f"la bibliothèque :\n\n{self._format_dep_list(res.to_add)}\n\n"
                f"Les ajouter au profil ?",
            )
            if ans == QMessageBox.StandardButton.Yes:
                for fname in res.to_add:
                    if fname != prof.map_mod and fname not in prof.mods:
                        prof.mods.append(fname)
                        added_any = True

        if res.missing:
            miss = "\n".join(f"• {m}" for m in res.missing)
            QMessageBox.warning(
                self,
                "Dépendances introuvables",
                f"{len(res.missing)} dépendance(s) requise(s) sont absentes de la "
                f"bibliothèque :\n\n{miss}\n\n"
                f"Télécharge-les puis relance un scan de la bibliothèque.",
            )

        if added_any:
            self._reload_content()
            self.changed.emit()

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

    def _set_excluded(self, fname: str, excluded: bool) -> None:
        if not isinstance(self._target, Profile):
            return
        prof = self._target
        if excluded and fname not in prof.excluded_mods:
            prof.excluded_mods.append(fname)
        elif not excluded and fname in prof.excluded_mods:
            prof.excluded_mods.remove(fname)
        else:
            return
        self._reload_content()
        self.changed.emit()

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
