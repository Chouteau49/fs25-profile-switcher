"""Manage collections: a list on the left, a library/contents editor on the right.

Mirrors the profile list + editor, minus the map (collections are mods only).
Changes are saved to disk immediately. Collections are mutated in place on the
:class:`~fsmods_gui.state.AppState`, so a profile's effective mod list reflects
edits without a reload.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import CatalogEntry
from ..profiles.collection import Collection
from .library_table import LibraryTable


class CollectionsManagerDialog(QDialog):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current: Collection | None = None
        self.setWindowTitle("Gestion des collections")
        self.setMinimumSize(1000, 640)

        # ---- left: collections list
        self.list = QListWidget(self)
        self.list.currentRowChanged.connect(self._on_row_changed)
        new_btn = QPushButton("➕ Nouvelle", self)
        dup_btn = QPushButton("🗐 Dupliquer", self)
        del_btn = QPushButton("✖ Supprimer", self)
        new_btn.clicked.connect(self._on_new)
        dup_btn.clicked.connect(self._on_duplicate)
        del_btn.clicked.connect(self._on_delete)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Collections", left))
        left_layout.addWidget(self.list, 1)
        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(dup_btn)
        btn_row.addWidget(del_btn)
        left_layout.addLayout(btn_row)

        # ---- right: library picker + collection contents
        self.title_label = QLabel("—", self)
        self.title_label.setStyleSheet("font-weight: 700; font-size: 15px;")

        self.library = LibraryTable(self)
        self.library.set_catalog(state.catalog)
        self.library.entry_double_clicked.connect(self._add_entry)

        self.add_btn = QPushButton("Ajouter à la collection →", self)
        self.add_btn.clicked.connect(self._add_selected)
        self.remove_btn = QPushButton("← Retirer", self)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.selected_list = QListWidget(self)
        self.selected_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.count_label = QLabel("0 mod", self)

        lib_box = QGroupBox("Bibliothèque", self)
        lib_layout = QVBoxLayout(lib_box)
        lib_layout.addWidget(self.library)

        content_box = QGroupBox("Mods de la collection", self)
        content_layout = QVBoxLayout(content_box)
        content_layout.addWidget(self.count_label)
        content_layout.addWidget(self.selected_list, 1)
        crow = QHBoxLayout()
        crow.addWidget(self.add_btn)
        crow.addWidget(self.remove_btn)
        content_layout.addLayout(crow)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.title_label)
        right_splitter = QSplitter(Qt.Orientation.Horizontal, right)
        right_splitter.addWidget(lib_box)
        right_splitter.addWidget(content_box)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        right_layout.addWidget(right_splitter, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(buttons)

        self._refresh_list()
        self._set_current(None)

    # ----------------------------------------------------------------- list

    def _refresh_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for col in self._state.collections:
            item = QListWidgetItem(f"{col.name}  ({len(col.mods)})")
            item.setData(Qt.ItemDataRole.UserRole, col.slug)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _select_slug(self, slug: str | None) -> None:
        if slug is None:
            return
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == slug:
                self.list.setCurrentRow(i)
                return

    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._state.collections):
            self._set_current(self._state.collections[row])
        else:
            self._set_current(None)

    def _set_current(self, col: Collection | None) -> None:
        self._current = col
        has = col is not None
        self.title_label.setText(col.name if col else "— Sélectionne une collection —")
        for w in (self.library, self.add_btn, self.remove_btn, self.selected_list):
            w.setEnabled(has)
        self._reload_selected()

    # -------------------------------------------------------------- actions

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvelle collection", "Nom :")
        if not ok or not name.strip():
            return
        try:
            col = self._state.new_collection(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        self._refresh_list()
        self._select_slug(col.slug)

    def _on_duplicate(self) -> None:
        if self._current is None:
            return
        name, ok = QInputDialog.getText(
            self, "Dupliquer", "Nom :", text=f"{self._current.name} (copie)"
        )
        if not ok or not name.strip():
            return
        try:
            new = self._state.new_collection(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        new.mods = list(self._current.mods)
        new.description = self._current.description
        new.save()
        self._refresh_list()
        self._select_slug(new.slug)

    def _on_delete(self) -> None:
        if self._current is None:
            return
        confirm = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer la collection « {self._current.name} » ?\n"
            f"Elle sera retirée des profils qui l'utilisent.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        affected = self._state.delete_collection(self._current)
        self._set_current(None)
        self._refresh_list()
        if affected:
            QMessageBox.information(
                self,
                "Collection supprimée",
                "Retirée des profils : " + ", ".join(affected),
            )

    # ----------------------------------------------------------- edit mods

    def _add_entry(self, entry: CatalogEntry) -> None:
        self._add_entries([entry])

    def _add_selected(self) -> None:
        self._add_entries(self.library.selected_entries())

    def _add_entries(self, entries: list[CatalogEntry]) -> None:
        if self._current is None or not entries:
            return
        maps_skipped = 0
        changed = False
        for entry in entries:
            if entry.is_map:
                maps_skipped += 1
                continue
            if entry.filename not in self._current.mods:
                self._current.mods.append(entry.filename)
                changed = True
        if changed:
            self._save_current()
        if maps_skipped:
            QMessageBox.information(
                self,
                "Cartes ignorées",
                "Les cartes ne peuvent pas faire partie d'une collection "
                "(la carte est un choix propre à chaque profil).",
            )

    def _remove_selected(self) -> None:
        if self._current is None:
            return
        rows = self.selected_list.selectedItems()
        changed = False
        for item in rows:
            fname = item.data(Qt.ItemDataRole.UserRole)
            if fname in self._current.mods:
                self._current.mods.remove(fname)
                changed = True
        if changed:
            self._save_current()

    def _reload_selected(self) -> None:
        self.selected_list.clear()
        if self._current is None:
            self.count_label.setText("0 mod")
            return
        catalog = self._state.catalog
        for fname in self._current.mods:
            label = fname
            if catalog is not None:
                entry = catalog.get(fname)
                if entry is not None:
                    label = f"{entry.display_title} ({fname})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, fname)
            if catalog is not None and fname not in catalog:
                item.setForeground(Qt.GlobalColor.red)
                item.setToolTip("Absent de la bibliothèque")
            self.selected_list.addItem(item)
        n = len(self._current.mods)
        self.count_label.setText(f"{n} mod{'s' if n > 1 else ''}")

    def _save_current(self) -> None:
        if self._current is None:
            return
        self._current.save()
        self._reload_selected()
        # Refresh the count shown in the list label.
        slug = self._current.slug
        self._refresh_list()
        self._select_slug(slug)
