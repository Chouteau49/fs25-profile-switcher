"""Edit a profile: pick a map, add/remove mods from the library."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileIconProvider,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog, CatalogEntry
from ..profiles.collection import Collection
from ..profiles.profile import Profile
from .library_table import LibraryTable

# Roles stored on items of the "mods du profil" list.
_KIND_MAP = "map"
_KIND_OWN = "own"
_KIND_INHERITED = "inherited"
_INHERITED_FG = QColor(70, 110, 200)
_EXCLUDED_FG = QColor(150, 150, 150)


class ProfileEditor(QWidget):
    """Two-pane editor.

    Left: the full library (search + table). Double-click adds the selected mod
    to the profile. Right: the profile's current selection (map + mods),
    metadata fields, and a "remove" button.
    """

    changed = Signal()  # emitted whenever the underlying profile is mutated

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile: Profile | None = None
        self._catalog: Catalog | None = None
        self._collections: list[Collection] = []

        self.name_input = QLineEdit(self)
        self.name_input.editingFinished.connect(self._on_name_edited)

        self.map_combo = QComboBox(self)
        self.map_combo.setMinimumWidth(280)
        self.map_combo.currentIndexChanged.connect(self._on_map_changed)

        self.description = QTextEdit(self)
        self.description.setMaximumHeight(80)
        self.description.textChanged.connect(self._on_description_changed)

        # Icon preview for the map
        self.map_icon = QLabel(self)
        self.map_icon.setFixedSize(100, 100)
        self.map_icon.setScaledContents(True)
        self.map_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_icon.setStyleSheet("border: 1px solid #555; background: #111; border-radius: 4px;")

        # Layout for top form + icon
        form_widget = QWidget(self)
        top_layout = QHBoxLayout(form_widget)
        
        form = QFormLayout()
        form.addRow("Nom du profil", self.name_input)
        form.addRow("Carte", self.map_combo)
        form.addRow("Notes", self.description)
        
        top_layout.addLayout(form, 1)
        top_layout.addWidget(self.map_icon)

        self.library = LibraryTable(self)
        self.library.entry_double_clicked.connect(self._add_entry)
        self.library.add_to_collection.connect(self._on_add_to_collection)

        self.add_btn = QPushButton("Ajouter au profil →", self)
        self.add_btn.clicked.connect(self._add_selected)
        self.remove_btn = QPushButton("← Retirer", self)
        self.remove_btn.clicked.connect(self._remove_selected)

        self.selected_list = QListWidget(self)
        self.selected_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.selected_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.selected_list.customContextMenuRequested.connect(self._on_selected_menu)

        # Inherited collections (checkable)
        self.collections_list = QListWidget(self)
        self.collections_list.setMaximumHeight(110)
        self.collections_list.itemChanged.connect(self._on_collection_toggled)
        coll_box = QGroupBox("Collections héritées", self)
        coll_layout = QVBoxLayout(coll_box)
        coll_layout.addWidget(self.collections_list)

        left_box = QGroupBox("Bibliothèque", self)
        left_layout = QVBoxLayout(left_box)
        left_layout.addWidget(self.library)

        right_box = QGroupBox("Mods du profil", self)
        right_layout = QVBoxLayout(right_box)
        right_layout.addWidget(coll_box)
        self.count_label = QLabel("0 mod")
        right_layout.addWidget(self.count_label)
        right_layout.addWidget(self.selected_list, 1)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.remove_btn)
        right_layout.addLayout(btn_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left_box)
        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root = QVBoxLayout(self)
        root.addWidget(form_widget)
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------ data

    def set_catalog(self, catalog: Catalog | None) -> None:
        self._catalog = catalog
        self.library.set_catalog(catalog)
        self._rebuild_map_combo()

    def set_collections(self, collections: list[Collection]) -> None:
        self._collections = list(collections)
        self._rebuild_collections_list()

    def _collection_mods_map(self) -> dict[str, list[str]]:
        return {c.slug: list(c.mods) for c in self._collections}

    def _rebuild_collections_list(self) -> None:
        self.collections_list.blockSignals(True)
        self.collections_list.clear()
        inherited = set(self._profile.collections) if self._profile else set()
        for col in self._collections:
            item = QListWidgetItem(f"{col.name}  ({len(col.mods)})")
            item.setData(Qt.ItemDataRole.UserRole, col.slug)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if col.slug in inherited else Qt.CheckState.Unchecked
            )
            self.collections_list.addItem(item)
        self.collections_list.blockSignals(False)

    def _on_add_to_collection(self, entries: list[CatalogEntry]) -> None:
        mods = [e for e in entries if not e.is_map]
        if not mods:
            QMessageBox.information(
                self,
                "Cartes ignorées",
                "Les cartes ne peuvent pas faire partie d'une collection.",
            )
            return
        if not self._collections:
            QMessageBox.information(
                self,
                "Aucune collection",
                "Crée d'abord une collection via le bouton « 🗂️ Collections ».",
            )
            return
        names = [c.name for c in self._collections]
        choice, ok = QInputDialog.getItem(
            self, "Ajouter à une collection", "Collection :", names, 0, False
        )
        if not ok or not choice:
            return
        col = next((c for c in self._collections if c.name == choice), None)
        if col is None:
            return
        added = 0
        for entry in mods:
            if entry.filename not in col.mods:
                col.mods.append(entry.filename)
                added += 1
        if added:
            col.save()
            self._rebuild_collections_list()
            # The active profile may inherit this collection → refresh its view.
            if self._profile and col.slug in self._profile.collections:
                self._reload_selected_list()
                self.changed.emit()
        QMessageBox.information(
            self,
            "Collection mise à jour",
            f"{added} mod(s) ajouté(s) à « {col.name} ».",
        )

    def _on_collection_toggled(self, item: QListWidgetItem) -> None:
        if self._profile is None:
            return
        slug = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        if checked and slug not in self._profile.collections:
            self._profile.collections.append(slug)
        elif not checked and slug in self._profile.collections:
            self._profile.collections = [
                s for s in self._profile.collections if s != slug
            ]
        self._reload_selected_list()
        self.changed.emit()

    def set_profile(self, profile: Profile | None) -> None:
        self._profile = profile
        block_name = self.name_input.blockSignals(True)
        block_desc = self.description.blockSignals(True)
        block_map = self.map_combo.blockSignals(True)
        if profile is None:
            self.name_input.clear()
            self.description.clear()
            self.map_combo.setCurrentIndex(0)
            self.selected_list.clear()
            self.count_label.setText("0 mod")
            self.setEnabled(False)
        else:
            self.setEnabled(True)
            self.name_input.setText(profile.name)
            self.description.setPlainText(profile.description)
            self._select_map_in_combo(profile.map_mod)
            self._reload_selected_list()
        self.name_input.blockSignals(block_name)
        self.description.blockSignals(block_desc)
        self.map_combo.blockSignals(block_map)
        self._rebuild_collections_list()
        self._update_map_icon()

        # Update library table profile filter
        self.library.set_profile(profile)

    def _update_map_icon(self) -> None:
        if not self._profile or not self._catalog:
            self.map_icon.setPixmap(QPixmap())
            return

        map_mod = self._profile.map_mod
        entry = self._catalog.entries.get(map_mod) if map_mod else None
        
        if entry and entry.icon_cache_path:
            pix = QPixmap(entry.icon_cache_path)
            if not pix.isNull():
                self.map_icon.setPixmap(pix)
                self.map_icon.setText("")
                return

        # Fallback to game icon from the executable
        game_exe = None
        if self._catalog and self._catalog.mods_dir:
            # We don't have direct access to config/install_dir here easily without passing it,
            # but we can try to guess or just use a generic icon.
            # However, the MainWindow has state.game.install_dir.
            pass

        # Try using QFileIconProvider on a dummy file or generic folder
        provider = QFileIconProvider()
        icon = provider.icon(QFileIconProvider.IconType.Computer)
        pix = icon.pixmap(100, 100)
        self.map_icon.setPixmap(pix)
        self.map_icon.setText("")
        self.map_icon.setStyleSheet("border: 1px solid #555; background: #111; border-radius: 4px;")

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
        if self._profile is not None:
            self._select_map_in_combo(self._profile.map_mod)
        self.map_combo.blockSignals(block)

    def _select_map_in_combo(self, filename: str | None) -> None:
        target = 0
        for i in range(self.map_combo.count()):
            if self.map_combo.itemData(i) == filename:
                target = i
                break
        self.map_combo.setCurrentIndex(target)

    def _on_map_changed(self) -> None:
        if self._profile is None:
            return
        new_map = self.map_combo.currentData()
        if new_map == self._profile.map_mod:
            return
        self._profile.map_mod = new_map
        self._reload_selected_list()
        self._update_map_icon()
        self.changed.emit()

    # -------------------------------------------------------------- editing

    def _add_entry(self, entry: CatalogEntry) -> None:
        if self._add_entry_no_sync(entry):
            if entry.is_map:
                self._select_map_in_combo(entry.filename)
            self._reload_selected_list()
            self.changed.emit()
            self._handle_dependencies([entry.filename])

    def _add_entry_no_sync(self, entry: CatalogEntry) -> bool:
        """Adds an entry but doesn't trigger UI reload or notification.
        Returns True if something was actually added or changed.
        """
        if self._profile is None:
            return False

        if entry.is_map:
            if self._profile.map_mod != entry.filename:
                self._profile.map_mod = entry.filename
                return True
            return False

        if entry.filename in self._profile.mods:
            return False

        self._profile.mods.append(entry.filename)
        # Adding explicitly overrides a prior exclusion of the same mod.
        if entry.filename in self._profile.excluded_mods:
            self._profile.excluded_mods.remove(entry.filename)
        return True

    def _add_selected(self) -> None:
        entries = self.library.selected_entries()
        if not entries:
            return

        changed = False
        map_changed = False
        added: list[str] = []
        for entry in entries:
            if self._add_entry_no_sync(entry):
                changed = True
                added.append(entry.filename)
                if entry.is_map:
                    map_changed = True

        if changed:
            if map_changed:
                self._select_map_in_combo(self._profile.map_mod)
            self._reload_selected_list()
            self.changed.emit()
            self._handle_dependencies(added)

    def _handle_dependencies(self, seed_filenames: list[str]) -> None:
        """Offer to pull in dependencies declared by the just-added mods.

        Best-effort: silent when the added mods declare no dependencies.
        """
        if self._profile is None or self._catalog is None or not seed_filenames:
            return
        from ..profiles.dependencies import resolve_new_dependencies

        res = resolve_new_dependencies(
            seed_filenames, self._profile.all_mod_filenames(), self._catalog
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
                    if fname != self._profile.map_mod and fname not in self._profile.mods:
                        self._profile.mods.append(fname)
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
            self._reload_selected_list()
            self.changed.emit()

    def _format_dep_list(self, filenames: list[str]) -> str:
        lines: list[str] = []
        for fname in filenames:
            entry = self._catalog.get(fname) if self._catalog else None
            label = f"{entry.display_title} ({fname})" if entry else fname
            lines.append(f"• {label}")
        return "\n".join(lines)

    def _remove_selected(self) -> None:
        if self._profile is None:
            return
        rows = self.selected_list.selectedItems()
        if not rows:
            return
        changed = False
        for item in rows:
            fname = item.data(Qt.ItemDataRole.UserRole)
            kind = item.data(Qt.ItemDataRole.UserRole + 1)
            if kind == _KIND_MAP:
                self._profile.map_mod = None
                self._select_map_in_combo(None)
                changed = True
            elif kind == _KIND_OWN and fname in self._profile.mods:
                self._profile.mods.remove(fname)
                changed = True
            elif kind == _KIND_INHERITED:
                # Can't delete from a shared collection — exclude for this profile.
                if fname not in self._profile.excluded_mods:
                    self._profile.excluded_mods.append(fname)
                    changed = True
        if changed:
            self._reload_selected_list()
            self.changed.emit()

    def _on_selected_menu(self, pos) -> None:
        if self._profile is None:
            return
        item = self.selected_list.itemAt(pos)
        if item is None:
            return
        fname = item.data(Qt.ItemDataRole.UserRole)
        kind = item.data(Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)
        if kind == _KIND_INHERITED:
            if fname in self._profile.excluded_mods:
                act = menu.addAction("↩ Réintégrer dans ce profil")
                act.triggered.connect(lambda: self._set_excluded(fname, False))
            else:
                act = menu.addAction("🚫 Exclure de ce profil")
                act.triggered.connect(lambda: self._set_excluded(fname, True))
        elif kind == _KIND_OWN:
            act = menu.addAction("← Retirer du profil")
            act.triggered.connect(self._remove_selected)
        elif kind == _KIND_MAP:
            act = menu.addAction("← Retirer la carte")
            act.triggered.connect(self._remove_selected)
        menu.exec_(self.selected_list.viewport().mapToGlobal(pos))

    def _set_excluded(self, fname: str, excluded: bool) -> None:
        if self._profile is None:
            return
        if excluded and fname not in self._profile.excluded_mods:
            self._profile.excluded_mods.append(fname)
        elif not excluded and fname in self._profile.excluded_mods:
            self._profile.excluded_mods.remove(fname)
        else:
            return
        self._reload_selected_list()
        self.changed.emit()

    def _reload_selected_list(self) -> None:
        self.selected_list.clear()
        if self._profile is None:
            self.count_label.setText("0 mod")
            return

        inherited_sources = self._profile.inherited_mod_filenames(
            self._collection_mods_map()
        )
        own = set(self._profile.mods)
        excluded = set(self._profile.excluded_mods)
        active_count = 0

        def make_item(fname: str, kind: str, *, is_excluded: bool = False) -> None:
            nonlocal active_count
            label = fname
            is_map = False
            if self._catalog is not None:
                entry = self._catalog.get(fname)
                if entry is not None:
                    is_map = entry.is_map
                    label = f"{entry.display_title} ({entry.filename})"
            if kind == _KIND_MAP:
                label += " [carte]"
            elif kind == _KIND_INHERITED:
                srcs = ", ".join(inherited_sources.get(fname, []))
                label += f"  — hérité : {srcs}" if srcs else "  — hérité"
                if is_excluded:
                    label += " (exclu)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, fname)
            item.setData(Qt.ItemDataRole.UserRole + 1, kind)
            if self._catalog is not None and fname not in self._catalog:
                item.setForeground(Qt.GlobalColor.red)
                item.setToolTip("Absent de la bibliothèque")
            elif kind == _KIND_INHERITED and is_excluded:
                item.setForeground(_EXCLUDED_FG)
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
            elif kind == _KIND_INHERITED:
                item.setForeground(_INHERITED_FG)
                item.setToolTip("Hérité d'une collection — clic droit pour exclure")
            self.selected_list.addItem(item)
            if not is_excluded:
                active_count += 1

        # Map first, then own mods, then inherited (incl. excluded, shown struck-out).
        if self._profile.map_mod:
            make_item(self._profile.map_mod, _KIND_MAP)
        for fname in self._profile.mods:
            make_item(fname, _KIND_OWN)
        for fname in inherited_sources:
            if fname in own or fname == self._profile.map_mod:
                continue
            make_item(fname, _KIND_INHERITED, is_excluded=fname in excluded)

        self.count_label.setText(
            f"{active_count} mod{'s' if active_count > 1 else ''} actif(s)"
        )

    # ----------------------------------------------------------- form props

    def _on_name_edited(self) -> None:
        if self._profile is None:
            return
        new = self.name_input.text().strip()
        if not new or new == self._profile.name:
            return
        self._profile.name = new
        self.changed.emit()

    def _on_description_changed(self) -> None:
        if self._profile is None:
            return
        self._profile.description = self.description.toPlainText()
        self.changed.emit()
