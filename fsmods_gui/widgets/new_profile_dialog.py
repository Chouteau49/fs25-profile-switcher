"""Création d'un profil sur un seul écran : nom, carte, collections, carrière.

Remplace les deux fenêtres enchaînées de 0.15 (« Nom du profil », puis « Type
de carrière ») et permet en plus de choisir la carte et les collections dès la
création.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class NewProfileChoice:
    name: str
    map_data: str | None  # comme les données du sélecteur de carte de l'éditeur
    collections: tuple[str, ...]
    scenario: str | None  # clé de modèle de carrière, None = aucune


class NewProfileDialog(QDialog):
    def __init__(
        self,
        maps: list[tuple[str, str | None]],
        collections: list[tuple[str, str, int]],
        scenarios: list[tuple[str, str | None]],
        existing_names: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouveau profil")
        self.setMinimumWidth(520)
        self._existing = {n.casefold() for n in existing_names}

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Ex. Montagne hiver")
        self.name_input.textChanged.connect(self._validate)
        self.map_combo = QComboBox(self)
        for label, data in maps:
            self.map_combo.addItem(label, userData=data)

        self.collection_boxes: list[tuple[str, QCheckBox]] = []
        cols = QVBoxLayout()
        cols.setSpacing(4)
        for slug, name, count in collections:
            box = QCheckBox(f"{name}  ({count} mods)", self)
            self.collection_boxes.append((slug, box))
            cols.addWidget(box)
        if not collections:
            none = QLabel("Aucune collection pour l'instant.", self)
            none.setProperty("role", "muted")
            cols.addWidget(none)

        self._scenario_keys: list[str | None] = []
        self.scenario_group = QButtonGroup(self)
        scen = QHBoxLayout()
        scen.setSpacing(6)
        for i, (label, key) in enumerate(scenarios):
            btn = QPushButton(label, self)
            btn.setCheckable(True)
            btn.setProperty("role", "choice")
            self.scenario_group.addButton(btn, i)
            self._scenario_keys.append(key)
            scen.addWidget(btn)
        scen.addStretch(1)
        if scenarios:
            self.scenario_group.button(0).setChecked(True)
        scen_wrap = QVBoxLayout()
        scen_wrap.addLayout(scen)
        hint = QLabel(
            "Des objectifs adaptés sont créés ; tout reste modifiable dans Carrière.", self
        )
        hint.setProperty("role", "muted")
        scen_wrap.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(12)
        form.addRow("Nom", self.name_input)
        form.addRow("Carte", self.map_combo)
        form.addRow("Collections", cols)
        form.addRow("Carrière", scen_wrap)

        self.error = QLabel(self)
        self.error.setProperty("role", "error")

        self.buttons = QDialogButtonBox(self)
        self.create_btn = self.buttons.addButton(
            "Créer le profil", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.create_btn.setProperty("variant", "primary")
        self.create_btn.style().unpolish(self.create_btn)
        self.create_btn.style().polish(self.create_btn)
        self.buttons.addButton("Annuler", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(14)
        heading = QLabel("Nouveau profil", self)
        heading.setProperty("role", "page-title")
        lay.addWidget(heading)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addWidget(self.buttons)
        self._validate()

    def _validate(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            msg = ""
        elif name.casefold() in self._existing:
            msg = "Un profil porte déjà ce nom."
        else:
            msg = ""
        self.error.setText(msg)
        self.create_btn.setEnabled(bool(name) and not msg)

    def choice(self) -> NewProfileChoice:
        idx = self.scenario_group.checkedId()
        scenario = self._scenario_keys[idx] if 0 <= idx < len(self._scenario_keys) else None
        return NewProfileChoice(
            name=self.name_input.text().strip(),
            map_data=self.map_combo.currentData(),
            collections=tuple(slug for slug, box in self.collection_boxes if box.isChecked()),
            scenario=scenario,
        )
