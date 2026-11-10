"""Choisir une partie téléchargée à importer, et vérifier ce qui sera créé."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..profiles.savegame_import import ProfilePlan, SaveArchive, read_save_archive

PlanFor = Callable[[SaveArchive], ProfilePlan]


class SaveImportDialog(QDialog):
    """Pick a downloaded save, check its map and mods, name the new profile."""

    def __init__(
        self,
        archives: list[SaveArchive],
        plan_for: PlanFor,
        existing_names: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importer une partie")
        self._plan_for = plan_for
        self._existing = existing_names
        self._archives: list[SaveArchive] = []
        self.chosen: SaveArchive | None = None

        intro = QLabel(
            "Une partie téléchargée (zip de sauvegarde FS25) devient une nouvelle partie du jeu "
            "et un profil avec sa carte et ses mods. Rien d'existant n'est écrasé."
        )
        intro.setWordWrap(True)
        self.list = QListWidget(self)
        self.list.currentRowChanged.connect(self._on_row)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept_if_ready())
        browse = QPushButton("Parcourir…", self)
        browse.setToolTip("Choisir un zip de partie ailleurs sur le disque.")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(browse)

        self.name = QLineEdit(self)
        self.name.setPlaceholderText("Nom du profil")
        self.name.textChanged.connect(lambda _text: self._refresh())
        self.summary = QLabel("", self)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Importer")
        buttons.accepted.connect(self._accept_if_ready)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        if archives:
            layout.addWidget(QLabel("Parties trouvées dans Téléchargements :", self))
        else:
            layout.addWidget(QLabel("Aucune partie trouvée dans Téléchargements.", self))
        layout.addWidget(self.list, 1)
        layout.addLayout(row)
        layout.addWidget(QLabel("Nom du profil :", self))
        layout.addWidget(self.name)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)
        self.resize(560, 520)

        for archive in archives:
            self._add(archive)
        if archives:
            self.list.setCurrentRow(0)
        else:
            self._refresh()

    def _add(self, archive: SaveArchive) -> None:
        self._archives.append(archive)
        date = f" · {archive.save_date}" if archive.save_date else ""
        title = archive.map_title or archive.map_id
        QListWidgetItem(
            f"{archive.name or archive.path.stem}  —  {title}{date}  ({archive.path.name})",
            self.list,
        )

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une partie", "", "Zip (*.zip)")
        if not path:
            return
        archive = read_save_archive(Path(path))
        if archive is None:
            self.summary.setText("Ce fichier n'est pas une partie FS25 lisible.")
            return
        self._add(archive)
        self.list.setCurrentRow(len(self._archives) - 1)

    def _on_row(self, row: int) -> None:
        if 0 <= row < len(self._archives):
            archive = self._archives[row]
            self.name.setText(archive.name or archive.path.stem)
        self._refresh()

    def _current(self) -> SaveArchive | None:
        row = self.list.currentRow()
        return self._archives[row] if 0 <= row < len(self._archives) else None

    def _refresh(self) -> None:
        archive = self._current()
        if archive is None:
            self.summary.setText("")
            self.ok_button.setEnabled(False)
            return
        plan = self._plan_for(archive)
        lines = []
        if plan.map_mod:
            lines.append(f"Carte : {plan.map_mod}")
        elif plan.official_map:
            lines.append(f"Carte officielle : {plan.official_map}")
        else:
            lines.append(f"Carte absente de la bibliothèque : {archive.map_id}")
        lines.append(f"Mods trouvés dans la bibliothèque : {len(plan.mods)}")
        if plan.missing:
            shown = ", ".join(plan.missing[:8])
            more = f" (+{len(plan.missing) - 8})" if len(plan.missing) > 8 else ""
            lines.append(f"À télécharger, absents : {shown}{more}")
        self.summary.setText("\n".join(lines))
        self.ok_button.setEnabled(bool(self.name.text().strip()))

    def _accept_if_ready(self) -> None:
        archive = self._current()
        if archive is None or not self.name.text().strip():
            return
        self.chosen = archive
        self.accept()

    def selected_name(self) -> str:
        return self.name.text().strip()
