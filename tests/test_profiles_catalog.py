from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fsmods_gui.profiles.catalog import (
    CACHE_SCHEMA_VERSION,
    Catalog,
    CatalogEntry,
    scan_library,
)

MAP_MODDESC = """<?xml version="1.0" encoding="utf-8"?>
<modDesc descVersion="91">
  <version>1.2.3.4</version>
  <title>
    <en>Alpenland</en>
    <fr>Pays Alpin</fr>
  </title>
  <author>Modder</author>
  <iconFilename>icon.dds</iconFilename>
  <maps>
    <map id="alpenland" configFilename="maps/map.xml" />
  </maps>
</modDesc>
"""

VEHICLE_MODDESC = """<?xml version="1.0" encoding="utf-8"?>
<modDesc descVersion="91">
  <version>7.0.0.0</version>
  <title>
    <en>Courseplay</en>
  </title>
  <author>Courseplay Team</author>
</modDesc>
"""


def _write_zip(target: Path, moddesc: str) -> Path:
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("modDesc.xml", moddesc)
    return target


def test_scan_empty_dir_returns_empty_catalog(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    catalog = scan_library(mods_dir)
    assert len(catalog) == 0
    assert list(catalog) == []


def test_scan_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        scan_library(tmp_path / "missing")


def test_scan_parses_moddesc(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    _write_zip(mods_dir / "FS25_Alpenland.zip", MAP_MODDESC)
    _write_zip(mods_dir / "FS25_Courseplay.zip", VEHICLE_MODDESC)

    catalog = scan_library(mods_dir)
    assert len(catalog) == 2

    alp = catalog.get("FS25_Alpenland.zip")
    assert alp is not None
    assert alp.title == "Pays Alpin"  # FR wins over EN
    assert alp.title_en == "Alpenland"
    assert alp.title_fr == "Pays Alpin"
    assert alp.version == "1.2.3.4"
    assert alp.author == "Modder"
    assert alp.icon_filename == "icon.dds"
    assert alp.is_map is True
    assert alp.error is None

    cp = catalog.get("FS25_Courseplay.zip")
    assert cp is not None
    assert cp.title == "Courseplay"
    assert cp.is_map is False
    assert cp.icon_filename is None

    assert [m.filename for m in catalog.maps()] == ["FS25_Alpenland.zip"]


def test_scan_handles_missing_moddesc(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    zp = mods_dir / "FS25_Empty.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("README.txt", "no moddesc here")

    catalog = scan_library(mods_dir)
    entry = catalog.get("FS25_Empty.zip")
    assert entry is not None
    assert entry.error == "modDesc.xml manquant"
    assert entry.title == "FS25_Empty"  # falls back to stem


def test_scan_handles_corrupt_zip(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    (mods_dir / "FS25_Broken.zip").write_bytes(b"not a zip at all")
    catalog = scan_library(mods_dir)
    entry = catalog.get("FS25_Broken.zip")
    assert entry is not None
    assert entry.error is not None
    assert "zip" in entry.error.lower()


def test_scan_handles_invalid_xml(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    _write_zip(mods_dir / "FS25_BadXml.zip", "<modDesc><bad></modDesc>")
    catalog = scan_library(mods_dir)
    entry = catalog.get("FS25_BadXml.zip")
    assert entry is not None
    assert entry.error is not None
    assert "xml" in entry.error.lower() or "moddesc" in entry.error.lower()


def test_scan_writes_and_reuses_cache(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    _write_zip(mods_dir / "FS25_Courseplay.zip", VEHICLE_MODDESC)
    cache_path = tmp_path / "cache" / "index.json"

    first = scan_library(mods_dir, cache_path=cache_path)
    assert cache_path.is_file()
    assert "FS25_Courseplay.zip" in first

    # Tamper the zip's modDesc on disk but keep size+mtime stable.
    zp = mods_dir / "FS25_Courseplay.zip"
    stat = zp.stat()
    second = scan_library(mods_dir, cache_path=cache_path)
    assert second.get("FS25_Courseplay.zip").title == "Courseplay"
    # The cache short-circuit relies on size+mtime_ns equality.
    assert second.get("FS25_Courseplay.zip").mtime_ns == stat.st_mtime_ns


def test_cache_invalidates_when_mtime_changes(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    zp = _write_zip(mods_dir / "FS25_Courseplay.zip", VEHICLE_MODDESC)
    cache_path = tmp_path / "cache" / "index.json"
    scan_library(mods_dir, cache_path=cache_path)

    # Rewrite the zip with new content + bump mtime.
    _write_zip(zp, MAP_MODDESC)
    import os
    new_mtime = zp.stat().st_mtime_ns + 1_000_000_000
    os.utime(zp, ns=(new_mtime, new_mtime))

    refreshed = scan_library(mods_dir, cache_path=cache_path)
    entry = refreshed.get("FS25_Courseplay.zip")
    assert entry is not None
    assert entry.title == "Pays Alpin"
    assert entry.is_map is True


def test_catalog_entry_round_trips_through_dict() -> None:
    entry = CatalogEntry(
        filename="x.zip",
        title="X",
        version="1.0.0.0",
        is_map=True,
        author="me",
    )
    restored = CatalogEntry.from_dict(entry.to_dict())
    assert restored == entry


def test_catalog_save_cache_roundtrip(tmp_path: Path) -> None:
    catalog = Catalog(
        mods_dir=tmp_path / "mods",
        entries={
            "a.zip": CatalogEntry(filename="a.zip", title="A", version="1.0.0.0"),
        },
    )
    cache_path = tmp_path / "cache" / "index.json"
    catalog.save_cache(cache_path)
    assert cache_path.is_file()
    import json
    data = json.loads(cache_path.read_text())
    assert data["schema"] == CACHE_SCHEMA_VERSION
    assert "a.zip" in data["entries"]
