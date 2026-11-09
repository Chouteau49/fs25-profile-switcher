"""Top-level window: profile list (left) + editor (right) + activate button.

The window owns an :class:`AppState` and orchestrates the workers. Widgets are
passive: they read state via setters, emit signals on user actions.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QActionGroup, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import navigation as nav
from .app_logging import default_log_dir, set_error_listener
from .profiles.activator import ActivationReport, game_process_running
from .profiles.sync_back import (
    add_to_profile,
    compute_diff,
    import_into_library,
    remove_from_profile,
    snapshot_fingerprints,
)
from .state import AppState
from .widgets import icons
from .widgets.editor_panel import EditorPanel
from .widgets.home_page import HomePage
from .widgets.shell import SessionBar, SideNav, section_header
from .widgets.sync_dialog import (
    ADD_IGNORE,
    ADD_LIB_AND_PROFILE,
    ADD_LIB_ONLY,
    REMOVE_DROP,
    UPDATE_IGNORE,
    SyncDialog,
)
from .widgets.toast import Toast
from .workers import (
    ActivateWorker,
    ConfigBackupWorker,
    GameWatcher,
    ScanWorker,
    TestRunnerWorker,
    make_worker_thread,
)

if TYPE_CHECKING:
    from .profiles.profile import Profile
    from .widgets.testrunner_dialog import TestRunnerPanel

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    # Uncaught errors can come from any thread: a signal brings them back to the GUI.
    internal_error = Signal()

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.internal_error.connect(self._on_internal_error)
        set_error_listener(self.internal_error.emit)
        self.setWindowTitle(f"FS Profile Switcher v{__version__} — {state.game_key}")
        self.resize(1200, 720)

        # ---- sidebar lists: profiles and collections (select what the editor edits)
        self.profile_list = QListWidget(self)
        self.profile_list.setIconSize(QSize(22, 22))
        self.profile_list.currentRowChanged.connect(self._on_profile_row_changed)
        self.collection_list = QListWidget(self)
        self.collection_list.currentRowChanged.connect(self._on_collection_row_changed)

        # ---- profile page: unified editor (profile or collection) + play button
        self.editor = EditorPanel(self)
        self.editor.set_official_thumbnail_provider(self._official_thumbnail)
        self.editor.changed.connect(self._on_editor_changed)
        self.editor.mod_delete_requested.connect(self._on_delete_mods)
        self.editor.add_to_profile_requested.connect(self._add_mods_to_profile)
        self.editor.add_to_collection_requested.connect(self._add_mods_to_collection)

        self.activate_btn = QPushButton("Jouer", self)
        self.activate_btn.setProperty("variant", "primary")
        self.activate_btn.setToolTip("Active les mods du profil puis lance FS25 via Steam.")
        self.activate_btn.setMinimumHeight(44)
        self.activate_btn.setIconSize(QSize(28, 28))
        self.activate_btn.clicked.connect(self._on_activate)
        icons.bind(self.activate_btn, "play", icons.ROLE_ON_ACCENT)

        editor_page = QWidget(self)
        right_layout = QVBoxLayout(editor_page)
        right_layout.setContentsMargins(16, 12, 16, 8)
        header = QHBoxLayout()
        header.addStretch(1)
        header.addWidget(self.activate_btn)
        right_layout.addLayout(header)
        right_layout.addWidget(self.editor, 1)

        # ---- pages: one per sidebar section; a section with several views
        # shows them as sub-tabs. Each view is rebuilt from the current state
        # whenever it becomes visible (same behaviour as the former tabs).
        self._TAB_CAREER = nav.FEATURE_CAREER
        self._TAB_DUP = nav.FEATURE_DUPLICATES
        self._TAB_STATS = nav.FEATURE_STATS
        self._TAB_LOG = nav.FEATURE_LOG
        self._TAB_AUDIT = nav.FEATURE_AUDIT
        self._TAB_AUTODRIVE = nav.FEATURE_AUTODRIVE
        self._TAB_NEWMODS = nav.FEATURE_NEWMODS
        self._TAB_TESTRUNNER = nav.FEATURE_TESTRUNNER
        self._tab_builders = {
            self._TAB_CAREER: self._build_career_panel,
            self._TAB_DUP: self._build_duplicates_panel,
            self._TAB_STATS: self._build_stats_panel,
            self._TAB_LOG: self._build_log_panel,
            self._TAB_AUDIT: self._build_audit_panel,
            self._TAB_AUTODRIVE: self._build_autodrive_panel,
            self._TAB_NEWMODS: self._build_new_mods_panel,
            self._TAB_TESTRUNNER: self._build_testrunner_panel,
        }
        self._feature_panels: dict[str, QWidget] = {}
        self._feature_containers: dict[str, QWidget] = {}
        self._section_tabs: dict[str, QTabWidget] = {}
        self._section_pages: dict[str, int] = {}
        self.pages = QStackedWidget(self)
        self.home = HomePage(self)
        self.home.play_requested.connect(self._on_home_play)
        self.home.open_requested.connect(self._on_home_open)
        self.home.new_requested.connect(self._on_new_profile)
        self.home.inbox_requested.connect(lambda: self._show_section(nav.SECTION_LIBRARY))
        for section in nav.SECTIONS:
            if section.key == nav.SECTION_HOME:
                page: QWidget = self.home
                self._feature_containers[nav.FEATURE_HOME] = self.home
            elif section.key == nav.SECTION_PROFILES:
                page = editor_page
                self._feature_containers[nav.FEATURE_EDITOR] = editor_page
            elif len(section.features) == 1:
                page = self._make_tab_container()
                self._feature_containers[section.features[0].key] = page
            else:
                tabs = QTabWidget(self)
                tabs.setProperty("role", "subtabs")
                tabs.setDocumentMode(True)
                tabs.setIconSize(QSize(16, 16))
                for feature in section.features:
                    container = self._make_tab_container()
                    self._feature_containers[feature.key] = container
                    tabs.addTab(container, feature.label)
                tabs.currentChanged.connect(lambda _i: self._on_view_changed())
                self._section_tabs[section.key] = tabs
                page = QWidget(self)
                page_layout = QVBoxLayout(page)
                page_layout.setContentsMargins(8, 8, 8, 0)
                page_layout.addWidget(tabs)
            self._section_pages[section.key] = self.pages.addWidget(page)
        self._apply_tab_icons()

        # ---- sidebar
        self.sidebar = SideNav(self)
        self.sidebar.section_selected.connect(self._show_section)
        self.sidebar.add_widget(
            section_header(
                "Profils",
                [
                    ("plus", "Nouveau profil", self._on_new_profile),
                    ("copy", "Dupliquer le profil", self._on_duplicate_profile),
                    ("trash", "Supprimer le profil", self._on_delete_profile),
                ],
                self.sidebar,
            )
        )
        self.sidebar.add_widget(self.profile_list, 3)
        self.sidebar.add_widget(
            section_header(
                "Collections",
                [
                    ("plus", "Nouvelle collection", self._on_new_collection),
                    ("copy", "Dupliquer la collection", self._on_duplicate_collection),
                    ("trash", "Supprimer la collection", self._on_delete_collection),
                ],
                self.sidebar,
            )
        )
        self.sidebar.add_widget(self.collection_list, 2)
        self.sidebar.add_spacing(6)
        self.sidebar.add_widget(self._make_footer_buttons())

        self.session = SessionBar(self)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.pages, 1)
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(body, 1)
        central_layout.addWidget(self.session)
        self.setCentralWidget(central)
        self.toast = Toast(central, bottom_margin=self.session.sizeHint().height() + 14)
        self._activating_slug: str | None = None
        self._running_slug: str | None = None
        self.sidebar.set_current(nav.SECTION_HOME)
        self.pages.setCurrentIndex(self._section_pages[nav.SECTION_HOME])

        # ---- workers (kept as attributes so they survive the call)
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._activate_thread: QThread | None = None
        self._activating_profile: Profile | None = None
        self._activate_worker: ActivateWorker | None = None
        self._testrunner_thread: QThread | None = None
        self._testrunner_worker: TestRunnerWorker | None = None
        self._testrunner_panel: TestRunnerPanel | None = None

        self._backup_thread: QThread | None = None
        self._backup_worker: ConfigBackupWorker | None = None
        self._backup_pending = False
        self._backup_timer = QTimer(self)
        self._backup_timer.setSingleShot(True)
        self._backup_timer.setInterval(2000)  # coalesce bursts of edits
        self._backup_timer.timeout.connect(self._run_backup)

        self._watcher = GameWatcher(parent=self)
        self._watcher.started.connect(self._on_game_started)
        self._watcher.stopped.connect(self._on_game_stopped)
        self._watching_for_profile: str | None = None
        self._watching_baseline: dict[str, str] = {}

        # ---- initial load
        self._refresh_profiles_ui()
        self._refresh_session()
        self._start_scan()

        # Restore saved geometry (position + size)
        settings = QSettings()
        geometry: QByteArray = settings.value("mainWindow/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        QSettings().setValue("mainWindow/geometry", self.saveGeometry())
        set_error_listener(None)
        self._watcher.stop()

        # Gracefully stop background threads so Qt doesn't warn on exit
        for attr in ("_scan_thread", "_activate_thread", "_testrunner_thread", "_backup_thread"):
            thread = getattr(self, attr, None)
            if thread is not None and thread.isRunning():
                thread.quit()
                if not thread.wait(3000):
                    log.warning("Thread encore actif à la fermeture : %s", attr)

        super().closeEvent(event)

    # ============================================================ helpers

    def _request_backup(self) -> None:
        """Ask for a config backup; coalesced and run in a worker thread."""
        try:
            if not self.state.game.backup_targets:
                return
        except KeyError:
            return
        self._backup_timer.start()

    def _run_backup(self) -> None:
        if self._backup_thread is not None and self._backup_thread.isRunning():
            self._backup_pending = True  # rerun once the current one is done
            return
        self._backup_worker = ConfigBackupWorker(self.state)
        self._backup_worker.finished.connect(self._on_backup_done)
        self._backup_worker.failed.connect(lambda msg: self._status(f"Sauvegarde config : {msg}"))
        self._backup_thread = make_worker_thread(self._backup_worker)
        self._backup_thread.start()

    def _on_backup_done(self, reports: object) -> None:
        from datetime import datetime

        from .profiles.config_backup import summarize_reports

        if isinstance(reports, list) and reports:
            text = summarize_reports(reports)
            ok = all(r.ok for r in reports)
            self.session.set_backup(
                nav.backup_label(ok, datetime.now(), datetime.now()), text
            )
            if any(not r.ok or r.warnings for r in reports):
                log.warning(text)
            if not ok:
                self._status(text)
        if self._backup_pending:
            self._backup_pending = False
            self._backup_timer.start()

    # ============================================================ sidebar footer

    def _make_footer_buttons(self) -> QWidget:
        """Bas de la barre latérale : rescanner, outils (export, import, journal), thème."""
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        rescan = QToolButton(row)
        rescan.setProperty("role", "icon")
        rescan.setToolTip("Rescanner la bibliothèque")
        rescan.setAccessibleName("Rescanner la bibliothèque")
        icons.bind(rescan, "refresh", icons.ROLE_MUTED)
        rescan.clicked.connect(self._on_rescan)

        tools_menu = QMenu(self)
        export_action = tools_menu.addAction("Exporter la config…")
        icons.bind(export_action, "upload")
        export_action.triggered.connect(self._on_export_config)
        import_action = tools_menu.addAction("Importer une config…")
        icons.bind(import_action, "download")
        import_action.triggered.connect(self._on_import_config)
        tools_menu.addSeparator()
        log_action = tools_menu.addAction("Journal de l'appli")
        icons.bind(log_action, "file-text")
        log_action.setToolTip("Ouvre le dossier des journaux (erreurs internes, plantages).")
        log_action.triggered.connect(self._on_open_log_dir)
        tools = QToolButton(row)
        tools.setProperty("role", "icon")
        tools.setToolTip("Outils : export, import, journal")
        tools.setAccessibleName("Outils")
        tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tools.setMenu(tools_menu)
        icons.bind(tools, "settings", icons.ROLE_MUTED)

        theme_btn = QToolButton(row)
        theme_btn.setProperty("role", "icon")
        theme_btn.setToolTip("Thème : clair, sombre ou comme Windows")
        theme_btn.setAccessibleName("Thème")
        theme_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        theme_btn.setMenu(self._make_theme_menu())
        icons.bind(theme_btn, "palette", icons.ROLE_MUTED)

        for btn in (rescan, tools, theme_btn):
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(btn)
        lay.addStretch(1)
        return row

    # ============================================================ theme

    def _make_theme_menu(self) -> QMenu:
        """Menu « Thème » : système / clair / sombre (mémorisé)."""
        from . import theme as theme_mod
        from .widgets import theming

        menu = QMenu(self)
        group = QActionGroup(self)
        current = theming.saved_mode()
        for mode, label in (
            (theme_mod.MODE_SYSTEM, "Comme Windows"),
            (theme_mod.MODE_LIGHT, "Clair"),
            (theme_mod.MODE_DARK, "Sombre"),
        ):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(mode == current)
            group.addAction(act)
            act.triggered.connect(lambda _checked=False, m=mode: self._set_theme(m))
        return menu

    def _set_theme(self, mode: str) -> None:
        from .widgets import theming

        app = QApplication.instance()
        if isinstance(app, QApplication):
            theming.set_mode(app, mode)
            self._apply_tab_icons()

    def _apply_tab_icons(self) -> None:
        for section in nav.SECTIONS:
            tabs = self._section_tabs.get(section.key)
            if tabs is None:
                continue
            for index, feature in enumerate(section.features):
                tabs.setTabIcon(index, icons.icon(feature.icon))

    def _status(self, msg: str) -> None:
        self.session.flash(msg)

    def notify(
        self,
        message: str,
        action_label: str | None = None,
        action=None,
        *,
        error: bool = False,
    ) -> None:
        """Notification non bloquante (remplace les fenêtres d'information)."""
        self.toast.show_message(message, action_label, action, error=error)

    # ============================================================ home

    def _refresh_home(self) -> None:
        from datetime import datetime

        from .home import build_cards

        catalog = self.state.catalog
        map_titles = (
            {e.filename: e.display_title for e in catalog.maps()} if catalog else {}
        )
        counts: dict[str, int] = {}
        if catalog is not None:
            for prof in self.state.profiles:
                counts[prof.slug] = len(self.state.effective_filenames(prof))
        cards = build_cards(self.state.profiles, counts, map_titles, datetime.now())
        pixmaps: dict[str, QPixmap | None] = {}
        for prof in self.state.profiles:
            path = self._profile_icon_path(prof)
            pixmaps[prof.slug] = QPixmap(path) if path else None
        self.home.set_cards(cards, pixmaps)
        self.home.set_activity(self._activating_slug, self._running_slug)
        try:
            inbox = self.state.game.inbox_dir_effective
        except KeyError:
            inbox = None
        from .profiles.inbox import count_waiting

        self.home.set_waiting(count_waiting(inbox))

    def _profile_by_slug(self, slug: str):
        return next((p for p in self.state.profiles if p.slug == slug), None)

    def _on_home_play(self, slug: str) -> None:
        prof = self._profile_by_slug(slug)
        if prof is None:
            return
        self._select_profile_row(prof)
        self._on_activate()

    def _on_home_open(self, slug: str) -> None:
        prof = self._profile_by_slug(slug)
        if prof is None:
            return
        self._select_profile_row(prof)
        self._show_section(nav.SECTION_PROFILES)

    def _select_profile_row(self, prof) -> None:
        """Sélectionne un profil dans la liste latérale sans changer d'écran."""
        row = self.state.profiles.index(prof)
        self.profile_list.blockSignals(True)
        self.profile_list.setCurrentRow(row)
        self.profile_list.blockSignals(False)
        self._select_profile(prof)

    def _on_internal_error(self) -> None:
        self.session.flash("⚠ Erreur interne : détails dans Outils › Journal de l'appli.", 15000)

    def _on_open_log_dir(self) -> None:
        folder = default_log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ============================================================ session bar

    def _refresh_session(self) -> None:
        """Profil installé dans le jeu (dernier joué) et badge « à ranger »."""
        from .profiles.inbox import count_waiting
        from .profiles.profile import most_recently_played

        played = most_recently_played(self.state.profiles)
        self.session.set_active_profile(played.name if played else None)
        try:
            inbox = self.state.game.inbox_dir_effective
        except KeyError:
            inbox = None
        waiting = count_waiting(inbox)
        self.sidebar.set_badge(nav.SECTION_LIBRARY, waiting)
        library_btn = self.sidebar.button(nav.SECTION_LIBRARY)
        base_tip = nav.section(nav.SECTION_LIBRARY).tooltip
        library_btn.setToolTip(
            f"{base_tip}\n{waiting} mod(s) en attente dans _inbox "
            "(le dossier Téléchargements est examiné à l'ouverture de la vue)."
            if waiting
            else base_tip
        )

    # ====================================================== navigation

    def _make_tab_container(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        return container

    def _set_tab_content(self, key: str, widget: QWidget) -> None:
        """Replace a view's content with a freshly built panel."""
        container = self._feature_containers.get(key)
        layout = container.layout() if container is not None else None
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            old = item.widget() if item is not None else None
            if old is not None:
                old.deleteLater()
        layout.addWidget(widget)
        self._feature_panels[key] = widget

    def _rebuild_feature_tab(self, key: str) -> None:
        builder = self._tab_builders.get(key)
        if builder is not None:
            self._set_tab_content(key, builder())

    def _visible_feature(self) -> str | None:
        """Vue actuellement affichée (clé de :mod:`navigation`)."""
        current = self.sidebar.current()
        if current is None:
            return None
        section = nav.section(current)
        tabs = self._section_tabs.get(current)
        if tabs is not None:
            return section.features[max(0, tabs.currentIndex())].key
        return section.features[0].key

    def _on_view_changed(self) -> None:
        # Rebuild from current state every time a view becomes visible.
        key = self._visible_feature()
        if key is not None:
            self._rebuild_feature_tab(key)

    def _show_section(self, key: str) -> None:
        self.sidebar.set_current(key)
        self.pages.setCurrentIndex(self._section_pages[key])
        if key == nav.SECTION_HOME:
            self._refresh_home()
        self._on_view_changed()

    def _show_feature_tab(self, key: str) -> None:
        """Afficher une vue (reconstruite même si elle est déjà visible)."""
        section = nav.section_of(key)
        tabs = self._section_tabs.get(section.key)
        if tabs is not None:
            index = [f.key for f in section.features].index(key)
            tabs.blockSignals(True)
            tabs.setCurrentIndex(index)
            tabs.blockSignals(False)
        self._show_section(section.key)

    # ---- builders: each returns the panel to show in its tab

    def _build_duplicates_panel(self) -> QWidget:
        if self.state.catalog is None:
            return QLabel("Scan de la bibliothèque en cours… réessaie dans un instant.")
        from .widgets.duplicates_dialog import DuplicatesPanel

        return DuplicatesPanel(self.state.catalog)

    def _build_stats_panel(self) -> QWidget:
        if self.state.catalog is None:
            return QLabel("Scan de la bibliothèque en cours… réessaie dans un instant.")
        from .widgets.stats_dashboard import StatsPanel

        return StatsPanel(
            self.state.catalog, self.state.profiles, self.state.collections
        )

    def _career_dir_and_user_dir(self, profile) -> tuple[Path, Path] | None:
        try:
            game = self.state.game
            careers = game.library_careers_dir
            user_dir = game.mods_dir.parent
        except KeyError:
            return None
        if careers is None:
            return None
        from .career.store import career_dir_for

        return career_dir_for(careers, profile.slug), user_dir

    def _game_install_dir(self) -> Path | None:
        try:
            return self.state.game.install_dir
        except KeyError:
            return None

    def _library_mods_dir(self) -> Path | None:
        try:
            return self.state.game.library_mods_dir
        except KeyError:
            return None

    def _sync_career(self, profile):
        """Load a profile's career, link its savegame if obvious, and sync it.

        Returns ``(career, report)``; ``report`` is ``None`` when nothing was synced.
        """
        from .career.store import Career
        from .career.sync import guess_savegame, sync_career

        dirs = self._career_dir_and_user_dir(profile)
        if dirs is None:
            return None, None
        career_dir, user_dir = dirs
        career = Career.load(career_dir)
        if not career.settings.savegame:
            career.settings.savegame = guess_savegame(
                profile.map_mod, user_dir, profile.official_map
            )
        if not career.settings.savegame:
            return career, None
        return career, sync_career(
            career, user_dir, self._game_install_dir(), self._library_mods_dir()
        )

    def _build_career_panel(self) -> QWidget:
        profile = self.state.current_profile
        if profile is None:
            return QLabel("Sélectionne un profil à gauche pour voir sa carrière.")
        from .career.store import CareerError
        from .widgets.career_panel import CareerPanel

        try:
            career, report = self._sync_career(profile)
        except CareerError as exc:
            return QLabel(f"Données de carrière illisibles :\n{exc}")
        dirs = self._career_dir_and_user_dir(profile)
        if career is None or dirs is None:
            return QLabel("Jeu ou bibliothèque non configuré.")
        panel = CareerPanel(
            profile.name,
            career,
            dirs[1],
            report,
            install_dir=self._game_install_dir(),
            library_mods_dir=self._library_mods_dir(),
        )
        panel.changed.connect(self._request_backup)
        if report is not None and report.ok:
            self._request_backup()
        return panel

    def _build_log_panel(self) -> QWidget:
        try:
            mods_dir = self.state.game.mods_dir
        except KeyError:
            return QLabel("Jeu non configuré.")
        from .profiles.log_analyzer import analyze_log, log_path_for
        from .widgets.log_report_dialog import LogReportPanel

        log_path = log_path_for(mods_dir)
        if not log_path.is_file():
            return QLabel(f"Aucun fichier log.txt trouvé :\n{log_path}")
        return LogReportPanel(analyze_log(log_path), log_path=str(log_path))

    def _build_audit_panel(self) -> QWidget:
        profile = self.state.current_profile
        if profile is None:
            return QLabel("Sélectionne un profil à gauche pour l'auditer.")
        try:
            user_dir = self.state.game.mods_dir.parent
        except KeyError:
            return QLabel("Jeu non configuré.")
        from .widgets.savegame_audit_dialog import SavegameAuditPanel

        panel = SavegameAuditPanel(
            profile,
            self.state.catalog,
            user_dir,
            collection_mods=self.state.collection_mods_map(),
        )
        panel.apply_requested.connect(
            lambda rem, add, p=profile: self._apply_audit(p, rem, add)
        )
        panel.delete_requested.connect(self._delete_from_audit)
        return panel

    def _delete_from_audit(self, filenames: list[str]) -> None:
        """Delete the selected mods from the library, then re-audit."""
        if not filenames or self.state.catalog is None:
            return
        entries = [
            self.state.catalog.entries[f]
            for f in filenames
            if f in self.state.catalog.entries
        ]
        if not entries:
            return
        self._on_delete_mods(entries)
        self._rebuild_feature_tab(self._TAB_AUDIT)

    def _build_autodrive_panel(self) -> QWidget:
        try:
            game = self.state.game
        except KeyError:
            return QLabel("Jeu non configuré.")
        from .profiles.autodrive import scan_packs
        from .widgets.autodrive_dialog import AutoDrivePanel

        lib = game.library_autodrive_dir
        panel = AutoDrivePanel(
            game.new_mod_source_dirs(), game.mods_dir.parent, library_dir=lib
        )
        panel.rescan_requested.connect(
            lambda: panel.set_packs(scan_packs(game.new_mod_source_dirs(), lib))
        )
        panel.install_requested.connect(lambda: self._install_autodrive(panel))
        panel.import_requested.connect(lambda: self._import_autodrive(panel))
        return panel

    def _import_autodrive(self, panel) -> None:
        """Move the selected route pack from downloads into the AutoDrive library."""
        from .profiles.autodrive import import_pack, scan_packs

        pack = panel.selected_pack()
        lib = self.state.game.library_autodrive_dir
        if pack is None or lib is None or pack.in_library:
            return
        try:
            dest = import_pack(pack, lib)
        except (OSError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Import AutoDrive", f"Échec de l'import : {exc}")
            return
        panel.set_packs(scan_packs(self.state.game.new_mod_source_dirs(), lib))
        self._status(f"Pack AutoDrive importé dans la bibliothèque : {dest.name}")

    def _build_new_mods_panel(self) -> QWidget:
        try:
            game = self.state.game
        except KeyError:
            return QLabel("Jeu non configuré.")
        if game.library_mods_dir is None:
            return QLabel(
                f"Bibliothèque non configurée : renseigne "
                f"games.{self.state.game_key}.library_dir dans config.yaml."
            )
        if self.state.catalog is None:
            return QLabel("Scan de la bibliothèque en cours… réessaie dans un instant.")
        from .widgets.new_mods_dialog import NewModsPanel

        panel = NewModsPanel(self._scan_new_mods(), self.state)
        panel.rescan_requested.connect(
            lambda: panel.set_pending(self._scan_new_mods())
        )
        panel.import_requested.connect(
            lambda plans: self._apply_new_mods_import(panel, plans)
        )
        panel.test_requested.connect(
            lambda paths, p=panel: self._test_new_mods(p, paths)
        )
        return panel

    def _test_new_mods(self, panel, paths: list) -> None:
        """Validate downloaded mods (source paths) before they enter the library."""
        from pathlib import Path as _Path

        zip_paths = [_Path(p) for p in paths if p]
        if not zip_paths:
            return
        game = self.state.game
        exe_path = game.testrunner_exe
        if exe_path is not None and not exe_path.is_file():
            exe_path = None
        xsd_path = game.find_moddesc_xsd()

        panel.set_test_running(True)
        self._testrunner_worker = TestRunnerWorker(
            zip_paths,
            xsd_path=xsd_path,
            testrunner_exe=exe_path,
            editor_exe=game.editor_exe,
        )
        self._testrunner_worker.progress.connect(panel.set_test_progress)
        self._testrunner_worker.finished.connect(
            lambda results, p=panel: self._on_new_mods_test_done(p, results)
        )
        self._testrunner_worker.failed.connect(
            lambda msg, p=panel: (p.set_test_running(False), p.flash_status(msg, error=True))
        )
        self._testrunner_thread = make_worker_thread(self._testrunner_worker)
        self._testrunner_thread.start()
        self._status(f"Validation de {len(zip_paths)} mod(s) téléchargé(s)…")

    def _on_new_mods_test_done(self, panel, results: object) -> None:
        panel.set_test_running(False)
        if not isinstance(results, list):
            return
        panel.set_test_results(results)
        self._status(f"Test des nouveaux mods terminé : {len(results)} mod(s).")

    def _build_testrunner_panel(self) -> QWidget:
        try:
            game = self.state.game
        except KeyError:
            return QLabel("Jeu non configuré.")
        if game.library_mods_dir is None:
            return QLabel(
                f"Bibliothèque non configurée : renseigne "
                f"games.{self.state.game_key}.library_dir dans config.yaml."
            )
        if self.state.catalog is None:
            return QLabel("Scan de la bibliothèque en cours… réessaie dans un instant.")
        from .widgets.testrunner_dialog import TestRunnerPanel

        panel = TestRunnerPanel(self.state)
        panel.run_requested.connect(
            lambda scope, exe, p=panel: self._run_testrunner(p, scope, exe)
        )
        panel.delete_requested.connect(
            lambda fns, p=panel: self._delete_from_testrunner(p, fns)
        )
        self._testrunner_panel = panel
        return panel

    def _delete_from_testrunner(self, panel, filenames: list[str]) -> None:
        """Delete faulty mods from the library, then drop them from the results."""
        if not filenames or self.state.catalog is None:
            return
        entries = [
            self.state.catalog.entries[f]
            for f in filenames
            if f in self.state.catalog.entries
        ]
        if not entries:
            return
        self._on_delete_mods(entries)
        # Drop from the panel whatever actually got deleted (gone from catalog).
        deleted = [f for f in filenames if f not in self.state.catalog.entries]
        if deleted:
            panel.remove_results(deleted)

    # ========================================================= test runner

    def _run_testrunner(self, panel, scope: str, exe_text: str) -> None:
        from pathlib import Path as _Path

        from .widgets.testrunner_dialog import SCOPE_PROFILE

        if self.state.catalog is None:
            self.notify("Scan en cours, réessaye.")
            return
        mods_dir = self.state.game.library_mods_dir
        if mods_dir is None:
            return

        if scope == SCOPE_PROFILE:
            profile = self.state.current_profile
            if profile is None:
                self.notify("Sélectionne un profil à tester.")
                return
            filenames = self.state.effective_filenames(profile)
        else:
            filenames = sorted(self.state.catalog.entries)
        zip_paths = [mods_dir / f for f in filenames]
        if not zip_paths:
            self.notify("Aucun mod à valider pour cette portée.")
            return

        exe_path: _Path | None = None
        if exe_text:
            exe_path = _Path(exe_text).expanduser()
            if not exe_path.is_file():
                QMessageBox.warning(
                    self,
                    "TestRunner introuvable",
                    f"Le fichier indiqué n'existe pas :\n{exe_path}\n\n"
                    "Les tests utiliseront uniquement les contrôles intégrés.",
                )
                exe_path = None

        xsd_path = self.state.game.find_moddesc_xsd()

        panel.set_running(True)
        self._testrunner_worker = TestRunnerWorker(
            zip_paths,
            xsd_path=xsd_path,
            testrunner_exe=exe_path,
            editor_exe=self.state.game.editor_exe,
        )
        self._testrunner_worker.progress.connect(panel.set_progress)
        self._testrunner_worker.finished.connect(
            lambda results, p=panel: self._on_testrunner_done(p, results)
        )
        self._testrunner_worker.failed.connect(
            lambda msg, p=panel: self._on_testrunner_failed(p, msg)
        )
        self._testrunner_thread = make_worker_thread(self._testrunner_worker)
        self._testrunner_thread.start()
        self._status(f"Validation de {len(zip_paths)} mod(s)…")

    def _on_testrunner_done(self, panel, results: object) -> None:
        panel.set_running(False)
        if not isinstance(results, list):
            return
        panel.set_results(results)
        from .widgets.testrunner_dialog import STATUS_KO, STATUS_WARN

        ko = sum(1 for r in results if r.status == STATUS_KO)
        warn = sum(1 for r in results if r.status == STATUS_WARN)
        self._status(
            f"Tests terminés : {len(results)} mod(s) — {ko} KO, {warn} à vérifier."
        )

    def _on_testrunner_failed(self, panel, message: str) -> None:
        panel.set_running(False)
        QMessageBox.warning(self, "Validation échouée", message)

    # =========================================================== profiles

    def _official_thumbnail(self, map_id: str) -> Path | None:
        from .profiles.official_maps import official_map_thumbnail

        try:
            game = self.state.game
        except KeyError:
            return None
        return official_map_thumbnail(map_id, game.install_dir, game.library_cache_dir)

    def _profile_icon_path(self, prof) -> str | None:
        """Icon of a profile's map: the map mod's icon, or the official map thumbnail."""
        if prof.map_mod:
            entry = self.state.catalog.entries.get(prof.map_mod) if self.state.catalog else None
            return entry.icon_cache_path if entry and entry.icon_cache_path else None
        if prof.official_map:
            thumb = self._official_thumbnail(prof.official_map)
            return str(thumb) if thumb else None
        return None

    def _refresh_profiles_ui(self) -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for prof in self.state.profiles:
            item = QListWidgetItem(prof.name)

            # Map icon decoration (map mod icon, or official map thumbnail)
            icon_path = self._profile_icon_path(prof)
            if icon_path:
                pix = QPixmap(icon_path)
                if not pix.isNull():
                    item.setIcon(QIcon(pix))

            item.setData(Qt.ItemDataRole.UserRole, prof.slug)
            self.profile_list.addItem(item)
        self.profile_list.blockSignals(False)
        if self.state.current_profile is not None:
            slug = self.state.current_profile.slug
            for i in range(self.profile_list.count()):
                if self.profile_list.item(i).data(Qt.ItemDataRole.UserRole) == slug:
                    self.profile_list.blockSignals(True)
                    self.profile_list.setCurrentRow(i)
                    self.profile_list.blockSignals(False)
                    break
            self._select_profile(self.state.current_profile)
        else:
            self.editor.set_target(None)

    def _refresh_collections_ui(self) -> None:
        self.collection_list.blockSignals(True)
        self.collection_list.clear()
        for col in self.state.collections:
            item = QListWidgetItem(f"{col.name}  ({len(col.mods)})")
            item.setData(Qt.ItemDataRole.UserRole, col.slug)
            self.collection_list.addItem(item)
        self.collection_list.blockSignals(False)

    # ---- active-target selection (mutually exclusive between the two lists)

    def _select_profile(self, prof) -> None:
        self.collection_list.blockSignals(True)
        self.collection_list.setCurrentRow(-1)
        self.collection_list.blockSignals(False)
        self.state.current_profile = prof
        self.editor.set_target(prof)
        self.activate_btn.setEnabled(True)
        self._update_activate_btn_icon()
        if self._visible_feature() == self._TAB_CAREER:
            self._rebuild_feature_tab(self._TAB_CAREER)

    def _select_collection(self, col) -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.setCurrentRow(-1)
        self.profile_list.blockSignals(False)
        self.editor.set_target(col)
        self.activate_btn.setEnabled(False)

    def _on_profile_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.state.profiles):
            return
        self._select_profile(self.state.profiles[row])
        # Choisir un profil ouvre son éditeur, sauf depuis Carrière (qui suit le profil).
        if self.sidebar.current() != nav.SECTION_CAREER:
            self._show_section(nav.SECTION_PROFILES)

    def _on_collection_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.state.collections):
            return
        self._select_collection(self.state.collections[row])
        self._show_section(nav.SECTION_PROFILES)

    def _update_activate_btn_icon(self) -> None:
        prof = self.state.current_profile
        name = prof.name if prof else ""
        self.activate_btn.setText(f"Jouer · {name}" if name else "Jouer")

    def _on_new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau profil", "Nom du profil :")
        if not ok or not name.strip():
            return
        try:
            profile = self.state.new_profile(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        self._refresh_profiles_ui()
        self._ask_career_scenario(profile)
        self._request_backup()

    def _ask_career_scenario(self, profile) -> None:
        """Offer a career type for a new profile and create its starting objectives."""
        from .career.store import Career, CareerError
        from .career.templates import SCENARIOS, build_template

        dirs = self._career_dir_and_user_dir(profile)
        if dirs is None:
            return
        labels = [label for label, _key in SCENARIOS]
        choice, ok = QInputDialog.getItem(
            self,
            "Type de carrière",
            f"Quel type de carrière souhaitez-vous pour « {profile.name} » ?\n"
            "(des objectifs adaptés sont créés ; modifiable dans l'onglet Carrière)",
            labels,
            0,
            False,
        )
        template_key = dict(SCENARIOS).get(choice) if ok else None
        if template_key is None:
            return
        try:
            career = Career.load(dirs[0])
            career.add_objectives(build_template(template_key))
            career.save()
            self._request_backup()
        except (CareerError, OSError) as exc:
            QMessageBox.warning(self, "Carrière", f"Objectifs non créés : {exc}")

    def _on_duplicate_profile(self) -> None:
        src = self.state.current_profile
        if src is None:
            return
        name, ok = QInputDialog.getText(
            self, "Dupliquer", "Nom du nouveau profil :", text=f"{src.name} (copie)"
        )
        if not ok or not name.strip():
            return
        try:
            new = self.state.new_profile(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        new.mods = list(src.mods)
        new.map_mod = src.map_mod
        new.official_map = src.official_map
        new.collections = list(src.collections)
        new.excluded_mods = list(src.excluded_mods)
        new.description = src.description
        new.save()
        self._refresh_profiles_ui()
        self._request_backup()

    def _on_delete_profile(self) -> None:
        prof = self.state.current_profile
        if prof is None:
            return
        confirm = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer définitivement le profil « {prof.name} » et sa carrière "
            "(objectifs, surfaces saisies) ?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.state.delete_profile(prof)
        self._refresh_profiles_ui()
        self._request_backup()

    def _on_editor_changed(self) -> None:
        target = self.editor.current_target()
        if target is None:
            return
        from .profiles.collection import Collection

        if isinstance(target, Collection):
            target.save()
            row = self.collection_list.currentRow()
            if row >= 0:
                self.collection_list.item(row).setText(
                    f"{target.name}  ({len(target.mods)})"
                )
            # Inherited-collection counts in the editor may need refreshing.
            self.editor.set_collections(self.state.collections)
            self._request_backup()
            self._status(f"Collection enregistrée : {target.name}")
            return

        # Profile
        path = self.state.save_current()
        if path is None:
            return
        row = self.profile_list.currentRow()
        if row >= 0:
            item = self.profile_list.item(row)
            item.setText(target.name)
            icon_path = self._profile_icon_path(target)
            pix = QPixmap(icon_path) if icon_path else QPixmap()
            item.setIcon(QIcon(pix) if not pix.isNull() else QIcon())
        self._update_activate_btn_icon()
        self._request_backup()
        self._status(f"Profil enregistré : {path.name}")

    def _add_mods_to_profile(self, filenames: list[str]) -> None:
        """Add the given mods to a profile chosen by the user (e.g. from a collection)."""
        filenames = [f for f in filenames if f]
        if not filenames:
            return
        if not self.state.profiles:
            self.notify("Crée d'abord un profil pour y ajouter des mods.")
            return
        names = [p.name for p in self.state.profiles]
        choice, ok = QInputDialog.getItem(
            self,
            "Ajouter à un profil",
            f"Ajouter {len(filenames)} mod(s) au profil :",
            names,
            0,
            False,
        )
        if not ok or not choice:
            return
        prof = self.state.profiles[names.index(choice)]
        added = 0
        for fname in filenames:
            entry = self.state.catalog.get(fname) if self.state.catalog else None
            if entry is not None and entry.is_map:
                if not prof.map_mod:
                    prof.map_mod = fname
                    added += 1
                continue
            if fname not in prof.mods:
                prof.mods.append(fname)
                if fname in prof.excluded_mods:
                    prof.excluded_mods.remove(fname)
                added += 1
        if added:
            prof.save()
            self._request_backup()
            # Reflect the change if that profile is the one being edited.
            if (
                self.state.current_profile is not None
                and prof.slug == self.state.current_profile.slug
            ):
                self.editor.set_target(prof)
            self._status(f"{added} mod(s) ajouté(s) au profil « {prof.name} ».")
            self.notify(f"{added} mod(s) ajouté(s) au profil « {prof.name} ».")
        else:
            self._status(f"Aucun mod ajouté : déjà présents dans « {prof.name} ».")

    def _add_mods_to_collection(self, filenames: list[str]) -> None:
        """Add the given mods to a collection chosen by the user (no duplicates)."""
        filenames = [f for f in filenames if f]
        if not filenames:
            return
        if not self.state.collections:
            self.notify("Crée d'abord une collection pour y ajouter des mods.")
            return
        names = [c.name for c in self.state.collections]
        choice, ok = QInputDialog.getItem(
            self,
            "Ajouter à une collection",
            f"Ajouter {len(filenames)} mod(s) à la collection :",
            names,
            0,
            False,
        )
        if not ok or not choice:
            return
        col = self.state.collections[names.index(choice)]
        added = 0
        maps_skipped = 0
        for fname in filenames:
            entry = self.state.catalog.get(fname) if self.state.catalog else None
            if entry is not None and entry.is_map:
                maps_skipped += 1
                continue
            if fname not in col.mods:  # no duplicates
                col.mods.append(fname)
                added += 1
        if added:
            col.save()
            self._request_backup()
            # Refresh collection counts + the editor (inherited list / content).
            self.editor.set_collections(self.state.collections)
            self._refresh_collections_ui()
            target = self.editor.current_target()
            from .profiles.collection import Collection

            if isinstance(target, Collection) and target.slug == col.slug:
                self.editor.set_target(col)
            self._status(f"{added} mod(s) ajouté(s) à la collection « {col.name} ».")
        msg = (
            f"{added} mod(s) ajouté(s) à la collection « {col.name} »."
            if added
            else f"Aucun mod ajouté : déjà présents dans « {col.name} »."
        )
        if maps_skipped:
            msg += (
                f"\n\n{maps_skipped} carte(s) ignorée(s) : une carte ne peut pas "
                "faire partie d'une collection (c'est un choix propre à chaque profil)."
            )
        self.notify(msg)

    # ========================================================== collections

    def _on_new_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvelle collection", "Nom :")
        if not ok or not name.strip():
            return
        try:
            col = self.state.new_collection(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        self.editor.set_collections(self.state.collections)
        self._refresh_collections_ui()
        self._select_collection_slug(col.slug)
        self._request_backup()

    def _on_duplicate_collection(self) -> None:
        src = self._current_collection()
        if src is None:
            return
        name, ok = QInputDialog.getText(
            self, "Dupliquer", "Nom :", text=f"{src.name} (copie)"
        )
        if not ok or not name.strip():
            return
        try:
            new = self.state.new_collection(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        new.mods = list(src.mods)
        new.description = src.description
        new.save()
        self.editor.set_collections(self.state.collections)
        self._refresh_collections_ui()
        self._select_collection_slug(new.slug)
        self._request_backup()

    def _on_delete_collection(self) -> None:
        col = self._current_collection()
        if col is None:
            return
        confirm = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer la collection « {col.name} » ?\n"
            f"Elle sera retirée des profils qui l'utilisent.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        affected = self.state.delete_collection(col)
        self.editor.set_collections(self.state.collections)
        self.editor.set_target(None)
        self._refresh_collections_ui()
        self._request_backup()
        if affected:
            self.notify("Retirée des profils : " + ", ".join(affected))

    def _current_collection(self):
        row = self.collection_list.currentRow()
        if 0 <= row < len(self.state.collections):
            return self.state.collections[row]
        return None

    def _select_collection_slug(self, slug: str) -> None:
        for i in range(self.collection_list.count()):
            if self.collection_list.item(i).data(Qt.ItemDataRole.UserRole) == slug:
                self.collection_list.setCurrentRow(i)
                return

    # ===================================================== delete from library

    def _on_delete_mods(self, entries: list) -> None:
        if not entries:
            return
        if self.state.catalog is None:
            self.notify("Scan en cours, réessaye.")
            return
        names = [e.filename for e in entries]
        preview = "\n".join(
            f"• {e.display_title} ({e.filename})" for e in entries[:12]
        )
        extra = f"\n… (+{len(entries) - 12} autres)" if len(entries) > 12 else ""
        confirm = QMessageBox.question(
            self,
            "Supprimer de la bibliothèque",
            f"Supprimer définitivement {len(entries)} mod(s) ?\n\n{preview}{extra}\n\n"
            "Le(s) fichier(s) .zip seront effacés du disque et retirés de tous les "
            "profils et collections.\nCette action est irréversible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        target = self.editor.current_target()
        result = self.state.delete_mods(names)

        # Refresh everything that referenced the catalog / mod lists.
        self.editor.set_catalog(self.state.catalog)
        self.editor.set_collections(self.state.collections)
        self._refresh_collections_ui()
        self._refresh_profiles_ui()
        # Re-apply the active target (a collection selection is lost above).
        from .profiles.collection import Collection

        if isinstance(target, Collection):
            self._select_collection_slug(target.slug)
        elif target is not None:
            self.editor.set_target(target)
        self._request_backup()

        msg = f"{len(result.removed_files)} fichier(s) supprimé(s)."
        if result.affected_profiles:
            msg += "\nProfils mis à jour : " + ", ".join(result.affected_profiles)
        if result.affected_collections:
            msg += "\nCollections mises à jour : " + ", ".join(
                result.affected_collections
            )
        self._status(f"{len(result.removed_files)} mod(s) supprimé(s).")
        self.notify(msg)

    # ============================================================= scan

    def _start_scan(self) -> None:
        try:
            game = self.state.game
        except KeyError:
            return
        if game.library_mods_dir is None:
            QMessageBox.warning(
                self,
                "Bibliothèque non configurée",
                f"Renseigne games.{self.state.game_key}.library_dir dans config.yaml.",
            )
            return
        game.library_mods_dir.mkdir(parents=True, exist_ok=True)
        cache = game.library_cache_dir / "index.json" if game.library_cache_dir else None
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
        self._scan_worker = ScanWorker(game.library_mods_dir, cache)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_thread = make_worker_thread(self._scan_worker)
        self._scan_thread.start()
        self._status("Scan de la bibliothèque…")

    def _on_scan_done(self, catalog: object) -> None:
        from .profiles.catalog import Catalog as _Catalog
        if not isinstance(catalog, _Catalog):
            return
        self.state.catalog = catalog
        self.editor.set_catalog(catalog)
        self.state.refresh_collections()
        self.editor.set_collections(self.state.collections)
        self._refresh_collections_ui()
        self.state.refresh_profiles()
        self.state.detect_official_maps()
        self._refresh_profiles_ui()
        self.session.set_library(len(catalog))
        self._refresh_session()
        self._refresh_home()
        self._warn_broken_configs()

    def _warn_broken_configs(self) -> None:
        broken = self.state.broken_configs
        if not broken:
            return
        for path, reason in broken:
            log.error("Fichier de config illisible : %s (%s)", path, reason)
        names = "\n".join(f"• {path.name}" for path, _reason in broken[:10])
        targets = self.state.game.backup_targets
        hint = (
            f"\n\nUne copie saine se trouve sans doute dans {targets[0]}."
            if targets
            else ""
        )
        QMessageBox.warning(
            self,
            "Fichiers illisibles",
            f"{len(broken)} fichier(s) de config n'ont pas pu être lus et sont ignorés :\n"
            f"{names}{hint}",
        )

    def _on_scan_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Scan échoué", message)

    def _on_rescan(self) -> None:
        self._start_scan()

    # =================================================== new mods (download)

    def _scan_new_mods(self):
        """Scan the source folders with a wait cursor; return pending mods."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return self.state.scan_new_mods()
        finally:
            QApplication.restoreOverrideCursor()

    def _apply_new_mods_import(self, dlg, plans: list) -> None:
        if not plans:
            return
        result = self.state.import_new_mods(plans)
        if result.affected_profiles or result.affected_collections:
            self._request_backup()
        self._refresh_session()

        # Refresh everything the import may have touched.
        self.editor.set_catalog(self.state.catalog)
        self.editor.set_collections(self.state.collections)
        self._refresh_collections_ui()
        target = self.editor.current_target()
        self._refresh_profiles_ui()
        from .profiles.collection import Collection

        if isinstance(target, Collection):
            self._select_collection_slug(target.slug)
        elif target is not None:
            self.editor.set_target(target)

        # Drop the imported rows; the dialog keeps the rest for further work.
        dlg.remove_imported(result.imported)

        msg = f"{len(result.imported)} mod(s) importé(s)."
        extras = []
        if result.affected_profiles:
            extras.append("profils : " + ", ".join(result.affected_profiles))
        if result.affected_collections:
            extras.append("collections : " + ", ".join(result.affected_collections))
        if extras:
            msg += " (" + " ; ".join(extras) + ")"
        self._status(f"{len(result.imported)} nouveau(x) mod(s) importé(s).")
        dlg.flash_status(
            msg + (f"  ⚠ {len(result.errors)} erreur(s)." if result.errors else ""),
            error=bool(result.errors),
        )
        if result.errors:
            QMessageBox.warning(
                self,
                "Import : erreurs",
                msg + "\n\nErreurs :\n" + "\n".join(result.errors[:10]),
            )

    # =================================================== config backup (#4)

    def _on_export_config(self) -> None:
        try:
            game = self.state.game
        except KeyError:
            return
        if game.library_profiles_dir is None:
            QMessageBox.warning(self, "Export", "Bibliothèque non configurée.")
            return
        from datetime import date

        default_name = f"{self.state.game_key}-config-{date.today().isoformat()}.zip"
        dest, _ = QFileDialog.getSaveFileName(
            self, "Exporter la config", default_name, "Archives ZIP (*.zip)"
        )
        if not dest:
            return
        from .profiles.config_backup import export_config

        try:
            path = export_config(
                game.library_profiles_dir,
                game.library_collections_dir,
                Path(dest),
                game.library_careers_dir,
            )
        except OSError as exc:
            QMessageBox.critical(self, "Export échoué", str(exc))
            return
        self._status(f"Config exportée : {path.name}")
        self.notify(f"Profils, collections et carrières exportés vers :\n{path}")

    def _on_import_config(self) -> None:
        try:
            game = self.state.game
        except KeyError:
            return
        if game.library_profiles_dir is None or game.library_collections_dir is None:
            QMessageBox.warning(self, "Import", "Bibliothèque non configurée.")
            return
        src, _ = QFileDialog.getOpenFileName(
            self, "Importer une config", "", "Archives ZIP (*.zip)"
        )
        if not src:
            return
        from .profiles.config_backup import MODE_MERGE, MODE_REPLACE, import_config

        box = QMessageBox(self)
        box.setWindowTitle("Importer la config")
        box.setText(
            "Comment importer les profils, collections et carrières de cette archive ?"
        )
        box.setInformativeText(
            "Fusionner : ajoute/écrase par nom, garde les autres.\n"
            "Remplacer : efface d'abord les profils/collections actuels "
            "(et les carrières si l'archive en contient)."
        )
        merge_btn = box.addButton("Fusionner", QMessageBox.ButtonRole.AcceptRole)
        replace_btn = box.addButton("Remplacer", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is merge_btn:
            mode = MODE_MERGE
        elif clicked is replace_btn:
            mode = MODE_REPLACE
        else:
            return

        try:
            result = import_config(
                Path(src),
                game.library_profiles_dir,
                game.library_collections_dir,
                mode=mode,
                careers_dir=game.library_careers_dir,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import échoué", str(exc))
            return

        # Reload everything from disk and refresh the UI.
        self.state.refresh_collections()
        self.editor.set_collections(self.state.collections)
        self._refresh_collections_ui()
        self.state.refresh_profiles()
        self._refresh_profiles_ui()
        self._request_backup()
        self.notify(f"{result.profiles_imported} profil(s) et "
            f"{result.collections_imported} collection(s) et "
            f"{result.careers_imported} carrière(s) importé(s)"
            + (" (remplacement)." if result.replaced else " (fusion)."))

    def _apply_audit(self, profile, remove: list[str], add: list[str]) -> None:
        changed = False
        for fname in remove:
            if fname == profile.map_mod:
                profile.map_mod = None
                changed = True
            elif fname in profile.mods:
                profile.mods.remove(fname)
                changed = True
            elif fname not in profile.excluded_mods:
                # Inherited from a collection — exclude it for this profile.
                profile.excluded_mods.append(fname)
                changed = True
        for fname in add:
            if fname != profile.map_mod and fname not in profile.mods:
                profile.mods.append(fname)
                changed = True
        if changed:
            profile.save()
            self.editor.set_target(profile)
            self._request_backup()
            self._status(
                f"Profil mis à jour après audit : "
                f"-{len(remove)} / +{len(add)} mod(s)."
            )
            # Re-audit so the panel reflects the updated profile.
            self._rebuild_feature_tab(self._TAB_AUDIT)

    def _install_autodrive(self, panel) -> None:
        from .profiles.autodrive import install_pack

        pack = panel.selected_pack()
        savegame = panel.selected_savegame()
        if pack is None or savegame is None:
            return

        result = install_pack(pack, savegame, backup=panel.backup_enabled())
        if result.installed:
            lines = [
                f"{len(result.installed)} fichier(s) installé(s) dans "
                f"{savegame.name} : {', '.join(result.installed)}."
            ]
            if result.backed_up:
                lines.append("Sauvegardes : " + " ; ".join(result.backed_up))
            self._status(
                f"AutoDrive : {len(result.installed)} fichier(s) installé(s) "
                f"dans {savegame.name}."
            )
            if result.errors:
                QMessageBox.warning(
                    self,
                    "Routes AutoDrive",
                    "\n".join(lines) + "\n\nErreurs :\n" + "\n".join(result.errors),
                )
            else:
                self.notify("\n".join(lines))
        else:
            QMessageBox.warning(
                self,
                "Routes AutoDrive",
                "Aucun fichier installé.\n\n" + "\n".join(result.errors),
            )

    # ========================================================== activate

    def _on_activate(self) -> None:
        if self.state.current_profile is None:
            self.notify("Sélectionne un profil.")
            return
        if game_process_running(self.state.game_key):
            QMessageBox.warning(
                self,
                "Jeu en cours",
                "Farming Simulator est lancé : ses mods sont utilisés.\n"
                "Ferme le jeu, puis active le profil.",
            )
            return
        if self.state.catalog is None:
            self.notify("Scan en cours, réessaye.")
            return
        missing = self.state.current_profile.missing_against(
            self.state.catalog, self.state.collection_mods_map()
        )
        if missing:
            preview = "\n".join(missing[:10])
            extra = f"\n… (+{len(missing) - 10} autres)" if len(missing) > 10 else ""
            ans = QMessageBox.question(
                self,
                "Mods manquants",
                f"{len(missing)} mod(s) du profil ne sont pas dans la "
                f"bibliothèque :\n\n{preview}{extra}\n\nContinuer quand même ?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        self._launch_activate(launch_after=True)

    def _launch_activate(self, *, launch_after: bool) -> None:
        profile = self.state.current_profile
        if profile is None or self.state.catalog is None:
            return
        self._activating_profile = profile
        self._activating_slug = profile.slug
        self.session.set_game(nav.GAME_ACTIVATING)
        self.home.set_activity(self._activating_slug, self._running_slug)
        self.activate_btn.setEnabled(False)
        self.activate_btn.setText("Activation…")

        self._activate_worker = ActivateWorker(
            profile,
            self.state.game,
            self.state.catalog,
            launch_after=launch_after,
            mod_filenames=self.state.effective_filenames(profile),
        )
        self._activate_worker.progress.connect(self._on_activate_progress)
        self._activate_worker.finished.connect(self._on_activate_done)
        self._activate_worker.failed.connect(self._on_activate_failed)
        self._activate_thread = make_worker_thread(self._activate_worker)
        self._activate_thread.start()

    def _on_activate_progress(self, current: int, total: int, message: str) -> None:
        # Progress may arrive after _on_activate_done: ignore it then.
        slug = self._activating_slug
        if slug is None:
            return
        percent = int(current * 100 / total) if total else 0
        self.home.set_progress(slug, percent, message)
        self.session.flash(message, 3000)

    def _end_activation(self) -> None:
        self._activating_slug = None
        self.session.set_game(nav.GAME_CLOSED)
        self.activate_btn.setEnabled(self.state.current_profile is not None)
        self._update_activate_btn_icon()

    def _on_activate_done(self, report: object, launched: bool) -> None:
        self._end_activation()
        if not isinstance(report, ActivationReport):
            self._refresh_home()
            return
        log.info(
            "Activation de %s : %d activés, %d mis à l'abri, %d manquants, %d erreurs",
            report.profile_name, len(report.activated), len(report.rescued),
            len(report.missing), len(report.errors),
        )
        for path in report.rescued:
            log.info("Mis à l'abri : %s", path)
        for name, message in report.errors:
            log.error("Activation, %s : %s", name, message)
        played = self._activating_profile
        if played is not None and played.path is not None and not report.errors:
            played.mark_played()  # the app reopens on this profile next time
            played.save()
            self._request_backup()
        from .profiles.activator import activation_summary

        summary = activation_summary(report, launched)
        if report.errors:
            errs = "\n".join(f"{name}: {msg}" for name, msg in report.errors[:5])
            QMessageBox.warning(self, "Activation : erreurs", f"{errs}\n\n{summary}")
        elif report.rescued:
            self.notify(
                summary, "Ranger", lambda: self._show_section(nav.SECTION_LIBRARY)
            )
        else:
            self.notify(summary)
        if launched and self.state.current_profile is not None:
            self._running_slug = self.state.current_profile.slug
            self._watching_for_profile = self.state.current_profile.slug
            self._watching_baseline = snapshot_fingerprints(
                self.state.game.mods_dir,
                self.state.effective_filenames(self.state.current_profile),
            )
            self._watcher.start()
        self._refresh_session()
        self._refresh_home()

    def _on_activate_failed(self, message: str) -> None:
        self._end_activation()
        self._refresh_home()
        QMessageBox.critical(self, "Activation échouée", message)

    # ============================================================ watcher

    def _on_game_started(self) -> None:
        self.session.set_game(nav.GAME_RUNNING)
        self.home.set_activity(self._activating_slug, self._running_slug)
        self._status("FS25 détecté en cours d'exécution.")

    def _on_game_stopped(self) -> None:
        self.session.set_game(nav.GAME_CLOSED)
        self._running_slug = None
        self._status("FS25 fermé — vérification de la synchronisation…")
        try:
            mods_dir = self.state.game.mods_dir
        except KeyError:
            mods_dir = None
        self._sync_career_after_game()
        self._reconcile_after_game()
        self._refresh_session()
        self._refresh_home()
        # Analyse du log FS25 de la session qui vient de se terminer : on ouvre
        # l'onglet Log uniquement si des problèmes sont détectés.
        if mods_dir is not None:
            from .profiles.log_analyzer import analyze_log, log_path_for

            log_path = log_path_for(mods_dir)
            if log_path.is_file() and analyze_log(log_path):
                self._show_feature_tab(self._TAB_LOG)
                self._status("Log FS25 : problèmes détectés — voir Diagnostic › Log FS25.")
            else:
                self._status("Log FS25 : aucun problème détecté.")

    def _sync_career_after_game(self) -> None:
        """Refresh the career of the profile that was just played."""
        slug = self._watching_for_profile
        profile = next((p for p in self.state.profiles if p.slug == slug), None)
        if profile is None:
            return
        from .career.store import CareerError

        try:
            _career, report = self._sync_career(profile)
        except CareerError:
            return
        if report is None or not report.ok:
            return
        self._request_backup()
        if report.newly_completed:
            self._status(f"🎉 {len(report.newly_completed)} objectif(s) de carrière terminé(s) !")
            self._show_feature_tab(self._TAB_CAREER)

    def _reconcile_after_game(self) -> None:
        if self.state.catalog is None or self._watching_for_profile is None:
            return
        # Use whichever profile was active when we started watching, even if the
        # user has since clicked another in the GUI.
        profile = next(
            (p for p in self.state.profiles if p.slug == self._watching_for_profile),
            None,
        )
        self._watching_for_profile = None
        if profile is None:
            self._watching_baseline = {}
            return
        diff = compute_diff(
            profile,
            self.state.game,
            self.state.catalog,
            baseline=self._watching_baseline,
            effective=self.state.effective_filenames(profile),
        )
        self._watching_baseline = {}
        if not diff.has_changes:
            self._status("Aucune différence détectée après la partie.")
            return
        dlg = SyncDialog(diff, profile.name, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        self._apply_sync_choices(
            profile,
            diff,
            dlg.added_actions(),
            dlg.updated_actions(),
            dlg.removed_actions(),
        )

    def _apply_sync_choices(
        self,
        profile,  # Profile
        diff,
        added: dict[str, str],
        updated: dict[str, str],
        removed: dict[str, str],
    ) -> None:
        catalog = self.state.catalog
        if catalog is None:
            return
        changed = False
        errors: list[str] = []
        for fname, action in added.items():
            if action == ADD_IGNORE:
                continue
            try:
                import_into_library(fname, self.state.game, catalog)
            except (OSError, ValueError) as exc:
                errors.append(f"{fname}: {exc}")
                continue
            if action == ADD_LIB_AND_PROFILE:
                if add_to_profile(profile, fname):
                    changed = True
            elif action == ADD_LIB_ONLY:
                pass
        for fname, action in updated.items():
            if action == UPDATE_IGNORE:
                continue
            try:
                import_into_library(fname, self.state.game, catalog)
            except (OSError, ValueError) as exc:
                errors.append(f"{fname}: {exc}")
        for fname, action in removed.items():
            if action == REMOVE_DROP and remove_from_profile(profile, fname):
                changed = True

        # Save catalog if any mods were imported (added or updated)
        any_imported = any(
            action != ADD_IGNORE for action in added.values()
        ) or any(
            action != UPDATE_IGNORE for action in updated.values()
        )
        if any_imported and self.state.game.library_cache_dir:
            cache_path = self.state.game.library_cache_dir / "index.json"
            catalog.save_cache(cache_path)

        if changed:
            profile.save()
            self.editor.set_target(profile)
            self._request_backup()
            self._status("Profil mis à jour après synchronisation.")
        if errors:
            QMessageBox.warning(self, "Synchronisation : erreurs", "\n".join(errors))
