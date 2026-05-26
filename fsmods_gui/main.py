"""GUI entry point — creates the Qt application and shows the main window."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from . import config as cfgmod


def _show_startup_error(title: str, message: str) -> int:
    """Display a Qt message box if PySide6 is available, else print to stderr."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
        del app
    except ImportError:
        print(f"[{title}] {message}", file=sys.stderr)
    return 2


def run(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 n'est pas installé. Installe les dépendances avec : "
            "pip install -e .",
            file=sys.stderr,
        )
        return 2

    try:
        cfg = cfgmod.load()
    except FileNotFoundError as exc:
        return _show_startup_error("Config manquante", str(exc))
    except (ValueError, OSError) as exc:
        return _show_startup_error("Config invalide", str(exc))

    game_key = cfg.default_game
    try:
        game = cfg.profile(game_key)
    except KeyError as exc:
        return _show_startup_error("Config", str(exc))
    if game.library_dir is None:
        return _show_startup_error(
            "Bibliothèque non configurée",
            f"Renseigne games.{game_key}.library_dir dans config.yaml "
            f"(ex. D:/FS25-Library) puis relance.",
        )

    from .main_window import MainWindow
    from .state import AppState

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("fs25-profile-switcher")
    app.setOrganizationName("fs25-profile-switcher")

    try:
        state = AppState(cfg=cfg, game_key=game_key)
        window = MainWindow(state)
    except Exception:  # noqa: BLE001
        return _show_startup_error("Erreur au démarrage", traceback.format_exc())

    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
