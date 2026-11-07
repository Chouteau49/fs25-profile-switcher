"""Atomic file writes: a crash leaves the old file or the new one, never a truncated mix.

Profiles, collections and careers are small JSON files rewritten on every change. A
plain ``write_text`` cut halfway loses the file, and the backup would then copy the
damage. Content goes to a temporary file first, and ``os.replace`` swaps it in.

On Windows that swap fails while another thread or process holds the target open (the
config backup reading it, an antivirus): this is brief, so it is retried a few times.

Pure logic (stdlib only).
"""
from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

RETRIES = 5
RETRY_DELAY_S = 0.05


def _replace(source: Path, target: Path) -> None:
    for attempt in range(RETRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY_S)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data``; on failure the previous content stays untouched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temporary, path)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
