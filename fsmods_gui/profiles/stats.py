"""Aggregate library statistics for the "Carte des mods" dashboard.

Pure computation over the already-scanned :class:`Catalog`, the loaded
:class:`Profile` list and the :class:`Collection` list — no Qt, no disk access.
Reuses duplicate detection (#2) and the catalog's category/brand fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog
from .collection import Collection
from .duplicates import find_duplicate_groups
from .profile import Profile


@dataclass
class LibraryStats:
    total_mods: int = 0
    total_size_bytes: int = 0
    maps: int = 0
    parse_errors: list[str] = field(default_factory=list)  # filenames with a parse error
    by_category: dict[str, int] = field(default_factory=dict)
    by_category_size: dict[str, int] = field(default_factory=dict)
    top_brands: list[tuple[str, int]] = field(default_factory=list)
    duplicate_groups: int = 0
    duplicate_files: int = 0
    orphan_files: list[str] = field(default_factory=list)  # in library, in no profile/collection
    profiles_count: int = 0
    collections_count: int = 0
    mods_per_profile: list[tuple[str, int]] = field(default_factory=list)  # name -> effective mod count
    mods_per_collection: list[tuple[str, int]] = field(default_factory=list)


def compute_stats(
    catalog: Catalog | None,
    profiles: list[Profile] | None = None,
    collections: list[Collection] | None = None,
    *,
    top_brands: int = 15,
) -> LibraryStats:
    profiles = profiles or []
    collections = collections or []
    stats = LibraryStats(
        profiles_count=len(profiles),
        collections_count=len(collections),
    )
    if catalog is None:
        return stats

    brand_counts: dict[str, int] = {}
    for entry in catalog.entries.values():
        stats.total_mods += 1
        stats.total_size_bytes += entry.size_bytes
        if entry.is_map:
            stats.maps += 1
        if entry.error:
            stats.parse_errors.append(entry.filename)
        cat = entry.category or "Divers"
        stats.by_category[cat] = stats.by_category.get(cat, 0) + 1
        stats.by_category_size[cat] = stats.by_category_size.get(cat, 0) + entry.size_bytes
        if entry.brand:
            brand_counts[entry.brand] = brand_counts.get(entry.brand, 0) + 1

    stats.top_brands = sorted(
        brand_counts.items(), key=lambda kv: (-kv[1], kv[0].lower())
    )[:top_brands]

    groups = find_duplicate_groups(catalog)
    stats.duplicate_groups = len(groups)
    stats.duplicate_files = sum(len(g.entries) for g in groups)

    # Referenced = any profile's own mods/map + any collection's mods.
    collection_mods = {c.slug: list(c.mods) for c in collections}
    referenced: set[str] = set()
    for prof in profiles:
        referenced.update(prof.effective_mod_filenames(collection_mods))
        stats.mods_per_profile.append(
            (prof.name, len(prof.effective_mod_filenames(collection_mods)))
        )
    for col in collections:
        referenced.update(col.mods)
        stats.mods_per_collection.append((col.name, len(col.mods)))

    stats.orphan_files = sorted(
        fname for fname in catalog.entries if fname not in referenced
    )
    stats.mods_per_profile.sort(key=lambda kv: (-kv[1], kv[0].lower()))
    stats.mods_per_collection.sort(key=lambda kv: (-kv[1], kv[0].lower()))
    return stats


def human_size(num_bytes: int) -> str:
    """Format a byte count as a compact human string (e.g. ``1.5 Go``)."""
    size = float(num_bytes)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if size < 1024 or unit == "To":
            if unit == "o":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} To"
