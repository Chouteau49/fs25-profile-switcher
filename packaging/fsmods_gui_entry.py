"""Entry point for Nuitka — évite les imports relatifs de __main__.py."""
import sys
from pathlib import Path

# Prefer repository sources over an installed package copy.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from fsmods_gui.main import run

if __name__ == "__main__":
    sys.exit(run())
