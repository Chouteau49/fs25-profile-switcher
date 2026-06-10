from __future__ import annotations

import json
from pathlib import Path

import pytest

from fsmods_gui.profiles.collection import (
    COLLECTION_SCHEMA_VERSION,
    Collection,
    collection_path_for,
    list_collections,
)
from fsmods_gui.profiles.profile import (
    PROFILE_SCHEMA_VERSION,
    Profile,
    ProfileError,
)


# ----------------------------------------------------------------- Collection


def test_collection_roundtrip(tmp_path: Path) -> None:
    col = Collection(name="Viticulture", mods=["FS25_A.zip", "FS25_B.zip"])
    path = collection_path_for(tmp_path, "Viticulture")
    col.save(path)
    assert path.is_file()
    loaded = Collection.load(path)
    assert loaded.name == "Viticulture"
    assert loaded.mods == ["FS25_A.zip", "FS25_B.zip"]
    assert loaded.slug == "viticulture"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == COLLECTION_SCHEMA_VERSION


def test_list_collections_sorted(tmp_path: Path) -> None:
    Collection(name="Zeta").save(collection_path_for(tmp_path, "Zeta"))
    Collection(name="Alpha").save(collection_path_for(tmp_path, "Alpha"))
    names = [c.name for c in list_collections(tmp_path)]
    assert names == ["Alpha", "Zeta"]


def test_collection_rejects_bad_schema(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"schema": 99, "name": "X"}), encoding="utf-8")
    with pytest.raises(ProfileError):
        Collection.load(p)


# --------------------------------------------------- Profile v2 + effective


def test_profile_saves_schema_v2(tmp_path: Path) -> None:
    prof = Profile(name="P", collections=["viticulture"], excluded_mods=["FS25_X.zip"])
    path = tmp_path / "p.json"
    prof.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == PROFILE_SCHEMA_VERSION == 2
    assert data["collections"] == ["viticulture"]
    assert data["excluded_mods"] == ["FS25_X.zip"]


def test_v1_profile_migrates_on_load(tmp_path: Path) -> None:
    p = tmp_path / "old.json"
    p.write_text(
        json.dumps(
            {
                "schema": 1,
                "name": "Old",
                "game": "fs25",
                "map_mod": "FS25_Map.zip",
                "mods": ["FS25_A.zip"],
            }
        ),
        encoding="utf-8",
    )
    prof = Profile.load(p)
    assert prof.collections == []
    assert prof.excluded_mods == []
    # Re-saving upgrades the file to v2.
    prof.save()
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == 2


def test_effective_includes_collection_mods() -> None:
    prof = Profile(name="P", mods=["FS25_Own.zip"], collections=["viti"])
    eff = prof.effective_mod_filenames({"viti": ["FS25_Grape.zip", "FS25_Wine.zip"]})
    assert eff == ["FS25_Own.zip", "FS25_Grape.zip", "FS25_Wine.zip"]


def test_effective_dedups_and_keeps_map_first() -> None:
    prof = Profile(
        name="P",
        map_mod="FS25_Map.zip",
        mods=["FS25_Own.zip"],
        collections=["viti"],
    )
    eff = prof.effective_mod_filenames({"viti": ["FS25_Own.zip", "FS25_Grape.zip"]})
    assert eff == ["FS25_Map.zip", "FS25_Own.zip", "FS25_Grape.zip"]


def test_effective_applies_exclusions() -> None:
    prof = Profile(
        name="P",
        collections=["viti"],
        excluded_mods=["FS25_Grape.zip"],
    )
    eff = prof.effective_mod_filenames({"viti": ["FS25_Grape.zip", "FS25_Wine.zip"]})
    assert eff == ["FS25_Wine.zip"]


def test_exclusion_never_drops_map() -> None:
    prof = Profile(name="P", map_mod="FS25_Map.zip", excluded_mods=["FS25_Map.zip"])
    assert prof.effective_mod_filenames() == ["FS25_Map.zip"]


def test_inherited_mod_filenames_tracks_sources() -> None:
    prof = Profile(name="P", collections=["a", "b"])
    inh = prof.inherited_mod_filenames(
        {"a": ["FS25_X.zip"], "b": ["FS25_X.zip", "FS25_Y.zip"]}
    )
    assert inh["FS25_X.zip"] == ["a", "b"]
    assert inh["FS25_Y.zip"] == ["b"]


def test_missing_against_uses_effective() -> None:
    from fsmods_gui.profiles.catalog import Catalog, CatalogEntry

    cat = Catalog(mods_dir=Path("."), entries={
        "FS25_Own.zip": CatalogEntry(filename="FS25_Own.zip", title="o", version="1"),
    })
    prof = Profile(name="P", mods=["FS25_Own.zip"], collections=["viti"])
    missing = prof.missing_against(cat, {"viti": ["FS25_Grape.zip"]})
    assert missing == ["FS25_Grape.zip"]
