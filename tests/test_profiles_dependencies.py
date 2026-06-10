from __future__ import annotations

import zipfile
from pathlib import Path

from fsmods_gui.profiles.catalog import Catalog, CatalogEntry, scan_library
from fsmods_gui.profiles.dependencies import (
    build_modid_index,
    resolve_new_dependencies,
)


def _entry(filename: str, requires: list[str] | None = None) -> CatalogEntry:
    return CatalogEntry(
        filename=filename,
        title=Path(filename).stem,
        version="1.0.0.0",
        requires=requires or [],
    )


def _catalog(*entries: CatalogEntry) -> Catalog:
    return Catalog(mods_dir=Path("."), entries={e.filename: e for e in entries})


# --------------------------------------------------------------------- parsing

DEP_MODDESC = """<?xml version="1.0" encoding="utf-8"?>
<modDesc descVersion="91">
  <version>1.0.0.0</version>
  <title><en>Needs Stuff</en></title>
  <dependencies>
    <dependency>FS25_BasePack</dependency>
    <dependency>FS25_Extra</dependency>
  </dependencies>
</modDesc>
"""


def test_scan_parses_dependencies(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    with zipfile.ZipFile(mods_dir / "FS25_NeedsStuff.zip", "w") as zf:
        zf.writestr("modDesc.xml", DEP_MODDESC)
    catalog = scan_library(mods_dir)
    entry = catalog.get("FS25_NeedsStuff.zip")
    assert entry is not None
    assert entry.requires == ["FS25_BasePack", "FS25_Extra"]


def test_no_dependencies_is_empty_list(tmp_path: Path) -> None:
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    with zipfile.ZipFile(mods_dir / "FS25_Plain.zip", "w") as zf:
        zf.writestr("modDesc.xml", '<modDesc descVersion="91"><version>1</version></modDesc>')
    catalog = scan_library(mods_dir)
    assert catalog.get("FS25_Plain.zip").requires == []


# ------------------------------------------------------------------- resolving


def test_mod_id_is_zip_stem() -> None:
    assert _entry("FS25_Foo.zip").mod_id == "FS25_Foo"


def test_build_index_is_case_insensitive() -> None:
    cat = _catalog(_entry("FS25_Base.zip"))
    index = build_modid_index(cat)
    assert index["fs25_base"] == "FS25_Base.zip"


def test_resolve_present_dependency() -> None:
    cat = _catalog(
        _entry("FS25_A.zip", requires=["FS25_B"]),
        _entry("FS25_B.zip"),
    )
    res = resolve_new_dependencies(["FS25_A.zip"], ["FS25_A.zip"], cat)
    assert res.to_add == ["FS25_B.zip"]
    assert res.missing == []


def test_resolve_missing_dependency() -> None:
    cat = _catalog(_entry("FS25_A.zip", requires=["FS25_Gone"]))
    res = resolve_new_dependencies(["FS25_A.zip"], ["FS25_A.zip"], cat)
    assert res.to_add == []
    assert res.missing == ["FS25_Gone"]


def test_resolve_skips_deps_already_in_profile() -> None:
    cat = _catalog(
        _entry("FS25_A.zip", requires=["FS25_B"]),
        _entry("FS25_B.zip"),
    )
    # B is already in the profile -> nothing to add.
    res = resolve_new_dependencies(["FS25_A.zip"], ["FS25_A.zip", "FS25_B.zip"], cat)
    assert res.to_add == []
    assert res.missing == []


def test_resolve_is_transitive() -> None:
    cat = _catalog(
        _entry("FS25_A.zip", requires=["FS25_B"]),
        _entry("FS25_B.zip", requires=["FS25_C"]),
        _entry("FS25_C.zip"),
    )
    res = resolve_new_dependencies(["FS25_A.zip"], ["FS25_A.zip"], cat)
    assert res.to_add == ["FS25_B.zip", "FS25_C.zip"]


def test_resolve_transitive_with_missing_leaf() -> None:
    cat = _catalog(
        _entry("FS25_A.zip", requires=["FS25_B"]),
        _entry("FS25_B.zip", requires=["FS25_Missing"]),
    )
    res = resolve_new_dependencies(["FS25_A.zip"], ["FS25_A.zip"], cat)
    assert res.to_add == ["FS25_B.zip"]
    assert res.missing == ["FS25_Missing"]


def test_resolve_handles_cycles() -> None:
    cat = _catalog(
        _entry("FS25_A.zip", requires=["FS25_B"]),
        _entry("FS25_B.zip", requires=["FS25_A"]),
    )
    res = resolve_new_dependencies(["FS25_A.zip"], ["FS25_A.zip"], cat)
    assert res.to_add == ["FS25_B.zip"]
    assert res.missing == []


def test_resolve_none_catalog_safe() -> None:
    res = resolve_new_dependencies(["FS25_A.zip"], [], None)
    assert not res.has_any
