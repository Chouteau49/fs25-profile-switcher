"""Reconcile the game's ``mods/`` folder back into the library + active profile.

After a play session the user may have:
  * downloaded a new mod **into the game folder** (via in-game ModHub),
  * removed a mod they didn't like.

This module compares ``game.mods_dir`` to ``profile.all_mod_filenames()`` and
produces an actionable diff. It also exposes apply helpers to:
  * copy a new zip into the library + add it to the active profile,
  * ignore it (no-op).
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..config import GameProfile
from .catalog import Catalog, _read_moddesc_from_zip
from .profile import Profile


@dataclass
class SyncDiff:
    """Difference between what's in the game folder vs. what the profile lists."""

    added_in_game: list[str] = field(default_factory=list)
    """Zips present in the game folder but absent from the profile."""

    removed_in_game: list[str] = field(default_factory=list)
    """Zips referenced by the profile but no longer present in the game folder."""

    untracked_in_library: list[str] = field(default_factory=list)
    """Zips in the game folder that the library doesn't know about yet."""

    updated_in_game: list[str] = field(default_factory=list)
    """Zips present in profile+library+game but changed in the game folder."""

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_in_game
            or self.removed_in_game
            or self.untracked_in_library
            or self.updated_in_game
        )


def _list_game_zips(mods_dir: Path) -> list[str]:
    if not mods_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in mods_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".zip"
    )


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_updated_in_game(filename: str, game_profile: GameProfile, catalog: Catalog) -> bool:
    if game_profile.library_mods_dir is None:
        return False
    game_zip = game_profile.mods_dir / filename
    library_zip = game_profile.library_mods_dir / filename
    if not game_zip.is_file() or not library_zip.is_file():
        return False
    return _sha256(game_zip) != _sha256(library_zip)


def compute_diff(
    profile: Profile, game_profile: GameProfile, catalog: Catalog
) -> SyncDiff:
    """Compare the live game folder to ``profile`` and ``catalog``."""
    game_zips = set(_list_game_zips(game_profile.mods_dir))
    profile_zips = set(profile.all_mod_filenames())
    library_zips = set(catalog.entries)

    diff = SyncDiff()
    diff.added_in_game = sorted(game_zips - profile_zips)
    diff.removed_in_game = sorted(profile_zips - game_zips)
    diff.untracked_in_library = sorted(game_zips - library_zips)
    common_tracked = game_zips & profile_zips & library_zips
    diff.updated_in_game = sorted(
        filename
        for filename in common_tracked
        if _is_updated_in_game(filename, game_profile, catalog)
    )
    return diff


def import_into_library(
    filename: str, game_profile: GameProfile, catalog: Catalog
) -> Catalog:
    """Copy ``filename`` from the game folder into the library and update the catalog.

    Existing files in the library are overwritten — the game folder version wins,
    matching the user's most-recent download.
    """
    if game_profile.library_mods_dir is None:
        raise ValueError("library_dir not configured for this game.")
    src = game_profile.mods_dir / filename
    if not src.is_file():
        raise FileNotFoundError(f"{filename} not found in game folder.")
    library_mods = game_profile.library_mods_dir
    library_mods.mkdir(parents=True, exist_ok=True)
    dst = library_mods / filename
    shutil.copy2(src, dst)
    catalog.entries[filename] = _read_moddesc_from_zip(dst)
    return catalog


def add_to_profile(profile: Profile, filename: str) -> bool:
    """Add ``filename`` to ``profile.mods`` (or set as map if applicable).

    Returns True if the profile was modified.
    """
    if filename == profile.map_mod or filename in profile.mods:
        return False
    profile.mods.append(filename)
    return True


def remove_from_profile(profile: Profile, filename: str) -> bool:
    """Drop ``filename`` from the profile. Returns True if anything changed."""
    changed = False
    if profile.map_mod == filename:
        profile.map_mod = None
        changed = True
    if filename in profile.mods:
        profile.mods.remove(filename)
        changed = True
    return changed
