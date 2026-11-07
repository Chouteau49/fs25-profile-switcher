"""Small dialogs used by the career panel."""
from __future__ import annotations

import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..career.formatting import format_value, parse_area
from ..career.objectives import (
    DIFFICULTY_LABELS_FR,
    OPERATORS,
    Condition,
    Objective,
    Reward,
    now_iso,
)
from ..career.stats import CATEGORIES_FR, STAT_DEFS, FarmInfo, StatsSnapshot, label_for

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


def farm_combo(
    farms: list[FarmInfo], parent: QWidget | None = None, *, follow_label: str
) -> QComboBox:
    """Farm picker: first entry (data ``""``) follows the career's tracked farm."""
    combo = QComboBox(parent)
    combo.addItem(follow_label, userData="")
    for farm in farms:
        combo.addItem(farm.label, userData=farm.id)
    return combo


class DecimalSpinBox(QDoubleSpinBox):
    """Spin box taking "," and "." alike.

    With a French locale Qt silently drops a typed dot, so "1.95" becomes 195 — and
    the numeric keypad of an AZERTY keyboard types a dot.
    """

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        separator = self.locale().decimalPoint()
        if event.text() in (".", ",") and event.text() != separator:
            event = QKeyEvent(event.type(), event.key(), event.modifiers(), separator)
        super().keyPressEvent(event)


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
        self.target = DecimalSpinBox(self)
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
        farms: list[FarmInfo] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouvel objectif personnalisé")
        self.farm = farm_combo(farms or [], self, follow_label="Ferme suivie par la carrière")
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
        if farms:
            form.addRow("Ferme concernée :", self.farm)
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
            farm=self.farm.currentData() or "",
            reward=Reward(money=self.money.value(), xp=self.xp.value(),
                          badge=self.badge.text().strip()),
            template="custom",
            created_at=stamp,
        )


class _AreaEdit(QLineEdit):
    """Area field: Enter goes to the next parcel and never reaches the dialog's OK."""

    next_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.next_requested.emit()
            return
        super().keyPressEvent(event)


class ParcelAreasDialog(QDialog):
    """Area of every owned parcel: read from the map, or typed in when it can't be (DLC).

    ``rows`` = ``(farm label, parcel id, area from the map or None)``. A blank field
    means "not known yet", ``0`` is a real value. Plain text fields rather than spin
    boxes: both decimal separators work and "unknown" needs no sentinel value.
    """

    def __init__(
        self,
        rows: list[tuple[str, str, float | None]],
        typed: dict[str, float],
        map_note: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Surfaces des parcelles")
        self._rows = rows
        self._edits: dict[str, _AreaEdit] = {}
        intro = QLabel(map_note + (
            "\n\nTape la surface affichée en jeu (carte → parcelle), par exemple 2,05. "
            "Entrée passe à la parcelle suivante. Laisse vide une surface inconnue : "
            "le total reste alors incomplet."
            if any(area is None for _f, _p, area in rows) else ""
        ))
        intro.setWordWrap(True)
        self._table = QTableWidget(len(rows), 4, self)
        self._table.setHorizontalHeaderLabels(["Parcelle", "Ferme", "Surface (ha)", "Source"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for r, (farm, pid, area) in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(f"n° {pid}"))
            self._table.setItem(r, 1, QTableWidgetItem(farm))
            if area is not None:
                self._table.setItem(r, 2, QTableWidgetItem(format_value(area)))
                self._table.setItem(r, 3, QTableWidgetItem("🟠 carte du jeu"))
                continue
            edit = _AreaEdit(self._table)
            edit.setPlaceholderText("à saisir")
            if pid in typed:
                edit.setText(format_value(typed[pid]))
            edit.textChanged.connect(self._refresh_total)
            edit.next_requested.connect(lambda p=pid: self._focus_after(p))
            self._edits[pid] = edit
            self._table.setCellWidget(r, 2, edit)
            self._table.setItem(r, 3, QTableWidgetItem("🔵 saisie"))
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)
        self.total_label = QLabel("", self)
        self.total_label.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self._table, 1)
        layout.addWidget(self.total_label)
        layout.addWidget(buttons)
        self.resize(560, 480)
        self._refresh_total()

    def _focus_after(self, pid: str) -> None:
        order = list(self._edits)
        following = order[order.index(pid) + 1:]
        if not following:
            self.ok_button.setFocus()
            return
        edit = self._edits[following[0]]
        edit.setFocus()
        edit.selectAll()
        row = next(r for r, (_f, p, _a) in enumerate(self._rows) if p == following[0])
        self._table.scrollToItem(self._table.item(row, 0))

    def _parsed(self, pid: str) -> float | None:
        return parse_area(self._edits[pid].text())

    def _refresh_total(self) -> None:
        total = 0.0
        missing: list[str] = []
        unreadable: list[str] = []
        for _farm, pid, area in self._rows:
            if area is not None:
                total += area
                continue
            try:
                typed = self._parsed(pid)
            except ValueError:
                unreadable.append(pid)
                continue
            if typed is None:
                missing.append(pid)
            else:
                total += typed
        text = f"<b>Total : {format_value(total, 'ha')}</b>"
        if missing:
            listed = ", ".join(f"n° {p}" for p in missing)
            text = f"<b>Total : ≥ {format_value(total, 'ha')}</b> — incomplet, reste : {listed}"
        if unreadable:
            listed = ", ".join(f"n° {p}" for p in unreadable)
            text += f"<br>⚠ Surface illisible : {listed}"
        self.total_label.setText(text)
        self.ok_button.setEnabled(not unreadable)

    def typed_areas(self) -> dict[str, float]:
        """Areas typed in, ``0`` included; blank or unreadable fields are left out."""
        out: dict[str, float] = {}
        for pid in self._edits:
            try:
                value = self._parsed(pid)
            except ValueError:
                continue
            if value is not None:
                out[pid] = value
        return out


class ManualStatDialog(QDialog):
    """Type in (or clear) a value for a statistic the savegame cannot give."""

    def __init__(
        self,
        snapshot: StatsSnapshot,
        manual: dict[str, float],
        parent: QWidget | None = None,
        farms: list[FarmInfo] | None = None,
        tracked_farm: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Statistique manuelle")
        self._manual = manual
        self._tracked = tracked_farm
        self.farm = QComboBox(self)
        for farm in farms or []:
            self.farm.addItem(farm.label, userData=farm.id)
        self.farm.setCurrentIndex(max(self.farm.findData(tracked_farm), 0))
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
        self.farm.currentIndexChanged.connect(self._on_changed)
        self.value = DecimalSpinBox(self)
        self.value.setRange(-_MAX, _MAX)
        self.value.setDecimals(2)
        self.value.setGroupSeparatorShown(True)
        self.clear = QCheckBox("Supprimer la valeur saisie", self)

        form = QFormLayout()
        if farms:
            form.addRow("Ferme :", self.farm)
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

    def _storage_key(self, key: str) -> str:
        """Unprefixed for the tracked farm, ``"<farm>|<key>"`` for any other farm."""
        farm = self.farm.currentData() or ""
        prefixed = f"{farm}|{key}"
        if not farm or (farm == self._tracked and prefixed not in self._manual):
            return key
        return prefixed

    def _on_changed(self) -> None:
        key = self.stat.currentData()
        self.value.setValue(self._manual.get(self._storage_key(key), 0.0) if key else 0.0)

    def result_entry(self) -> tuple[str, float | None] | None:
        key = self.stat.currentData()
        if not key:
            return None
        return (self._storage_key(str(key)), None if self.clear.isChecked() else self.value.value())


def confirm_reward(parent: QWidget, objective: Objective) -> bool:
    """Walk the player through applying a money reward by hand (e.g. with PowerTools)."""
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
