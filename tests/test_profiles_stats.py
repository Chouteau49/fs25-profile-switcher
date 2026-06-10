from __future__ import annotations

from pathlib import Path

from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.collection import Collection
from fsmods_gui.profiles.profile import Profile
from fsmods_gui.profiles.stats import compute_stats, human_size


def _entry(filename, category="Véhicule", brand=None, size=1000, is_map=False, error=None):
    return CatalogEntry(
        filename=filename,
        title=Path(filename).stem,
        version="1.0",
        category=category,
        brand=brand,
        size_bytes=size,
        is_map=is_map,
        error=error,
    )


def _catalog(*entries):
    return Catalog(mods_dir=Path("."), entries={e.filename: e for e in entries})


def test_empty_catalog_stats():
    stats = compute_stats(None)
    assert stats.total_mods == 0
    assert stats.orphan_files == []


def test_totals_and_categories():
    cat = _catalog(
        _entry("FS25_Map.zip", category="Carte", size=5000, is_map=True),
        _entry("FS25_Tractor.zip", category="Véhicule", brand="Fendt", size=2000),
        _entry("FS25_Barn.zip", category="Bâtiment", size=3000),
        _entry("FS25_Bad.zip", category="Divers", size=10, error="modDesc.xml manquant"),
    )
    stats = compute_stats(cat)
    assert stats.total_mods == 4
    assert stats.total_size_bytes == 10010
    assert stats.maps == 1
    assert stats.by_category["Véhicule"] == 1
    assert stats.by_category["Carte"] == 1
    assert stats.parse_errors == ["FS25_Bad.zip"]


def test_top_brands_sorted():
    cat = _catalog(
        _entry("a.zip", brand="Fendt"),
        _entry("b.zip", brand="Fendt"),
        _entry("c.zip", brand="Claas"),
    )
    stats = compute_stats(cat)
    assert stats.top_brands[0] == ("Fendt", 2)
    assert ("Claas", 1) in stats.top_brands


def test_duplicates_counted():
    cat = _catalog(
        _entry("FS25_Mod.zip", category="Véhicule"),
        _entry("FS25_Mod (1).zip", category="Véhicule"),
        _entry("FS25_Other.zip", category="Véhicule"),
    )
    stats = compute_stats(cat)
    assert stats.duplicate_groups == 1
    assert stats.duplicate_files == 2


def test_orphans_and_per_profile():
    cat = _catalog(
        _entry("FS25_Used.zip"),
        _entry("FS25_InColl.zip"),
        _entry("FS25_Orphan.zip"),
    )
    col = Collection(name="C", mods=["FS25_InColl.zip"])
    prof = Profile(name="P", mods=["FS25_Used.zip"], collections=[col.slug])
    stats = compute_stats(cat, [prof], [col])
    # Orphan = in library but referenced by no profile/collection.
    assert stats.orphan_files == ["FS25_Orphan.zip"]
    # Effective per profile = own + inherited.
    assert stats.mods_per_profile == [("P", 2)]
    assert stats.mods_per_collection == [("C", 1)]


def test_human_size():
    assert human_size(512) == "512 o"
    assert human_size(1536) == "1.5 Ko"
    assert human_size(5 * 1024 * 1024) == "5.0 Mo"
    assert human_size(2 * 1024**3) == "2.0 Go"
