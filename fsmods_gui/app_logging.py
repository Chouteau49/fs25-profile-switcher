"""Application log file.

The packaged exe has no console: without this file, an exception in a Qt slot, a
failing worker or a hard crash leaves no trace at all. Everything goes to
``%LOCALAPPDATA%/fs25-profile-switcher/logs``, outside the library so that the logs
are neither backed up nor shared with the config.

Pure stdlib, no Qt: Qt's own messages are forwarded from ``main.py``.
"""
from __future__ import annotations

import contextlib
import faulthandler
import logging
import logging.handlers
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO

LOG_FILE = "fsmods-gui.log"
CRASH_FILE = "crash.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

log = logging.getLogger("fsmods_gui")

_handler: logging.Handler | None = None
_crash_stream: IO[str] | None = None
_listener: Callable[[], None] | None = None


def default_log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "fs25-profile-switcher" / "logs"


def set_error_listener(listener: Callable[[], None] | None) -> None:
    """Called after each uncaught error, from any thread (the GUI uses it to warn the user)."""
    global _listener
    _listener = listener


def _notify() -> None:
    if _listener is not None:
        with contextlib.suppress(Exception):  # the window may already be gone
            _listener()


def _on_uncaught(exc_type, exc, traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, traceback)
        return
    log.critical("Erreur non gérée", exc_info=(exc_type, exc, traceback))
    _notify()


def _on_thread_error(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread else "?"
    log.critical(
        "Erreur non gérée dans le thread %s",
        name,
        exc_info=args.exc_value,
    )
    _notify()


def setup_logging(log_dir: Path | None = None, *, crash_dump: bool = True) -> Path:
    """Send logs, uncaught exceptions and hard crashes to files. Returns the log path."""
    global _handler, _crash_stream
    target = log_dir or default_log_dir()
    target.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
    path = target / LOG_FILE
    _handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    _handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(_handler)
    root.setLevel(logging.INFO)
    logging.captureWarnings(True)
    sys.excepthook = _on_uncaught
    threading.excepthook = _on_thread_error
    if crash_dump and _crash_stream is None:
        # Kept open for the whole run: a segfault in Qt cannot open a file any more.
        _crash_stream = (target / CRASH_FILE).open("a", encoding="utf-8")
        faulthandler.enable(file=_crash_stream)
    return path


def shutdown_logging() -> None:
    """Undo :func:`setup_logging` (tests; at exit ``logging`` closes the file by itself)."""
    global _handler, _crash_stream
    set_error_listener(None)
    logging.captureWarnings(False)
    sys.excepthook = sys.__excepthook__
    threading.excepthook = threading.__excepthook__
    if _handler is not None:
        logging.getLogger().removeHandler(_handler)
        _handler.close()
        _handler = None
    if _crash_stream is not None:
        faulthandler.disable()
        _crash_stream.close()
        _crash_stream = None
