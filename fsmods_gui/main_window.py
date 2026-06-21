"""Top-level window: profile list (left) + editor (right) + activate button.

The window owns an :class:`AppState` and orchestrates the workers. Widgets are
passive: they read state via setters, emit signals on user actions.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .profiles.activator import ActivationReport
from .profiles.sync_back import (
    add_to_profile,
    compute_diff,
    import_into_library,
    remove_from_profile,
    snapshot_hashes,
)
from .state import AppState
from .widgets.editor_panel import EditorPanel
from .widgets.sync_dialog import (
    ADD_IGNORE,
    ADD_LIB_AND_PROFILE,
    ADD_LIB_ONLY,
    REMOVE_DROP,
    UPDATE_IGNORE,
    SyncDialog,
)
from .workers import (
    ActivateWorker,
    GameWatcher,
    ScanWorker,
    TestRunnerWorker,
    make_worker_thread,
)


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.setWindowTitle(f"FS Profile Switcher v{__version__} — {state.game_key}")
        self.resize(1200, 720)

        # ---- left: profile list + collection list + buttons
        self.profile_list = QListWidget(self)
        self.profile_list.currentRowChanged.connect(self._on_profile_row_changed)

        new_btn = QPushButton("➕ Nouveau", self)
        dup_btn = QPushButton("🗐 Dupliquer", self)
        del_btn = QPushButton("✖ Supprimer", self)
        new_btn.clicked.connect(self._on_new_profile)
        dup_btn.clicked.connect(self._on_duplicate_profile)
        del_btn.clicked.connect(self._on_delete_profile)

        self.collection_list = QListWidget(self)
        self.collection_list.currentRowChanged.connect(self._on_collection_row_changed)
        cnew_btn = QPushButton("➕ Nouvelle", self)
        cdup_btn = QPushButton("🗐 Dupliquer", self)
        cdel_btn = QPushButton("✖ Supprimer", self)
        cnew_btn.clicked.connect(self._on_new_collection)
        cdup_btn.clicked.connect(self._on_duplicate_collection)
        cdel_btn.clicked.connect(self._on_delete_collection)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        self._left_version_label = QLabel(f"FS Profile Switcher v{__version__}", left_panel)
        self._left_version_label.setStyleSheet(
            "QLabel { font-weight: 700; color: #2b6cb0; padding-bottom: 4px; }"
        )
        left_layout.addWidget(self._left_version_label)
        left_layout.addWidget(QLabel("Profils", left_panel))
        left_layout.addWidget(self.profile_list, 2)
        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(dup_btn)
        btn_row.addWidget(del_btn)
        left_layout.addLayout(btn_row)
        left_layout.addWidget(QLabel("🗂️ Collections", left_panel))
        left_layout.addWidget(self.collection_list, 1)
        cbtn_row = QHBoxLayout()
        cbtn_row.addWidget(cnew_btn)
        cbtn_row.addWidget(cdup_btn)
        cbtn_row.addWidget(cdel_btn)
        left_layout.addLayout(cbtn_row)

        # ---- right: unified editor (profile or collection) + activate
        self.editor = EditorPanel(self)
        self.editor.changed.connect(self._on_editor_changed)
        self.editor.mod_delete_requested.connect(self._on_delete_mods)

        self.activate_btn = QPushButton("  Activer & lancer", self)
        self.activate_btn.setMinimumHeight(50)
        self.activate_btn.setIconSize(QSize(32, 32)) 
        self.activate_btn.clicked.connect(self._on_activate)
        
        # Try to find an icon
        provider = QFileIconProvider()
        self.activate_btn.setIcon(provider.icon(QFileIconProvider.IconType.File)) 

        editor_tab = QWidget(self)
        right_layout = QVBoxLayout(editor_tab)
        header = QHBoxLayout()
        header.addStretch(1)
        self._header_version_label = QLabel(f"Version {__version__}", self)
        self._header_version_label.setStyleSheet(
            "QLabel {"
            "padding: 4px 10px;"
            "border: 1px solid #888;"
            "border-radius: 10px;"
            "font-weight: 600;"
            "}"
        )
        header.addWidget(self._header_version_label)
        header.addWidget(self.activate_btn)
        right_layout.addLayout(header)
        right_layout.addWidget(self.editor, 1)

        # ---- right side is a tab stack: editor + feature panels (no popups)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(editor_tab, "📝 Éditeur")
        self._feature_panels: dict[int, QWidget] = {}
        self._TAB_DUP = self.tabs.addTab(self._make_tab_container(), "🧬 Doublons")
        self._TAB_STATS = self.tabs.addTab(self._make_tab_container(), "📊 Statistiques")
        self._TAB_LOG = self.tabs.addTab(self._make_tab_container(), "📋 Log FS25")
        self._TAB_AUDIT = self.tabs.addTab(
            self._make_tab_container(), "🔍 Audit sauvegarde"
        )
        self._TAB_AUTODRIVE = self.tabs.addTab(
            self._make_tab_container(), "🛣 Routes AutoDrive"
        )
        self._TAB_NEWMODS = self.tabs.addTab(
            self._make_tab_container(), "📥 Nouveaux mods"
        )
        self._TAB_TESTRUNNER = self.tabs.addTab(
            self._make_tab_container(), "🧪 Tester les mods"
        )
        self._tab_builders = {
            self._TAB_DUP: self._build_duplicates_panel,
            self._TAB_STATS: self._build_stats_panel,
            self._TAB_LOG: self._build_log_panel,
            self._TAB_AUDIT: self._build_audit_panel,
            self._TAB_AUTODRIVE: self._build_autodrive_panel,
            self._TAB_NEWMODS: self._build_new_mods_panel,
            self._TAB_TESTRUNNER: self._build_testrunner_panel,
        }
        self.tabs.currentChanged.connect(self._on_tab_changed)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar(self))
        self._version_label = QLabel(f"Version {__version__}", self)
        self.statusBar().addPermanentWidget(self._version_label)

        # The library/maintenance views (Doublons, Stats, Log, Audit, AutoDrive,
        # Nouveaux mods) live in the tab stack on the right — no toolbar button
        # duplicates them. The toolbar only keeps actions without a tab.
        toolbar = QToolBar("Principal", self)
        self.addToolBar(toolbar)
        rescan = QAction("🔄 Rescanner la bibliothèque", self)
        rescan.triggered.connect(self._on_rescan)
        toolbar.addAction(rescan)
        toolbar.addSeparator()
        export_action = QAction("📤 Exporter config", self)
        export_action.triggered.connect(self._on_export_config)
        toolbar.addAction(export_action)
        import_action = QAction("📥 Importer config", self)
        import_action.triggered.connect(self._on_import_config)
        toolbar.addAction(import_action)
        toolbar.addSeparator()
        version_action = QAction(f"Version {__version__}", self)
        version_action.setEnabled(False)
        toolbar.addAction(version_action)

        # ---- workers (kept as attributes so they survive the call)
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._activate_thread: QThread | None = None
        self._activate_worker: ActivateWorker | None = None
        self._progress: QProgressDialog | None = None
        self._testrunner_thread: QThread | None = None
        self._testrunner_worker: TestRunnerWorker | None = None
        self._testrunner_panel = None

        self._watcher = GameWatcher(parent=self)
        self._watcher.started.connect(self._on_game_started)
        self._watcher.stopped.connect(self._on_game_stopped)
        self._watching_for_profile: str | None = None
        self._watching_hashes: dict[str, str] = {}

        # ---- initial load
        self._refresh_profiles_ui()
        self._start_scan()

    # ============================================================ helpers

    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)

    # ====================================================== feature tabs

    def _make_tab_container(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        return container

    def _set_tab_content(self, index: int, widget: QWidget) -> None:
        """Replace a feature tab's content with a freshly built panel."""
        container = self.tabs.widget(index)
        layout = container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.deleteLater()
        layout.addWidget(widget)
        self._feature_panels[index] = widget

    def _rebuild_feature_tab(self, index: int) -> None:
        builder = self._tab_builders.get(index)
        if builder is not None:
            self._set_tab_content(index, builder())

    def _on_tab_changed(self, index: int) -> None:
        # Rebuild from current state every time a feature tab becomes visible.
        self._rebuild_feature_tab(index)

    def _show_feature_tab(self, index: int) -> None:
        """Switch to a feature tab (rebuilding even if it is already current)."""
        if self.tabs.currentIndex() == index:
            self._rebuild_feature_tab(index)
        else:
            self.tabs.setCurrentIndex(index)

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

        panel = AutoDrivePanel(game.new_mod_source_dirs(), game.mods_dir.parent)
        panel.rescan_requested.connect(
            lambda: panel.set_packs(scan_packs(game.new_mod_source_dirs()))
        )
        panel.install_requested.connect(lambda: self._install_autodrive(panel))
        return panel

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
        return panel

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
        self._testrunner_panel = panel
        return panel

    # ========================================================= test runner

    def _run_testrunner(self, panel, scope: str, exe_text: str) -> None:
        from pathlib import Path as _Path

        from .widgets.testrunner_dialog import SCOPE_PROFILE

        if self.state.catalog is None:
            QMessageBox.information(self, "Bibliothèque", "Scan en cours, réessaye.")
            return
        mods_dir = self.state.game.library_mods_dir
        if mods_dir is None:
            return

        if scope == SCOPE_PROFILE:
            profile = self.state.current_profile
            if profile is None:
                QMessageBox.information(
                    self, "Aucun profil", "Sélectionne un profil à tester."
                )
                return
            filenames = self.state.effective_filenames(profile)
        else:
            filenames = sorted(self.state.catalog.entries)
        zip_paths = [mods_dir / f for f in filenames]
        if not zip_paths:
            QMessageBox.information(
                self, "Rien à tester", "Aucun mod à valider pour cette portée."
            )
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
            zip_paths, xsd_path=xsd_path, testrunner_exe=exe_path
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

    def _refresh_profiles_ui(self) -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for prof in self.state.profiles:
            item = QListWidgetItem(prof.name)

            # Map icon decoration
            if prof.map_mod and self.state.catalog:
                entry = self.state.catalog.entries.get(prof.map_mod)
                if entry and entry.icon_cache_path:
                    pix = QPixmap(entry.icon_cache_path)
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

    def _on_collection_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.state.collections):
            return
        self._select_collection(self.state.collections[row])

    def _update_activate_btn_icon(self) -> None:
        prof = self.state.current_profile
        if prof and prof.map_mod and self.state.catalog:
            entry = self.state.catalog.entries.get(prof.map_mod)
            if entry and entry.icon_cache_path:
                pix = QPixmap(entry.icon_cache_path)
                if not pix.isNull():
                    self.activate_btn.setIcon(QIcon(pix))
                    return
        
        # Fallback
        provider = QFileIconProvider()
        self.activate_btn.setIcon(provider.icon(QFileIconProvider.IconType.File))

    def _on_new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau profil", "Nom du profil :")
        if not ok or not name.strip():
            return
        try:
            self.state.new_profile(name.strip())
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "Création impossible", str(exc))
            return
        self._refresh_profiles_ui()
        self.state.backup_config()

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
        new.collections = list(src.collections)
        new.excluded_mods = list(src.excluded_mods)
        new.description = src.description
        new.save()
        self._refresh_profiles_ui()
        self.state.backup_config()

    def _on_delete_profile(self) -> None:
        prof = self.state.current_profile
        if prof is None:
            return
        confirm = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer définitivement le profil « {prof.name} » ?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.state.delete_profile(prof)
        self._refresh_profiles_ui()
        self.state.backup_config()

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
            self.state.backup_config()
            self._status(f"Collection enregistrée : {target.name}")
            return

        # Profile
        path = self.state.save_current()
        if path is None:
            return
        row = self.profile_list.currentRow()
        if row >= 0:
            self.profile_list.item(row).setText(target.name)
        self._update_activate_btn_icon()
        self.state.backup_config()
        self._status(f"Profil enregistré : {path.name}")

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
        self.state.backup_config()

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
        self.state.backup_config()

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
        self.state.backup_config()
        if affected:
            QMessageBox.information(
                self,
                "Collection supprimée",
                "Retirée des profils : " + ", ".join(affected),
            )

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
            QMessageBox.information(self, "Bibliothèque", "Scan en cours, réessaye.")
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
        self.state.backup_config()

        msg = f"{len(result.removed_files)} fichier(s) supprimé(s)."
        if result.affected_profiles:
            msg += "\nProfils mis à jour : " + ", ".join(result.affected_profiles)
        if result.affected_collections:
            msg += "\nCollections mises à jour : " + ", ".join(
                result.affected_collections
            )
        self._status(f"{len(result.removed_files)} mod(s) supprimé(s).")
        QMessageBox.information(self, "Suppression terminée", msg)

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
        self._refresh_profiles_ui()
        self._status(f"Bibliothèque : {len(catalog)} mods")

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
                game.library_profiles_dir, game.library_collections_dir, Path(dest)
            )
        except OSError as exc:
            QMessageBox.critical(self, "Export échoué", str(exc))
            return
        self._status(f"Config exportée : {path.name}")
        QMessageBox.information(
            self,
            "Export terminé",
            f"Profils + collections exportés vers :\n{path}",
        )

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
            "Comment importer les profils et collections de cette archive ?"
        )
        box.setInformativeText(
            "Fusionner : ajoute/écrase par nom, garde les autres.\n"
            "Remplacer : efface d'abord les profils/collections actuels."
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
        self.state.backup_config()
        QMessageBox.information(
            self,
            "Import terminé",
            f"{result.profiles_imported} profil(s) et "
            f"{result.collections_imported} collection(s) importé(s)"
            + (" (remplacement)." if result.replaced else " (fusion)."),
        )

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
            self.state.backup_config()
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
                QMessageBox.information(
                    self, "Routes AutoDrive", "\n".join(lines)
                )
        else:
            QMessageBox.warning(
                self,
                "Routes AutoDrive",
                "Aucun fichier installé.\n\n" + "\n".join(result.errors),
            )

    # ========================================================== activate

    def _on_activate(self) -> None:
        if self.state.current_profile is None:
            QMessageBox.information(self, "Aucun profil", "Sélectionne un profil.")
            return
        if self.state.catalog is None:
            QMessageBox.information(self, "Bibliothèque", "Scan en cours, réessaye.")
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
        self._progress = QProgressDialog(
            "Activation…", "Annuler", 0, 100, self
        )
        self._progress.setWindowTitle("Activation du profil")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setAutoClose(True)
        self._progress.setCancelButton(None)  # cancel unsupported
        self._progress.setMinimumDuration(0)
        self._progress.show()

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
        # Progress signal might arrive after _on_activate_done has cleared _progress
        progress = self._progress
        if progress is None:
            return
        progress.setMaximum(total)
        progress.setValue(current)
        progress.setLabelText(message)

    def _on_activate_done(self, report: object, launched: bool) -> None:
        if self._progress is not None:
            self._progress.setValue(self._progress.maximum())
            self._progress = None
        if not isinstance(report, ActivationReport):
            return
        summary = (
            f"{len(report.activated)} mod(s) activé(s) "
            f"({sum(1 for m in report.activated if m.method == 'hardlink')} hardlinks, "
            f"{sum(1 for m in report.activated if m.method == 'copy')} copies)."
        )
        if report.missing:
            summary += f"\n⚠ {len(report.missing)} manquant(s) ignoré(s)."
        if report.errors:
            errs = "\n".join(f"{name}: {msg}" for name, msg in report.errors[:5])
            QMessageBox.warning(self, "Activation : erreurs", errs)
        else:
            QMessageBox.information(
                self,
                "Activation OK",
                summary + ("\n✓ FS25 lancé." if launched else ""),
            )
        if launched and self.state.current_profile is not None:
            self._watching_for_profile = self.state.current_profile.slug
            self._watching_hashes = snapshot_hashes(
                self.state.game.mods_dir,
                self.state.effective_filenames(self.state.current_profile),
            )
            self._watcher.start()

    def _on_activate_failed(self, message: str) -> None:
        if self._progress is not None:
            self._progress.cancel()
            self._progress = None
        QMessageBox.critical(self, "Activation échouée", message)

    # ============================================================ watcher

    def _on_game_started(self) -> None:
        self._status("FS25 détecté en cours d'exécution.")

    def _on_game_stopped(self) -> None:
        self._status("FS25 fermé — vérification de la synchronisation…")
        try:
            mods_dir = self.state.game.mods_dir
        except KeyError:
            mods_dir = None
        self._reconcile_after_game()
        # Analyse du log FS25 de la session qui vient de se terminer : on ouvre
        # l'onglet Log uniquement si des problèmes sont détectés.
        if mods_dir is not None:
            from .profiles.log_analyzer import analyze_log, log_path_for

            log_path = log_path_for(mods_dir)
            if log_path.is_file() and analyze_log(log_path):
                self._show_feature_tab(self._TAB_LOG)
                self._status("Log FS25 : problèmes détectés — voir l'onglet « Log FS25 ».")
            else:
                self._status("Log FS25 : aucun problème détecté.")

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
            self._watching_hashes = {}
            return
        diff = compute_diff(
            profile,
            self.state.game,
            self.state.catalog,
            baseline_hashes=self._watching_hashes,
        )
        self._watching_hashes = {}
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
        changed = False
        errors: list[str] = []
        for fname, action in added.items():
            if action == ADD_IGNORE:
                continue
            try:
                import_into_library(fname, self.state.game, self.state.catalog)
            except (FileNotFoundError, ValueError) as exc:
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
                import_into_library(fname, self.state.game, self.state.catalog)
            except (FileNotFoundError, ValueError) as exc:
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
            self.state.catalog.save_cache(cache_path)
        
        if changed:
            profile.save()
            self.editor.set_target(profile)
            self.state.backup_config()
            self._status("Profil mis à jour après synchronisation.")
        if errors:
            QMessageBox.warning(self, "Synchronisation : erreurs", "\n".join(errors))
