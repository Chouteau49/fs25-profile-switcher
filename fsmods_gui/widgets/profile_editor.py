"""Edit a profile: pick a map, add/remove mods from the library."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileIconProvider,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog, CatalogEntry
from ..profiles.profile import Profile
from .library_table import LibraryTable


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

        self.add_btn = QPushButton("Ajouter au profil →", self)
        self.add_btn.clicked.connect(self._add_selected)
        self.remove_btn = QPushButton("← Retirer", self)
        self.remove_btn.clicked.connect(self._remove_selected)

        self.selected_list = QListWidget(self)
        self.selected_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

        left_box = QGroupBox("Bibliothèque", self)
        left_layout = QVBoxLayout(left_box)
        left_layout.addWidget(self.library)

        right_box = QGroupBox("Mods du profil", self)
        right_layout = QVBoxLayout(right_box)
        self.count_label = QLabel("0 mod")
        right_layout.addWidget(self.count_label)
        right_layout.addWidget(self.selected_list)
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
        self._update_map_icon()

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
        return True

    def _add_selected(self) -> None:
        entries = self.library.selected_entries()
        if not entries:
            return

        changed = False
        map_changed = False
        for entry in entries:
            if self._add_entry_no_sync(entry):
                changed = True
                if entry.is_map:
                    map_changed = True

        if changed:
            if map_changed:
                self._select_map_in_combo(self._profile.map_mod)
            self._reload_selected_list()
            self.changed.emit()

    def _remove_selected(self) -> None:
        if self._profile is None:
            return
        rows = self.selected_list.selectedItems()
        if not rows:
            return
        targets = [item.data(Qt.ItemDataRole.UserRole) for item in rows]
        changed = False
        for fname in targets:
            if fname == self._profile.map_mod:
                self._profile.map_mod = None
                self._select_map_in_combo(None)
                changed = True
            elif fname in self._profile.mods:
                self._profile.mods.remove(fname)
                changed = True
        if changed:
            self._reload_selected_list()
            self.changed.emit()

    def _reload_selected_list(self) -> None:
        self.selected_list.clear()
        if self._profile is None:
            self.count_label.setText("0 mod")
            return
        for fname in self._profile.all_mod_filenames():
            label = fname
            if self._catalog is not None:
                entry = self._catalog.get(fname)
                if entry is not None:
                    suffix = " [carte]" if entry.is_map else ""
                    label = f"{entry.display_title} ({entry.filename}){suffix}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, fname)
            if self._catalog is not None and fname not in self._catalog:
                item.setForeground(Qt.GlobalColor.red)
                item.setToolTip("Absent de la bibliothèque")
            self.selected_list.addItem(item)
        n = len(self._profile.all_mod_filenames())
        self.count_label.setText(f"{n} mod{'s' if n > 1 else ''}")

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
