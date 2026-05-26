"""Entry point for Nuitka — évite les imports relatifs de __main__.py."""
import sys

from fsmods_gui.main import run

if __name__ == "__main__":
    sys.exit(run())
