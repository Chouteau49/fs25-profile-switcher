"""Resolve mod dependencies declared in ``modDesc.xml`` ``<dependencies>``.

Farming Simulator lets a mod declare other mods it needs by *modName* (the
other mod's ``.zip`` stem). We parse those into :attr:`CatalogEntry.requires`
during the catalog scan; this module turns them into actionable lists: which
required mods are present in the library (so we can offer to add them) and which
are missing (so we can warn).

Coverage is **best-effort**: many mods leave ``<dependencies>`` empty, so an
empty result does not mean "no dependencies".

Pure logic, no Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog, CatalogEntry


def build_modid_index(catalog: Catalog | None) -> dict[str, str]:
    """Map ``mod_id`` (lower-cased) → filename for every catalog entry.

    Lower-casing makes dependency lookups case-insensitive, since declared
    modNames don't always match the on-disk filename casing.
    """
    index: dict[str, str] = {}
    if catalog is None:
        return index
    for entry in catalog.entries.values():
        index.setdefault(entry.mod_id.lower(), entry.filename)
    return index


@dataclass
class DependencyResolution:
    """Outcome of resolving the dependency closure of some seed mods."""

    to_add: list[str] = field(default_factory=list)   # dep filenames present in lib, not yet in profile
    missing: list[str] = field(default_factory=list)  # required modNames absent from the library

    @property
    def has_any(self) -> bool:
        return bool(self.to_add or self.missing)


def resolve_new_dependencies(
    seed_filenames: list[str],
    existing_filenames: list[str],
    catalog: Catalog | None,
) -> DependencyResolution:
    """Compute the transitive dependencies pulled in by ``seed_filenames``.

    ``existing_filenames`` is what the profile already contains (typically the
    seeds plus whatever was there before); dependencies already satisfied by it
    are not re-offered. The full transitive closure is walked, so a dependency's
    own dependencies are discovered too.

    Returns deps present in the library but not yet in the profile (``to_add``)
    and required modNames with no matching library file (``missing``).
    """
    if catalog is None:
        return DependencyResolution()

    index = build_modid_index(catalog)
    existing = {f for f in existing_filenames}

    to_add: list[str] = []
    to_add_seen: set[str] = set()
    missing: list[str] = []
    missing_seen: set[str] = set()

    visited: set[str] = set()
    queue: list[str] = list(seed_filenames)

    while queue:
        filename = queue.pop(0)
        if filename in visited:
            continue
        visited.add(filename)
        entry: CatalogEntry | None = catalog.get(filename)
        if entry is None:
            continue
        for req in entry.requires:
            key = req.strip().lower()
            if not key:
                continue
            dep_filename = index.get(key)
            if dep_filename is None:
                if key not in missing_seen:
                    missing_seen.add(key)
                    missing.append(req.strip())
                continue
            # Present in library — always traverse it to find transitive deps.
            if dep_filename not in visited:
                queue.append(dep_filename)
            # Only offer to add it if the profile doesn't already have it.
            if dep_filename not in existing and dep_filename not in to_add_seen:
                to_add_seen.add(dep_filename)
                to_add.append(dep_filename)

    to_add.sort(key=str.lower)
    missing.sort(key=str.lower)
    return DependencyResolution(to_add=to_add, missing=missing)
