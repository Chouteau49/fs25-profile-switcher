from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from fsmods_gui.workers import make_worker_thread


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        self.finished.emit([])


def test_thread_stays_usable_after_its_worker_finished() -> None:
    # MainWindow keeps the thread and asks isRunning() before the next backup: a
    # thread deleted behind its back raised RuntimeError, so only the first backup
    # of a session ever ran.
    app = QApplication.instance() or QApplication([])  # widget tests share it
    assert app is not None
    worker = _Worker()  # like MainWindow: the caller keeps the worker alive
    thread = make_worker_thread(worker)
    loop = QEventLoop()
    # Attendre la fin réelle du thread (pas un délai fixe : 300 ms ne suffisaient
    # pas quand la machine est chargée, le test échouait au hasard).
    thread.finished.connect(loop.quit)
    QTimer.singleShot(10_000, loop.quit)  # garde-fou
    thread.start()
    loop.exec()
    assert thread.isRunning() is False
