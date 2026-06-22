"""Reusable panel showing a *fixed* set of mods as cards or a compact list.

Unlike :class:`~fsmods_gui.widgets.library_table.LibraryTable` (which renders the
whole catalog from a table model and acts as a *picker*), this panel renders an
explicit list of mod filenames — the **contents** of a profile or a collection —
resolved against the catalog, with the same gallery ↔ list toggle as the library.

Each item carries a *kind* (``map`` / ``own`` / ``inherited`` / ``plain``) and an
``excluded`` flag so the profile view keeps its inheritance semantics (inherited
mods shown in blue, excluded ones struck out).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog, CatalogEntry
from .library_table import CARD_H, CARD_PAD, CARD_THUMB, CARD_W

# Item kinds (mirrors the markers the profile editor used on its list rows).
KIND_MAP = "map"
KIND_OWN = "own"
KIND_INHERITED = "inherited"
KIND_PLAIN = "plain"  # a collection's mods — no inheritance semantics

# Custom item-data roles exposed by ModListModel.
ROLE_ENTRY = int(Qt.ItemDataRole.UserRole)
ROLE_FILENAME = int(Qt.ItemDataRole.UserRole) + 1
ROLE_KIND = int(Qt.ItemDataRole.UserRole) + 2
ROLE_EXCLUDED = int(Qt.ItemDataRole.UserRole) + 3
ROLE_SOURCES = int(Qt.ItemDataRole.UserRole) + 4

_INHERITED_FG = QColor(70, 110, 200)
_EXCLUDED_FG = QColor(150, 150, 150)
_MISSING_FG = QColor(220, 80, 80)


@dataclass
class GalleryItem:
    """One row of the panel: a mod filename plus how the target uses it."""

    filename: str
    entry: CatalogEntry | None = None
    kind: str = KIND_PLAIN
    excluded: bool = False
    sources: list[str] = field(default_factory=list)  # collections it's inherited from

    @property
    def title(self) -> str:
        return self.entry.display_title if self.entry else self.filename

    @property
    def missing(self) -> bool:
        return self.entry is None


class ModListModel(QAbstractListModel):
    """A flat list of :class:`GalleryItem`, shared by the grid and list views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[GalleryItem] = []
        self._icons: dict[str, QIcon] = {}

    def set_items(self, items: list[GalleryItem]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self._icons = {}
        self.endResetModel()

    def item_at(self, row: int) -> GalleryItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def _small_icon(self, entry: CatalogEntry | None) -> QIcon | None:
        if entry is None or not entry.icon_cache_path:
            return None
        key = entry.icon_cache_path
        if key not in self._icons:
            pix = QPixmap(key)
            if pix.isNull():
                return None
            self._icons[key] = QIcon(
                pix.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return self._icons[key]

    def _list_label(self, item: GalleryItem) -> str:
        label = item.title
        if item.kind == KIND_MAP:
            label += "  [carte]"
        elif item.kind == KIND_INHERITED:
            srcs = ", ".join(item.sources)
            label += f"  — hérité : {srcs}" if srcs else "  — hérité"
            if item.excluded:
                label += " (exclu)"
        return label

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return self._list_label(item)
        if role == Qt.ItemDataRole.DecorationRole:
            return self._small_icon(item.entry)
        if role == Qt.ItemDataRole.ToolTipRole:
            if item.missing:
                return f"{item.filename} — absent de la bibliothèque"
            if item.kind == KIND_INHERITED and not item.excluded:
                return "Hérité d'une collection — clic droit pour exclure"
            return item.filename
        if role == Qt.ItemDataRole.ForegroundRole:
            if item.missing:
                return _MISSING_FG
            if item.kind == KIND_INHERITED and item.excluded:
                return _EXCLUDED_FG
            if item.kind == KIND_INHERITED:
                return _INHERITED_FG
            return None
        if role == Qt.ItemDataRole.FontRole and item.excluded:
            font = QFont()
            font.setStrikeOut(True)
            return font
        if role == ROLE_ENTRY:
            return item.entry
        if role == ROLE_FILENAME:
            return item.filename
        if role == ROLE_KIND:
            return item.kind
        if role == ROLE_EXCLUDED:
            return item.excluded
        if role == ROLE_SOURCES:
            return item.sources
        return None


class ContentCardDelegate(QStyledItemDelegate):
    """Render a :class:`GalleryItem` as a ModHub-style card with a kind badge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmaps: dict[str, QPixmap] = {}

    def _thumb(self, entry: CatalogEntry | None) -> QPixmap | None:
        if entry is None or not entry.icon_cache_path:
            return None
        path = entry.icon_cache_path
        if path not in self._pixmaps:
            pix = QPixmap(path)
            self._pixmaps[path] = (
                QPixmap()
                if pix.isNull()
                else pix.scaled(
                    CARD_THUMB,
                    CARD_THUMB,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        pix = self._pixmaps[path]
        return pix if not pix.isNull() else None

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        return QSize(CARD_W, CARD_H)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        entry = index.data(ROLE_ENTRY)
        filename = index.data(ROLE_FILENAME) or ""
        kind = index.data(ROLE_KIND) or KIND_PLAIN
        excluded = bool(index.data(ROLE_EXCLUDED))
        title = entry.display_title if isinstance(entry, CatalogEntry) else filename

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            bg = option.palette.highlight().color()
            border = bg.lighter(120)
        elif entry is None:
            bg = QColor("#2a2424")
            border = _MISSING_FG
        elif kind == KIND_INHERITED and not excluded:
            bg = QColor("#22293a") if not hovered else QColor("#2b3550")
            border = _INHERITED_FG
        else:
            bg = QColor("#2a2a2a") if not hovered else QColor("#343434")
            border = QColor("#555") if not hovered else QColor("#7a7a7a")
        if excluded:
            painter.setOpacity(0.55)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(rect, 8, 8)

        thumb_zone = QRect(
            rect.left() + CARD_PAD, rect.top() + CARD_PAD, CARD_THUMB, CARD_THUMB
        )
        pix = self._thumb(entry if isinstance(entry, CatalogEntry) else None)
        if pix is not None:
            px = thumb_zone.left() + (thumb_zone.width() - pix.width()) // 2
            py = thumb_zone.top() + (thumb_zone.height() - pix.height()) // 2
            painter.drawPixmap(px, py, pix)
        else:
            painter.setPen(QPen(QColor("#888")))
            painter.drawText(
                thumb_zone,
                Qt.AlignmentFlag.AlignCenter,
                "⚠" if entry is None else "🧩",
            )

        # Kind badge (top-left corner of the thumbnail)
        badge = ""
        if kind == KIND_MAP:
            badge = "🗺"
        elif kind == KIND_INHERITED:
            badge = "🔗"
        if excluded:
            badge = "🚫"
        if badge:
            badge_font = QFont(option.font)
            badge_font.setPointSizeF(option.font.pointSizeF() + 2)
            painter.setFont(badge_font)
            painter.drawText(
                thumb_zone.adjusted(2, 0, 0, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                badge,
            )

        text_color = (
            option.palette.highlightedText().color()
            if selected
            else (_MISSING_FG if entry is None else QColor("#e6e6e6"))
        )

        title_rect = QRect(
            rect.left() + CARD_PAD,
            thumb_zone.bottom() + 4,
            rect.width() - 2 * CARD_PAD,
            18,
        )
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setStrikeOut(excluded)
        painter.setFont(title_font)
        painter.setPen(QPen(text_color))
        shown = painter.fontMetrics().elidedText(
            title, Qt.TextElideMode.ElideRight, title_rect.width()
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            shown,
        )

        sub_rect = QRect(title_rect.left(), title_rect.bottom() + 1, title_rect.width(), 16)
        sub_font = QFont(option.font)
        sub_font.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))
        painter.setFont(sub_font)
        if entry is None:
            painter.setPen(QPen(_MISSING_FG))
            sub = "absent de la bibliothèque"
        else:
            painter.setPen(QPen(QColor("#9aa0a6") if not selected else text_color))
            sub = entry.category
            if entry.type:
                sub = f"{sub} · {entry.type}"
            if entry.version and entry.version != "0.0.0.0":
                sub = f"{sub} · v{entry.version}"
        sub = painter.fontMetrics().elidedText(
            sub, Qt.TextElideMode.ElideRight, sub_rect.width()
        )
        painter.drawText(
            sub_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            sub,
        )

        painter.restore()


class ModContentPanel(QWidget):
    """Toolbar (count + list/grid toggle) over a single view of mod contents.

    Emits :attr:`remove_requested` with the selected filenames, and
    :attr:`exclude_requested` (filename, excluded) from the context menu so the
    owner can apply profile-specific exclusion rules.
    """

    remove_requested = Signal(list)  # list[str] filenames
    exclude_requested = Signal(str, bool)  # filename, excluded
    selection_changed = Signal(list)  # list[str] filenames
    entry_double_clicked = Signal(str)  # filename
    add_to_profile_requested = Signal(list)  # list[str] filenames → add to a profile
    add_to_collection_requested = Signal(list)  # list[str] filenames → add to a collection

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog: Catalog | None = None
        self.model = ModListModel(self)
        self._card_delegate = ContentCardDelegate(self)
        self._list_delegate = QStyledItemDelegate(self)
        self._view_mode = "grid"

        self.count_label = QLabel("0 mod", self)
        self.list_btn = QToolButton(self)
        self.list_btn.setText("☰")
        self.list_btn.setToolTip("Vue liste")
        self.list_btn.setCheckable(True)
        self.list_btn.clicked.connect(lambda: self.set_view_mode("list"))
        self.grid_btn = QToolButton(self)
        self.grid_btn.setText("▦")
        self.grid_btn.setToolTip("Vue galerie (grandes vignettes)")
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.clicked.connect(lambda: self.set_view_mode("grid"))

        self.view = QListView(self)
        self.view.setModel(self.model)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(True)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.selectionModel().selectionChanged.connect(self._on_selection)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(self.count_label)
        top.addStretch(1)
        top.addWidget(self.list_btn)
        top.addWidget(self.grid_btn)
        layout.addLayout(top)
        layout.addWidget(self.view, 1)

        self.set_view_mode("grid")

    # ------------------------------------------------------------- view mode

    def set_view_mode(self, mode: str) -> None:
        if mode not in ("list", "grid"):
            return
        self._view_mode = mode
        is_grid = mode == "grid"
        self.grid_btn.setChecked(is_grid)
        self.list_btn.setChecked(not is_grid)
        if is_grid:
            self.view.setItemDelegate(self._card_delegate)
            self.view.setViewMode(QListView.ViewMode.IconMode)
            self.view.setFlow(QListView.Flow.LeftToRight)
            self.view.setWrapping(True)
            self.view.setMovement(QListView.Movement.Static)
            self.view.setSpacing(6)
        else:
            self.view.setItemDelegate(self._list_delegate)
            self.view.setViewMode(QListView.ViewMode.ListMode)
            self.view.setFlow(QListView.Flow.TopToBottom)
            self.view.setWrapping(False)
            self.view.setMovement(QListView.Movement.Static)
            self.view.setSpacing(2)

    # ----------------------------------------------------------------- data

    def set_catalog(self, catalog: Catalog | None) -> None:
        self._catalog = catalog

    def set_items(self, items: list[GalleryItem]) -> None:
        self.model.set_items(items)
        n = sum(1 for it in items if not it.excluded)
        self.count_label.setText(f"{n} mod{'s' if n > 1 else ''}")

    def selected_filenames(self) -> list[str]:
        sel = self.view.selectionModel()
        if sel is None:
            return []
        out: list[str] = []
        for idx in sel.selectedIndexes():
            item = self.model.item_at(idx.row())
            if item is not None:
                out.append(item.filename)
        return out

    # --------------------------------------------------------------- events

    def _on_selection(self) -> None:
        self.selection_changed.emit(self.selected_filenames())

    def _on_double_click(self, index: QModelIndex) -> None:
        item = self.model.item_at(index.row())
        if item is not None:
            self.entry_double_clicked.emit(item.filename)

    def _on_context_menu(self, pos) -> None:
        idx = self.view.indexAt(pos)
        menu = QMenu(self)
        if idx.isValid():
            # Right-clicking an unselected item acts on it alone.
            sel = self.view.selectionModel()
            if sel is not None and not sel.isSelected(idx):
                self.view.clearSelection()
                self.view.setCurrentIndex(idx)
            item = self.model.item_at(idx.row())
            if item is not None:
                if item.kind == KIND_INHERITED:
                    if item.excluded:
                        act = menu.addAction("↩ Réintégrer dans ce profil")
                        act.triggered.connect(
                            lambda: self.exclude_requested.emit(item.filename, False)
                        )
                    else:
                        act = menu.addAction("🚫 Exclure de ce profil")
                        act.triggered.connect(
                            lambda: self.exclude_requested.emit(item.filename, True)
                        )
                else:
                    label = (
                        "← Retirer la carte"
                        if item.kind == KIND_MAP
                        else "← Retirer"
                    )
                    act = menu.addAction(label)
                    act.triggered.connect(self._emit_remove)
                # Push the selected mod(s) into another profile / a collection.
                menu.addSeparator()
                add_prof_act = menu.addAction("➕ Ajouter à un profil…")
                add_prof_act.triggered.connect(self._emit_add_to_profile)
                add_coll_act = menu.addAction("🗂️ Ajouter à une collection…")
                add_coll_act.triggered.connect(self._emit_add_to_collection)
        if not menu.isEmpty():
            menu.exec_(self.view.viewport().mapToGlobal(pos))

    def _emit_remove(self) -> None:
        names = self.selected_filenames()
        if names:
            self.remove_requested.emit(names)

    def _emit_add_to_profile(self) -> None:
        names = self.selected_filenames()
        if names:
            self.add_to_profile_requested.emit(names)

    def _emit_add_to_collection(self) -> None:
        names = self.selected_filenames()
        if names:
            self.add_to_collection_requested.emit(names)
