"""Background workers: catalog scan, profile activation, FS25 process watcher.

Each worker is a :class:`QObject` moved to its own :class:`QThread` so the UI
never blocks. Use signals for progress + completion.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from .config import GameProfile
from .profiles.activator import (
    ActivationReport,
    activate_profile,
    launch_game,
)
from .profiles.catalog import Catalog, scan_library
from .profiles.profile import Profile


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
            self.failed.emit(str(exc))
            return
        self.finished.emit(catalog)


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
    ) -> None:
        super().__init__()
        self._profile = profile
        self._game = game_profile
        self._catalog = catalog
        self._launch_after = launch_after

    def run(self) -> None:
        try:
            report = activate_profile(
                self._profile,
                self._game,
                self._catalog,
                progress=lambda c, t, m: self.progress.emit(c, t, m),
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        launched = False
        if self._launch_after and not report.errors:
            launched = launch_game(self._game)
        self.finished.emit(report, launched)


class GameWatcher(QObject):
    """Poll for the FS process; emit :attr:`stopped` once it terminates.

    Relies on ``psutil`` to enumerate processes by executable name. The watcher
    only fires :attr:`stopped` once it has *seen* the process running at least
    once — that avoids a spurious "game closed" right after activation, before
    Steam has had time to spin the binary up.
    """

    started = Signal()
    stopped = Signal()

    DEFAULT_PROCESS_NAMES = ("FarmingSimulator2025.exe", "FarmingSimulator2022.exe")
    POLL_MS = 3000

    def __init__(
        self,
        process_names: tuple[str, ...] = DEFAULT_PROCESS_NAMES,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._names = tuple(n.lower() for n in process_names)
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

    def _is_running(self) -> bool:
        try:
            import psutil  # local import: keeps Qt-free modules importable on systems w/o psutil
        except ImportError:
            return False
        for proc in psutil.process_iter(["name"]):
            # Get name safely, handle potential AccessDenied errors
            try:
                name = (proc.info.get("name") or "").lower()
                if not name:
                    continue
                # Exact match
                if name in self._names:
                    return True
                # Partial match for robustness (e.g. FS25.exe or different capitalization)
                if "farmingsimulator" in name and name.endswith(".exe"):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def _tick(self) -> None:
        if not self._active:
            return
        running = self._is_running()
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
    thread object to outlive its execution).
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
    thread.finished.connect(thread.deleteLater)
    return thread
