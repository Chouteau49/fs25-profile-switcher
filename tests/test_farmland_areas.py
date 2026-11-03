from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from fsmods_gui.career.farmland_areas import grle_value_counts, map_farmland_areas


def encode_grle(pixels: bytes, width: int, height: int) -> bytes:
    """GRLE encoder matching the game's layout (see farmland_areas docstring)."""
    out = bytearray()
    i = 0
    while i < len(pixels):
        v = pixels[i]
        j = i
        while j < len(pixels) and pixels[j] == v:
            j += 1
        run = j - i
        out.append(v)
        if run >= 2:
            out.append(v)
            rest = run - 2
            while rest >= 255:
                out.append(255)
                rest -= 255
            out.append(rest)
        i = j
    header = (
        b"GRLE" + struct.pack("<HHHH", 1, width // 256, 0, height // 256)
        + bytes([0, 1, 0, 0, 0]) + struct.pack("<I", len(out))
    )
    assert len(header) == 21
    return header + bytes(out)


def layer(counts: dict[int, int], width: int = 256, height: int = 256) -> bytes:
    """A width×height layer: ``counts`` pixels per value, the rest 255 (no farmland)."""
    pixels = bytearray()
    for value, n in counts.items():
        pixels += bytes([value]) * n
    pixels += bytes([255]) * (width * height - len(pixels))
    return encode_grle(bytes(pixels), width, height)


def test_grle_roundtrip_counts_runs_and_singles() -> None:
    pixels = bytes([1, 2, 2, 3] + [4] * 600) + bytes([5]) * (256 * 256 - 604)
    w, h, counts = grle_value_counts(encode_grle(pixels, 256, 256))
    assert (w, h) == (256, 256)
    assert counts[1] == 1 and counts[2] == 2 and counts[3] == 1 and counts[4] == 600
    assert sum(counts) == 256 * 256


def test_grle_rejects_garbage_and_truncation() -> None:
    assert grle_value_counts(b"nope") is None
    data = layer({1: 10})
    assert grle_value_counts(data[:-3]) is None


MAPS_XML = """<map width="512" height="512">
  <filename>maps/map.i3d</filename>
  <farmlands filename="maps/config/farmlands.xml"/>
</map>"""


def make_map_mod(mods: Path, farmlands_attr: str, extra: dict[str, bytes]) -> Path:
    mods.mkdir(parents=True, exist_ok=True)
    path = mods / "FS25_Test.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "modDesc.xml",
            '<modDesc><maps><map id="TestMap" configFilename="maps/maps.xml"/></maps></modDesc>',
        )
        zf.writestr("maps/maps.xml", MAPS_XML)
        zf.writestr(
            "maps/config/farmlands.xml",
            f'<map><farmlands {farmlands_attr} pricePerHa="1">'
            '<farmland id="1"/><farmland id="2"/></farmlands></map>',
        )
        for name, data in extra.items():
            zf.writestr(name, data)
    return path


def test_mod_map_with_density_map_filename(tmp_path: Path) -> None:
    # 512 m map, 256 px layer: 2 m × 2 m = 4 m² per pixel.
    make_map_mod(
        tmp_path / "mods",
        'densityMapFilename="maps/data/infoLayer_farmlands.png"',
        {"maps/data/infoLayer_farmlands.grle": layer({1: 2500, 2: 5000})},
    )
    res = map_farmland_areas("FS25_Test.TestMap", None, [tmp_path / "mods"])
    assert res is not None and res.source == "FS25_Test.zip"
    assert res.areas == {"1": pytest.approx(1.0), "2": pytest.approx(2.0)}  # 255 excluded


def test_mod_map_with_info_layer_resolved_through_i3d(tmp_path: Path) -> None:
    i3d = (
        '<i3D><Files><File fileId="7" filename="data/fl.png"/></Files>'
        '<InfoLayer name="farmlands" fileId="7" numChannels="8"/></i3D>'
    )
    make_map_mod(
        tmp_path / "lib",
        'infoLayer="farmlands"',
        {"maps/map.i3d": i3d.encode(), "maps/data/fl.grle": layer({2: 2500})},
    )
    res = map_farmland_areas("FS25_Test.TestMap", None, [tmp_path / "game", tmp_path / "lib"])
    assert res is not None
    assert res.areas == {"2": pytest.approx(1.0)}


def test_base_game_map_read_from_install(tmp_path: Path) -> None:
    install = tmp_path / "install"
    base = install / "data" / "maps" / "mapEU"
    (base / "config").mkdir(parents=True)
    (base / "data").mkdir()
    (base / "mapEU.xml").write_text(
        '<map width="256" height="256"><farmlands filename="$data/maps/mapEU/config/farmlands.xml"/></map>',
        encoding="utf-8",
    )
    (base / "config" / "farmlands.xml").write_text(
        '<map><farmlands densityMapFilename="$data/maps/mapEU/data/infoLayer_farmlands.png">'
        '<farmland id="3"/></farmlands></map>',
        encoding="utf-8",
    )
    (base / "data" / "infoLayer_farmlands.grle").write_bytes(layer({3: 10_000}))
    res = map_farmland_areas("MapEU", install, [])
    assert res is not None
    assert res.areas == {"3": pytest.approx(1.0)}  # 1 m² per pixel


def test_dlc_and_missing_maps_are_unreadable(tmp_path: Path) -> None:
    assert map_farmland_areas("pdlc_highlandsFishingPack.HighlandsFishingMap", tmp_path, []) is None
    assert map_farmland_areas("FS25_Absent.Map", None, [tmp_path]) is None
    assert map_farmland_areas("", None, []) is None
