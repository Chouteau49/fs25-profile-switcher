from __future__ import annotations

import importlib
import os
import pkgutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import fsmods_gui

MODULES = [
    m.name for m in pkgutil.walk_packages(fsmods_gui.__path__, "fsmods_gui.")
    if not m.name.endswith("__main__")
]


@pytest.mark.parametrize("module", MODULES)
def test_every_module_imports(module: str) -> None:
    # Most widgets have no test of their own: at least they must load.
    importlib.import_module(module)
