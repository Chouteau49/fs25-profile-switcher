"""Création d'une collection : nom, description (à quoi elle sert), et une aide sur l'usage.

Remplace la simple invite « Nom : » de 0.16 : la description donne tout de suite
le sens de la collection (« Viticulture », « Vieux matériel pour petite carte
française »…), et l'aide explique qu'elle se coche ensuite dans les profils.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

HELP = (
    "Une collection regroupe des mods que tu installes souvent ensemble. Un profil "
    "reçoit ses mods en cochant la collection dans sa page (onglet « Collections "
    "héritées »). Exemples : tout le viticole, le forestier, « mes indispensables » "
    "pour chaque partie, ou le vieux matériel pour une petite carte française."
)


class NewCollectionDialog(QDialog):
    def __init__(self, existing_names: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouvelle collection")
        self.setMinimumWidth(520)
        self._existing = {n.casefold() for n in existing_names}

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Ex. Viticulture")
        self.name_input.textChanged.connect(self._validate)

        self.description = QTextEdit(self)
        self.description.setFixedHeight(72)
        self.description.setPlaceholderText(
            "Ex. : tracteurs, pulvérisateurs et outils de vigne, pour les cartes en Provence."
        )

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Nom", self.name_input)
        form.addRow("Description", self.description)

        heading = QLabel("Nouvelle collection", self)
        heading.setProperty("role", "page-title")
        help_label = QLabel(HELP, self)
        help_label.setWordWrap(True)
        help_label.setProperty("role", "muted")

        self.error = QLabel(self)
        self.error.setProperty("role", "error")

        self.buttons = QDialogButtonBox(self)
        self.create_btn = self.buttons.addButton(
            "Créer la collection", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.create_btn.setProperty("variant", "primary")
        self.buttons.addButton("Annuler", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(14)
        lay.addWidget(heading)
        lay.addWidget(help_label)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addWidget(self.buttons)
        self._validate()

    def _validate(self) -> None:
        name = self.name_input.text().strip()
        taken = bool(name) and name.casefold() in self._existing
        self.error.setText("Une collection porte déjà ce nom." if taken else "")
        self.create_btn.setEnabled(bool(name) and not taken)

    def choice(self) -> tuple[str, str]:
        return self.name_input.text().strip(), self.description.toPlainText().strip()
