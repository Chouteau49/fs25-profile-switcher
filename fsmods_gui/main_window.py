"""Top-level window: profile list (left) + editor (right) + activate button.

The window owns an :class:`AppState` and orchestrates the workers. Widgets are
passive: they read state via setters, emit signals on user actions.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QSize
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .profiles.activator import ActivationReport
from .profiles.sync_back import (
    add_to_profile,
    compute_diff,
    import_into_library,
    remove_from_profile,
)
from .state import AppState
from .widgets.profile_editor import ProfileEditor
from .widgets.sync_dialog import (
    ADD_IGNORE,
    ADD_LIB_AND_PROFILE,
    ADD_LIB_ONLY,
    REMOVE_DROP,
    SyncDialog,
    UPDATE_IGNORE,
)
from .workers import ActivateWorker, GameWatcher, ScanWorker, make_worker_thread


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.setWindowTitle(f"FS Profile Switcher — {state.game_key}")
        self.resize(1200, 720)

        # ---- left: profile list + buttons
        self.profile_list = QListWidget(self)
        self.profile_list.currentRowChanged.connect(self._on_profile_row_changed)

        new_btn = QPushButton("➕ Nouveau", self)
        dup_btn = QPushButton("🗐 Dupliquer", self)
        del_btn = QPushButton("✖ Supprimer", self)
        new_btn.clicked.connect(self._on_new_profile)
        dup_btn.clicked.connect(self._on_duplicate_profile)
        del_btn.clicked.connect(self._on_delete_profile)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Profils", left_panel))
        left_layout.addWidget(self.profile_list, 1)
        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(dup_btn)
        btn_row.addWidget(del_btn)
        left_layout.addLayout(btn_row)

        # ---- right: editor + activate
        self.editor = ProfileEditor(self)
        self.editor.changed.connect(self._on_profile_changed)

        self.activate_btn = QPushButton("  Activer & lancer", self)
        self.activate_btn.setMinimumHeight(50)
        self.activate_btn.setIconSize(QSize(32, 32)) 
        self.activate_btn.clicked.connect(self._on_activate)
        
        # Try to find an icon
        provider = QFileIconProvider()
        self.activate_btn.setIcon(provider.icon(QFileIconProvider.IconType.File)) 

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        header = QHBoxLayout()
        header.addStretch(1)
        header.addWidget(self.activate_btn)
        right_layout.addLayout(header)
        right_layout.addWidget(self.editor, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar(self))

        toolbar = QToolBar("Principal", self)
        self.addToolBar(toolbar)
        rescan = QAction("🔄 Rescanner la bibliothèque", self)
        rescan.triggered.connect(self._on_rescan)
        toolbar.addAction(rescan)

        # ---- workers (kept as attributes so they survive the call)
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._activate_thread: QThread | None = None
        self._activate_worker: ActivateWorker | None = None
        self._progress: QProgressDialog | None = None

        self._watcher = GameWatcher(parent=self)
        self._watcher.started.connect(self._on_game_started)
        self._watcher.stopped.connect(self._on_game_stopped)
        self._watching_for_profile: str | None = None

        # ---- initial load
        self._refresh_profiles_ui()
        self._start_scan()

    # ============================================================ helpers

    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 5000)

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
                    self.profile_list.setCurrentRow(i)
                    break
        self.editor.set_profile(self.state.current_profile)

    def _on_profile_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.state.profiles):
            self.state.current_profile = None
        else:
            self.state.current_profile = self.state.profiles[row]
        self.editor.set_profile(self.state.current_profile)
        self._update_activate_btn_icon()

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
        new.description = src.description
        new.save()
        self._refresh_profiles_ui()

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

    def _on_profile_changed(self) -> None:
        path = self.state.save_current()
        if path is None:
            return
        # Sync the visible name in the list if it changed.
        if self.state.current_profile is not None:
            row = self.profile_list.currentRow()
            if row >= 0:
                self.profile_list.item(row).setText(self.state.current_profile.name)
        self._status(f"Profil enregistré : {path.name}")

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
        self.state.refresh_profiles()
        self._refresh_profiles_ui()
        self._status(f"Bibliothèque : {len(catalog)} mods")

    def _on_scan_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Scan échoué", message)

    def _on_rescan(self) -> None:
        self._start_scan()

    # ========================================================== activate

    def _on_activate(self) -> None:
        if self.state.current_profile is None:
            QMessageBox.information(self, "Aucun profil", "Sélectionne un profil.")
            return
        if self.state.catalog is None:
            QMessageBox.information(self, "Bibliothèque", "Scan en cours, réessaye.")
            return
        missing = self.state.current_profile.missing_against(self.state.catalog)
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
            return
        diff = compute_diff(profile, self.state.game, self.state.catalog)
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
        if changed:
            profile.save()
            self.editor.set_profile(profile)
            self._status("Profil mis à jour après synchronisation.")
        if errors:
            QMessageBox.warning(self, "Synchronisation : erreurs", "\n".join(errors))
