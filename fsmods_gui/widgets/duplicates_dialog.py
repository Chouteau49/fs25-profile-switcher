"""Report dialog listing duplicate mods found in the library."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..profiles.catalog import Catalog
from ..profiles.duplicates import DUP_CONTENT, DuplicateGroup, find_duplicate_groups

_KIND_FR = {
    DUP_CONTENT: "même titre + auteur",
    "filename": "même nom de fichier",
}


class DuplicatesDialog(QDialog):
    """Show duplicate groups grouped by their detected identity."""

    def __init__(self, catalog: Catalog | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Doublons de la bibliothèque")
        self.setMinimumSize(680, 460)

        groups = find_duplicate_groups(catalog)
        total_files = sum(len(g.entries) for g in groups)

        if groups:
            intro = QLabel(
                f"<b>{len(groups)}</b> groupe(s) de doublons détecté(s) "
                f"({total_files} fichiers concernés).<br/>"
                f"Détection <i>indicative</i> : vérifie avant de supprimer un fichier."
            )
        else:
            intro = QLabel("✓ Aucun doublon détecté dans la bibliothèque.")
        intro.setWordWrap(True)

        tree = QTreeWidget(self)
        tree.setColumnCount(3)
        tree.setHeaderLabels(["Mod / Fichier", "Version", "Auteur"])
        tree.setAlternatingRowColors(True)
        tree.header().setStretchLastSection(True)

        for group in groups:
            self._add_group(tree, group)
        tree.expandAll()
        for col in range(3):
            tree.resizeColumnToContents(col)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(tree, 1)
        layout.addWidget(buttons)

    def _add_group(self, tree: QTreeWidget, group: DuplicateGroup) -> None:
        reason = _KIND_FR.get(group.kind, group.kind)
        parent = QTreeWidgetItem(tree, [f"{group.label}  ({len(group.entries)} — {reason})"])
        parent.setFirstColumnSpanned(True)
        font = parent.font(0)
        font.setBold(True)
        parent.setFont(0, font)
        for entry in group.entries:
            child = QTreeWidgetItem(
                parent,
                [entry.filename, entry.version or "", entry.author or ""],
            )
            child.setToolTip(0, entry.display_title)
