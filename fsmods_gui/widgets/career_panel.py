"""Career tab: dashboard, pending rewards and the objectives of one profile."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..career.formatting import format_value
from ..career.history import CHART_SERIES, series
from ..career.objectives import (
    DIFFICULTY_LABELS_FR,
    MODE_LABELS_FR,
    MODE_OFF,
    RW_PENDING,
    ST_COMPLETED,
    ST_LOCKED,
    ST_NOT_STARTED,
    STATUS_LABELS_FR,
    Objective,
    claim_reward,
    complete_manually,
    level_for_xp,
    rewards_enabled,
    summarize,
)
from ..career.stats import (
    CATEGORIES_FR,
    Q_NA,
    QUALITY_LABELS_FR,
    FarmInfo,
    apply_manual,
    list_farms,
)
from ..career.store import Career
from ..career.sync import SyncReport, sync_career
from ..career.templates import TEMPLATES, build_template
from ..profiles.savegame_audit import list_savegames, parse_savegame
from .career_dialogs import ManualStatDialog, ObjectiveDialog, confirm_reward
from .history_chart import HistoryChart

# Statistics shown as dashboard cards: (key, icon).
_CARDS = (
    ("netWorth", "💰"),
    ("money", "💵"),
    ("land.area", "🌾"),
    ("land.count", "🧩"),
    ("vehicles.count", "🚜"),
    ("animals.total", "🐄"),
    ("contracts.completed", "🚛"),
    ("productions.count", "🏭"),
    ("playTime", "⏱️"),
)
_QUALITY_ICON = {"auto": "🟢", "calc": "🟠", "manual": "🔵", "na": "🔴"}


class CareerPanel(QWidget):
    # Emitted after the career files were rewritten (so the config backup can run).
    changed = Signal()

    def __init__(
        self,
        profile_name: str,
        career: Career,
        user_dir: Path,
        report: SyncReport | None = None,
        parent: QWidget | None = None,
        install_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._install_dir = install_dir
        self._career = career
        self._user_dir = user_dir
        self._profile_name = profile_name
        self._rows: list[Objective] = []

        # ---- header: savegame + mode + actions
        self.savegame_combo = QComboBox(self)
        self.savegame_combo.addItem("— aucune —", userData="")
        for sg in list_savegames(user_dir):
            self.savegame_combo.addItem(parse_savegame(sg).label, userData=sg.name)
        idx = self.savegame_combo.findData(career.settings.savegame)
        self.savegame_combo.setCurrentIndex(max(idx, 0))
        self.savegame_combo.currentIndexChanged.connect(self._on_savegame_changed)

        self._farms: list[FarmInfo] = []
        self.farm_combo = QComboBox(self)
        self.farm_combo.setToolTip(
            "Ferme dont les statistiques alimentent le tableau de bord et les objectifs "
            "sans ferme précise. Chaque objectif peut aussi viser une ferme particulière."
        )
        self.farm_filter = QComboBox(self)
        self._reload_farms()
        self.farm_combo.currentIndexChanged.connect(self._on_farm_changed)

        self.mode_combo = QComboBox(self)
        for key, label in MODE_LABELS_FR.items():
            self.mode_combo.addItem(label, userData=key)
        self.mode_combo.setCurrentIndex(max(self.mode_combo.findData(career.settings.mode), 0))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        sync_btn = QPushButton("🔄 Synchroniser", self)
        sync_btn.clicked.connect(self._on_sync_clicked)
        template_btn = QPushButton("📦 Ajouter un modèle…", self)
        template_btn.clicked.connect(self._on_add_template)
        custom_btn = QPushButton("➕ Objectif perso…", self)
        custom_btn.clicked.connect(self._on_add_custom)
        manual_btn = QPushButton("✏ Statistique manuelle…", self)
        manual_btn.clicked.connect(self._on_manual_stat)

        head1 = QHBoxLayout()
        head1.addWidget(QLabel("Sauvegarde :", self))
        head1.addWidget(self.savegame_combo, 2)
        head1.addWidget(QLabel("Ferme suivie :", self))
        head1.addWidget(self.farm_combo, 2)
        head1.addWidget(QLabel("Mode :", self))
        head1.addWidget(self.mode_combo, 2)
        head1.addWidget(sync_btn)
        head2 = QHBoxLayout()
        head2.addWidget(template_btn)
        head2.addWidget(custom_btn)
        head2.addWidget(manual_btn)
        head2.addStretch(1)

        title = QLabel(f"<h2>🎯 Carrière — {profile_name}</h2>", self)
        self.sync_label = QLabel("", self)
        self.sync_label.setWordWrap(True)

        # ---- dashboard
        self.cards_box = QGroupBox("Tableau de bord", self)
        self.cards_grid = QGridLayout(self.cards_box)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.summary_label = QLabel("", self)
        self.summary_label.setWordWrap(True)
        self.level_label = QLabel("", self)
        self.level_label.setWordWrap(True)

        # ---- history chart
        self.history_box = QGroupBox("📈 Historique", self)
        self.history_combo = QComboBox(self.history_box)
        for key, label, unit in CHART_SERIES:
            self.history_combo.addItem(label, userData=(key, unit))
        self.history_chart = HistoryChart(self.history_box)
        history_layout = QVBoxLayout(self.history_box)
        history_layout.addWidget(self.history_combo)
        history_layout.addWidget(self.history_chart)
        self.history_combo.currentIndexChanged.connect(self._fill_history)

        # ---- pending rewards
        self.rewards_box = QGroupBox("🎁 Récompenses à attribuer", self)
        self.rewards_layout = QVBoxLayout(self.rewards_box)

        # ---- filters + table
        self.cat_filter = QComboBox(self)
        self.cat_filter.addItem("Toutes catégories", userData="")
        for key, label in CATEGORIES_FR.items():
            self.cat_filter.addItem(label, userData=key)
        self.status_filter = QComboBox(self)
        self.status_filter.addItem("Tous statuts", userData="")
        for key, label in STATUS_LABELS_FR.items():
            self.status_filter.addItem(label, userData=key)
        self.diff_filter = QComboBox(self)
        self.diff_filter.addItem("Toutes difficultés", userData=0)
        for key, label in DIFFICULTY_LABELS_FR.items():
            self.diff_filter.addItem(label, userData=key)
        for combo in (self.cat_filter, self.status_filter, self.diff_filter, self.farm_filter):
            combo.currentIndexChanged.connect(self._fill_table)
        filters = QHBoxLayout()
        filters.addWidget(self.cat_filter)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.diff_filter)
        filters.addWidget(self.farm_filter)
        filters.addStretch(1)

        self.table = QTableWidget(self)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["Statut", "Objectif", "Ferme", "Catégorie", "Difficulté", "Progression",
             "Actuel / cible", "Récompense"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_actions)

        self.validate_btn = QPushButton("✅ Valider (objectif manuel)", self)
        self.validate_btn.clicked.connect(self._on_validate)
        self.delete_btn = QPushButton("🗑 Retirer l'objectif", self)
        self.delete_btn.clicked.connect(self._on_delete)
        actions = QHBoxLayout()
        actions.addWidget(self.validate_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        self.detail_label = QLabel("", self)
        self.detail_label.setWordWrap(True)

        content = QWidget()
        col = QVBoxLayout(content)
        col.addWidget(title)
        col.addLayout(head1)
        col.addLayout(head2)
        col.addWidget(self.sync_label)
        col.addWidget(self.cards_box)
        col.addWidget(self.progress_bar)
        col.addWidget(self.summary_label)
        col.addWidget(self.level_label)
        col.addWidget(self.history_box)
        col.addWidget(self.rewards_box)
        col.addLayout(filters)
        col.addWidget(self.table, 1)
        col.addWidget(self.detail_label)
        col.addLayout(actions)
        self.table.setMinimumHeight(260)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        if report is not None:
            self._show_report(report)
        elif career.settings.mode == MODE_OFF:
            self.sync_label.setText("Carrière désactivée pour ce profil.")
        self._refresh()

    # ------------------------------------------------------------- refresh

    def _reload_farms(self) -> None:
        """(Re)read the farms of the linked savegame into the picker."""
        savegame = self._career.settings.savegame
        self._farms = list_farms(self._user_dir / savegame) if savegame else []
        self.farm_combo.blockSignals(True)
        self.farm_combo.clear()
        self.farm_combo.addItem("Automatique (ferme 1)", userData="")
        for farm in self._farms:
            self.farm_combo.addItem(farm.label, userData=farm.id)
        idx = self.farm_combo.findData(self._career.settings.farm)
        self.farm_combo.setCurrentIndex(max(idx, 0))
        self.farm_combo.setEnabled(bool(self._farms))
        self.farm_combo.blockSignals(False)

    def _farm_label(self, farm_id: str) -> str:
        if not farm_id:
            return "suivie"
        name = next((f.name for f in self._farms if f.id == farm_id), "")
        return name or f"ferme {farm_id}"

    def _reload_farm_filter(self) -> None:
        current = self.farm_filter.currentData() if self.farm_filter.count() else None
        used = sorted({o.farm for o in self._career.objectives if o.farm})
        self.farm_filter.blockSignals(True)
        self.farm_filter.clear()
        self.farm_filter.addItem("Toutes fermes", userData=None)
        self.farm_filter.addItem("Ferme suivie", userData="")
        for farm in used:
            self.farm_filter.addItem(self._farm_label(farm), userData=farm)
        self.farm_filter.setCurrentIndex(max(self.farm_filter.findData(current), 0))
        self.farm_filter.blockSignals(False)

    def _refresh(self) -> None:
        self._reload_farm_filter()
        self._fill_cards()
        self._fill_summary()
        self._fill_rewards()
        self._fill_history()
        self._fill_table()

    def _fill_history(self) -> None:
        key, unit = self.history_combo.currentData()
        self.history_chart.set_points(series(self._career.history, key), unit)

    def _fill_cards(self) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0).widget()
            if item is not None:
                item.deleteLater()
        snapshot = self._career.snapshot
        farm = snapshot.farm_name or (f"ferme {snapshot.farm_id}" if snapshot.farm_id else "")
        self.cards_box.setTitle(f"Tableau de bord — {farm}" if farm else "Tableau de bord")
        for i, (key, icon) in enumerate(_CARDS):
            stat = snapshot.get(key)
            label = stat.label if stat else key
            value = format_value(stat.value, stat.unit) if stat else "—"
            quality = stat.quality if stat else Q_NA
            card = QLabel(
                f"<span style='font-size:11px;color:#666'>{icon} {label}</span><br>"
                f"<b style='font-size:16px'>{value}</b> {_QUALITY_ICON[quality]}",
                self.cards_box,
            )
            card.setToolTip(
                f"{QUALITY_LABELS_FR[quality]}" + (f"\n{stat.note}" if stat and stat.note else "")
            )
            card.setMinimumHeight(56)
            card.setStyleSheet("QLabel { border: 1px solid #ccc; border-radius: 6px; padding: 6px; }")
            self.cards_grid.addWidget(card, i // 3, i % 3)

    def _fill_summary(self) -> None:
        s = summarize(self._career.objectives)
        self.progress_bar.setValue(round(s.percent))
        self.progress_bar.setFormat(f"Objectifs : {s.percent:.0f} %")
        extra = []
        if s.unavailable:
            extra.append(f"🔴 {s.unavailable} non disponibles")
        if s.manual:
            extra.append(f"🔵 {s.manual} à valider")
        if s.locked:
            extra.append(f"🔒 {s.locked} verrouillés")
        self.summary_label.setText(
            f"🟢 {s.completed} terminés · 🟠 {s.in_progress} en cours · "
            f"⚪ {s.not_started} non commencés"
            + ("".join(f" · {e}" for e in extra))
        )
        level, into, need = level_for_xp(s.xp)
        badges = ", ".join(f"🏅 {b}" for b in dict.fromkeys(s.badges)) or "aucun"
        self.level_label.setText(
            f"⭐ Niveau {level} — {s.xp} XP ({into}/{need} avant le suivant) · Badges : {badges}"
        )

    def _fill_rewards(self) -> None:
        while self.rewards_layout.count():
            item = self.rewards_layout.takeAt(0)
            if item.layout() is not None:
                self._clear_layout(item.layout())
        pending = [o for o in self._career.objectives if o.reward_state == RW_PENDING]
        self.rewards_box.setVisible(rewards_enabled(self._career.settings.mode) and bool(pending))
        for obj in pending:
            row = QHBoxLayout()
            row.addWidget(
                QLabel(f"{obj.name} — 💰 +{format_value(obj.reward.money, '€')}", self.rewards_box),
                1,
            )
            btn = QPushButton("Attribuer la récompense", self.rewards_box)
            btn.clicked.connect(lambda _=False, o=obj: self._on_claim(o))
            row.addWidget(btn)
            self.rewards_layout.addLayout(row)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _visible_objectives(self) -> list[Objective]:
        cat = self.cat_filter.currentData()
        status = self.status_filter.currentData()
        diff = self.diff_filter.currentData()
        farm = self.farm_filter.currentData() if self.farm_filter.count() else None
        out = []
        for o in self._career.objectives:
            if o.hidden and o.status in (ST_LOCKED, ST_NOT_STARTED):
                continue  # hidden objectives only appear once unlocked and started
            if cat and o.category != cat:
                continue
            if status and o.status != status:
                continue
            if diff and o.difficulty != diff:
                continue
            if farm is not None and o.farm != farm:
                continue
            out.append(o)
        return sorted(
            out,
            key=lambda o: (o.status == ST_COMPLETED, o.status == ST_LOCKED, o.priority, o.name),
        )

    def _fill_table(self) -> None:
        self._rows = self._visible_objectives()
        self.table.clearContents()
        self.table.setRowCount(len(self._rows))
        for r, o in enumerate(self._rows):
            cur = format_value(o.current_value, o.unit) if o.condition else "—"
            if o.is_leaf:
                text = f"{cur} / {o.operator} {format_value(o.target, o.unit)}"
            elif o.condition is not None:
                text = f"combiné ({len(o.condition.leaves())} conditions)"
            else:
                text = "manuel"
            reward = []
            if o.reward.money:
                reward.append(f"💰 {format_value(o.reward.money, '€')}")
            if o.reward.xp:
                reward.append(f"⭐ {o.reward.xp} XP")
            if o.reward.badge:
                reward.append(f"🏅 {o.reward.badge}")
            state = {"pending": " (à attribuer)", "claimed": " ✅", "waived": " (non due)"}.get(
                o.reward_state, ""
            )
            values = [
                STATUS_LABELS_FR[o.status],
                o.name + (" (optionnel)" if o.optional else ""),
                self._farm_label(o.farm),
                CATEGORIES_FR.get(o.category, o.category),
                DIFFICULTY_LABELS_FR.get(o.difficulty, ""),
                None,
                text,
                (" · ".join(reward) + state) if reward else "—",
            ]
            for c, v in enumerate(values):
                if v is not None:
                    item = QTableWidgetItem(v)
                    if o.description and c == 1:
                        item.setToolTip(o.description)
                    self.table.setItem(r, c, item)
            bar = QProgressBar(self.table)
            bar.setRange(0, 1000)
            bar.setValue(round(o.progress * 1000))
            bar.setFormat(f"{o.progress * 100:.1f} %".replace(".", ","))
            self.table.setCellWidget(r, 5, bar)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._update_actions()

    def _selected(self) -> Objective | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or rows[0].row() >= len(self._rows):
            return None
        return self._rows[rows[0].row()]

    def _update_actions(self) -> None:
        obj = self._selected()
        self.validate_btn.setEnabled(
            obj is not None and obj.condition is None and not obj.completed
            and obj.status != ST_LOCKED
        )
        self.delete_btn.setEnabled(obj is not None)
        if obj is None:
            self.detail_label.setText("")
            return
        bits = [obj.description] if obj.description else []
        if obj.requires:
            names = {o.id: o.name for o in self._career.objectives}
            bits.append("Prérequis : " + ", ".join(names.get(r, r) for r in obj.requires))
        if obj.condition is not None:
            for leaf in obj.condition.leaves():
                stat = self._career.snapshot_for(obj).get(leaf.stat)
                quality = QUALITY_LABELS_FR[stat.quality] if stat else QUALITY_LABELS_FR[Q_NA]
                note = f" — {stat.note}" if stat and stat.note else ""
                bits.append(f"{leaf.stat} : {quality}{note}")
        if obj.completed_at:
            bits.append(f"Terminé le {obj.completed_at.replace('T', ' ')}")
        self.detail_label.setText("<br>".join(bits))

    # ------------------------------------------------------------ actions

    def _show_report(self, report: SyncReport) -> None:
        lines = [report.message]
        if report.ok:
            lines += [f"✓ {d}" for d in report.detected]
            if report.newly_completed:
                lines.append(f"🎉 {len(report.newly_completed)} objectif(s) terminé(s) !")
                lines += [f"   • {o.name}" for o in report.newly_completed]
            if report.newly_unlocked:
                lines.append(f"🔓 {len(report.newly_unlocked)} nouvel(s) objectif(s) débloqué(s) :")
                lines += [f"   • {o.name}" for o in report.newly_unlocked]
        self.sync_label.setText("<br>".join(lines))

    def _on_sync_clicked(self) -> None:
        report = sync_career(self._career, self._user_dir, self._install_dir)
        self._reload_farms()
        self._show_report(report)
        self._refresh()
        self.changed.emit()

    def _on_savegame_changed(self) -> None:
        self._career.settings.savegame = self.savegame_combo.currentData() or ""
        self._career.save()
        self._on_sync_clicked()

    def _on_farm_changed(self) -> None:
        self._career.settings.farm = self.farm_combo.currentData() or ""
        self._career.save()
        self._on_sync_clicked()

    def _on_mode_changed(self) -> None:
        self._career.settings.mode = self.mode_combo.currentData()
        self._career.save()
        self._on_sync_clicked()

    def _persist_and_refresh(self) -> None:
        self._career.save()
        self._refresh()
        self.changed.emit()

    def _reevaluate(self) -> None:
        self._career.evaluate()

    def _on_add_template(self) -> None:
        keys = list(TEMPLATES)
        names = [f"{TEMPLATES[k].name} — {len(TEMPLATES[k].specs)} objectifs" for k in keys]
        choice, ok = QInputDialog.getItem(
            self, "Modèle d'objectifs", "Quelle carrière souhaitez-vous ?", names, 0, False
        )
        if not ok:
            return
        tpl = TEMPLATES[keys[names.index(choice)]]
        farm = self._ask_farm()
        if farm is None:
            return
        added = self._career.add_objectives(build_template(tpl.key, farm))
        self._reevaluate()
        self._persist_and_refresh()
        QMessageBox.information(
            self, "Modèle", f"{added} objectif(s) ajouté(s) ({tpl.description})"
            + ("\nLes déjà présents ont été ignorés." if added < len(tpl.specs) else "")
        )

    def _ask_farm(self) -> str | None:
        """Farm a batch of objectives applies to; ``""`` = tracked farm, ``None`` = cancelled."""
        if not self._farms:
            return ""
        labels = ["Ferme suivie par la carrière"] + [f.label for f in self._farms]
        choice, ok = QInputDialog.getItem(
            self, "Ferme concernée", "Ces objectifs concernent quelle ferme ?", labels, 0, False
        )
        if not ok:
            return None
        pos = labels.index(choice)
        return "" if pos == 0 else self._farms[pos - 1].id

    def _on_add_custom(self) -> None:
        dlg = ObjectiveDialog(
            self._career.snapshot, self._career.objectives, self, farms=self._farms
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        self._career.add_objectives([dlg.build()])
        self._reevaluate()
        self._persist_and_refresh()

    def _on_manual_stat(self) -> None:
        dlg = ManualStatDialog(
            self._career.snapshot,
            self._career.settings.manual_stats,
            self,
            farms=self._farms,
            tracked_farm=self._career.snapshot.farm_id,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        entry = dlg.result_entry()
        if entry is None:
            return
        key, value = entry
        if value is None:
            self._career.settings.manual_stats.pop(key, None)
            self._on_sync_clicked()  # re-read the savegame value instead of the override
            return
        self._career.settings.manual_stats[key] = value
        if self._career.settings.savegame:
            self._on_sync_clicked()
        else:
            apply_manual(self._career.snapshot, {key: value})
            self._reevaluate()
            self._persist_and_refresh()

    def _on_validate(self) -> None:
        obj = self._selected()
        if obj is None or not complete_manually(obj, self._career.settings.mode):
            return
        self._persist_and_refresh()

    def _on_delete(self) -> None:
        obj = self._selected()
        if obj is None:
            return
        if (
            QMessageBox.question(self, "Retirer", f"Retirer l'objectif « {obj.name} » ?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._career.remove_objective(obj.id)
        self._reevaluate()
        self._persist_and_refresh()

    def _on_claim(self, obj: Objective) -> None:
        if not confirm_reward(self, obj):
            return
        if claim_reward(obj):
            self._reevaluate()  # may unlock the next step in "required rewards" mode
            self._persist_and_refresh()

