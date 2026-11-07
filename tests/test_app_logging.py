from __future__ import annotations

import logging
import logging.handlers
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from fsmods_gui import app_logging
from fsmods_gui.app_logging import default_log_dir, set_error_listener, setup_logging


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    hook, thread_hook = sys.excepthook, threading.excepthook
    path = setup_logging(tmp_path, crash_dump=False)
    yield path
    app_logging.shutdown_logging()
    sys.excepthook, threading.excepthook = hook, thread_hook


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_default_log_dir_is_outside_the_library(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", "C:/AppData/Local")
    assert default_log_dir() == Path("C:/AppData/Local/fs25-profile-switcher/logs")


def test_messages_reach_the_file_and_it_rotates(log_file: Path) -> None:
    logging.getLogger("fsmods_gui.test").warning("été")
    assert "été" in _text(log_file)
    handler = next(
        h for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    )
    assert handler.maxBytes > 0 and handler.backupCount > 0


def test_uncaught_exception_is_logged_with_its_traceback(log_file: Path) -> None:
    calls: list[int] = []
    set_error_listener(lambda: calls.append(1))
    try:
        raise ValueError("boum dans un slot")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert "boum dans un slot" in _text(log_file)
    assert "Traceback" in _text(log_file)
    assert calls == [1]


def test_exception_in_a_qt_slot_is_logged(log_file: Path) -> None:
    # The packaged exe has no console: this is the case that used to vanish.
    class Emitter(QObject):
        fired = Signal()

    app = QApplication.instance() or QApplication([])  # widget tests share it
    assert app is not None

    def slot() -> None:
        raise RuntimeError("erreur dans un slot Qt")

    emitter = Emitter()
    emitter.fired.connect(slot)
    emitter.fired.emit()
    assert "erreur dans un slot Qt" in _text(log_file)


def test_exception_in_a_thread_is_logged(log_file: Path) -> None:
    def work() -> None:
        raise KeyError("erreur dans un thread")

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert "erreur dans un thread" in _text(log_file)


def test_a_failing_listener_never_hides_the_error(log_file: Path) -> None:
    def broken() -> None:
        raise OSError("fenêtre fermée")

    set_error_listener(broken)
    try:
        raise ValueError("erreur d'origine")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    assert "erreur d'origine" in _text(log_file)


def test_setup_twice_does_not_write_each_line_twice(log_file: Path) -> None:
    setup_logging(log_file.parent, crash_dump=False)
    logging.getLogger("fsmods_gui.test").warning("une seule fois")
    assert _text(log_file).count("une seule fois") == 1


def test_hard_crashes_are_dumped_to_a_file(tmp_path: Path) -> None:
    # A separate process: faulthandler is global and pytest uses it too.
    code = (
        "import faulthandler, sys\n"
        "from pathlib import Path\n"
        "from fsmods_gui.app_logging import setup_logging\n"
        "setup_logging(Path(sys.argv[1]))\n"
        "print(faulthandler.is_enabled())\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "True"
    assert (tmp_path / app_logging.CRASH_FILE).is_file()
