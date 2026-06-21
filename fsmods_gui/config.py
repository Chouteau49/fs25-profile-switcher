"""Load and validate the config (multi-game)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Quand l'app est packagée par PyInstaller (onefile), sys.frozen est True et
# sys.executable pointe vers l'exe. On cherche config.yaml à côté de l'exe.
# En développement, on remonte depuis ce fichier jusqu'à la racine du dépôt.
if getattr(sys, "frozen", False):
    REPO_ROOT = Path(sys.executable).resolve().parent
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = REPO_ROOT / "config.example.yaml"

SUPPORTED_GAMES = ("fs25", "fs22")


def _default_config_candidates() -> list[Path]:
    candidates: list[Path] = [DEFAULT_CONFIG_PATH, Path.cwd() / "config.yaml"]

    # Persisted per-user config location for packaged app usage.
    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "fsmods-gui" / "config.yaml")

    # Keep order but remove duplicates.
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser()
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique


def _resolve_default_config_path() -> tuple[Path | None, list[Path]]:
    searched = _default_config_candidates()
    for candidate in searched:
        if candidate.exists():
            return candidate, searched
    return None, searched


@dataclass(frozen=True)
class GameProfile:
    name: str
    mods_dir: Path
    install_dir: Path | None = None
    library_dir: Path | None = None
    steam_app_id: int | None = None
    config_backup_dir: Path | None = None  # cloud-synced folder to mirror profiles+collections
    downloads_dir: Path | None = None  # override; defaults to the user's Downloads folder
    inbox_dir: Path | None = None  # override; defaults to <library_dir>/_inbox
    testrunner_exe: Path | None = None  # Giants TestRunner.exe (GDN) for mod validation

    @property
    def library_mods_dir(self) -> Path | None:
        return self.library_dir / "mods" if self.library_dir else None

    @property
    def inbox_dir_effective(self) -> Path | None:
        """Dedicated drop folder for freshly downloaded mods (``new_mods``).

        Uses the configured ``inbox_dir`` if set, otherwise ``<library_dir>/_inbox``.
        Returns ``None`` only when no library is configured and no override is set.
        """
        if self.inbox_dir is not None:
            return self.inbox_dir
        return self.library_dir / "_inbox" if self.library_dir else None

    @property
    def downloads_dir_effective(self) -> Path:
        """Folder to scan for downloaded mods; defaults to the OS Downloads dir."""
        return self.downloads_dir if self.downloads_dir is not None else Path.home() / "Downloads"

    def new_mod_source_dirs(self) -> list[Path]:
        """Ordered, de-duplicated folders to scan for new (un-imported) mods.

        The Downloads folder first, then the dedicated inbox/new_mods folder.
        Only folders that resolve to a path are returned (existence is the
        caller's concern — the inbox is created on demand).
        """
        dirs: list[Path] = [self.downloads_dir_effective]
        inbox = self.inbox_dir_effective
        if inbox is not None:
            dirs.append(inbox)
        out: list[Path] = []
        seen: set[Path] = set()
        for d in dirs:
            try:
                key = d.resolve()
            except OSError:
                key = d
            if key not in seen:
                seen.add(key)
                out.append(d)
        return out

    @property
    def library_profiles_dir(self) -> Path | None:
        return self.library_dir / "profiles" if self.library_dir else None

    @property
    def library_cache_dir(self) -> Path | None:
        return self.library_dir / "cache" if self.library_dir else None

    @property
    def library_collections_dir(self) -> Path | None:
        return self.library_dir / "collections" if self.library_dir else None

    def steam_launch_url(self) -> str | None:
        return f"steam://rungameid/{self.steam_app_id}" if self.steam_app_id else None

    def find_moddesc_xsd(self) -> Path | None:
        """Search the game install directory for a modDesc XSD schema.

        Giants ships the XSD inside the install dir under a few possible paths.
        Returns the first match, or None if the install dir is unset / not found.
        """
        if self.install_dir is None:
            return None
        candidates = [
            self.install_dir / "data" / "shared" / "xml" / "modDesc.xsd",
            self.install_dir / "data" / "xml" / "modDesc.xsd",
            self.install_dir / "data" / "modDesc.xsd",
            self.install_dir / "modDesc.xsd",
        ]
        for c in candidates:
            if c.is_file():
                return c
        # Fall back to a recursive search (game install can be large; limit depth).
        try:
            for path in self.install_dir.rglob("modDesc.xsd"):
                if path.is_file():
                    return path
        except (OSError, PermissionError):
            return None
        return None


@dataclass
class Config:
    games: dict[str, GameProfile]
    default_game: str
    pull_overwrite: bool = False
    push_overwrite: bool = True
    repo_root: Path = field(default_factory=lambda: REPO_ROOT)

    def mods_src_dir(self, game: str) -> Path:
        return self.repo_root / "mods" / game

    def dist_dir(self, game: str) -> Path:
        return self.repo_root / "dist" / game

    def profile(self, game: str | None = None) -> GameProfile:
        key = game or self.default_game
        if key not in self.games:
            raise KeyError(
                f"Unknown game '{key}'. Configured: {sorted(self.games)}."
            )
        return self.games[key]


def _parse_games(raw: object, cfg_path: Path) -> dict[str, GameProfile]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError(
            f"{cfg_path}: 'games' must be a non-empty mapping of "
            f"<key>: {{ mods_dir: ... }}."
        )
    profiles: dict[str, GameProfile] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{cfg_path}: games.{key} must be a mapping.")
        mods_dir = entry.get("mods_dir")
        if not mods_dir or str(mods_dir).startswith("/path/to/"):
            raise ValueError(
                f"{cfg_path}: set games.{key}.mods_dir to the real game mods folder."
            )
        install_raw = entry.get("install_dir")
        install_dir: Path | None = None
        if install_raw and not str(install_raw).startswith("/path/to/"):
            install_dir = Path(install_raw).expanduser()
        library_raw = entry.get("library_dir")
        library_dir: Path | None = None
        if library_raw and not str(library_raw).startswith("/path/to/"):
            library_dir = Path(library_raw).expanduser()
        backup_raw = entry.get("config_backup_dir")
        config_backup_dir: Path | None = None
        if backup_raw and not str(backup_raw).startswith("/path/to/"):
            config_backup_dir = Path(backup_raw).expanduser()
        downloads_raw = entry.get("downloads_dir")
        downloads_dir: Path | None = None
        if downloads_raw and not str(downloads_raw).startswith("/path/to/"):
            downloads_dir = Path(downloads_raw).expanduser()
        inbox_raw = entry.get("inbox_dir")
        inbox_dir: Path | None = None
        if inbox_raw and not str(inbox_raw).startswith("/path/to/"):
            inbox_dir = Path(inbox_raw).expanduser()
        testrunner_raw = entry.get("testrunner_exe")
        testrunner_exe: Path | None = None
        if testrunner_raw and not str(testrunner_raw).startswith("/path/to/"):
            testrunner_exe = Path(testrunner_raw).expanduser()
        steam_app_id_raw = entry.get("steam_app_id")
        steam_app_id: int | None = None
        if steam_app_id_raw is not None:
            try:
                steam_app_id = int(steam_app_id_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{cfg_path}: games.{key}.steam_app_id must be an integer."
                ) from exc
        profiles[key] = GameProfile(
            name=key,
            mods_dir=Path(mods_dir).expanduser(),
            install_dir=install_dir,
            library_dir=library_dir,
            steam_app_id=steam_app_id,
            config_backup_dir=config_backup_dir,
            downloads_dir=downloads_dir,
            inbox_dir=inbox_dir,
            testrunner_exe=testrunner_exe,
        )
    return profiles


def load(path: Path | None = None) -> Config:
    searched_paths: list[Path] = []
    if path is None:
        cfg_path, searched_paths = _resolve_default_config_path()
    else:
        cfg_path = path

    if cfg_path is None or not cfg_path.exists():
        searched = ""
        if searched_paths:
            searched = "\nSearched:\n- " + "\n- ".join(str(p) for p in searched_paths)
        raise FileNotFoundError(
            "Missing config.yaml. Copy config.example.yaml to config.yaml "
            "(next to the exe, in the current directory, or under %APPDATA%/fsmods-gui) "
            f"and set games.<game>.mods_dir.{searched}"
        )
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    games = _parse_games(data.get("games"), cfg_path)
    default_game = data.get("default_game") or next(iter(games))
    if default_game not in games:
        raise ValueError(
            f"{cfg_path}: default_game='{default_game}' is not in games "
            f"({sorted(games)})."
        )
    return Config(
        games=games,
        default_game=default_game,
        pull_overwrite=bool(data.get("pull_overwrite", False)),
        push_overwrite=bool(data.get("push_overwrite", True)),
    )
