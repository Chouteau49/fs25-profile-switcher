"""Post-session reconciliation dialog.

When FS25 exits, we compute :class:`SyncDiff` and show this dialog so the user
can decide how to handle each *added* (new download in-game) and *removed*
(deleted from the game folder) mod.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..profiles.sync_back import SyncDiff

ADD_IGNORE = "ignore"
ADD_LIB_AND_PROFILE = "library+profile"
ADD_LIB_ONLY = "library"

UPDATE_IMPORT = "import"
UPDATE_IGNORE = "ignore"

REMOVE_KEEP = "keep"
REMOVE_DROP = "drop"


class SyncDialog(QDialog):
    """Render a :class:`SyncDiff` and let the user pick actions per row."""

    def __init__(
        self,
        diff: SyncDiff,
        profile_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Synchronisation de fin de partie")
        self.setMinimumSize(640, 480)
        self._added_choices: dict[str, QComboBox] = {}
        self._updated_choices: dict[str, QComboBox] = {}
        self._removed_choices: dict[str, QComboBox] = {}

        intro = QLabel(
            f"FS25 vient d'être fermé. Voici les différences entre le dossier "
            f"<b>mods</b> du jeu et le profil <b>{profile_name}</b>.<br/>"
            f"Choisis ce qu'on fait pour chaque entrée."
        )
        intro.setWordWrap(True)

        scroll_content = QWidget()
        body = QVBoxLayout(scroll_content)
        body.addWidget(self._added_group(diff))
        body.addWidget(self._updated_group(diff))
        body.addWidget(self._removed_group(diff))
        body.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

    def _added_group(self, diff: SyncDiff) -> QGroupBox:
        box = QGroupBox(
            f"Nouveaux mods détectés dans le jeu ({len(diff.added_in_game)})", self
        )
        layout = QVBoxLayout(box)
        if not diff.added_in_game:
            layout.addWidget(QLabel("Aucun nouveau mod."))
            return box
        for filename in diff.added_in_game:
            row = QHBoxLayout()
            row.addWidget(QLabel(filename), 1)
            combo = QComboBox()
            combo.addItem("Importer dans la bibliothèque + ce profil", ADD_LIB_AND_PROFILE)
            combo.addItem("Importer dans la bibliothèque seulement", ADD_LIB_ONLY)
            combo.addItem("Ignorer", ADD_IGNORE)
            combo.setCurrentIndex(0)
            self._added_choices[filename] = combo
            row.addWidget(combo)
            wrap = QWidget()
            wrap.setLayout(row)
            layout.addWidget(wrap)
        return box

    def _updated_group(self, diff: SyncDiff) -> QGroupBox:
        box = QGroupBox(
            f"Mods mis a jour dans le jeu ({len(diff.updated_in_game)})", self
        )
        layout = QVBoxLayout(box)
        if not diff.updated_in_game:
            layout.addWidget(QLabel("Aucun mod mis a jour detecte."))
            return box
        for filename in diff.updated_in_game:
            row = QHBoxLayout()
            row.addWidget(QLabel(filename), 1)
            combo = QComboBox()
            combo.addItem("Recuperer la mise a jour dans la bibliotheque", UPDATE_IMPORT)
            combo.addItem("Ignorer", UPDATE_IGNORE)
            combo.setCurrentIndex(0)
            self._updated_choices[filename] = combo
            row.addWidget(combo)
            wrap = QWidget()
            wrap.setLayout(row)
            layout.addWidget(wrap)
        return box

    def _removed_group(self, diff: SyncDiff) -> QGroupBox:
        box = QGroupBox(
            f"Mods retirés du dossier du jeu ({len(diff.removed_in_game)})", self
        )
        layout = QVBoxLayout(box)
        if not diff.removed_in_game:
            layout.addWidget(QLabel("Aucun mod retiré."))
            return box
        for filename in diff.removed_in_game:
            row = QHBoxLayout()
            row.addWidget(QLabel(filename), 1)
            combo = QComboBox()
            combo.addItem("Garder dans le profil", REMOVE_KEEP)
            combo.addItem("Retirer du profil", REMOVE_DROP)
            combo.setCurrentIndex(1)  # par défaut : retirer
            self._removed_choices[filename] = combo
            row.addWidget(combo)
            wrap = QWidget()
            wrap.setLayout(row)
            layout.addWidget(wrap)
        return box

    def added_actions(self) -> dict[str, str]:
        return {fname: cb.currentData() for fname, cb in self._added_choices.items()}

    def removed_actions(self) -> dict[str, str]:
        return {fname: cb.currentData() for fname, cb in self._removed_choices.items()}

    def updated_actions(self) -> dict[str, str]:
        return {fname: cb.currentData() for fname, cb in self._updated_choices.items()}
