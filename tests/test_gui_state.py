"""Tests for the Qt-free GUI state container."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fsmods_gui.config import Config, GameProfile
from fsmods_gui.state import AppState
from fsmods_gui.profiles.profile import Profile

MODDESC = """<?xml version="1.0" encoding="utf-8"?>
<modDesc descVersion="91">
  <version>1.0.0.0</version>
  <title><en>Test</en></title>
</modDesc>
"""


def _make_zip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("modDesc.xml", MODDESC)
    return path


def _state(tmp_path: Path) -> AppState:
    library = tmp_path / "lib"
    (library / "mods").mkdir(parents=True)
    (library / "profiles").mkdir(parents=True)
    gp = GameProfile(
        name="fs25",
        mods_dir=tmp_path / "game" / "mods",
        library_dir=library,
    )
    cfg = Config(games={"fs25": gp}, default_game="fs25")
    return AppState(cfg=cfg, game_key="fs25")


def test_refresh_catalog_creates_dirs_and_scans(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _make_zip(state.game.library_mods_dir / "Mod.zip")
    catalog = state.refresh_catalog()
    assert "Mod.zip" in catalog
    cache = state.game.library_cache_dir / "index.json"
    assert cache.is_file()


def test_refresh_catalog_requires_library_dir(tmp_path: Path) -> None:
    gp = GameProfile(name="fs25", mods_dir=tmp_path / "g")
    cfg = Config(games={"fs25": gp}, default_game="fs25")
    state = AppState(cfg=cfg, game_key="fs25")
    with pytest.raises(ValueError):
        state.refresh_catalog()


def test_new_profile_saves_and_becomes_current(tmp_path: Path) -> None:
    state = _state(tmp_path)
    prof = state.new_profile("Montagne")
    assert prof.path is not None
    assert prof.path.is_file()
    assert state.current_profile == prof
    assert prof in state.profiles


def test_new_profile_rejects_duplicate(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.new_profile("X")
    with pytest.raises(FileExistsError):
        state.new_profile("X")


def test_delete_profile_removes_file_and_selection(tmp_path: Path) -> None:
    state = _state(tmp_path)
    a = state.new_profile("A")
    b = state.new_profile("B")
    state.current_profile = a
    state.delete_profile(a)
    assert not a.path.exists()
    assert a not in state.profiles
    assert state.current_profile == b


def test_refresh_profiles_picks_up_disk_changes(tmp_path: Path) -> None:
    state = _state(tmp_path)
    Profile(name="OnDisk").save(state.game.library_profiles_dir / "ondisk.json")
    state.refresh_profiles()
    assert [p.name for p in state.profiles] == ["OnDisk"]
    assert state.current_profile is not None
    assert state.current_profile.name == "OnDisk"


def test_save_current_writes_to_disk(tmp_path: Path) -> None:
    state = _state(tmp_path)
    prof = state.new_profile("X")
    prof.description = "edited"
    path = state.save_current()
    assert path == prof.path
    reloaded = Profile.load(path)
    assert reloaded.description == "edited"


# ----------------------------------------------------------------- collections


def test_new_collection_saves(tmp_path: Path) -> None:
    state = _state(tmp_path)
    col = state.new_collection("Viticulture")
    assert col.path is not None and col.path.is_file()
    assert col in state.collections


def test_collection_mods_map_and_effective(tmp_path: Path) -> None:
    state = _state(tmp_path)
    col = state.new_collection("Viti")
    col.mods = ["FS25_Grape.zip", "FS25_Wine.zip"]
    col.save()
    state.refresh_collections()
    prof = state.new_profile("P")
    prof.mods = ["FS25_Own.zip"]
    prof.collections = [col.slug]
    eff = state.effective_filenames(prof)
    assert eff == ["FS25_Own.zip", "FS25_Grape.zip", "FS25_Wine.zip"]


def test_delete_collection_unlinks_profiles(tmp_path: Path) -> None:
    state = _state(tmp_path)
    col = state.new_collection("Viti")
    prof = state.new_profile("P")
    prof.collections = [col.slug]
    prof.save()
    affected = state.delete_collection(col)
    assert affected == ["P"]
    assert col not in state.collections
    assert prof.collections == []
    # Persisted unlink.
    assert Profile.load(prof.path).collections == []


# ----------------------------------------------------------------- delete mods


def test_delete_mods_removes_file_and_cascades(tmp_path: Path) -> None:
    state = _state(tmp_path)
    mods = state.game.library_mods_dir
    _make_zip(mods / "FS25_Map.zip")
    _make_zip(mods / "FS25_Keep.zip")
    _make_zip(mods / "FS25_Gone.zip")
    state.refresh_catalog()

    col = state.new_collection("C")
    col.mods = ["FS25_Gone.zip", "FS25_Keep.zip"]
    col.save()

    prof = state.new_profile("P")
    prof.map_mod = "FS25_Map.zip"
    prof.mods = ["FS25_Gone.zip", "FS25_Keep.zip"]
    prof.excluded_mods = ["FS25_Gone.zip"]
    prof.save()

    result = state.delete_mods(["FS25_Gone.zip", "FS25_Map.zip"])

    # Files gone from disk and catalog.
    assert not (mods / "FS25_Gone.zip").exists()
    assert not (mods / "FS25_Map.zip").exists()
    assert (mods / "FS25_Keep.zip").exists()
    assert "FS25_Gone.zip" not in state.catalog
    assert "FS25_Map.zip" not in state.catalog
    assert set(result.removed_files) == {"FS25_Gone.zip", "FS25_Map.zip"}

    # Cascade into the profile (map cleared, mod + exclusion stripped).
    assert prof.map_mod is None
    assert prof.mods == ["FS25_Keep.zip"]
    assert prof.excluded_mods == []
    assert "P" in result.affected_profiles
    assert Profile.load(prof.path).mods == ["FS25_Keep.zip"]

    # Cascade into the collection.
    assert col.mods == ["FS25_Keep.zip"]
    assert "C" in result.affected_collections


def test_delete_mods_empty_is_noop(tmp_path: Path) -> None:
    state = _state(tmp_path)
    result = state.delete_mods([])
    assert result.removed_files == []
    assert result.affected_profiles == []
    assert result.affected_collections == []
