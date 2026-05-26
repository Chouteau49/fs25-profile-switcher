from __future__ import annotations

import json
from pathlib import Path

import pytest

from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.profile import (
    PROFILE_SCHEMA_VERSION,
    Profile,
    ProfileError,
    list_profiles,
    profile_path_for,
    slugify,
)


def test_slugify_basic() -> None:
    assert slugify("Montagne") == "montagne"
    assert slugify("Grandes Plaines") == "grandes-plaines"
    assert slugify("  No Man's Land  ") == "no-man-s-land"
    assert slugify("FR / DE") == "fr-de"
    assert slugify("???") == "profile"


def test_profile_save_and_load_roundtrip(tmp_path: Path) -> None:
    p = Profile(
        name="Montagne",
        game="fs25",
        mods=["FS25_Courseplay.zip", "FS25_EasyDev.zip"],
        map_mod="FS25_Alpenland.zip",
        description="Partie alpine",
    )
    out = p.save(tmp_path / "montagne.json")
    assert out.is_file()

    data = json.loads(out.read_text())
    assert data["schema"] == PROFILE_SCHEMA_VERSION
    assert data["name"] == "Montagne"
    assert data["map_mod"] == "FS25_Alpenland.zip"
    assert data["created_at"]  # auto-set

    loaded = Profile.load(out)
    assert loaded.name == "Montagne"
    assert loaded.mods == ["FS25_Courseplay.zip", "FS25_EasyDev.zip"]
    assert loaded.map_mod == "FS25_Alpenland.zip"
    assert loaded.path == out


def test_profile_save_requires_path() -> None:
    p = Profile(name="X")
    with pytest.raises(ProfileError):
        p.save()


def test_profile_all_mod_filenames_dedup_with_map_first() -> None:
    p = Profile(
        name="X",
        mods=["A.zip", "B.zip", "Map.zip"],  # Map.zip already in mods
        map_mod="Map.zip",
    )
    # Map comes first, no duplicate, order preserved otherwise.
    assert p.all_mod_filenames() == ["Map.zip", "A.zip", "B.zip"]


def test_profile_all_mod_filenames_no_map() -> None:
    p = Profile(name="X", mods=["A.zip", "B.zip"])
    assert p.all_mod_filenames() == ["A.zip", "B.zip"]


def test_profile_missing_against_catalog() -> None:
    cat = Catalog(
        mods_dir=Path("/x"),
        entries={
            "A.zip": CatalogEntry(filename="A.zip", title="A", version="1"),
        },
    )
    p = Profile(name="X", mods=["A.zip", "B.zip"], map_mod="Map.zip")
    assert p.missing_against(cat) == ["Map.zip", "B.zip"]


def test_profile_load_rejects_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ProfileError):
        Profile.load(bad)


def test_profile_load_rejects_wrong_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": 99, "name": "X"}))
    with pytest.raises(ProfileError):
        Profile.load(bad)


def test_profile_load_rejects_empty_name(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": 1, "name": "  "}))
    with pytest.raises(ProfileError):
        Profile.load(bad)


def test_profile_load_rejects_non_string_mods(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": 1, "name": "X", "mods": [1, 2]}))
    with pytest.raises(ProfileError):
        Profile.load(bad)


def test_list_profiles_skips_broken(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    Profile(name="A").save(profiles_dir / "a.json")
    Profile(name="B").save(profiles_dir / "b.json")
    (profiles_dir / "broken.json").write_text("{not json")
    (profiles_dir / "ignored.txt").write_text("nope")

    listed = list_profiles(profiles_dir)
    names = [p.name for p in listed]
    assert names == ["A", "B"]


def test_list_profiles_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert list_profiles(tmp_path / "missing") == []


def test_profile_path_for_uses_slug(tmp_path: Path) -> None:
    p = profile_path_for(tmp_path, "Grandes Plaines!")
    assert p.parent == tmp_path
    assert p.name == "grandes-plaines.json"
