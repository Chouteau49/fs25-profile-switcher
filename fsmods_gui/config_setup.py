"""Réglages sans éditer de fichier : détection des dossiers et écriture de config.yaml.

Pourquoi : jusqu'en 0.15, il fallait copier ``config.example.yaml`` et l'éditer à
la main avant le premier lancement ; sans lui l'appli s'arrêtait sur une erreur.
L'assistant de premier lancement et la page Paramètres (0.16) s'appuient sur ce
module pur : il propose des chemins, vérifie que bibliothèque et dossier du jeu
sont sur le même disque (activation instantanée par liens physiques) et produit
le nouveau ``config.yaml`` en gardant les réglages qu'il ne connaît pas.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

GAME_FOLDERS = {"fs25": "FarmingSimulator2025", "fs22": "FarmingSimulator2022"}
STEAM_APP_IDS = {"fs25": 2300320, "fs22": 1248130}
GAME_TITLES = {"fs25": "Farming Simulator 25", "fs22": "Farming Simulator 22"}
STEAM_FOLDERS = {"fs25": "Farming Simulator 25", "fs22": "Farming Simulator 22"}


def documents_candidates(home: Path) -> list[Path]:
    """Dossiers « Documents » possibles (OneDrive le redirige souvent)."""
    return [home / "Documents", home / "OneDrive" / "Documents"]


def mods_dir_candidates(game: str, home: Path) -> list[Path]:
    folder = GAME_FOLDERS[game]
    out: list[Path] = []
    for docs in documents_candidates(home):
        path = docs / "My Games" / folder / "mods"
        if path not in out:
            out.append(path)
    return out


def detect_mods_dir(game: str, home: Path) -> Path | None:
    """Premier dossier ``mods`` du jeu qui existe (ou dont le dossier du jeu existe)."""
    for path in mods_dir_candidates(game, home):
        if path.is_dir() or path.parent.is_dir():
            return path
    return None


def steam_install_candidates(game: str, program_files: list[Path]) -> list[Path]:
    return [
        base / "Steam" / "steamapps" / "common" / STEAM_FOLDERS[game] for base in program_files
    ]


def detect_install_dir(game: str, program_files: list[Path]) -> Path | None:
    for path in steam_install_candidates(game, program_files):
        if path.is_dir():
            return path
    return None


def volume_of(path: Path) -> str:
    """Lecteur (``D:``) ou racine d'un chemin, en minuscules ; ``""`` si relatif."""
    anchor = path.drive or path.anchor
    return anchor.rstrip("\\/").lower()


def same_volume(a: Path, b: Path) -> bool:
    """Vrai si les deux chemins sont sur le même disque (liens physiques possibles)."""
    va, vb = volume_of(a), volume_of(b)
    return bool(va) and va == vb


def suggested_library_dir(game: str, mods_dir: Path) -> Path:
    """Bibliothèque proposée : à la racine du disque du jeu (``D:/FS25-Library``)."""
    name = "FS25-Library" if game == "fs25" else "FS22-Library"
    anchor = mods_dir.anchor or str(mods_dir.parents[-1])
    return Path(anchor) / name


@dataclass(frozen=True)
class Check:
    ok: bool
    text: str


def library_check(mods_dir: Path | None, library_dir: Path | None) -> Check:
    """Message de la page Paramètres / de l'assistant sur le choix de la bibliothèque."""
    if library_dir is None or not str(library_dir).strip():
        return Check(False, "Choisis le dossier de la bibliothèque.")
    if mods_dir is None:
        return Check(True, "Bibliothèque choisie.")
    if same_volume(mods_dir, library_dir):
        return Check(
            True,
            f"Même disque que le jeu ({volume_of(mods_dir).upper()}) : activation "
            "instantanée par liens physiques, sans espace disque en plus.",
        )
    return Check(
        False,
        f"{volume_of(library_dir).upper() or 'Ce dossier'} n'est pas le disque du jeu "
        f"({volume_of(mods_dir).upper()}) : les mods seront copiés à chaque activation, "
        "plus lent et deux fois plus d'espace disque.",
    )


def default_config_path(appdata: Path | None, fallback_dir: Path) -> Path:
    """Où écrire un nouveau config.yaml : ``%APPDATA%/fsmods-gui`` sinon à côté de l'appli."""
    if appdata is not None:
        return appdata / "fsmods-gui" / "config.yaml"
    return fallback_dir / "config.yaml"


@dataclass(frozen=True)
class GameSettings:
    game: str
    mods_dir: Path
    library_dir: Path
    steam_app_id: int | None = None
    backup_dirs: tuple[Path, ...] = ()
    install_dir: Path | None = None


def _posix(path: Path) -> str:
    return path.as_posix()


def updated_config_text(old_text: str | None, settings: GameSettings) -> str:
    """Nouveau contenu de config.yaml : les réglages du jeu sont remplacés, le reste
    (autres jeux, clés inconnues de l'appli) est conservé.

    Les commentaires du fichier d'origine ne survivent pas à la réécriture : la
    fenêtre garde donc une copie ``config.yaml.bak`` avant d'écrire.
    """
    data = yaml.safe_load(old_text) if old_text else None
    if not isinstance(data, dict):
        data = {}
    games = data.get("games")
    if not isinstance(games, dict):
        games = {}
    entry = games.get(settings.game)
    if not isinstance(entry, dict):
        entry = {}
    entry["mods_dir"] = _posix(settings.mods_dir)
    entry["library_dir"] = _posix(settings.library_dir)
    if settings.steam_app_id is not None:
        entry["steam_app_id"] = int(settings.steam_app_id)
    if settings.install_dir is not None:
        entry["install_dir"] = _posix(settings.install_dir)
    if settings.backup_dirs:
        entry["config_backup_dirs"] = [_posix(d) for d in settings.backup_dirs]
    else:
        entry.pop("config_backup_dirs", None)
    games[settings.game] = entry
    data["games"] = games
    data.setdefault("default_game", settings.game)
    header = (
        "# Réglages de FS25 Profile Switcher, écrits par l'appli (Paramètres).\n"
        "# Modifiable à la main ; voir config.example.yaml pour toutes les options.\n"
    )
    return header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def initial_import_plan(mods_dir: Path, library_mods_dir: Path) -> list[Path]:
    """Zips du dossier du jeu absents de la bibliothèque (à y lier ou copier).

    Rien n'est déplacé ni supprimé dans le dossier du jeu : l'import ne fait
    qu'ajouter à la bibliothèque.
    """
    if not mods_dir.is_dir():
        return []
    existing = (
        {p.name.lower() for p in library_mods_dir.iterdir()} if library_mods_dir.is_dir() else set()
    )
    return sorted(
        (p for p in mods_dir.iterdir()
         if p.is_file() and p.suffix.lower() == ".zip" and p.name.lower() not in existing),
        key=lambda p: p.name.lower(),
    )


@dataclass
class ImportResult:
    added: list[str]
    errors: list[tuple[str, str]]


def import_into_library(
    files: list[Path], library_mods_dir: Path, progress=None
) -> ImportResult:
    """Ajoute les zips à la bibliothèque : lien physique (instantané) ou copie.

    Le dossier du jeu n'est jamais modifié. Un fichier déjà présent dans la
    bibliothèque est laissé tel quel ; une erreur sur un fichier n'arrête pas les
    autres.
    """
    import os
    import shutil

    library_mods_dir.mkdir(parents=True, exist_ok=True)
    result = ImportResult([], [])
    for i, src in enumerate(files, 1):
        dst = library_mods_dir / src.name
        if progress is not None:
            progress(i, len(files), src.name)
        if dst.exists():
            continue
        try:
            try:
                os.link(src, dst)
            except OSError:
                tmp = dst.with_name(dst.name + ".part")
                shutil.copy2(src, tmp)
                tmp.replace(dst)
            result.added.append(src.name)
        except OSError as exc:
            result.errors.append((src.name, str(exc)))
    return result


def program_files_dirs(env: dict[str, str]) -> list[Path]:
    """Dossiers Program Files où chercher Steam (variables d'environnement Windows)."""
    keys = ("PROGRAMFILES(X86)", "PROGRAMFILES")
    upper = {k.upper(): v for k, v in env.items()}
    return [Path(upper[k]) for k in keys if upper.get(k)]
