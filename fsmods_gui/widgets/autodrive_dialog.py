"""Dialog: install a downloaded AutoDrive route pack into a savegame.

Left  : the AutoDrive route packs found in the source folders (Downloads + the
        ``new_mods`` inbox) — zips holding ``AutoDrive_config.xml`` /
        ``AutoDriveUsersData.xml`` rather than a ``modDesc.xml``.
Right : a combo to pick the target ``savegameN`` (name + map), and a note on
        what will be written / backed up.

On install, existing AutoDrive XML in the savegame is renamed to ``.bak`` and
the pack's files are dropped in — the automated equivalent of the manual
"delete the old XML, unzip, copy both files in" procedure.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..profiles.autodrive import AutoDrivePack, scan_packs
from ..profiles.savegame_audit import list_savegames, parse_savegame

_ROLE_PACK = int(Qt.ItemDataRole.UserRole)


class AutoDriveDialog(QDialog):
    """Pick a route pack + a savegame, then install the AutoDrive XML."""

    rescan_requested = Signal()

    def __init__(
        self,
        source_dirs: list[Path],
        user_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._user_dir = user_dir
        self.setWindowTitle("🛣 Routes AutoDrive")
        self.resize(820, 520)

        intro = QLabel(
            "Installe un <b>pack de routes AutoDrive</b> téléchargé (un zip "
            "contenant <code>AutoDrive_config.xml</code> / "
            "<code>AutoDriveUsersData.xml</code>) dans une sauvegarde. Les XML "
            "déjà présents sont <b>sauvegardés en .bak</b> avant d'être remplacés.",
            self,
        )
        intro.setWordWrap(True)

        # ---- left: detected packs
        self.packs_list = QListWidget(self)
        self.packs_list.itemSelectionChanged.connect(self._refresh_detail)
        packs_box = QGroupBox("Packs de routes détectés", self)
        packs_l = QVBoxLayout(packs_box)
        self.packs_count = QLabel("", self)
        packs_l.addWidget(self.packs_count)
        packs_l.addWidget(self.packs_list, 1)

        # ---- right: target savegame + detail
        self.savegame_combo = QComboBox(self)
        self._savegames = list_savegames(user_dir)
        for sg in self._savegames:
            info = parse_savegame(sg)
            self.savegame_combo.addItem(info.label, userData=str(sg))
        self.savegame_combo.currentIndexChanged.connect(self._refresh_detail)

        self.backup_check = QCheckBox(
            "Sauvegarder les XML existants en .bak (recommandé)", self
        )
        self.backup_check.setChecked(True)

        self.detail = QLabel("", self)
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        target_box = QGroupBox("Sauvegarde cible", self)
        target_l = QVBoxLayout(target_box)
        sg_row = QHBoxLayout()
        sg_row.addWidget(QLabel("Sauvegarde :", self))
        sg_row.addWidget(self.savegame_combo, 1)
        target_l.addLayout(sg_row)
        target_l.addWidget(self.backup_check)
        target_l.addWidget(self.detail, 1)

        cols = QHBoxLayout()
        cols.addWidget(packs_box, 1)
        cols.addWidget(target_box, 1)

        # ---- buttons
        buttons = QDialogButtonBox(self)
        rescan_btn = buttons.addButton(
            "🔄 Rescanner", QDialogButtonBox.ButtonRole.ResetRole
        )
        rescan_btn.clicked.connect(self.rescan_requested.emit)
        self.install_btn = buttons.addButton(
            "🛣 Installer dans la sauvegarde", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.install_btn.clicked.connect(self.accept)
        buttons.addButton("Fermer", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(cols, 1)
        layout.addWidget(buttons)

        self.set_packs(scan_packs(source_dirs))

    # ----------------------------------------------------------------- populate

    def set_packs(self, packs: list[AutoDrivePack]) -> None:
        self.packs_list.clear()
        for pack in packs:
            files = " + ".join(pack.provided)
            item = QListWidgetItem(f"{pack.filename}\n   {files}")
            item.setData(_ROLE_PACK, pack)
            item.setToolTip(f"Source : {pack.source_label}\nContient : {files}")
            self.packs_list.addItem(item)
        if packs:
            self.packs_count.setText(f"{len(packs)} pack(s) trouvé(s).")
            self.packs_list.setCurrentRow(0)
        else:
            self.packs_count.setText(
                "Aucun pack AutoDrive trouvé dans les dossiers source "
                "(Téléchargements + new_mods)."
            )
        self._refresh_detail()

    # ------------------------------------------------------------------- detail

    def selected_pack(self) -> AutoDrivePack | None:
        items = self.packs_list.selectedItems()
        return items[0].data(_ROLE_PACK) if items else None

    def selected_savegame(self) -> Path | None:
        data = self.savegame_combo.currentData()
        return Path(data) if data else None

    def backup_enabled(self) -> bool:
        return self.backup_check.isChecked()

    def _refresh_detail(self) -> None:
        pack = self.selected_pack()
        sg = self.selected_savegame()
        ready = pack is not None and sg is not None
        self.install_btn.setEnabled(ready)
        if pack is None:
            self.detail.setText("Sélectionne un pack de routes à gauche.")
            return
        if not self._savegames:
            self.detail.setText(
                "Aucune sauvegarde trouvée dans "
                f"<code>{self._user_dir}</code>."
            )
            return
        lines = [f"<b>Fichiers à installer :</b> {', '.join(pack.provided)}"]
        if sg is not None:
            existing = [f for f in pack.provided if (sg / f).exists()]
            if existing:
                action = "sauvegardés en .bak" if self.backup_enabled() else "supprimés"
                lines.append(
                    f"⚠ Déjà présents (seront {action}) : {', '.join(existing)}"
                )
            else:
                lines.append("Aucun fichier AutoDrive existant dans cette sauvegarde.")
        self.detail.setText("<br>".join(lines))
