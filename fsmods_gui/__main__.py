"""Enable ``python -m fsmods_gui``."""
from __future__ import annotations

import sys

from . import run

if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
