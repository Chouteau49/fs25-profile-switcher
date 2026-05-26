from __future__ import annotations

from pathlib import Path

import pytest

from fsmods_gui import config as cfgmod


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cfgmod.load(tmp_path / "nope.yaml")


def test_load_rejects_placeholder_path(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "default_game: fs25\n"
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /path/to/FarmingSimulator2025/mods\n"
    )
    with pytest.raises(ValueError):
        cfgmod.load(p)


def test_load_rejects_missing_games(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("pull_overwrite: true\n")
    with pytest.raises(ValueError):
        cfgmod.load(p)


def test_load_rejects_unknown_default_game(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "default_game: fs23\n"
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
    )
    with pytest.raises(ValueError):
        cfgmod.load(p)


def test_load_expands_user_and_defaults(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "default_game: fs25\n"
        "games:\n"
        "  fs25:\n"
        "    mods_dir: ~/fsmods\n"
    )
    cfg = cfgmod.load(p)
    assert cfg.profile("fs25").mods_dir == Path("~/fsmods").expanduser()
    assert cfg.default_game == "fs25"
    assert cfg.pull_overwrite is False
    assert cfg.push_overwrite is True


def test_load_reads_multi_game_and_overrides(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "default_game: fs22\n"
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
        "  fs22:\n"
        "    mods_dir: /tmp/fs22\n"
        "pull_overwrite: true\n"
        "push_overwrite: false\n"
    )
    cfg = cfgmod.load(p)
    assert set(cfg.games) == {"fs25", "fs22"}
    assert cfg.default_game == "fs22"
    assert cfg.profile().mods_dir == Path("/tmp/fs22")
    assert cfg.profile("fs25").mods_dir == Path("/tmp/fs25")
    assert cfg.pull_overwrite is True
    assert cfg.push_overwrite is False


def test_default_game_falls_back_to_first(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
    )
    cfg = cfgmod.load(p)
    assert cfg.default_game == "fs25"


def test_profile_rejects_unknown_game(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
    )
    cfg = cfgmod.load(p)
    with pytest.raises(KeyError):
        cfg.profile("fs22")


def test_install_dir_optional(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
    )
    cfg = cfgmod.load(p)
    assert cfg.profile("fs25").install_dir is None
    assert cfg.profile("fs25").find_moddesc_xsd() is None


def test_install_dir_loaded(tmp_path: Path) -> None:
    install = tmp_path / "fs25_install"
    install.mkdir()
    p = tmp_path / "config.yaml"
    p.write_text(
        f"games:\n"
        f"  fs25:\n"
        f"    mods_dir: /tmp/fs25\n"
        f"    install_dir: {install}\n"
    )
    cfg = cfgmod.load(p)
    assert cfg.profile("fs25").install_dir == install


def test_install_dir_placeholder_ignored(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
        "    install_dir: /path/to/Farming Simulator 25\n"
    )
    cfg = cfgmod.load(p)
    assert cfg.profile("fs25").install_dir is None


def test_find_moddesc_xsd_in_install_dir(tmp_path: Path) -> None:
    install = tmp_path / "fs25_install"
    xsd_dir = install / "data" / "shared" / "xml"
    xsd_dir.mkdir(parents=True)
    xsd = xsd_dir / "modDesc.xsd"
    xsd.write_text('<?xml version="1.0"?><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')

    from fsmods_gui.config import GameProfile
    profile = GameProfile(name="fs25", mods_dir=tmp_path / "mods", install_dir=install)
    assert profile.find_moddesc_xsd() == xsd


def test_library_dir_optional(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
    )
    cfg = cfgmod.load(p)
    profile = cfg.profile("fs25")
    assert profile.library_dir is None
    assert profile.library_mods_dir is None
    assert profile.library_profiles_dir is None
    assert profile.library_cache_dir is None


def test_library_dir_loaded(tmp_path: Path) -> None:
    library = tmp_path / "library"
    p = tmp_path / "config.yaml"
    p.write_text(
        f"games:\n"
        f"  fs25:\n"
        f"    mods_dir: /tmp/fs25\n"
        f"    library_dir: {library}\n"
    )
    cfg = cfgmod.load(p)
    profile = cfg.profile("fs25")
    assert profile.library_dir == library
    assert profile.library_mods_dir == library / "mods"
    assert profile.library_profiles_dir == library / "profiles"
    assert profile.library_cache_dir == library / "cache"


def test_library_dir_placeholder_ignored(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
        "    library_dir: /path/to/FS25-Library\n"
    )
    cfg = cfgmod.load(p)
    assert cfg.profile("fs25").library_dir is None


def test_steam_app_id_optional(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
    )
    cfg = cfgmod.load(p)
    profile = cfg.profile("fs25")
    assert profile.steam_app_id is None
    assert profile.steam_launch_url() is None


def test_steam_app_id_loaded(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
        "    steam_app_id: 2300320\n"
    )
    cfg = cfgmod.load(p)
    profile = cfg.profile("fs25")
    assert profile.steam_app_id == 2300320
    assert profile.steam_launch_url() == "steam://rungameid/2300320"


def test_steam_app_id_invalid_raises(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "games:\n"
        "  fs25:\n"
        "    mods_dir: /tmp/fs25\n"
        "    steam_app_id: not-a-number\n"
    )
    with pytest.raises(ValueError):
        cfgmod.load(p)
