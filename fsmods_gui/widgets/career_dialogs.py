"""Small dialogs used by the career panel."""
from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..career.objectives import (
    DIFFICULTY_LABELS_FR,
    OPERATORS,
    Condition,
    Objective,
    Reward,
    now_iso,
)
from ..career.stats import CATEGORIES_FR, STAT_DEFS, StatsSnapshot, label_for

_MAX = 1e12


def _stat_choices(snapshot: StatsSnapshot) -> list[tuple[str, str]]:
    """(key, label) for every known + discovered statistic, sorted by label."""
    keys = set(STAT_DEFS) | set(snapshot.stats)
    out = []
    for key in keys:
        stat = snapshot.get(key)
        label = stat.label if stat and stat.label else label_for(key)[0]
        out.append((key, label))
    return sorted(out, key=lambda kv: kv[1].lower())


class _ConditionRow(QWidget):
    """One ``[NOT] statistic operator target unit`` line of an objective."""

    def __init__(self, snapshot: StatsSnapshot, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self.negate = QCheckBox("NON", self)
        self.negate.setToolTip("Inverse la condition (la condition ne doit PAS être vraie).")
        self.stat = QComboBox(self)
        self.stat.setEditable(True)
        self.stat.setMaxVisibleItems(20)
        self.stat.setMinimumWidth(240)
        for key, label in _stat_choices(snapshot):
            self.stat.addItem(f"{label}  [{key}]", userData=key)
        self.operator = QComboBox(self)
        self.operator.addItems(list(OPERATORS))
        self.target = QDoubleSpinBox(self)
        self.target.setRange(-_MAX, _MAX)
        self.target.setDecimals(2)
        self.target.setGroupSeparatorShown(True)
        self.unit = QLineEdit(self)
        self.unit.setMaximumWidth(60)
        self.stat.currentIndexChanged.connect(self._on_stat_changed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        for w in (self.negate, self.stat, self.operator, self.target, self.unit):
            row.addWidget(w)
        self.stat.setCurrentIndex(0)
        self._on_stat_changed()

    def stat_key(self) -> str:
        data = self.stat.currentData()
        if data and self.stat.currentText().endswith(f"[{data}]"):
            return str(data)
        return self.stat.currentText().strip()  # free-typed key (e.g. raw.xxx)

    def _on_stat_changed(self) -> None:
        key = self.stat_key()
        known = self._snapshot.get(key)
        self.unit.setText(known.unit if known else STAT_DEFS.get(key, ("", "", ""))[1])

    def condition(self) -> Condition:
        leaf = Condition(
            stat=self.stat_key(),
            operator=self.operator.currentText(),
            target=self.target.value(),
            unit=self.unit.text().strip(),
        )
        return Condition(op="not", children=[leaf]) if self.negate.isChecked() else leaf


class ObjectiveDialog(QDialog):
    """Create a custom objective: one or several conditions (AND / OR / NOT), or manual."""

    def __init__(
        self,
        snapshot: StatsSnapshot,
        existing: list[Objective] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouvel objectif personnalisé")
        self._snapshot = snapshot
        self._rows: list[_ConditionRow] = []

        self.name_edit = QLineEdit(self)
        self.desc_edit = QLineEdit(self)
        self.category = QComboBox(self)
        for key, label in CATEGORIES_FR.items():
            self.category.addItem(label, userData=key)

        self.manual = QCheckBox("Objectif manuel (je le valide moi-même)", self)
        self.manual.toggled.connect(self._on_manual_toggled)
        self.combinator = QComboBox(self)
        self.combinator.addItem("Toutes les conditions (ET)", userData="and")
        self.combinator.addItem("Au moins une condition (OU)", userData="or")
        self.rows_layout = QVBoxLayout()
        self.add_btn = QPushButton("➕ Ajouter une condition", self)
        self.add_btn.clicked.connect(self._add_row)
        self.remove_btn = QPushButton("➖ Retirer la dernière", self)
        self.remove_btn.clicked.connect(self._remove_row)
        btns = QHBoxLayout()
        btns.addWidget(self.add_btn)
        btns.addWidget(self.remove_btn)
        btns.addStretch(1)

        self.requires = QListWidget(self)
        self.requires.setMaximumHeight(110)
        for obj in sorted(existing or [], key=lambda o: o.name.lower()):
            item = QListWidgetItem(obj.name, self.requires)
            item.setData(Qt.ItemDataRole.UserRole, obj.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)

        self.difficulty = QComboBox(self)
        for level, label in DIFFICULTY_LABELS_FR.items():
            self.difficulty.addItem(label, userData=level)
        self.difficulty.setCurrentIndex(1)
        self.money = QSpinBox(self)
        self.money.setRange(0, 2_000_000_000)
        self.money.setSingleStep(10_000)
        self.money.setSuffix(" €")
        self.money.setGroupSeparatorShown(True)
        self.xp = QSpinBox(self)
        self.xp.setRange(0, 1_000_000)
        self.badge = QLineEdit(self)
        self.optional = QCheckBox("Optionnel (ne compte pas dans le pourcentage)", self)

        form = QFormLayout()
        form.addRow("Nom :", self.name_edit)
        form.addRow("Description :", self.desc_edit)
        form.addRow("Catégorie :", self.category)
        form.addRow("", self.manual)
        form.addRow("Combinaison :", self.combinator)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(self.rows_layout)
        layout.addLayout(btns)
        form2 = QFormLayout()
        if self.requires.count():
            form2.addRow("Prérequis (à terminer avant) :", self.requires)
        form2.addRow("Difficulté :", self.difficulty)
        form2.addRow("Récompense (argent) :", self.money)
        form2.addRow("Récompense (XP) :", self.xp)
        form2.addRow("Badge :", self.badge)
        form2.addRow("", self.optional)
        layout.addLayout(form2)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._add_row()
        self.resize(720, self.sizeHint().height())

    def _add_row(self) -> None:
        row = _ConditionRow(self._snapshot, self)
        self._rows.append(row)
        self.rows_layout.addWidget(row)
        self._sync_controls()

    def _remove_row(self) -> None:
        if len(self._rows) <= 1:
            return
        row = self._rows.pop()
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._sync_controls()

    def _sync_controls(self) -> None:
        manual = self.manual.isChecked()
        self.combinator.setEnabled(not manual and len(self._rows) > 1)
        self.remove_btn.setEnabled(not manual and len(self._rows) > 1)
        self.add_btn.setEnabled(not manual)

    def _on_manual_toggled(self, manual: bool) -> None:
        for row in self._rows:
            row.setEnabled(not manual)
        self._sync_controls()

    def _accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Objectif", "Donne un nom à l'objectif.")
            return
        if not self.manual.isChecked() and any(not r.stat_key() for r in self._rows):
            QMessageBox.warning(self, "Objectif", "Choisis une statistique pour chaque condition.")
            return
        self.accept()

    def _condition(self) -> Condition | None:
        if self.manual.isChecked():
            return None
        conditions = [r.condition() for r in self._rows]
        if len(conditions) == 1:
            return conditions[0]
        return Condition(op=self.combinator.currentData(), children=conditions)

    def build(self) -> Objective:
        stamp = now_iso()
        requires = [
            self.requires.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.requires.count())
            if self.requires.item(i).checkState() == Qt.CheckState.Checked
        ]
        return Objective(
            id=f"custom.{uuid.uuid4().hex[:8]}",
            name=self.name_edit.text().strip(),
            description=self.desc_edit.text().strip(),
            category=self.category.currentData(),
            condition=self._condition(),
            difficulty=int(self.difficulty.currentData()),
            optional=self.optional.isChecked(),
            requires=requires,
            reward=Reward(money=self.money.value(), xp=self.xp.value(),
                          badge=self.badge.text().strip()),
            template="custom",
            created_at=stamp,
        )


class ManualStatDialog(QDialog):
    """Type in (or clear) a value for a statistic the savegame cannot give."""

    def __init__(
        self, snapshot: StatsSnapshot, manual: dict[str, float], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Statistique manuelle")
        self._manual = manual
        intro = QLabel(
            "Pour une statistique que la sauvegarde ne fournit pas (ex. la surface "
            "possédée). Elle est affichée « 🔵 Manuelle » et n'écrase jamais une valeur "
            "lue automatiquement."
        )
        intro.setWordWrap(True)
        self.stat = QComboBox(self)
        for key, label in _stat_choices(snapshot):
            stat = snapshot.get(key)
            if stat is None or stat.quality != "auto":
                suffix = " ✎" if key in manual else ""
                self.stat.addItem(f"{label}  [{key}]{suffix}", userData=key)
        self.stat.currentIndexChanged.connect(self._on_changed)
        self.value = QDoubleSpinBox(self)
        self.value.setRange(-_MAX, _MAX)
        self.value.setDecimals(2)
        self.value.setGroupSeparatorShown(True)
        self.clear = QCheckBox("Supprimer la valeur saisie", self)

        form = QFormLayout()
        form.addRow("Statistique :", self.stat)
        form.addRow("Valeur :", self.value)
        form.addRow("", self.clear)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._on_changed()
        self.resize(520, self.sizeHint().height())

    def _on_changed(self) -> None:
        key = self.stat.currentData()
        self.value.setValue(self._manual.get(key, 0.0) if key else 0.0)

    def result_entry(self) -> tuple[str, float | None] | None:
        key = self.stat.currentData()
        if not key:
            return None
        return (str(key), None if self.clear.isChecked() else self.value.value())


def confirm_reward(parent: QWidget, objective: Objective) -> bool:
    """Walk the player through applying a money reward by hand (e.g. with PowerTools)."""
    from ..career.formatting import format_value

    amount = format_value(objective.reward.money, "€")
    box = QMessageBox(parent)
    box.setWindowTitle("Attribuer la récompense")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(f"<b>{objective.name}</b><br>Récompense : 💰 +{amount}")
    box.setInformativeText(
        "Dans Farming Simulator 25 :\n"
        "1. Ouvrez le mod PowerTools (touche F12 par défaut).\n"
        f"2. Ajoutez {amount} à votre ferme.\n"
        "3. Revenez ici et confirmez.\n\n"
        "L'application ne modifie jamais la sauvegarde ni PowerTools : "
        "la récompense est marquée « attribuée » une seule fois."
    )
    done = box.addButton("J'ai ajouté l'argent ✅", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is done
