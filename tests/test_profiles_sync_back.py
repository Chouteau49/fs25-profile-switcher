from __future__ import annotations

import os
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
    snapshot_fingerprints,
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
    os.utime(lib_a, (1, 1))  # same size, and both could land on the same clock tick

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


def test_compute_diff_detects_updated_mod_with_snapshot_even_if_library_matches(tmp_path: Path) -> None:
    gp = _gp(tmp_path)

    # Initial state before game launch.
    _make_zip(gp.mods_dir / "A.zip", moddesc=MODDESC.replace("1.0.0.0", "1.0.0.0"))
    _make_zip(gp.library_mods_dir / "A.zip", moddesc=MODDESC.replace("1.0.0.0", "1.0.0.0"))

    profile = Profile(name="X", mods=["A.zip"])
    baseline = snapshot_fingerprints(gp.mods_dir, profile.all_mod_filenames())

    # Simulate in-game update with hardlink-like final state:
    # game and library both end up with the new content.
    _make_zip(gp.mods_dir / "A.zip", moddesc=MODDESC.replace("1.0.0.0", "1.3.0.0"))
    _make_zip(gp.library_mods_dir / "A.zip", moddesc=MODDESC.replace("1.0.0.0", "1.3.0.0"))
    os.utime(gp.mods_dir / "A.zip", (1, 1))  # same size: the time is what changed

    catalog = Catalog(
        mods_dir=gp.library_mods_dir,
        entries={"A.zip": CatalogEntry(filename="A.zip", title="A", version="1")},
    )

    diff = compute_diff(profile, gp, catalog, baseline=baseline)
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


# ---------------------------------------------- mods inherited from a collection


def _linked(gp: GameProfile, name: str) -> None:
    import os

    _make_zip(gp.library_mods_dir / name)
    os.link(gp.library_mods_dir / name, gp.mods_dir / name)


def test_inherited_mods_are_not_reported_as_new(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _linked(gp, "Own.zip")
    _linked(gp, "Inherited.zip")
    _make_zip(gp.mods_dir / "Downloaded.zip")
    catalog = Catalog(
        mods_dir=gp.library_mods_dir,
        entries={
            n: CatalogEntry(filename=n, title=n, version="1")
            for n in ("Own.zip", "Inherited.zip")
        },
    )
    profile = Profile(name="P", mods=["Own.zip"], collections=["c"])

    diff = compute_diff(profile, gp, catalog, effective=["Own.zip", "Inherited.zip"])

    assert diff.added_in_game == ["Downloaded.zip"]
    assert diff.removed_in_game == []


def test_missing_inherited_mod_is_not_offered_for_removal(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    catalog = Catalog(mods_dir=gp.library_mods_dir, entries={})
    profile = Profile(name="P", mods=["Own.zip"], collections=["c"])
    diff = compute_diff(profile, gp, catalog, effective=["Own.zip", "Inherited.zip"])
    # remove_from_profile can only drop the profile's own mods
    assert diff.removed_in_game == ["Own.zip"]


def test_import_into_library_of_a_hardlinked_mod_is_a_no_op(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _linked(gp, "Linked.zip")
    catalog = Catalog(mods_dir=gp.library_mods_dir, entries={})
    import_into_library("Linked.zip", gp, catalog)
    assert "Linked.zip" in catalog.entries
    assert (gp.library_mods_dir / "Linked.zip").is_file()


# ------------------------------------------- no reading of whole mods to compare


def _no_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if a zip is read: a profile weighs up to 30 GB."""
    import filecmp

    def refuse(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("contenu lu alors que les métadonnées suffisent")

    monkeypatch.setattr(filecmp, "cmp", refuse)


def test_snapshot_and_diff_of_hardlinked_mods_read_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gp = _gp(tmp_path)
    _linked(gp, "A.zip")
    catalog = Catalog(
        mods_dir=gp.library_mods_dir,
        entries={"A.zip": CatalogEntry(filename="A.zip", title="A", version="1")},
    )
    profile = Profile(name="X", mods=["A.zip"])
    _no_read(monkeypatch)
    baseline = snapshot_fingerprints(gp.mods_dir, ["A.zip", "Gone.zip"])
    assert list(baseline) == ["A.zip"]
    assert not compute_diff(profile, gp, catalog, baseline=baseline).has_changes


def _catalog_of(gp: GameProfile, name: str) -> Catalog:
    return Catalog(
        mods_dir=gp.library_mods_dir,
        entries={name: CatalogEntry(filename=name, title=name, version="1")},
    )


def test_a_mod_replaced_during_the_game_is_detected(tmp_path: Path) -> None:
    gp = _gp(tmp_path)
    _linked(gp, "A.zip")
    profile = Profile(name="X", mods=["A.zip"])
    baseline = snapshot_fingerprints(gp.mods_dir, ["A.zip"])
    (gp.mods_dir / "A.zip").unlink()  # ModHub update: the link is replaced by a new file
    _make_zip(gp.mods_dir / "A.zip", moddesc=MODDESC.replace("Newcomer", "Longer title"))
    diff = compute_diff(profile, gp, _catalog_of(gp, "A.zip"), baseline=baseline)
    assert diff.updated_in_game == ["A.zip"]


def test_copies_are_compared_without_a_baseline(tmp_path: Path) -> None:
    import shutil

    gp = _gp(tmp_path)
    _make_zip(gp.library_mods_dir / "A.zip")
    profile = Profile(name="X", mods=["A.zip"])
    shutil.copy2(gp.library_mods_dir / "A.zip", gp.mods_dir / "A.zip")  # cross-volume copy
    assert compute_diff(profile, gp, _catalog_of(gp, "A.zip")).updated_in_game == []

    data = (gp.library_mods_dir / "A.zip").read_bytes()
    (gp.mods_dir / "A.zip").write_bytes(data[:-1] + bytes([data[-1] ^ 1]))  # same size
    os.utime(gp.mods_dir / "A.zip", (1, 1))  # never the same clock tick as the copy
    assert compute_diff(profile, gp, _catalog_of(gp, "A.zip")).updated_in_game == ["A.zip"]
