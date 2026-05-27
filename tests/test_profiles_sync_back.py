from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fsmods_gui.config import GameProfile
from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.profile import Profile
from fsmods_gui.profiles.sync_back import (
    add_to_profile,
    compute_diff,
    import_into_library,
    remove_from_profile,
)

MODDESC = """<?xml version="1.0" encoding="utf-8"?>
<modDesc descVersion="91">
  <version>1.0.0.0</version>
  <title><en>Newcomer</en></title>
</modDesc>
"""


def _make_zip(path: Path, moddesc: str = MODDESC) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("modDesc.xml", moddesc)
    return path


def _gp(tmp_path: Path) -> GameProfile:
    library = tmp_path / "library"
    (library / "mods").mkdir(parents=True)
    mods_dir = tmp_path / "game" / "mods"
    mods_dir.mkdir(parents=True)
    return GameProfile(name="fs25", mods_dir=mods_dir, library_dir=library)


def test_compute_diff_detects_added_removed_and_untracked(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _make_zip(gp.mods_dir / "A.zip")
    _make_zip(gp.mods_dir / "NEW.zip")  # new download in-game
    # B is in the profile but missing from game (user removed it).

    catalog = Catalog(
        mods_dir=gp.library_mods_dir,
        entries={
            "A.zip": CatalogEntry(filename="A.zip", title="A", version="1"),
            "B.zip": CatalogEntry(filename="B.zip", title="B", version="1"),
        },
    )
    profile = Profile(name="X", mods=["A.zip", "B.zip"])

    diff = compute_diff(profile, gp, catalog)
    assert diff.added_in_game == ["NEW.zip"]
    assert diff.removed_in_game == ["B.zip"]
    assert diff.untracked_in_library == ["NEW.zip"]
    assert diff.updated_in_game == []
    assert diff.has_changes


def test_compute_diff_no_changes(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _make_zip(gp.mods_dir / "A.zip")
    catalog = Catalog(
        mods_dir=gp.library_mods_dir,
        entries={"A.zip": CatalogEntry(filename="A.zip", title="A", version="1")},
    )
    profile = Profile(name="X", mods=["A.zip"])
    diff = compute_diff(profile, gp, catalog)
    assert not diff.has_changes


def test_compute_diff_detects_updated_mod(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _make_zip(gp.mods_dir / "A.zip", moddesc=MODDESC.replace("1.0.0.0", "1.2.0.0"))

    lib_a = gp.library_mods_dir / "A.zip"
    _make_zip(lib_a, moddesc=MODDESC.replace("1.0.0.0", "1.0.0.0"))

    catalog = Catalog(
        mods_dir=gp.library_mods_dir,
        entries={"A.zip": CatalogEntry(filename="A.zip", title="A", version="1")},
    )
    profile = Profile(name="X", mods=["A.zip"])

    diff = compute_diff(profile, gp, catalog)
    assert diff.added_in_game == []
    assert diff.removed_in_game == []
    assert diff.untracked_in_library == []
    assert diff.updated_in_game == ["A.zip"]
    assert diff.has_changes


def test_import_into_library_copies_and_updates_catalog(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _make_zip(gp.mods_dir / "NEW.zip")
    catalog = Catalog(mods_dir=gp.library_mods_dir, entries={})

    import_into_library("NEW.zip", gp, catalog)
    assert (gp.library_mods_dir / "NEW.zip").is_file()
    entry = catalog.get("NEW.zip")
    assert entry is not None
    assert entry.title == "Newcomer"


def test_import_into_library_overwrites_existing(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _make_zip(gp.mods_dir / "X.zip")
    older = gp.library_mods_dir / "X.zip"
    older.write_bytes(b"older")
    catalog = Catalog(mods_dir=gp.library_mods_dir, entries={})
    import_into_library("X.zip", gp, catalog)
    assert older.read_bytes() != b"older"


def test_import_into_library_requires_library_dir(tmp_path: Path) -> None:
    gp = GameProfile(name="fs25", mods_dir=tmp_path)
    with pytest.raises(ValueError):
        import_into_library("X.zip", gp, Catalog(mods_dir=tmp_path, entries={}))


def test_import_into_library_missing_source(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    with pytest.raises(FileNotFoundError):
        import_into_library("X.zip", gp, Catalog(mods_dir=gp.library_mods_dir, entries={}))


def test_add_to_profile_dedups() -> None:
    p = Profile(name="X", mods=["A.zip"], map_mod="Map.zip")
    assert add_to_profile(p, "A.zip") is False
    assert add_to_profile(p, "Map.zip") is False
    assert add_to_profile(p, "B.zip") is True
    assert p.mods == ["A.zip", "B.zip"]


def test_remove_from_profile_handles_mods_and_map() -> None:
    p = Profile(name="X", mods=["A.zip", "B.zip"], map_mod="Map.zip")
    assert remove_from_profile(p, "Z.zip") is False
    assert remove_from_profile(p, "B.zip") is True
    assert p.mods == ["A.zip"]
    assert remove_from_profile(p, "Map.zip") is True
    assert p.map_mod is None
