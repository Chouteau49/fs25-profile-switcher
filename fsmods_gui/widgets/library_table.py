"""Sortable, filterable table of the entire mod library.

Used both in the main window (bibliothèque tab) and inside the profile editor
(left side: pick from here, add to the profile on the right).
"""
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QRect,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog, CatalogEntry
from ..profiles.profile import Profile

COL_ICON = 0
COL_FILENAME = 1
COL_TITLE = 2
COL_VERSION = 3
COL_BRAND = 4
COL_TYPE = 5
COL_AUTHOR = 6


def _make_searchable_combo(combo: QComboBox, placeholder: str = "Filtrer…") -> None:
    """Turn a combo into a type-to-filter combo (case-insensitive 'contains').

    The combo stays a real combo (its ``currentData`` drives the filters) but the
    user can type to narrow a long list; picking a completion selects the item.
    """
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.lineEdit().setPlaceholderText(placeholder)
    completer = combo.completer()
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def _snap() -> None:
        # Empty field → back to the "all" item; unknown text → revert to the
        # current valid selection so the box never shows a stale free-text value.
        text = combo.lineEdit().text().strip()
        if not text:
            combo.setCurrentIndex(0)
            return
        i = combo.findText(text, Qt.MatchFlag.MatchFixedString)
        if i >= 0:
            combo.setCurrentIndex(i)
        else:
            combo.setEditText(combo.itemText(combo.currentIndex()))

    combo.lineEdit().editingFinished.connect(_snap)

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


# ---- Gallery (grid) view -------------------------------------------------

CARD_THUMB = 150  # thumbnail square side, in px
CARD_PAD = 8
CARD_TEXT_H = 46  # room for two text lines under the thumbnail
CARD_W = CARD_THUMB + 2 * CARD_PAD
CARD_H = CARD_THUMB + CARD_TEXT_H + 2 * CARD_PAD


class ModCardDelegate(QStyledItemDelegate):
    """Render each catalog entry as a ModHub-style card (big thumbnail + title).

    Bound to a :class:`QListView` in icon mode whose model column is
    ``COL_TITLE`` so ``DisplayRole`` yields the title.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmaps: dict[str, QPixmap] = {}

    def _thumb(self, entry: CatalogEntry) -> QPixmap | None:
        path = entry.icon_cache_path
        if not path:
            return None
        if path not in self._pixmaps:
            pix = QPixmap(path)
            if pix.isNull():
                self._pixmaps[path] = QPixmap()  # cache the miss
            else:
                self._pixmaps[path] = pix.scaled(
                    CARD_THUMB,
                    CARD_THUMB,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        pix = self._pixmaps[path]
        return pix if not pix.isNull() else None

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(CARD_W, CARD_H)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        entry = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, CatalogEntry):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # Card background
        if selected:
            bg = option.palette.highlight().color()
            border = bg.lighter(120)
        else:
            bg = QColor("#2a2a2a") if not hovered else QColor("#343434")
            border = QColor("#555") if not hovered else QColor("#7a7a7a")
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(rect, 8, 8)

        # Thumbnail (centered in the upper square zone)
        thumb_zone = QRect(rect.left() + CARD_PAD, rect.top() + CARD_PAD, CARD_THUMB, CARD_THUMB)
        pix = self._thumb(entry)
        if pix is not None:
            px = thumb_zone.left() + (thumb_zone.width() - pix.width()) // 2
            py = thumb_zone.top() + (thumb_zone.height() - pix.height()) // 2
            painter.drawPixmap(px, py, pix)
        else:
            painter.setPen(QPen(QColor("#666")))
            painter.drawText(thumb_zone, Qt.AlignmentFlag.AlignCenter, "🧩")

        text_color = (
            option.palette.highlightedText().color() if selected else QColor("#e6e6e6")
        )

        # Title (one line, elided)
        title_rect = QRect(
            rect.left() + CARD_PAD,
            thumb_zone.bottom() + 4,
            rect.width() - 2 * CARD_PAD,
            18,
        )
        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QPen(text_color))
        title = painter.fontMetrics().elidedText(
            entry.display_title, Qt.TextElideMode.ElideRight, title_rect.width()
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, title)

        # Subtitle: category + version
        sub_rect = QRect(title_rect.left(), title_rect.bottom() + 1, title_rect.width(), 16)
        sub_font = QFont(option.font)
        sub_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))
        painter.setFont(sub_font)
        painter.setPen(QPen(QColor("#9aa0a6") if not selected else text_color))
        sub = entry.category
        if entry.type:
            sub = f"{sub} · {entry.type}"
        if entry.version and entry.version != "0.0.0.0":
            sub = f"{sub} · v{entry.version}"
        sub = painter.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideRight, sub_rect.width())
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, sub)

        # Error marker
        if entry.error:
            painter.setPen(QPen(QColor("#e57373")))
            painter.drawText(thumb_zone.adjusted(4, 4, -4, -4), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, "⚠")

        painter.restore()


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
        self._profile: Profile | None = None
        self._profile_filter_mode = "all"  # "all", "not_in_profile", "in_profile"

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

    def set_profile(self, profile: Profile | None) -> None:
        """Set the current profile for filtering."""
        self._profile = profile
        self.invalidateFilter()

    def set_profile_filter_mode(self, mode: str) -> None:
        """Set the profile filter mode: 'all', 'not_in_profile', 'in_profile'."""
        self._profile_filter_mode = mode
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
        
        # Profile filter
        if self._profile and self._profile_filter_mode != "all":
            is_in_profile = entry.filename in self._profile.all_mod_filenames()
            if self._profile_filter_mode == "not_in_profile" and is_in_profile:
                return False
            if self._profile_filter_mode == "in_profile" and not is_in_profile:
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
    add_to_collection = Signal(list)  # list[CatalogEntry]
    delete_requested = Signal(list)  # list[CatalogEntry] — remove from the library

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
        _make_searchable_combo(self.brand_filter, "Filtrer les marques…")

        self.type_filter = QComboBox(self)
        self.type_filter.addItem("Tous les types", userData="Tous")
        self.type_filter.currentIndexChanged.connect(self._on_type_filter_changed)
        _make_searchable_combo(self.type_filter, "Filtrer les types…")

        self.profile_filter = QComboBox(self)
        self.profile_filter.addItem("Tous les mods", userData="all")
        self.profile_filter.addItem("Non présents dans le profil", userData="not_in_profile")
        self.profile_filter.addItem("Présents dans le profil", userData="in_profile")
        self.profile_filter.currentIndexChanged.connect(self._on_profile_filter_changed)
        self.profile_filter.setEnabled(False)  # Disabled until a profile is selected

        self.count_label = QLabel("0 mod", self)

        # View-mode toggle (table / gallery)
        self.table_btn = QToolButton(self)
        self.table_btn.setText("☰")
        self.table_btn.setToolTip("Vue tableau")
        self.table_btn.setCheckable(True)
        self.table_btn.setChecked(True)
        self.table_btn.clicked.connect(lambda: self.set_view_mode("table"))

        self.grid_btn = QToolButton(self)
        self.grid_btn.setText("▦")
        self.grid_btn.setToolTip("Vue galerie (grandes vignettes)")
        self.grid_btn.setCheckable(True)
        self.grid_btn.clicked.connect(lambda: self.set_view_mode("grid"))

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

        # ---- Gallery (grid) view, sharing the same proxy model
        self.grid = QListView(self)
        self.grid.setModel(self.proxy)
        self.grid.setModelColumn(COL_TITLE)  # DisplayRole/keyboard search on the title
        self.grid.setItemDelegate(ModCardDelegate(self.grid))
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setFlow(QListView.Flow.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(6)
        self.grid.setMouseTracking(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.grid.doubleClicked.connect(self._on_double_click)
        self.grid.selectionModel().selectionChanged.connect(self._on_selection)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._on_grid_context_menu)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.view)   # index 0 = table
        self.stack.addWidget(self.grid)   # index 1 = gallery
        self._view_mode = "table"

        # Ctrl+A shortcut
        self.select_all_action = QAction("Tout sélectionner", self)
        self.select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.select_all_action.triggered.connect(self._select_all)
        self.addAction(self.select_all_action)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(self.search, 3)
        top.addWidget(self.cat_filter, 1)
        top.addWidget(self.brand_filter, 1)
        top.addWidget(self.type_filter, 1)
        top.addWidget(self.profile_filter, 1)
        top.addWidget(self.count_label)
        top.addWidget(self.table_btn)
        top.addWidget(self.grid_btn)
        layout.addLayout(top)
        layout.addWidget(self.stack)

        # Default to the gallery (thumbnail) view everywhere the library appears.
        self.set_view_mode("grid")

    # --------------------------------------------------------------- view mode

    def set_view_mode(self, mode: str) -> None:
        """Switch between the ``"table"`` and ``"grid"`` (gallery) views."""
        if mode not in ("table", "grid"):
            return
        self._view_mode = mode
        is_grid = mode == "grid"
        self.stack.setCurrentIndex(1 if is_grid else 0)
        self.table_btn.setChecked(not is_grid)
        self.grid_btn.setChecked(is_grid)
        self._on_selection()  # re-sync downstream listeners to the active view

    @property
    def _active_view(self) -> QAbstractItemView:
        return self.grid if self._view_mode == "grid" else self.view

    def _select_all(self) -> None:
        self._active_view.selectAll()

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
        idx = self._active_view.currentIndex()
        if not idx.isValid():
            return None
        source = self.proxy.mapToSource(idx)
        return self.model.entry_at(source.row())

    def selected_entries(self) -> list[CatalogEntry]:
        """Returns all selected entries (deduplicated by row, any view)."""
        sel = self._active_view.selectionModel()
        if sel is None:
            return []
        entries: list[CatalogEntry] = []
        seen: set[int] = set()
        for idx in sel.selectedIndexes():
            row = self.proxy.mapToSource(idx).row()
            if row in seen:
                continue
            seen.add(row)
            entry = self.model.entry_at(row)
            if entry:
                entries.append(entry)
        return entries

    def _on_context_menu(self, pos) -> None:
        self._show_context_menu(self.view, pos)

    def _on_grid_context_menu(self, pos) -> None:
        self._show_context_menu(self.grid, pos)

    def _show_context_menu(self, view: QAbstractItemView, pos) -> None:
        menu = QMenu(self)

        idx = view.indexAt(pos)
        if idx.isValid():
            view_details = QAction("👁 Voir les détails…", self)
            view_details.triggered.connect(lambda: self._show_details(idx))
            menu.addAction(view_details)
            add_coll = QAction("🗂️ Ajouter à une collection…", self)
            add_coll.triggered.connect(self._emit_add_to_collection)
            menu.addAction(add_coll)
            menu.addSeparator()
            delete_act = QAction("🗑 Supprimer de la bibliothèque…", self)
            delete_act.triggered.connect(self._emit_delete)
            menu.addAction(delete_act)
            menu.addSeparator()

        menu.addAction(self.select_all_action)
        menu.exec_(view.viewport().mapToGlobal(pos))

    def _current_entries(self) -> list[CatalogEntry]:
        entries = self.selected_entries()
        if not entries:
            entry = self.selected_entry()
            if entry is not None:
                entries = [entry]
        return entries

    def _emit_add_to_collection(self) -> None:
        entries = self._current_entries()
        if entries:
            self.add_to_collection.emit(entries)

    def _emit_delete(self) -> None:
        entries = self._current_entries()
        if entries:
            self.delete_requested.emit(entries)

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

    def _on_profile_filter_changed(self) -> None:
        mode = self.profile_filter.currentData()
        self.proxy.set_profile_filter_mode(mode)
        self._update_count()

    def set_profile(self, profile: Profile | None) -> None:
        """Set the current profile for filtering.
        
        When a profile is selected, automatically switches to "not_in_profile" mode.
        When profile is None, disables the profile filter.
        """
        self.proxy.set_profile(profile)
        
        if profile is None:
            self.profile_filter.setEnabled(False)
            self.profile_filter.blockSignals(True)
            self.profile_filter.setCurrentIndex(0)  # Reset to "Tous les mods"
            self.profile_filter.blockSignals(False)
        else:
            self.profile_filter.setEnabled(True)
            self.profile_filter.blockSignals(True)
            self.profile_filter.setCurrentIndex(1)  # Automatically set to "Non présents"
            self.profile_filter.blockSignals(False)
            self.proxy.set_profile_filter_mode("not_in_profile")
        
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
