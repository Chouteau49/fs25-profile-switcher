"""Embeddable panel: audit a savegame and propose profile clean-up / completion."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog
from ..profiles.profile import Profile
from ..profiles.savegame_audit import (
    STATUS_ABSENT,
    STATUS_LABELS_FR,
    STATUS_LOADED,
    STATUS_USED,
    AuditReport,
    audit_profile,
    list_savegames,
    parse_savegame,
)

_STATUS_BG = {
    STATUS_USED: QColor(214, 245, 214),
    STATUS_LOADED: QColor(255, 240, 196),
    STATUS_ABSENT: QColor(255, 205, 205),
}
_STATUS_FG = {
    STATUS_USED: QColor(0, 90, 0),
    STATUS_LOADED: QColor(120, 80, 0),
    STATUS_ABSENT: QColor(120, 0, 0),
}


class SavegameAuditPanel(QWidget):
    """Pick a savegame, see how each profile mod is used, act on the profile."""

    # Emitted when the user applies changes: (mods_to_remove, mods_to_add).
    apply_requested = Signal(list, list)
    # Emitted to delete the given filenames from the library (disk + configs).
    delete_requested = Signal(list)

    def __init__(
        self,
        profile: Profile,
        catalog: Catalog | None,
        user_dir: Path,
        parent: QWidget | None = None,
        collection_mods: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._catalog = catalog
        self._collection_mods = collection_mods or {}

        self._savegames = list_savegames(user_dir)
        self._report: AuditReport | None = None

        intro = QLabel(
            f"Profil <b>« {profile.name} »</b> — comparé au contenu réellement "
            "utilisé par une sauvegarde. <b>Aucun fichier n'est supprimé</b> : "
            "seules des modifications du profil sont proposées."
        )
        intro.setWordWrap(True)

        self.savegame_combo = QComboBox(self)
        if self._savegames:
            for sg in self._savegames:
                info = parse_savegame(sg)
                self.savegame_combo.addItem(info.label, userData=str(sg))
        self.savegame_combo.currentIndexChanged.connect(self._reload)

        sg_row = QHBoxLayout()
        sg_row.addWidget(QLabel("Sauvegarde :", self))
        sg_row.addWidget(self.savegame_combo, 1)

        self.summary = QLabel("", self)
        self.summary.setWordWrap(True)

        # ---- profile mods table
        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Retirer", "Statut", "Mod", "Note"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        # Bulk actions on the current multi-selection of profile mods.
        check_btn = QPushButton("☑ Cocher « Retirer »", self)
        check_btn.clicked.connect(lambda: self._set_remove_for_selection(True))
        uncheck_btn = QPushButton("☐ Décocher", self)
        uncheck_btn.clicked.connect(lambda: self._set_remove_for_selection(False))
        self.delete_btn = QPushButton("🗑 Supprimer de la bibliothèque…", self)
        self.delete_btn.setToolTip(
            "Effacer définitivement le(s) .zip sélectionné(s) du disque "
            "(retirés aussi de tous les profils et collections)."
        )
        self.delete_btn.clicked.connect(self._emit_delete)
        table_actions = QHBoxLayout()
        table_actions.addWidget(check_btn)
        table_actions.addWidget(uncheck_btn)
        table_actions.addStretch(1)
        table_actions.addWidget(self.delete_btn)

        # ---- missing-from-profile table
        self.missing_label = QLabel("", self)
        self.missing_table = QTableWidget(self)
        self.missing_table.setColumnCount(3)
        self.missing_table.setHorizontalHeaderLabels(["Ajouter", "Mod (utilisé par le save)", "Disponibilité"])
        self.missing_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.missing_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.missing_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.missing_table.verticalHeader().setVisible(False)
        self.missing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        add_check_btn = QPushButton("☑ Cocher « Ajouter »", self)
        add_check_btn.clicked.connect(lambda: self._set_add_for_selection(True))
        add_uncheck_btn = QPushButton("☐ Décocher", self)
        add_uncheck_btn.clicked.connect(lambda: self._set_add_for_selection(False))
        missing_actions = QHBoxLayout()
        missing_actions.addWidget(add_check_btn)
        missing_actions.addWidget(add_uncheck_btn)
        missing_actions.addStretch(1)

        self.apply_btn = QPushButton("✔ Appliquer au profil", self)
        self.apply_btn.clicked.connect(self._emit_apply)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.apply_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(intro)
        layout.addLayout(sg_row)
        layout.addWidget(self.summary)
        if not self._savegames:
            layout.addWidget(QLabel("Aucune sauvegarde trouvée dans le dossier du jeu."))
        layout.addWidget(QLabel("<b>Mods du profil</b>", self))
        layout.addWidget(self.table, 3)
        layout.addLayout(table_actions)
        layout.addWidget(self.missing_label)
        layout.addWidget(self.missing_table, 2)
        layout.addLayout(missing_actions)
        layout.addLayout(btn_row)

        if self._savegames:
            self._reload()

    def _emit_apply(self) -> None:
        self.apply_requested.emit(self.mods_to_remove(), self.mods_to_add())

    # --------------------------------------------------- multi-selection ops

    @staticmethod
    def _set_check_for_selected_rows(table: QTableWidget, checked: bool) -> None:
        """Set the column-0 check box for every (checkable) selected row."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in table.selectionModel().selectedRows():
            item = table.item(index.row(), 0)
            if item is not None and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                item.setCheckState(state)

    def _set_remove_for_selection(self, checked: bool) -> None:
        self._set_check_for_selected_rows(self.table, checked)

    def _set_add_for_selection(self, checked: bool) -> None:
        self._set_check_for_selected_rows(self.missing_table, checked)

    def _selected_profile_filenames(self) -> list[str]:
        """Filenames of the rows highlighted in the profile-mods table."""
        out: list[str] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            fname = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if fname:
                out.append(fname)
        return out

    def _emit_delete(self) -> None:
        names = self._selected_profile_filenames()
        if names:
            self.delete_requested.emit(names)

    # ------------------------------------------------------------------ render

    def _reload(self) -> None:
        path = self.savegame_combo.currentData()
        if not path:
            return
        info = parse_savegame(Path(path))
        self._report = audit_profile(
            self._profile, info, self._catalog, self._collection_mods
        )
        self._populate_profile_table()
        self._populate_missing_table()
        self._update_summary()

    def _update_summary(self) -> None:
        if self._report is None:
            return
        c = self._report.counts()
        self.summary.setText(
            f"🟢 {c[STATUS_USED]} utilisé(s)  ·  "
            f"🟡 {c[STATUS_LOADED]} chargé(s) sans objet  ·  "
            f"🔴 {c[STATUS_ABSENT]} absent(s) de la sauvegarde."
        )

    def _populate_profile_table(self) -> None:
        rows = self._report.rows if self._report else []
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            bg = _STATUS_BG.get(row.status)
            fg = _STATUS_FG.get(row.status)

            chk = QTableWidgetItem()
            if row.is_map:
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(Qt.CheckState.Unchecked)
                chk.setFlags(Qt.ItemFlag.NoItemFlags)  # map: never removable
            else:
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(
                    Qt.CheckState.Checked if row.suggested_remove else Qt.CheckState.Unchecked
                )
            chk.setData(Qt.ItemDataRole.UserRole, row.filename)

            status_item = QTableWidgetItem(STATUS_LABELS_FR.get(row.status, row.status))
            mod_item = QTableWidgetItem(f"{row.title}  ({row.filename})")
            note = ""
            if row.is_map:
                note = "Carte — requise"
            elif row.status == STATUS_LOADED and row.is_script:
                note = "Script — à garder probablement"
            elif row.status == STATUS_LOADED:
                note = "Aucun objet placé — à examiner"
            elif row.status == STATUS_ABSENT:
                note = "Pas chargé dans cette partie"
            note_item = QTableWidgetItem(note)

            for col, item in enumerate((chk, status_item, mod_item, note_item)):
                if bg is not None and col != 0:
                    item.setBackground(QBrush(bg))
                if fg is not None and col != 0:
                    item.setForeground(QBrush(fg))
                self.table.setItem(i, col, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _populate_missing_table(self) -> None:
        missing = self._report.missing_in_profile if self._report else []
        self.missing_label.setText(
            f"<b>Utilisés par la sauvegarde mais absents du profil</b> ({len(missing)})"
        )
        self.missing_table.setRowCount(len(missing))
        for i, m in enumerate(missing):
            chk = QTableWidgetItem()
            if m.in_library:
                chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk.setCheckState(Qt.CheckState.Unchecked)
                chk.setData(Qt.ItemDataRole.UserRole, m.filename)
            else:
                chk.setFlags(Qt.ItemFlag.NoItemFlags)
            label = f"{m.title}  ({m.mod_id})"
            avail = "Dans la bibliothèque" if m.in_library else "À télécharger (absent de la bibliothèque)"
            self.missing_table.setItem(i, 0, chk)
            self.missing_table.setItem(i, 1, QTableWidgetItem(label))
            self.missing_table.setItem(i, 2, QTableWidgetItem(avail))
        self.missing_table.resizeColumnsToContents()
        self.missing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    # ------------------------------------------------------------------ result

    def mods_to_remove(self) -> list[str]:
        out: list[str] = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                fname = item.data(Qt.ItemDataRole.UserRole)
                if fname:
                    out.append(fname)
        return out

    def mods_to_add(self) -> list[str]:
        out: list[str] = []
        for i in range(self.missing_table.rowCount()):
            item = self.missing_table.item(i, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                fname = item.data(Qt.ItemDataRole.UserRole)
                if fname:
                    out.append(fname)
        return out
