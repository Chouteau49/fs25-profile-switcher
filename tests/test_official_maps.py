from __future__ import annotations

from pathlib import Path

from PIL import Image

from fsmods_gui.profiles.official_maps import (
    official_map,
    official_map_thumbnail,
    steam_root,
)


def test_official_map_lookup() -> None:
    assert official_map("MapUS").title == "Riverbend Springs"
    assert official_map("mapeu").title == "Zielonka"  # case-insensitive / folder name
    kinlaig = official_map("pdlc_highlandsFishingPack.HighlandsFishingMap")
    assert kinlaig is not None and kinlaig.is_dlc and kinlaig.title == "Kinlaig"
    assert official_map("FS25_The_Mechet.FS25_Le_Mechet") is None
    assert official_map(None) is None


def test_steam_root_only_for_steam_installs(tmp_path: Path) -> None:
    install = tmp_path / "Steam" / "steamapps" / "common" / "Farming Simulator 25"
    assert steam_root(install) == tmp_path / "Steam"
    assert steam_root(tmp_path / "Giants" / "FS25") is None
    assert steam_root(None) is None


def test_base_map_thumbnail_from_preview(tmp_path: Path) -> None:
    install = tmp_path / "install"
    ui = install / "data" / "maps" / "mapUS" / "textures" / "ui"
    ui.mkdir(parents=True)
    Image.new("RGB", (512, 512), "blue").save(ui / "preview.png")
    cache = tmp_path / "cache"
    thumb = official_map_thumbnail("MapUS", install, cache)
    assert thumb == cache / "official_maps" / "MapUS.png"
    with Image.open(thumb) as img:
        assert img.size == (256, 256)
    # cached: a second call does not need the source any more
    (ui / "preview.png").unlink()
    assert official_map_thumbnail("MapUS", install, cache) == thumb


def test_dlc_thumbnail_from_steam_header_is_cropped(tmp_path: Path) -> None:
    install = tmp_path / "Steam" / "steamapps" / "common" / "Farming Simulator 25"
    install.mkdir(parents=True)
    header = tmp_path / "Steam" / "appcache" / "librarycache" / "3453970" / "abc" / "header.jpg"
    header.parent.mkdir(parents=True)
    Image.new("RGB", (460, 215), "green").save(header)
    thumb = official_map_thumbnail(
        "pdlc_highlandsFishingPack.HighlandsFishingMap", install, tmp_path / "cache"
    )
    assert thumb is not None
    with Image.open(thumb) as img:
        w, h = img.size
    assert abs(w - h) <= 2  # square scenery crop, away from the title block


def test_no_thumbnail_without_sources(tmp_path: Path) -> None:
    assert official_map_thumbnail("MapUS", tmp_path, tmp_path / "cache") is None
    assert official_map_thumbnail("FS25_Mod.Map", tmp_path, tmp_path / "cache") is None
    assert official_map_thumbnail("MapUS", tmp_path, None) is None


def test_official_preview_with_an_unexpected_format_is_ignored(tmp_path: Path) -> None:
    ui = tmp_path / "data" / "maps" / "mapUS" / "textures" / "ui"
    ui.mkdir(parents=True)
    Image.new("RGB", (64, 64), "blue").save(ui / "preview.png", "TIFF")
    assert official_map_thumbnail("MapUS", tmp_path, tmp_path / "cache") is None
