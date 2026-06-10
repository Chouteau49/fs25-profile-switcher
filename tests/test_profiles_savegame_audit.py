from __future__ import annotations

from pathlib import Path

from fsmods_gui.profiles.catalog import Catalog, CatalogEntry
from fsmods_gui.profiles.profile import Profile
from fsmods_gui.profiles.savegame_audit import (
    STATUS_ABSENT,
    STATUS_LOADED,
    STATUS_USED,
    audit_profile,
    list_savegames,
    parse_savegame,
)

CAREER = """<?xml version="1.0" encoding="utf-8"?>
<careerSavegame revision="2" valid="true">
  <settings>
    <savegameName>Ma partie</savegameName>
    <mapTitle>Les Combes</mapTitle>
    <mapId>FS25_The_Combes.SampleModMap</mapId>
    <saveDateFormatted>20/05/2026</saveDateFormatted>
  </settings>
  <mod modName="FS25_The_Combes" title="Les Combes" version="1.0.0.1" required="true"/>
  <mod modName="FS25_CoolTractor" title="Cool Tractor" version="1.0" required="false"/>
  <mod modName="FS25_Courseplay" title="Courseplay" version="7.0" required="false"/>
  <mod modName="FS25_UnusedPack" title="Unused Pack" version="1.0" required="false"/>
</careerSavegame>
"""

VEHICLES = """<?xml version="1.0" encoding="utf-8"?>
<vehicles>
  <vehicle modName="FS25_CoolTractor" filename="$moddir$FS25_CoolTractor/tractor.xml"/>
</vehicles>
"""


def _make_savegame(tmp_path: Path) -> Path:
    sg = tmp_path / "savegame1"
    sg.mkdir()
    (sg / "careerSavegame.xml").write_text(CAREER, encoding="utf-8")
    (sg / "vehicles.xml").write_text(VEHICLES, encoding="utf-8")
    return sg


def _catalog(*entries: CatalogEntry) -> Catalog:
    return Catalog(mods_dir=Path("."), entries={e.filename: e for e in entries})


def _entry(filename: str, category: str = "Véhicule") -> CatalogEntry:
    return CatalogEntry(filename=filename, title=Path(filename).stem, version="1.0", category=category)


# --------------------------------------------------------------------- parsing


def test_parse_savegame_basics(tmp_path: Path) -> None:
    sg = _make_savegame(tmp_path)
    info = parse_savegame(sg)
    assert info.name == "Ma partie"
    assert info.map_title == "Les Combes"
    assert info.map_mod_id == "FS25_The_Combes"
    assert "fs25_cooltractor" in info.loaded
    assert info.loaded["fs25_the_combes"].required is True
    # CoolTractor is placed in the world (vehicles.xml), map added to used set.
    assert "fs25_cooltractor" in info.used
    assert "fs25_the_combes" in info.used
    # Courseplay/UnusedPack are loaded but never placed.
    assert "fs25_courseplay" not in info.used
    assert "fs25_unusedpack" not in info.used


def test_list_savegames_natural_sort(tmp_path: Path) -> None:
    for n in (1, 2, 10):
        d = tmp_path / f"savegame{n}"
        d.mkdir()
        (d / "careerSavegame.xml").write_text("<careerSavegame/>", encoding="utf-8")
    backup = tmp_path / "savegameBackup"
    backup.mkdir()
    (backup / "careerSavegame.xml").write_text("<careerSavegame/>", encoding="utf-8")
    (tmp_path / "notasave").mkdir()

    names = [p.name for p in list_savegames(tmp_path)]
    assert names == ["savegame1", "savegame2", "savegame10", "savegameBackup"]


# ---------------------------------------------------------------------- audit


def test_audit_classifies_statuses(tmp_path: Path) -> None:
    sg = _make_savegame(tmp_path)
    info = parse_savegame(sg)
    catalog = _catalog(
        _entry("FS25_The_Combes.zip", category="Carte"),
        _entry("FS25_CoolTractor.zip"),
        _entry("FS25_Courseplay.zip", category="Script"),
        _entry("FS25_Orphan.zip"),  # not in the save at all
    )
    profile = Profile(
        name="Test",
        map_mod="FS25_The_Combes.zip",
        mods=["FS25_CoolTractor.zip", "FS25_Courseplay.zip", "FS25_Orphan.zip"],
    )
    report = audit_profile(profile, info, catalog)
    by_file = {r.filename: r for r in report.rows}

    assert by_file["FS25_The_Combes.zip"].status == STATUS_USED
    assert by_file["FS25_The_Combes.zip"].is_map is True
    assert by_file["FS25_CoolTractor.zip"].status == STATUS_USED
    assert by_file["FS25_Courseplay.zip"].status == STATUS_LOADED
    assert by_file["FS25_Courseplay.zip"].is_script is True
    assert by_file["FS25_Orphan.zip"].status == STATUS_ABSENT


def test_audit_prudent_preselection(tmp_path: Path) -> None:
    sg = _make_savegame(tmp_path)
    info = parse_savegame(sg)
    catalog = _catalog(
        _entry("FS25_The_Combes.zip", category="Carte"),
        _entry("FS25_CoolTractor.zip"),
        _entry("FS25_Courseplay.zip", category="Script"),
        _entry("FS25_Orphan.zip"),
    )
    profile = Profile(
        name="Test",
        map_mod="FS25_The_Combes.zip",
        mods=["FS25_CoolTractor.zip", "FS25_Courseplay.zip", "FS25_Orphan.zip"],
    )
    report = audit_profile(profile, info, catalog)
    suggested = {r.filename for r in report.rows if r.suggested_remove}
    # Only the absent mod is pre-checked; map/used/loaded are not.
    assert suggested == {"FS25_Orphan.zip"}


def test_audit_missing_in_profile_bidirectional(tmp_path: Path) -> None:
    sg = _make_savegame(tmp_path)
    info = parse_savegame(sg)
    # Library has CoolTractor (addable) but the profile lacks it.
    catalog = _catalog(_entry("FS25_CoolTractor.zip"))
    profile = Profile(name="Empty", mods=[])
    report = audit_profile(profile, info, catalog)
    by_id = {m.mod_id.lower(): m for m in report.missing_in_profile}
    # CoolTractor and the map were used by the save; both missing from profile.
    assert "fs25_cooltractor" in by_id
    assert by_id["fs25_cooltractor"].filename == "FS25_CoolTractor.zip"
    assert by_id["fs25_cooltractor"].in_library is True
    # The map is used but not in the library -> not addable.
    assert by_id["fs25_the_combes"].in_library is False


def test_list_savegames_missing_dir(tmp_path: Path) -> None:
    assert list_savegames(tmp_path / "nope") == []
