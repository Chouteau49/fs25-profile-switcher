"""Background workers: catalog scan, profile activation, FS25 process watcher.

Each worker is a :class:`QObject` moved to its own :class:`QThread` so the UI
never blocks. Use signals for progress + completion.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from .config import GameProfile
from .profiles.activator import (
    activate_profile,
    game_process_running,
    launch_game,
)
from .profiles.catalog import Catalog, scan_library
from .profiles.profile import Profile

log = logging.getLogger(__name__)


class ScanWorker(QObject):
    """Scan the library mods folder. Emits :attr:`finished` with the new catalog."""

    finished = Signal(object)  # Catalog
    failed = Signal(str)

    def __init__(self, mods_dir: Path, cache_path: Path | None) -> None:
        super().__init__()
        self._mods_dir = mods_dir
        self._cache_path = cache_path

    def run(self) -> None:
        try:
            catalog = scan_library(self._mods_dir, cache_path=self._cache_path)
        except Exception as exc:  # noqa: BLE001 — surface any failure to UI
            log.exception("Scan de la bibliothèque échoué")
            self.failed.emit(str(exc))
            return
        self.finished.emit(catalog)


class ConfigBackupWorker(QObject):
    """Mirror the config to every backup target off the GUI thread (a NAS may hang)."""

    finished = Signal(object)  # list[TargetReport]
    failed = Signal(str)

    def __init__(self, state) -> None:
        super().__init__()
        self._state = state

    def run(self) -> None:
        try:
            reports = self._state.backup_config()
        except Exception as exc:  # noqa: BLE001 — surface any failure to UI
            log.exception("Sauvegarde de la config échouée")
            self.failed.emit(str(exc))
            return
        self.finished.emit(reports)


class ActivateWorker(QObject):
    """Apply a profile to the game folder, with progress."""

    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(object, bool)   # ActivationReport, launched
    failed = Signal(str)

    def __init__(
        self,
        profile: Profile,
        game_profile: GameProfile,
        catalog: Catalog,
        *,
        launch_after: bool,
        mod_filenames: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._profile = profile
        self._game = game_profile
        self._catalog = catalog
        self._launch_after = launch_after
        self._mod_filenames = mod_filenames

    def run(self) -> None:
        try:
            report = activate_profile(
                self._profile,
                self._game,
                self._catalog,
                progress=lambda c, t, m: self.progress.emit(c, t, m),
                mod_filenames=self._mod_filenames,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Activation échouée")
            self.failed.emit(str(exc))
            return
        launched = False
        if self._launch_after and not report.errors:
            launched = launch_game(self._game)
        self.finished.emit(report, launched)


class TestRunnerWorker(QObject):
    """Validate a list of mod ``.zip`` files (built-in checks + optional TestRunner)."""

    progress = Signal(int, int, str)  # done, total, current filename
    finished = Signal(object)         # list[ModTestResult]
    failed = Signal(str)

    def __init__(
        self,
        zip_paths: list[Path],
        *,
        xsd_path: Path | None = None,
        testrunner_exe: Path | None = None,
        editor_exe: Path | None = None,
    ) -> None:
        super().__init__()
        self._zip_paths = zip_paths
        self._xsd_path = xsd_path
        self._testrunner_exe = testrunner_exe
        self._editor_exe = editor_exe

    def run(self) -> None:
        from .profiles.testrunner import validate_mods

        try:
            results = validate_mods(
                self._zip_paths,
                xsd_path=self._xsd_path,
                testrunner_exe=self._testrunner_exe,
                editor_exe=self._editor_exe,
                progress=lambda done, total, name: self.progress.emit(done, total, name),
            )
        except Exception as exc:  # noqa: BLE001 — surface any failure to UI
            log.exception("Validation des mods échouée")
            self.failed.emit(str(exc))
            return
        self.finished.emit(results)


class GameWatcher(QObject):
    """Poll for the FS process; emit :attr:`stopped` once it terminates.

    Relies on :func:`.profiles.activator.game_process_running`. The watcher only
    fires :attr:`stopped` once it has *seen* the process running at least
    once — that avoids a spurious "game closed" right after activation, before
    Steam has had time to spin the binary up.
    """

    started = Signal()
    stopped = Signal()

    POLL_MS = 3000

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._tick)
        self._seen_running = False
        self._active = False

    def start(self) -> None:
        self._seen_running = False
        self._active = True
        self._timer.start()

    def stop(self) -> None:
        self._active = False
        self._timer.stop()

    def _tick(self) -> None:
        if not self._active:
            return
        running = game_process_running()
        if running and not self._seen_running:
            self._seen_running = True
            self.started.emit()
        elif self._seen_running and not running:
            self._active = False
            self._timer.stop()
            self.stopped.emit()


def make_worker_thread(worker: QObject) -> Any:
    """Wrap a worker in a fresh QThread and wire start → run → cleanup.

    Returns the QThread so the caller can keep a reference (Qt requires the
    thread object to outlive its execution). The caller owns it: deleting it when it
    finishes would leave that reference dangling, and the next ``isRunning()`` raises.
    """
    from PySide6.QtCore import QThread  # local: heavy import, only when used

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)  # type: ignore[attr-defined]
    # Quit the thread when the worker signals done.
    for sig_name in ("finished", "failed"):
        sig = getattr(worker, sig_name, None)
        if sig is not None:
            sig.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    return thread


class LibraryImportWorker(QObject):
    """Import initial des mods du jeu dans la bibliothèque (assistant de démarrage)."""

    progress = Signal(int, int, str)
    finished = Signal(object)  # config_setup.ImportResult
    failed = Signal(str)

    def __init__(self, files: list, library_mods_dir) -> None:
        super().__init__()
        self._files = files
        self._dest = library_mods_dir

    def run(self) -> None:
        from .config_setup import import_into_library

        try:
            result = import_into_library(self._files, self._dest, self.progress.emit)
        except Exception as exc:  # noqa: BLE001 - reported to the UI, logged by the hook
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
