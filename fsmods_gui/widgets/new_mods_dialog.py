"""Dialog to triage freshly downloaded mods into the library.

Left  : a thumbnail grid of mods found in the source folders (Downloads + the
        ``new_mods`` inbox) that aren't in the library yet. Each card has a
        check box — *checked = will be imported*.
Right : two checkable lists (profiles + collections). Ticking a target classifies
        every *selected* card into it (and auto-checks those cards for import).

On accept, :meth:`result_plans` returns one :class:`ImportPlan` per checked card
so the caller can move the zips into the library and wire up the assignments.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..profiles.inbox import (
    STATUS_DUPLICATE,
    STATUS_NEW,
    STATUS_UPDATE,
    PendingMod,
)
from ..state import AppState, ImportPlan

_ROLE_PENDING = int(Qt.ItemDataRole.UserRole)
_ROLE_SLUG = int(Qt.ItemDataRole.UserRole) + 1
_THUMB = 96


class NewModsDialog(QDialog):
    """Triage + classify downloaded mods before importing them."""

    rescan_requested = Signal()

    def __init__(
        self,
        pending: list[PendingMod],
        state: AppState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("📥 Nouveaux mods")
        self.resize(1080, 680)

        # filename -> {"p": set[slug], "c": set[slug]}
        self._assign: dict[str, dict[str, set[str]]] = {}
        self._suppress = False

        # ---- left: pending mods grid
        self.grid = QListWidget(self)
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setIconSize(QSize(_THUMB, _THUMB))
        self.grid.setGridSize(QSize(_THUMB + 40, _THUMB + 58))
        self.grid.setSpacing(8)
        self.grid.setWordWrap(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setUniformItemSizes(True)
        self.grid.itemChanged.connect(self._on_card_changed)
        self.grid.itemSelectionChanged.connect(self._refresh_targets)

        left = QWidget(self)
        left_l = QVBoxLayout(left)
        self.count_label = QLabel(self)
        left_l.addWidget(self.count_label)
        left_l.addWidget(self.grid, 1)
        sel_row = QHBoxLayout()
        all_btn = QPushButton("Tout sélectionner", self)
        all_btn.clicked.connect(self.grid.selectAll)
        none_btn = QPushButton("Tout désélectionner", self)
        none_btn.clicked.connect(self.grid.clearSelection)
        check_btn = QPushButton("☑ Cocher la sélection", self)
        check_btn.clicked.connect(lambda: self._set_checked_for_selected(True))
        uncheck_btn = QPushButton("☐ Décocher la sélection", self)
        uncheck_btn.clicked.connect(lambda: self._set_checked_for_selected(False))
        for b in (all_btn, none_btn, check_btn, uncheck_btn):
            sel_row.addWidget(b)
        sel_row.addStretch(1)
        left_l.addLayout(sel_row)

        # ---- right: classify panel
        self.target_header = QLabel(self)
        self.target_header.setWordWrap(True)
        self.profiles_list = QListWidget(self)
        self.profiles_list.itemChanged.connect(
            lambda it: self._on_target_changed(it, "p")
        )
        self.collections_list = QListWidget(self)
        self.collections_list.itemChanged.connect(
            lambda it: self._on_target_changed(it, "c")
        )

        prof_box = QGroupBox("Profils", self)
        prof_l = QVBoxLayout(prof_box)
        prof_l.addWidget(self.profiles_list)
        col_box = QGroupBox("Collections", self)
        col_l = QVBoxLayout(col_box)
        col_l.addWidget(self.collections_list)

        right = QWidget(self)
        right_l = QVBoxLayout(right)
        right_l.addWidget(self.target_header)
        right_l.addWidget(prof_box, 1)
        right_l.addWidget(col_box, 1)
        hint = QLabel(
            "Astuce : sélectionne un ou plusieurs mods à gauche, puis coche "
            "les profils / collections où les classer. Cocher une cible marque "
            "aussi le mod « à importer ». Les mods cochés sans cible sont juste "
            "ajoutés à la bibliothèque.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("QLabel { color: #888; }")
        right_l.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # ---- buttons
        buttons = QDialogButtonBox(self)
        rescan_btn = buttons.addButton(
            "🔄 Rescanner", QDialogButtonBox.ButtonRole.ResetRole
        )
        rescan_btn.clicked.connect(self.rescan_requested.emit)
        self.import_btn = buttons.addButton(
            "📥 Importer les mods cochés", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.import_btn.clicked.connect(self._on_accept)
        buttons.addButton("Fermer", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(buttons)

        self._populate_targets()
        self.set_pending(pending)

    # --------------------------------------------------------------- populate

    def set_pending(self, pending: list[PendingMod]) -> None:
        self._suppress = True
        self.grid.clear()
        self._assign.clear()
        for pm in pending:
            entry = pm.entry
            # New mods and updates are worth importing → checked by default.
            # Already-in-library duplicates start unchecked (the user may just
            # want to clean up the download or classify them).
            default_checked = pm.status != STATUS_DUPLICATE
            item = QListWidgetItem(self._card_text(pm, checked=default_checked))
            item.setData(_ROLE_PENDING, pm)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if default_checked else Qt.CheckState.Unchecked
            )
            icon = self._thumb_icon(entry.icon_cache_path if entry else None)
            if icon is not None:
                item.setIcon(icon)
            if pm.status == STATUS_DUPLICATE:
                item.setForeground(QBrush(QColor("#999")))
            badge = "🗺 " if (entry and entry.is_map) else ""
            cat = entry.category if entry else ""
            ver = (
                f" · v{entry.version}"
                if entry and entry.version and entry.version != "0.0.0.0"
                else ""
            )
            item.setToolTip(
                f"{badge}{pm.filename}\n{cat}{ver}\n"
                f"Statut : {pm.status_label}\nSource : {pm.source_label}"
            )
            self._assign[pm.filename] = {"p": set(), "c": set()}
            self.grid.addItem(item)
        self._suppress = False
        self._update_count()
        self._refresh_targets()

    def _populate_targets(self) -> None:
        self._suppress = True
        self.profiles_list.clear()
        for prof in self.state.profiles:
            it = QListWidgetItem(prof.name)
            it.setData(_ROLE_SLUG, prof.slug)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.profiles_list.addItem(it)
        self.collections_list.clear()
        for col in self.state.collections:
            it = QListWidgetItem(f"{col.name}  ({len(col.mods)})")
            it.setData(_ROLE_SLUG, col.slug)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.collections_list.addItem(it)
        self._suppress = False

    # ----------------------------------------------------------------- render

    @staticmethod
    def _thumb_icon(icon_path: str | None) -> QIcon | None:
        if not icon_path:
            return None
        pix = QPixmap(icon_path)
        if pix.isNull():
            return None
        return QIcon(
            pix.scaled(
                _THUMB,
                _THUMB,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    _STATUS_TAG = {
        STATUS_UPDATE: "⬆ màj",
        STATUS_DUPLICATE: "≡ déjà en biblio",
    }

    def _card_text(self, pm: PendingMod, checked: bool) -> str:
        title = pm.entry.display_title if pm.entry else pm.filename
        n = 0
        a = self._assign.get(pm.filename)
        if a:
            n = len(a["p"]) + len(a["c"])
        mark = "✓ " if checked else ""
        tag = self._STATUS_TAG.get(pm.status, "")
        bits = [b for b in (tag, f"{n} cible(s)" if n else "") if b]
        suffix = "  ·  " + "  ·  ".join(bits) if bits else ""
        return f"{mark}{title}{suffix}"

    def _update_count(self) -> None:
        total = self.grid.count()
        checked = 0
        counts = {STATUS_NEW: 0, STATUS_UPDATE: 0, STATUS_DUPLICATE: 0}
        for i in range(total):
            item = self.grid.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked += 1
            pm = item.data(_ROLE_PENDING)
            counts[pm.status] = counts.get(pm.status, 0) + 1
        if total == 0:
            self.count_label.setText(
                "Aucun mod trouvé dans les dossiers source (Téléchargements + new_mods)."
            )
        else:
            self.count_label.setText(
                f"{total} mod(s) — {counts[STATUS_NEW]} nouveau(x), "
                f"{counts[STATUS_UPDATE]} màj, {counts[STATUS_DUPLICATE]} déjà en "
                f"bibliothèque — {checked} coché(s) à importer."
            )
        self.import_btn.setEnabled(checked > 0)

    # ------------------------------------------------------------- selection

    def _selected_items(self) -> list[QListWidgetItem]:
        return list(self.grid.selectedItems())

    def _target_items(self) -> list[QListWidgetItem]:
        """Cards the right-hand check boxes act on.

        The current left selection, or — when nothing is selected — *all* cards,
        so ticking a profile/collection always does something obvious.
        """
        items = self._selected_items()
        if items:
            return items
        return [self.grid.item(i) for i in range(self.grid.count())]

    def _set_checked_for_selected(self, checked: bool) -> None:
        items = self._selected_items() or [
            self.grid.item(i) for i in range(self.grid.count())
        ]
        self._suppress = True
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for it in items:
            it.setCheckState(state)
            pm = it.data(_ROLE_PENDING)
            it.setText(self._card_text(pm, checked))
        self._suppress = False
        self._update_count()

    def _refresh_targets(self) -> None:
        """Reflect the assignments of the target cards in the right-hand lists."""
        selected = self._selected_items()
        items = self._target_items()
        # Lists stay usable as long as there is at least one mod to classify.
        enabled = bool(items)
        self.profiles_list.setEnabled(enabled)
        self.collections_list.setEnabled(enabled)
        if not items:
            self.target_header.setText("Aucun nouveau mod à classer.")
        elif selected:
            self.target_header.setText(
                f"<b>Classer {len(selected)} mod(s) sélectionné(s)</b>"
            )
        else:
            self.target_header.setText(
                "<b>Aucune sélection</b> — les cases ci-dessous s'appliquent à "
                f"<b>tous</b> les {len(items)} nouveaux mods."
            )
        filenames = [it.data(_ROLE_PENDING).filename for it in items]

        self._suppress = True
        for lst, key in ((self.profiles_list, "p"), (self.collections_list, "c")):
            for i in range(lst.count()):
                target = lst.item(i)
                slug = target.data(_ROLE_SLUG)
                if not filenames:
                    target.setCheckState(Qt.CheckState.Unchecked)
                    continue
                has = [slug in self._assign[f][key] for f in filenames]
                if all(has):
                    target.setCheckState(Qt.CheckState.Checked)
                elif any(has):
                    target.setCheckState(Qt.CheckState.PartiallyChecked)
                else:
                    target.setCheckState(Qt.CheckState.Unchecked)
        self._suppress = False

    # --------------------------------------------------------------- events

    def _on_card_changed(self, item: QListWidgetItem) -> None:
        if self._suppress:
            return
        pm = item.data(_ROLE_PENDING)
        checked = item.checkState() == Qt.CheckState.Checked
        self._suppress = True
        item.setText(self._card_text(pm, checked))
        self._suppress = False
        self._update_count()

    def _on_target_changed(self, item: QListWidgetItem, key: str) -> None:
        if self._suppress:
            return
        slug = item.data(_ROLE_SLUG)
        add = item.checkState() != Qt.CheckState.Unchecked
        # A user click never lands on PartiallyChecked, but normalize anyway.
        if item.checkState() == Qt.CheckState.PartiallyChecked:
            self._suppress = True
            item.setCheckState(Qt.CheckState.Checked)
            self._suppress = False
            add = True
        for grid_item in self._target_items():
            pm = grid_item.data(_ROLE_PENDING)
            bucket = self._assign[pm.filename][key]
            if add:
                bucket.add(slug)
                # Classifying a mod implies importing it.
                if grid_item.checkState() != Qt.CheckState.Checked:
                    self._suppress = True
                    grid_item.setCheckState(Qt.CheckState.Checked)
                    self._suppress = False
            else:
                bucket.discard(slug)
            self._suppress = True
            grid_item.setText(
                self._card_text(
                    pm, grid_item.checkState() == Qt.CheckState.Checked
                )
            )
            self._suppress = False
        self._update_count()

    def _on_accept(self) -> None:
        if not self.result_plans():
            return
        self.accept()

    # ----------------------------------------------------------------- result

    def result_plans(self) -> list[ImportPlan]:
        """One plan per checked card (assignments included)."""
        plans: list[ImportPlan] = []
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            pm = item.data(_ROLE_PENDING)
            a = self._assign.get(pm.filename, {"p": set(), "c": set()})
            plans.append(
                ImportPlan(
                    pending=pm,
                    profile_slugs=sorted(a["p"]),
                    collection_slugs=sorted(a["c"]),
                )
            )
        return plans
