from __future__ import annotations

import os
from pathlib import Path

import pytest

from fsmods_gui.config import Config, GameProfile
from fsmods_gui.profiles.activator import (
    activate_and_launch,
    activate_profile,
    clear_game_mods,
    launch_game,
)
from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.profile import Profile


def _make_zip(path: Path, content: bytes = b"PK\x03\x04dummy") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _catalog_with(library_mods: Path, filenames: list[str]) -> Catalog:
    entries: dict[str, CatalogEntry] = {}
    for fname in filenames:
        _make_zip(library_mods / fname)
        entries[fname] = CatalogEntry(filename=fname, title=fname, version="1.0.0.0")
    return Catalog(mods_dir=library_mods, entries=entries)


def _game_profile(tmp_path: Path) -> GameProfile:
    library = tmp_path / "library"
    (library / "mods").mkdir(parents=True)
    mods_dir = tmp_path / "game" / "mods"
    mods_dir.mkdir(parents=True)
    return GameProfile(
        name="fs25",
        mods_dir=mods_dir,
        library_dir=library,
    )


def test_clear_game_mods_removes_only_zips(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "a.zip").write_bytes(b"x")
    (mods / "b.zip").write_bytes(b"y")
    (mods / "modSettings.xml").write_text("<x/>")
    sub = mods / "savegame1"
    sub.mkdir()

    removed = clear_game_mods(mods)
    assert {p.name for p in removed} == {"a.zip", "b.zip"}
    assert (mods / "modSettings.xml").exists()
    assert sub.is_dir()


def test_clear_game_mods_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert clear_game_mods(tmp_path / "nope") == []


def test_activate_profile_hardlinks_when_same_volume(tmp_path: Path) -> None:
    gp = _game_profile(tmp_path)
    catalog = _catalog_with(
        gp.library_mods_dir, ["FS25_Courseplay.zip", "FS25_Alpenland.zip"]
    )
    profile = Profile(
        name="Montagne",
        mods=["FS25_Courseplay.zip"],
        map_mod="FS25_Alpenland.zip",
    )

    report = activate_profile(profile, gp, catalog)
    assert report.ok
    assert {m.filename for m in report.activated} == {
        "FS25_Courseplay.zip",
        "FS25_Alpenland.zip",
    }
    for activation in report.activated:
        assert activation.dst.exists()
        # tmp_path is on a single volume → hardlink works.
        assert activation.method == "hardlink"
        assert activation.dst.stat().st_ino == activation.src.stat().st_ino


def test_activate_profile_wipes_prior_zips(tmp_path: Path) -> None:
    gp = _game_profile(tmp_path)
    (gp.mods_dir / "stale.zip").write_bytes(b"old")
    (gp.mods_dir / "keep.xml").write_text("<x/>")
    catalog = _catalog_with(gp.library_mods_dir, ["FS25_New.zip"])
    profile = Profile(name="X", mods=["FS25_New.zip"])

    report = activate_profile(profile, gp, catalog)
    assert (gp.mods_dir / "stale.zip").exists() is False
    assert (gp.mods_dir / "keep.xml").exists()
    assert (gp.mods_dir / "FS25_New.zip").exists()
    assert {p.name for p in report.removed} == {"stale.zip"}


def test_activate_profile_reports_missing_mods(tmp_path: Path) -> None:
    gp = _game_profile(tmp_path)
    catalog = _catalog_with(gp.library_mods_dir, ["FS25_Have.zip"])
    profile = Profile(name="X", mods=["FS25_Have.zip", "FS25_Missing.zip"])

    report = activate_profile(profile, gp, catalog)
    assert report.missing == ["FS25_Missing.zip"]
    assert report.ok is False
    assert (gp.mods_dir / "FS25_Have.zip").exists()
    assert (gp.mods_dir / "FS25_Missing.zip").exists() is False


def test_activate_profile_falls_back_to_copy_when_link_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gp = _game_profile(tmp_path)
    catalog = _catalog_with(gp.library_mods_dir, ["FS25_X.zip"])
    profile = Profile(name="X", mods=["FS25_X.zip"])

    def boom(src, dst):
        raise OSError("simulated cross-volume")

    monkeypatch.setattr("fsmods_gui.profiles.activator.os.link", boom)

    report = activate_profile(profile, gp, catalog)
    assert report.ok
    assert report.activated[0].method == "copy"
    assert (gp.mods_dir / "FS25_X.zip").is_file()


def test_activate_profile_requires_library_dir(tmp_path: Path) -> None:
    gp = GameProfile(name="fs25", mods_dir=tmp_path / "mods")
    catalog = Catalog(mods_dir=tmp_path / "nope", entries={})
    profile = Profile(name="X")
    report = activate_profile(profile, gp, catalog)
    assert report.ok is False
    assert report.errors and report.errors[0][0] == "config"


def test_activate_profile_calls_progress(tmp_path: Path) -> None:
    gp = _game_profile(tmp_path)
    catalog = _catalog_with(gp.library_mods_dir, ["A.zip", "B.zip"])
    profile = Profile(name="X", mods=["A.zip", "B.zip"])
    seen: list[tuple[int, int, str]] = []

    activate_profile(profile, gp, catalog, progress=lambda c, t, m: seen.append((c, t, m)))
    assert seen[0][0] == 0          # initial wipe call
    assert seen[-1][0] == seen[-1][1]  # final reaches 100%
    assert any("Activation A.zip" in s[2] for s in seen)


def test_launch_game_returns_false_without_steam_id(tmp_path: Path) -> None:
    gp = GameProfile(name="fs25", mods_dir=tmp_path)
    assert launch_game(gp) is False


def test_activate_and_launch_invokes_launcher_when_ok(tmp_path: Path) -> None:
    gp = _game_profile(tmp_path)
    gp = GameProfile(
        name="fs25",
        mods_dir=gp.mods_dir,
        library_dir=gp.library_dir,
        steam_app_id=2300320,
    )
    catalog = _catalog_with(gp.library_mods_dir, ["A.zip"])
    profile = Profile(name="X", mods=["A.zip"])
    cfg = Config(games={"fs25": gp}, default_game="fs25")

    called: list[GameProfile] = []
    def fake_launcher(gprof: GameProfile) -> bool:
        called.append(gprof)
        return True

    report, launched = activate_and_launch(
        profile, cfg, catalog, launcher=fake_launcher
    )
    assert report.ok
    assert launched is True
    assert called == [gp]


def test_activate_and_launch_skips_launcher_on_error(tmp_path: Path) -> None:
    gp = GameProfile(name="fs25", mods_dir=tmp_path / "mods")  # no library_dir
    catalog = Catalog(mods_dir=tmp_path / "x", entries={})
    cfg = Config(games={"fs25": gp}, default_game="fs25")
    profile = Profile(name="X")
    called: list[GameProfile] = []
    report, launched = activate_and_launch(
        profile, cfg, catalog, launcher=lambda gp: called.append(gp) or True
    )
    assert report.ok is False
    assert launched is False
    assert called == []
