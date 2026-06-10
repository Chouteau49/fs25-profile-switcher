from __future__ import annotations

from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.duplicates import (
    DUP_CONTENT,
    DUP_FILENAME,
    find_duplicate_groups,
    normalize_stem,
    duplicate_filenames,
)


def _entry(filename: str, title: str = "", author: str = "", version: str = "1.0.0.0") -> CatalogEntry:
    return CatalogEntry(filename=filename, title=title or filename, version=version, author=author or None)


def _catalog(*entries: CatalogEntry) -> Catalog:
    return Catalog(mods_dir=__import__("pathlib").Path("."), entries={e.filename: e for e in entries})


def test_normalize_strips_copy_marker() -> None:
    assert normalize_stem("FS25_Courseplay.zip") == "fs25_courseplay"
    assert normalize_stem("FS25_Courseplay (1).zip") == "fs25_courseplay"
    assert normalize_stem("FS25_Courseplay (2).zip") == "fs25_courseplay"


def test_normalize_strips_version_and_words() -> None:
    assert normalize_stem("FS25_Mod_v1.2.3.zip") == "fs25_mod"
    assert normalize_stem("FS25_Mod_old.zip") == "fs25_mod"
    assert normalize_stem("FS25_Mod - copie.zip") == "fs25_mod"


def test_no_duplicates_returns_empty() -> None:
    cat = _catalog(_entry("FS25_A.zip", "Alpha"), _entry("FS25_B.zip", "Beta"))
    assert find_duplicate_groups(cat) == []


def test_filename_duplicate_detected() -> None:
    cat = _catalog(
        _entry("FS25_Courseplay.zip", "Courseplay"),
        _entry("FS25_Courseplay (1).zip", "Courseplay"),
    )
    groups = find_duplicate_groups(cat)
    assert len(groups) == 1
    assert groups[0].kind == DUP_FILENAME
    assert set(groups[0].filenames()) == {"FS25_Courseplay.zip", "FS25_Courseplay (1).zip"}


def test_content_duplicate_detected_when_filenames_differ() -> None:
    cat = _catalog(
        _entry("FS25_BigTractor.zip", "Super Tractor", author="ModderX"),
        _entry("FS25_GiantTractor.zip", "Super Tractor", author="ModderX"),
    )
    groups = find_duplicate_groups(cat)
    assert len(groups) == 1
    assert groups[0].kind == DUP_CONTENT
    assert groups[0].label == "Super Tractor"


def test_filename_group_wins_over_content_group() -> None:
    cat = _catalog(
        _entry("FS25_Mod.zip", "Same Title", author="A"),
        _entry("FS25_Mod (1).zip", "Same Title", author="A"),
    )
    groups = find_duplicate_groups(cat)
    # Only one (filename) group, not also a content group for the same files.
    assert len(groups) == 1
    assert groups[0].kind == DUP_FILENAME


def test_weak_titles_do_not_trigger_content_dupes() -> None:
    # Titles equal to filename (no real metadata) must not group.
    cat = _catalog(_entry("FS25_X.zip", "FS25_X"), _entry("FS25_Y.zip", "FS25_Y"))
    assert find_duplicate_groups(cat) == []


def test_duplicate_filenames_flat_set() -> None:
    cat = _catalog(
        _entry("FS25_Courseplay.zip", "Courseplay"),
        _entry("FS25_Courseplay (1).zip", "Courseplay"),
        _entry("FS25_Other.zip", "Other"),
    )
    assert duplicate_filenames(cat) == {"FS25_Courseplay.zip", "FS25_Courseplay (1).zip"}


def test_none_catalog_safe() -> None:
    assert find_duplicate_groups(None) == []
    assert duplicate_filenames(None) == set()
