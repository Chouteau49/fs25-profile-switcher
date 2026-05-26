"""GUI entry point — creates the Qt application and shows the main window."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from . import config as cfgmod


def _qt_plugin_root_candidates() -> list[Path]:
    candidates: list[Path] = []

    exe_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            exe_dir / "PySide6" / "qt-plugins",
            exe_dir / "PySide6" / "plugins",
            exe_dir / "qt-plugins",
            exe_dir / "plugins",
        ]
    )

    for entry in sys.path:
        if not entry:
            continue
        p = Path(entry)
        candidates.extend(
            [
                p / "PySide6" / "qt-plugins",
                p / "PySide6" / "plugins",
            ]
        )

    # Keep order while removing duplicates.
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique


def _select_qt_plugin_root(candidates: list[Path]) -> Path | None:
    for root in candidates:
        platforms = root / "platforms"
        if (platforms / "qwindows.dll").is_file() or (platforms / "qminimal.dll").is_file():
            return root
    return None


def _configure_qt_plugin_paths() -> None:
    if os.getenv("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return

    root = _select_qt_plugin_root(_qt_plugin_root_candidates())
    if root is None:
        return

    os.environ["QT_PLUGIN_PATH"] = str(root)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(root / "platforms")


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
    _configure_qt_plugin_paths()

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
