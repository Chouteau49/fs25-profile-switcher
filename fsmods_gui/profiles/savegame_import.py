"""Importer une partie téléchargée : un zip de sauvegarde FS25 devient un dossier
``savegameN`` du jeu, et un profil est préparé avec sa carte et ses mods.

Un zip de partie contient ``careerSavegame.xml`` à la racine, ou dans un seul dossier.
Rien n'écrase une partie existante : la sauvegarde est extraite dans un dossier
temporaire, puis renommée. Un échec ne laisse donc aucun dossier à moitié rempli.

Pur, sans Qt.
"""
from __future__ import annotations

import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .official_maps import official_map

CAREER_FILE = "careerSavegame.xml"
DEFAULT_NAME = "Partie importée"
_SAVEGAME_DIR = re.compile(r"^savegame(\d+)$")
# FS25 only shows these slots in its menu: a save outside them would be invisible.
GAME_SLOTS = range(1, 21)
# What an empty slot holds: Steam's cloud file, nothing else.
_EMPTY_SLOT_FILES = frozenset({"steam_autocloud.vdf"})


class SaveImportError(ValueError):
    """Raised when a save cannot be extracted safely (shown to the player)."""


@dataclass(frozen=True)
class SaveArchive:
    path: Path
    name: str
    map_id: str
    map_title: str
    save_date: str
    mods: tuple[str, ...]  # mod names as the save lists them (<mod modName=…/>)


@dataclass(frozen=True)
class ProfilePlan:
    map_mod: str | None  # library zip of the map
    official_map: str | None  # base-game or DLC map id
    mods: tuple[str, ...]  # library zips of the save's other mods
    missing: tuple[str, ...]  # mods the save needs but the library lacks


def _root_names(names: list[str]) -> list[str]:
    """Member names relative to the save folder (one wrapping folder is removed)."""
    names = [n.replace("\\", "/") for n in names]
    if CAREER_FILE in names:
        return names
    tops = {n.split("/", 1)[0] for n in names if "/" in n}
    if len(tops) == 1 and f"{next(iter(tops))}/{CAREER_FILE}" in names:
        prefix = next(iter(tops)) + "/"
        return [n[len(prefix):] if n.startswith(prefix) else n for n in names]
    return names


def read_save_archive(zip_path: Path) -> SaveArchive | None:
    """The save described by ``zip_path``, or ``None`` if it is not a readable save."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
            relative = _root_names(members)  # same order as ``members``
            if CAREER_FILE not in relative:
                return None
            raw = zf.read(members[relative.index(CAREER_FILE)])
    except (OSError, zipfile.BadZipFile, KeyError):
        return None
    try:
        root = ET.fromstring(raw.decode("utf-8-sig", errors="replace"))
    except ET.ParseError:
        return None
    settings = root.find("settings")
    if settings is None:
        return None
    mods = tuple(
        name for mod in root.iter("mod")
        if (name := (mod.get("modName") or "").strip())
    )
    return SaveArchive(
        path=zip_path,
        name=(settings.findtext("savegameName") or "").strip(),
        map_id=(settings.findtext("mapId") or "").strip(),
        map_title=(settings.findtext("mapTitle") or "").strip(),
        save_date=(settings.findtext("saveDate") or "").strip(),
        mods=mods,
    )


def scan_save_archives(folders: list[Path]) -> list[SaveArchive]:
    """Saves found in the zips of ``folders`` (missing folders are skipped)."""
    found: list[SaveArchive] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for zip_path in sorted(folder.glob("*.zip"), key=lambda p: p.name.lower()):
            archive = read_save_archive(zip_path)
            if archive is not None:
                found.append(archive)
    return found


def _is_free_slot(folder: Path) -> bool:
    """True when the slot is absent, or holds nothing but the Steam cloud file."""
    if not folder.exists():
        return True
    if not folder.is_dir():
        return False
    return all(child.name in _EMPTY_SLOT_FILES and child.is_file() for child in folder.iterdir())


def next_savegame_dir(user_dir: Path) -> Path:
    """The first free slot of the game (``savegame1`` to ``savegame20``); nothing is created.

    A slot holding another save, or any leftover file, is never reused.
    """
    for number in GAME_SLOTS:
        folder = user_dir / f"savegame{number}"
        if _is_free_slot(folder):
            return folder
    raise SaveImportError(
        "Les 20 emplacements de partie de FS25 sont utilisés : supprime-en un dans le jeu."
    )


def extract_save(archive: SaveArchive, target: Path) -> None:
    """Extract the save into ``target``, which must not exist yet.

    Written into a temporary sibling first, then renamed: on any failure nothing is
    left behind. Paths that would leave the folder refuse the whole import.
    """
    if target.exists() and not _is_free_slot(target):
        raise SaveImportError(f"Le dossier {target.name} existe déjà : rien n'a été écrit.")
    keep_cloud_file = target.is_dir() and (target / "steam_autocloud.vdf").is_file()
    staging = target.parent / f".{target.name}.importing"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        staging.mkdir(parents=True)
        with zipfile.ZipFile(archive.path) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            names = _root_names([m.filename for m in members])
            for member, rel in zip(members, names, strict=True):
                rel_path = PurePosixPath(rel)
                if rel_path.is_absolute() or ".." in rel_path.parts or not rel_path.parts:
                    raise SaveImportError(f"Chemin refusé dans l'archive : {member.filename}")
                dest = staging.joinpath(*rel_path.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
        if not (staging / CAREER_FILE).is_file():
            raise SaveImportError("careerSavegame.xml absent de l'extraction.")
        if keep_cloud_file:
            shutil.copy2(target / "steam_autocloud.vdf", staging / "steam_autocloud.vdf")
            shutil.rmtree(target)  # only the empty slot's cloud file was in it, copied above
        os.replace(staging, target)
    except SaveImportError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise SaveImportError(f"Extraction impossible : {exc}") from exc


def unique_profile_name(name: str, existing: set[str]) -> str:
    """``name``, or ``name (2)``, ``name (3)``… when a profile already has it."""
    base = name.strip() or DEFAULT_NAME
    candidate, n = base, 2
    while candidate in existing:
        candidate = f"{base} ({n})"
        n += 1
    return candidate


def plan_profile(archive: SaveArchive, library: dict[str, str]) -> ProfilePlan:
    """Map and mods of the profile for ``archive``.

    ``library`` maps a lower-case mod name (zip stem) to its library filename. The map
    is the mod named before the dot of the ``mapId``; a base-game or DLC map is
    recognised as an official map.
    """
    map_mod_name = archive.map_id.split(".", 1)[0].lower() if archive.map_id else ""
    map_mod = library.get(map_mod_name)
    official = official_map(archive.map_id)
    official_id = official.map_id if official is not None and map_mod is None else None

    mods: list[str] = []
    missing: list[str] = []
    for name in archive.mods:
        key = name.lower()
        if key == map_mod_name:
            continue
        filename = library.get(key)
        if filename is None:
            missing.append(name)
        elif filename not in mods:
            mods.append(filename)
    if map_mod is None and official_id is None and map_mod_name:
        missing.insert(0, archive.map_id.split(".", 1)[0])
    return ProfilePlan(
        map_mod=map_mod,
        official_map=official_id,
        mods=tuple(mods),
        missing=tuple(missing),
    )
