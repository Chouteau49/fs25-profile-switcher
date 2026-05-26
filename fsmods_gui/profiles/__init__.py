"""Mod library + per-save profile management (used by the GUI).

This package owns the data model for:
  * the on-disk library at ``<library_dir>/mods/*.zip`` (read-only catalog),
  * the per-savegame profiles stored as JSON under ``<library_dir>/profiles/``,
  * activation: replacing the game's ``mods/`` folder with the profile selection
    via NTFS hardlinks (falling back to copy across volumes).
"""
from __future__ import annotations

from .catalog import Catalog, CatalogEntry, scan_library
from .profile import Profile, ProfileError

__all__ = [
    "Catalog",
    "CatalogEntry",
    "Profile",
    "ProfileError",
    "scan_library",
]
