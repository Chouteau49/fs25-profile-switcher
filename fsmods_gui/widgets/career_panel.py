"""Career tab: dashboard, pending rewards and the objectives of one profile."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..career.campaigns import CAMPAIGNS
from ..career.farmland_areas import is_dlc_map, map_farmland_areas
from ..career.formatting import format_stat, format_value
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
    set_reward_paid,
    summarize,
)
from ..career.presentation import group_objectives
from ..career.presentation import subtitle as card_subtitle
from ..career.stats import (
    CATEGORIES_FR,
    Q_NA,
    QUALITY_LABELS_FR,
    STAT_DEFS,
    FarmInfo,
    apply_manual,
    list_farms,
    owned_parcels,
    savegame_map_id,
)
from ..career.store import Career, CareerError
from ..career.sync import SyncReport, sync_career
from ..career.templates import TEMPLATES, build_template
from ..career.time_window import WINDOW_PRESETS, window_line
from ..profiles.savegame_audit import list_savegames, parse_savegame
from . import icons
from .career_dialogs import (
    ManualStatDialog,
    ObjectiveDialog,
    ParcelAreasDialog,
    confirm_reward,
)
from .history_chart import HistoryChart
from .objective_cards import ObjectiveCards
from .toast import notify

# Statistics shown as dashboard cards.
_CARDS = (
    "netWorth",
    "money",
    "land.area",
    "land.count",
    "vehicles.count",
    "animals.total",
    "contracts.completed",
    "productions.count",
    "playTime",
)


class CareerPanel(QWidget):
    #: Vue choisie (0 tableau de bord, 1 objectifs) : le panneau est reconstruit
    #: à chaque affichage, on retrouve la même vue.
    _last_view = 0

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
        library_mods_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._install_dir = install_dir
        self._library_mods_dir = library_mods_dir
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

        sync_btn = QPushButton("Synchroniser", self)
        icons.bind(sync_btn, "refresh")
        sync_btn.clicked.connect(self._on_sync_clicked)
        template_btn = QPushButton("Ajouter un modèle…", self)
        icons.bind(template_btn, "box")
        template_btn.clicked.connect(self._on_add_template)
        custom_btn = QPushButton("Objectif perso…", self)
        icons.bind(custom_btn, "plus")
        custom_btn.clicked.connect(self._on_add_custom)
        manual_btn = QPushButton("Statistique manuelle…", self)
        icons.bind(manual_btn, "pencil")
        manual_btn.clicked.connect(self._on_manual_stat)
        parcels_btn = QPushButton("Surfaces des parcelles…", self)
        icons.bind(parcels_btn, "map")
        parcels_btn.setToolTip(
            "Surface de chaque parcelle possédée : lue sur la carte du jeu, "
            "ou à saisir pour une carte DLC (chiffrée)."
        )
        parcels_btn.clicked.connect(self._on_parcel_areas)
        windows_btn = QPushButton("Lancer un défi…", self)
        icons.bind(windows_btn, "plus")
        windows_btn.setToolTip("Défi sur une fenêtre de temps de jeu, p. ex. 2 M€ en 24 h.")
        windows_btn.clicked.connect(self._on_start_window)

        # Contexte de la carrière (sauvegarde, ferme, mode) dans une carte.
        context = QWidget(self)
        context.setProperty("role", "card")
        context.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        head1 = QHBoxLayout(context)
        head1.setContentsMargins(14, 10, 14, 10)
        head1.setSpacing(14)
        for caption, combo in (
            ("Sauvegarde", self.savegame_combo),
            ("Ferme suivie", self.farm_combo),
            ("Mode", self.mode_combo),
        ):
            field = QVBoxLayout()
            field.setSpacing(3)
            caption_label = QLabel(caption, context)
            caption_label.setProperty("role", "muted")
            field.addWidget(caption_label)
            field.addWidget(combo)
            head1.addLayout(field, 2)

        title = QLabel(f"Carrière · {profile_name}", self)
        title.setProperty("role", "page-title")
        title_row = QHBoxLayout()
        title_row.addWidget(title, 1)
        sync_btn.setMinimumHeight(36)
        title_row.addWidget(sync_btn)
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
        self.history_box = QGroupBox("Historique", self)
        self.history_combo = QComboBox(self.history_box)
        for key, label, unit in CHART_SERIES:
            self.history_combo.addItem(label, userData=(key, unit))
        self.history_chart = HistoryChart(self.history_box)
        history_layout = QVBoxLayout(self.history_box)
        history_layout.addWidget(self.history_combo)
        history_layout.addWidget(self.history_chart)
        self.history_combo.currentIndexChanged.connect(self._fill_history)

        # ---- pending rewards
        self.rewards_box = QGroupBox("Récompenses à attribuer", self)
        self.rewards_layout = QVBoxLayout(self.rewards_box)

        # ---- défis en fenêtre de temps de jeu
        self.windows_box = QGroupBox("Défis en fenêtre de temps", self)
        self.windows_label = QLabel("", self.windows_box)
        self.windows_label.setWordWrap(True)
        windows_layout = QVBoxLayout(self.windows_box)
        windows_layout.addWidget(self.windows_label)

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
        for level, label in DIFFICULTY_LABELS_FR.items():
            self.diff_filter.addItem(label, userData=level)
        for combo in (self.cat_filter, self.status_filter, self.diff_filter, self.farm_filter):
            combo.currentIndexChanged.connect(self._fill_table)
        filters = QHBoxLayout()
        filters.addWidget(self.cat_filter)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.diff_filter)
        filters.addWidget(self.farm_filter)
        filters.addStretch(1)

        self.cards = ObjectiveCards(self)
        self.cards.selected.connect(self._on_card_selected)
        self.cards.paid_toggled.connect(self._on_paid_toggled)
        self._selected_id: str | None = None

        self.validate_btn = QPushButton("Valider (objectif manuel)", self)
        icons.bind(self.validate_btn, "check")
        self.validate_btn.clicked.connect(self._on_validate)
        self.delete_btn = QPushButton("Retirer l'objectif", self)
        icons.bind(self.delete_btn, "trash")
        self.delete_btn.clicked.connect(self._on_delete)
        actions = QHBoxLayout()
        actions.addWidget(self.validate_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        self.detail_label = QLabel("", self)
        self.detail_label.setWordWrap(True)

        # ---- vue « Tableau de bord » (défilante)
        dash_tools = QHBoxLayout()
        dash_tools.addWidget(manual_btn)
        dash_tools.addWidget(parcels_btn)
        dash_tools.addWidget(windows_btn)
        dash_tools.addStretch(1)
        dash_content = QWidget()
        dash = QVBoxLayout(dash_content)
        dash.setContentsMargins(0, 0, 8, 0)
        dash.setSpacing(12)
        dash.addWidget(self.cards_box)
        dash.addWidget(self.progress_bar)
        dash.addWidget(self.summary_label)
        dash.addWidget(self.level_label)
        dash.addWidget(self.windows_box)
        dash.addWidget(self.rewards_box)
        dash.addWidget(self.history_box)
        dash.addLayout(dash_tools)
        dash.addStretch(1)
        dash_scroll = QScrollArea(self)
        dash_scroll.setWidgetResizable(True)
        dash_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        dash_scroll.setWidget(dash_content)
        self.history_chart.setMinimumHeight(200)

        # ---- vue « Objectifs »
        obj_page = QWidget(self)
        obj = QVBoxLayout(obj_page)
        obj.setContentsMargins(0, 0, 0, 0)
        obj.setSpacing(10)
        filters.addWidget(template_btn)
        filters.addWidget(custom_btn)
        obj.addLayout(filters)
        obj.addWidget(self.cards, 1)
        obj.addWidget(self.detail_label)
        obj.addLayout(actions)

        self.views = QStackedWidget(self)
        self.views.addWidget(dash_scroll)  # 0 : tableau de bord
        self.views.addWidget(obj_page)  # 1 : objectifs

        # Commutateur segmenté entre les deux vues.
        self.dash_btn = QPushButton("Tableau de bord", self)
        self.obj_btn = QPushButton(f"Objectifs ({len(career.objectives)})", self)
        switch = QWidget(self)
        switch.setProperty("role", "segmented")
        switch.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sw = QHBoxLayout(switch)
        sw.setContentsMargins(3, 3, 3, 3)
        sw.setSpacing(3)
        self._view_group = QButtonGroup(self)
        for i, btn in enumerate((self.dash_btn, self.obj_btn)):
            btn.setCheckable(True)
            btn.setProperty("role", "segment")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._view_group.addButton(btn, i)
            # Réserve la largeur du texte en gras (sinon tronqué une fois coché).
            bold = btn.font()
            bold.setBold(True)
            btn.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(btn.text()) + 40)
            sw.addWidget(btn)
        self._view_group.idClicked.connect(self.show_view)
        switch_row = QHBoxLayout()
        switch_row.addWidget(switch)
        switch_row.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 0)
        outer.setSpacing(12)
        outer.addLayout(title_row)
        outer.addWidget(context)
        outer.addWidget(self.sync_label)
        outer.addLayout(switch_row)
        outer.addWidget(self.views, 1)
        self.show_view(CareerPanel._last_view)

        if report is not None:
            self._show_report(report)
        elif career.settings.mode == MODE_OFF:
            self.sync_label.setText("Carrière désactivée pour ce profil.")
        self._refresh()

    # ------------------------------------------------------------- refresh

    def show_view(self, index: int) -> None:
        """Afficher le tableau de bord (0) ou la liste des objectifs (1)."""
        index = 1 if index == 1 else 0
        CareerPanel._last_view = index
        self.views.setCurrentIndex(index)
        (self.obj_btn if index == 1 else self.dash_btn).setChecked(True)

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
        self._fill_windows()
        self._fill_history()
        self._fill_table()

    def _fill_history(self) -> None:
        key, unit = self.history_combo.currentData()
        self.history_chart.set_points(
            series(self._career.history, key, self._career.snapshot.farm_id), unit
        )

    def _fill_cards(self) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        snapshot = self._career.snapshot
        farm = snapshot.farm_name or (f"ferme {snapshot.farm_id}" if snapshot.farm_id else "")
        self.cards_box.setTitle(f"Tableau de bord — {farm}" if farm else "Tableau de bord")
        t = theme.current()
        dot_color = {
            "auto": t.accent, "calc": t.amber, "manual": t.blue, "na": t.red,
        }
        for i, key in enumerate(_CARDS):
            stat = snapshot.get(key)
            # Sans sauvegarde lue, on affiche quand même le nom lisible, jamais la clé.
            label = stat.label if stat else STAT_DEFS.get(key, (key,))[0]
            value = format_stat(stat) if stat else "—"
            quality = stat.quality if stat else Q_NA
            quality_text = QUALITY_LABELS_FR[quality]
            card = QLabel(
                f"<span style='font-size:12px;color:{t.muted}'>{label}</span><br>"
                f"<span style='font-size:20px;font-weight:700'>{value}</span><br>"
                f"<span style='font-size:11px;color:{t.muted}'>"
                f"<span style='color:{dot_color[quality]}'>●</span> {quality_text}</span>",
                self.cards_box,
            )
            card.setToolTip(
                f"{QUALITY_LABELS_FR[quality]}" + (f"\n{stat.note}" if stat and stat.note else "")
            )
            card.setMinimumHeight(78)
            card.setProperty("role", "card")
            self.cards_grid.addWidget(card, i // 3, i % 3)

    def _fill_summary(self) -> None:
        s = summarize(self._career.objectives)
        self.progress_bar.setValue(round(s.percent))
        self.progress_bar.setFormat(f"Objectifs : {s.percent:.0f} %")
        extra = []
        if s.unavailable:
            extra.append(f"{s.unavailable} non disponibles")
        if s.manual:
            extra.append(f"{s.manual} à valider")
        if s.locked:
            extra.append(f"{s.locked} verrouillés")
        self.summary_label.setText(
            f"{s.completed} terminés · {s.in_progress} en cours · "
            f"{s.not_started} non commencés"
            + ("".join(f" · {e}" for e in extra))
        )
        level, into, need = level_for_xp(s.xp)
        badges = ", ".join(dict.fromkeys(s.badges)) or "aucun"
        money = ""
        if s.money_earned:
            money = (
                f" · versé : {format_value(s.money_claimed, '€')} sur "
                f"{format_value(s.money_earned, '€')} gagnés"
            )
        self.level_label.setText(
            f"Niveau {level} · {s.xp} XP ({into}/{need} avant le suivant) · badges : {badges}"
            + money
        )

    def _fill_windows(self) -> None:
        windows = self._career.windows
        self.windows_box.setVisible(bool(windows))
        self.windows_label.setText("<br>".join(window_line(w) for w in windows))

    def _fill_rewards(self) -> None:
        while self.rewards_layout.count():
            item = self.rewards_layout.takeAt(0)
            sub_layout = item.layout() if item is not None else None
            if sub_layout is not None:
                self._clear_layout(sub_layout)
        pending = [o for o in self._career.objectives if o.reward_state == RW_PENDING]
        self.rewards_box.setVisible(rewards_enabled(self._career.settings.mode) and bool(pending))
        for obj in pending:
            row = QHBoxLayout()
            row.addWidget(
                QLabel(f"{obj.name} : +{format_value(obj.reward.money, '€')}", self.rewards_box),
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
        names = {o.id: o.name for o in self._career.objectives}
        self.cards.set_groups(
            group_objectives(self._rows),
            lambda o: card_subtitle(
                o,
                CATEGORIES_FR.get(o.category, o.category),
                self._farm_label(o.farm) if o.farm else "",  # sans ferme : rien à dire
            ),
            lambda o: ", ".join(names.get(r, r) for r in o.requires),
        )
        if self._selected_id not in {o.id for o in self._rows}:
            self._selected_id = None
        self.cards.select(self._selected_id)
        self._update_actions()

    def _on_card_selected(self, objective_id: str) -> None:
        self._selected_id = objective_id
        self._update_actions()

    def _on_paid_toggled(self, objective_id: str, paid: bool) -> None:
        obj = next((o for o in self._rows if o.id == objective_id), None)
        if obj is None:
            return
        if set_reward_paid(obj, paid, self._career.settings.mode):
            self._reevaluate()  # may unlock the next step in "required rewards" mode
            # Deferred: rebuilding the cards inside their own signal is unsafe.
            QTimer.singleShot(0, self._persist_and_refresh)

    def _selected(self) -> Objective | None:
        return next((o for o in self._rows if o.id == self._selected_id), None)

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
            lines += [f"• {d}" for d in report.detected]
            if report.newly_completed:
                lines.append(f"{len(report.newly_completed)} objectif(s) terminé(s) !")
                lines += [f"   • {o.name}" for o in report.newly_completed]
            if report.newly_unlocked:
                lines.append(f"{len(report.newly_unlocked)} nouvel(s) objectif(s) débloqué(s) :")
                lines += [f"   • {o.name}" for o in report.newly_unlocked]
        self.sync_label.setText("<br>".join(lines))

    def _on_sync_clicked(self) -> None:
        report = sync_career(
            self._career, self._user_dir, self._install_dir, self._library_mods_dir
        )
        self._reload_farms()
        self._show_report(report)
        self._refresh()
        self.changed.emit()

    def _on_savegame_changed(self) -> None:
        self._career.settings.savegame = self.savegame_combo.currentData() or ""
        self._career.save()
        self._on_sync_clicked()

    def _on_farm_changed(self) -> None:
        previous = self._farm_label(self._career.snapshot.farm_id)
        pinned = self._career.set_tracked_farm(self.farm_combo.currentData() or "")
        self._career.save()
        self._on_sync_clicked()
        if pinned:
            self.sync_label.setText(
                f"{self.sync_label.text()}<br>{pinned} objectif(s) restent sur « {previous} »."
            )

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
        names += [f"{c.name} — {c.summary}" for c in CAMPAIGNS]
        choice, ok = QInputDialog.getItem(
            self, "Modèle d'objectifs", "Quelle carrière souhaitez-vous ?", names, 0, False
        )
        if not ok:
            return
        index = names.index(choice)
        farm = self._ask_farm()
        if farm is None:
            return
        if index < len(keys):
            tpl = TEMPLATES[keys[index]]
            added = self._career.add_objectives(build_template(tpl.key, farm))
            total, description = len(tpl.specs), tpl.description
        else:
            campaign = CAMPAIGNS[index - len(keys)]
            objectives = campaign.build(farm)
            added = self._career.add_objectives(objectives)
            total, description = len(objectives), campaign.description
        self._reevaluate()
        self._persist_and_refresh()
        QMessageBox.information(
            self, "Modèle", f"{added} objectif(s) ajouté(s) ({description})"
            + ("\nLes déjà présents ont été ignorés." if added < total else "")
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

    def _on_start_window(self) -> None:
        names = [c.name for c in WINDOW_PRESETS]
        choice, ok = QInputDialog.getItem(
            self, "Lancer un défi", "Quel défi lancer maintenant ?", names, 0, False
        )
        if not ok:
            return
        try:
            self._career.start_window(WINDOW_PRESETS[names.index(choice)])
        except CareerError as exc:
            QMessageBox.warning(self, "Défi", str(exc))
            return
        self._persist_and_refresh()

    def _on_parcel_areas(self) -> None:
        savegame_name = self._career.settings.savegame
        if not savegame_name:
            notify(self, "Associe d'abord une sauvegarde à ce profil.")
            return
        savegame = self._user_dir / savegame_name
        map_id = savegame_map_id(savegame)
        owned = owned_parcels(savegame)
        if not owned:
            notify(self, "Aucune parcelle possédée dans cette sauvegarde.")
            return
        mod_dirs = [d for d in (self._user_dir / "mods", self._library_mods_dir) if d is not None]
        areas = map_farmland_areas(map_id, self._install_dir, mod_dirs)
        names = {f.id: f.label for f in self._farms}
        rows = [
            (names.get(farm, f"Ferme {farm}"), pid, areas.areas.get(pid) if areas else None)
            for farm in sorted(owned, key=lambda f: (f != self._career.snapshot.farm_id, f))
            for pid in owned[farm]
        ]
        if areas is not None:
            note = f"Surfaces lues sur la carte ({areas.source})."
        elif is_dlc_map(map_id):
            note = "Carte DLC chiffrée : le jeu ne permet pas de lire ses surfaces."
        else:
            note = "Carte des parcelles introuvable (mod de la carte absent ?)."
        typed = dict(self._career.settings.parcel_areas.get(map_id, {}))
        dlg = ParcelAreasDialog(rows, typed, note, self)
        if dlg.exec() != dlg.DialogCode.Accepted or areas is not None and not dlg.typed_areas():
            return
        # Keep values typed for parcels not listed now (sold, other farm…).
        listed = {pid for _farm, pid, area in rows if area is None}
        merged = {pid: ha for pid, ha in typed.items() if pid not in listed}
        merged.update(dlg.typed_areas())
        if merged:
            self._career.settings.parcel_areas[map_id] = merged
        else:
            self._career.settings.parcel_areas.pop(map_id, None)
        self._career.save()
        self._on_sync_clicked()

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

