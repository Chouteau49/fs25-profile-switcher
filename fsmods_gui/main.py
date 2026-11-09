"""GUI entry point — creates the Qt application and shows the main window."""
from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from . import config as cfgmod
from .app_logging import setup_logging

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)


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
    log.error("%s : %s", title, message)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
        del app
    except ImportError:
        print(f"[{title}] {message}", file=sys.stderr)
    return 2


def _forward_qt_messages() -> None:
    """Send Qt's own warnings ("QThread: Destroyed while…") to the log file."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    qt_log = logging.getLogger("qt")

    def forward(message_type, _context, message: str) -> None:
        qt_log.log(levels.get(message_type, logging.WARNING), message)

    qInstallMessageHandler(forward)


def _app_icon_candidates() -> list[Path]:
    exe_dir = Path(sys.executable).resolve().parent
    this_dir = Path(__file__).resolve().parent
    root_dir = this_dir.parent

    candidates = [
        exe_dir / "fsmods-gui.ico",
        this_dir / "assets" / "fsmods-gui.ico",
        root_dir / "packaging" / "assets" / "fsmods-gui.ico",
    ]

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique


def _configure_app_icon(app: QApplication) -> None:
    try:
        from PySide6.QtGui import QIcon
    except ImportError:
        return

    for icon_path in _app_icon_candidates():
        if not icon_path.is_file():
            continue
        icon = QIcon(str(icon_path))
        if icon.isNull():
            continue
        app.setWindowIcon(icon)
        return


def _first_run_setup():
    """Assistant de premier lancement : écrit config.yaml et le relit.

    Retourne ``(config, assistant)``, ou ``(None, None)`` si l'utilisateur annule.
    """
    from .config_setup import default_config_path, program_files_dirs, updated_config_text
    from .profiles.atomic import atomic_write_text
    from .widgets.settings_page import FirstRunWizard

    wizard = FirstRunWizard(Path.home(), program_files_dirs(dict(os.environ)))
    if wizard.exec() != wizard.DialogCode.Accepted:
        return None, None
    settings = wizard.settings()
    if settings is None:
        return None, None
    appdata = os.getenv("APPDATA")
    path = default_config_path(Path(appdata) if appdata else None, cfgmod.REPO_ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, updated_config_text(None, settings))
    for sub in ("mods", "profiles", "collections"):
        (settings.library_dir / sub).mkdir(parents=True, exist_ok=True)
    log.info("Config créée par l'assistant : %s", path)
    return cfgmod.load(path), wizard


def run(argv: list[str] | None = None) -> int:
    _configure_qt_plugin_paths()

    try:
        setup_logging()
    except OSError as exc:  # a log folder that can't be created must not stop the app
        print(f"Journal indisponible : {exc}", file=sys.stderr)
    log.info("Démarrage v%s (Python %s)", __version__, sys.version.split()[0])

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
        cfg: cfgmod.Config | None = cfgmod.load()
    except FileNotFoundError:
        cfg = None  # premier lancement : l'assistant crée la config
    except (ValueError, OSError) as exc:
        return _show_startup_error("Config invalide", str(exc))

    from .main_window import MainWindow
    from .state import AppState

    _forward_qt_messages()
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("fs25-profile-switcher")
    app.setOrganizationName("fs25-profile-switcher")
    _configure_app_icon(app)

    from .widgets import theming

    theming.install(app)

    wizard = None
    if cfg is None:
        try:
            cfg, wizard = _first_run_setup()
        except (ValueError, OSError) as exc:
            return _show_startup_error("Configuration impossible", str(exc))
        if cfg is None:
            return 0  # assistant annulé

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

    try:
        state = AppState(cfg=cfg, game_key=game_key)
        window = MainWindow(state)
        window.setWindowIcon(app.windowIcon())
    except Exception:  # noqa: BLE001
        return _show_startup_error("Erreur au démarrage", traceback.format_exc())

    window.show()
    if wizard is not None and wizard.import_requested():
        window.start_initial_import(create_profile=wizard.profile_requested())
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
