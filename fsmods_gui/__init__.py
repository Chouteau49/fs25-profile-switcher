"""PySide6-based desktop profile switcher for Farming Simulator 25 / 22.

Entry points::

    fsmods-gui          # installed as a console-less script (no terminal window)
    python -m fsmods_gui
"""
from __future__ import annotations

__all__ = ["run"]


def run() -> int:  # pragma: no cover - thin re-export
    from .main import run as _run
    return _run()
