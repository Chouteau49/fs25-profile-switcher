"""Sortable, filterable table of the entire mod library.

Used both in the main window (bibliothèque tab) and inside the profile editor
(left side: pick from here, add to the profile on the right).
"""
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QIcon, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog, CatalogEntry

COL_ICON = 0
COL_FILENAME = 1
COL_TITLE = 2
COL_VERSION = 3
COL_BRAND = 4
COL_TYPE = 5
COL_AUTHOR = 6

class CatalogTableModel(QAbstractTableModel):
    HEADERS = ("", "Fichier", "Titre", "Version", "Marque", "Catégorie", "Auteur")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[CatalogEntry] = []
        self._icons: dict[str, QIcon] = {}

    def set_catalog(self, catalog: Catalog | None) -> None:
        self.beginResetModel()
        self._entries = sorted(
            (catalog.entries.values() if catalog else []),
            key=lambda e: e.display_title.lower(),
        )
        self._icons = {}  # Clear icon cache
        self.endResetModel()

    def entry_at(self, row: int) -> CatalogEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        entry = self._entries[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DecorationRole and col == COL_ICON:
            if not entry.icon_cache_path:
                return None
            if entry.icon_cache_path not in self._icons:
                pix = QPixmap(entry.icon_cache_path)
                if not pix.isNull():
                    self._icons[entry.icon_cache_path] = QIcon(
                        pix.scaled(
                            32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                        )
                    )
                else:
                    # Fallback icon for the table
                    provider = QFileIconProvider()
                    self._icons[entry.icon_cache_path] = provider.icon(QFileIconProvider.IconType.File)
            return self._icons[entry.icon_cache_path]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_FILENAME:
                return entry.filename
            if col == COL_TITLE:
                return entry.display_title
            if col == COL_VERSION:
                return entry.version
            if col == COL_BRAND:
                return entry.brand or ""
            if col == COL_TYPE:
                return entry.category
            if col == COL_AUTHOR:
                return entry.author or ""
        if role == Qt.ItemDataRole.ToolTipRole and entry.error:
            return entry.error
        if role == Qt.ItemDataRole.UserRole:
            return entry
        return None


class LibraryFilterProxy(QSortFilterProxyModel):
    """Filter on filename + title + author across columns.

    The native Qt filter only matches a single column; we override
    :meth:`filterAcceptsRow` so a single search box matches any of those.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._needle = ""
        self._only_maps = False
        self._category = "Toutes"
        self._brand = "Toutes"
        self._sub_type = "Tous"

    def set_search(self, text: str) -> None:
        self._needle = text.strip().lower()
        self.invalidateFilter()

    def set_only_maps(self, value: bool) -> None:
        self._only_maps = value
        self.invalidateFilter()

    def set_category(self, value: str) -> None:
        self._category = value
        self.invalidateFilter()

    def set_brand(self, value: str) -> None:
        self._brand = value
        self.invalidateFilter()

    def set_sub_type(self, value: str) -> None:
        self._sub_type = value
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, CatalogTableModel):
            return True
        entry = model.entry_at(source_row)
        if entry is None:
            return False
        if self._only_maps and not entry.is_map:
            return False
        if self._category != "Toutes" and entry.category != self._category:
            return False
        if self._brand != "Toutes":
            if not entry.brand or entry.brand.lower() != self._brand.lower():
                return False
        if self._sub_type != "Tous":
            if not entry.type or entry.type.lower() != self._sub_type.lower():
                return False
                
        if not self._needle:
            return True
        haystack = " ".join(
            (entry.filename, entry.display_title, entry.author or "", entry.brand or "")
        ).lower()
        return self._needle in haystack


class LibraryTable(QWidget):
    """Search bar + table view bound to a :class:`CatalogTableModel`."""

    selection_changed = Signal(list)  # list[CatalogEntry]
    entry_double_clicked = Signal(object)  # CatalogEntry

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = CatalogTableModel(self)
        self.proxy = LibraryFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Rechercher (nom, titre, auteur)…")
        self.search.textChanged.connect(self.proxy.set_search)

        self.cat_filter = QComboBox(self)
        self.cat_filter.addItem("Toutes les catégories", userData="Toutes")
        # Fixed categories for now, matching catalog.py logic
        for cat in ["Carte", "Script", "Véhicule", "Bâtiment", "Objet", "Divers"]:
            self.cat_filter.addItem(cat, userData=cat)
        self.cat_filter.currentIndexChanged.connect(self._on_cat_filter_changed)

        self.brand_filter = QComboBox(self)
        self.brand_filter.addItem("Toutes les marques", userData="Toutes")
        self.brand_filter.currentIndexChanged.connect(self._on_brand_filter_changed)

        self.type_filter = QComboBox(self)
        self.type_filter.addItem("Tous les types", userData="Tous")
        self.type_filter.currentIndexChanged.connect(self._on_type_filter_changed)

        self.count_label = QLabel("0 mod", self)

        self.view = QTableView(self)
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.horizontalHeader().setStretchLastSection(True)

        header = self.view.horizontalHeader()
        header.setSectionResizeMode(COL_ICON, header.ResizeMode.Fixed)
        self.view.setColumnWidth(COL_ICON, 40)
        
        # On redimensionne d'abord au contenu pour les autres
        self.view.resizeColumnsToContents()
        
        # Puis on ajuste finement les colonnes prioritaires
        header.setSectionResizeMode(COL_FILENAME, header.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_TITLE, header.ResizeMode.Stretch)  # Le titre prend l'espace
        header.setDefaultSectionSize(120)  # Taille par défaut raisonnable
        
        self.view.sortByColumn(COL_TITLE, Qt.SortOrder.AscendingOrder)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.selectionModel().selectionChanged.connect(self._on_selection)

        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)

        # Ctrl+A shortcut
        self.select_all_action = QAction("Tout sélectionner", self)
        self.select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.select_all_action.triggered.connect(self.view.selectAll)
        self.addAction(self.select_all_action)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(self.search, 3)
        top.addWidget(self.cat_filter, 1)
        top.addWidget(self.brand_filter, 1)
        top.addWidget(self.type_filter, 1)
        top.addWidget(self.count_label)
        layout.addLayout(top)
        layout.addWidget(self.view)

    def set_catalog(self, catalog: Catalog | None) -> None:
        self.model.set_catalog(catalog)
        self._update_count()
        self._update_filters()
        self.proxy.modelReset.emit()
        # Ajuster les colonnes après le chargement des données
        self.view.resizeColumnsToContents()
        self.view.horizontalHeader().setSectionResizeMode(COL_TITLE, self.view.horizontalHeader().ResizeMode.Stretch)

    def _update_filters(self) -> None:
        """Repopulate brand and type filters based on current catalog."""
        brands = set()
        types = set()
        for i in range(self.model.rowCount()):
            entry = self.model.entry_at(i)
            if entry.brand:
                brands.add(entry.brand)
            if entry.type:
                types.add(entry.type)

        # Mapping des types FS vers le Français
        type_map = {
            "tractorss": "Tracteurs (Petits)",
            "tractorsm": "Tracteurs (Moyens)",
            "tractorsl": "Tracteurs (Gros)",
            "trucks": "Camions",
            "cars": "Voitures",
            "harvesters": "Moissonneuses",
            "forageharvesters": "Ensilage",
            "potatoharvesting": "Pommes de Terre",
            "beetharvesting": "Betteraves",
            "grapes": "Vignes",
            "olives": "Olives",
            "forestry": "Sylviculture",
            "trailers": "Remorques",
            "trailerssemi": "Semi-Remorques",
            "baleloaders": "Plateaux / Ramasseurs",
            "balers": "Presses",
            "mowers": "Faucheuses",
            "tedders": "Faneuses",
            "windrowers": "Andaineuses",
            "loaders": "Chargeuses",
            "teleloadervehicles": "Télescopiques",
            "skidsteervehicles": "Chargeuses compactes",
            "frontloadervehicles": "Chargeuses frontales",
            "cultivators": "Cultivateurs",
            "plows": "Charrues",
            "seeders": "Semoirs",
            "planters": "Planteuses",
            "slurrytanks": "Tonnes à lisier",
            "fertilizerspreaders": "Épandeurs d'engrais",
            "manurespreaders": "Épandeurs de fumier",
            "sprayers": "Pulvérisateurs",
            "weights": "Masses",
            "cutters": "Coupes",
            "cuttertrailers": "Chariots de coupe",
            "cornheaders": "Cueilleurs Maïs",
            "animaltransport": "Bétaillères",
            "waterTanks": "Citernes d'eau",
            "lowloaders": "Porte-engins",
            "augerwagons": "Transbordeurs",
            "loaderwagons": "Auto-chargeuses",
            "forestryharvesters": "Abatteuses",
            "forestryforwarders": "Porteurs forestiers",
            "woodtransport": "Remorques bois",
            "forestrymisc": "Matériel forestier",
            "misc": "Divers / Outils",
            "animalpens": "Enclos animaux",
            "beehives": "Ruches",
            "sheds": "Hangars",
            "silos": "Silos",
            "productionpoints": "Productions",
            "sellingpoints": "Points de vente",
            "placeablemisc": "Placeables divers",
            "decoration": "Décoration",
            "pallets": "Palettes / BigBags",
            "generators": "Générateurs",
            "farmhouses": "Maisons de ferme",
            "storages": "Stockages",
        }

        # Update Brand filter
        current_brand = self.brand_filter.currentData()
        self.brand_filter.blockSignals(True)
        self.brand_filter.clear()
        self.brand_filter.addItem("Toutes les marques", userData="Toutes")
        for b in sorted(list(brands)):
            self.brand_filter.addItem(b, userData=b)
        idx = self.brand_filter.findData(current_brand)
        self.brand_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.brand_filter.blockSignals(False)

        # Update Type filter
        current_type = self.type_filter.currentData()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("Tous les types", userData="Tous")
        
        # Sort by translated name
        sorted_types = sorted(list(types), key=lambda t: type_map.get(t.lower(), t))
        for t in sorted_types:
            label = type_map.get(t.lower(), t)
            self.type_filter.addItem(label, userData=t)
            
        idx = self.type_filter.findData(current_type)
        self.type_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_filter.blockSignals(False)

    def selected_entry(self) -> CatalogEntry | None:
        """Returns the 'current' (focused) entry."""
        idx = self.view.currentIndex()
        if not idx.isValid():
            return None
        source = self.proxy.mapToSource(idx)
        return self.model.entry_at(source.row())

    def selected_entries(self) -> list[CatalogEntry]:
        """Returns all selected entries."""
        idxs = self.view.selectionModel().selectedRows()
        entries = []
        for idx in idxs:
            source = self.proxy.mapToSource(idx)
            entry = self.model.entry_at(source.row())
            if entry:
                entries.append(entry)
        return entries

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        
        idx = self.view.indexAt(pos)
        if idx.isValid():
            view_details = QAction("👁 Voir les détails…", self)
            view_details.triggered.connect(lambda: self._show_details(idx))
            menu.addAction(view_details)
            menu.addSeparator()

        menu.addAction(self.select_all_action)
        menu.exec_(self.view.viewport().mapToGlobal(pos))

    def _show_details(self, proxy_idx: QModelIndex) -> None:
        source_idx = self.proxy.mapToSource(proxy_idx)
        entry = self.model.entry_at(source_idx.row())
        if entry:
            from .mod_detail import ModDetailDialog
            dlg = ModDetailDialog(entry, self)
            dlg.exec()

    def _on_cat_filter_changed(self) -> None:
        cat = self.cat_filter.currentData()
        self.proxy.set_category(cat)
        self._update_count()

    def _on_brand_filter_changed(self) -> None:
        brand = self.brand_filter.currentData()
        self.proxy.set_brand(brand)
        self._update_count()

    def _on_type_filter_changed(self) -> None:
        sub_type = self.type_filter.currentData()
        self.proxy.set_sub_type(sub_type)
        self._update_count()

    def _update_count(self) -> None:
        n = self.proxy.rowCount()
        total = self.model.rowCount()
        self.count_label.setText(f"{n}/{total} mods" if n != total else f"{total} mods")

    def _on_selection(self) -> None:
        self.selection_changed.emit(self.selected_entries())

    def _on_double_click(self, index: QModelIndex) -> None:
        entry = self.model.entry_at(self.proxy.mapToSource(index).row())
        if entry is not None:
            self.entry_double_clicked.emit(entry)
