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
