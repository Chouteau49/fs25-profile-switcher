"""Importer une partie téléchargée (zip de sauvegarde FS25) : lecture, dossier, profil."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fsmods_gui.profiles.savegame_import import (
    SaveImportError,
    extract_save,
    next_savegame_dir,
    plan_profile,
    read_save_archive,
    scan_save_archives,
    unique_profile_name,
)

CAREER = """<?xml version="1.0" encoding="utf-8"?>
<careerSavegame revision="2">
  <settings>
    <savegameName>Ma partie</savegameName>
    <mapId>FS25_The_Mechet.FS25_Le_Mechet</mapId>
    <mapTitle>Le Mechet</mapTitle>
    <saveDate>2026-11-08</saveDate>
  </settings>
  <mods>
    <mod modName="FS25_The_Mechet" title="Le Mechet" version="1.0" required="true"/>
    <mod modName="FS25_Courseplay" title="Courseplay" version="8.1" required="false"/>
    <mod modName="FS25_Absent" title="Absent" version="1.0" required="false"/>
  </mods>
</careerSavegame>
"""


def _zip(path: Path, files: dict[str, str | bytes], prefix: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(prefix + name, data)
    return path


def test_reads_name_map_date_and_mods_of_a_flat_save(tmp_path: Path) -> None:
    archive = read_save_archive(_zip(tmp_path / "partie.zip", {"careerSavegame.xml": CAREER}))
    assert archive is not None
    assert archive.name == "Ma partie"
    assert archive.map_id == "FS25_The_Mechet.FS25_Le_Mechet"
    assert archive.map_title == "Le Mechet"
    assert archive.save_date == "2026-11-08"
    assert archive.mods == ("FS25_The_Mechet", "FS25_Courseplay", "FS25_Absent")


def test_reads_a_save_wrapped_in_one_folder(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER}, prefix="savegame4/")
    archive = read_save_archive(zip_path)
    assert archive is not None and archive.map_id.endswith("Le_Mechet")


def test_a_zip_that_is_not_a_save_is_ignored(tmp_path: Path) -> None:
    mod = _zip(tmp_path / "FS25_Mod.zip", {"modDesc.xml": "<modDesc/>"})
    broken = tmp_path / "cut.zip"
    broken.write_bytes(b"pas un zip")
    assert read_save_archive(mod) is None
    assert read_save_archive(broken) is None
    assert read_save_archive(tmp_path / "absent.zip") is None


def test_scan_finds_saves_only_in_the_given_folders(tmp_path: Path) -> None:
    _zip(tmp_path / "Downloads" / "partie.zip", {"careerSavegame.xml": CAREER})
    _zip(tmp_path / "Downloads" / "mod.zip", {"modDesc.xml": "<modDesc/>"})
    _zip(tmp_path / "Other" / "autre.zip", {"careerSavegame.xml": CAREER})
    found = scan_save_archives([tmp_path / "Downloads", tmp_path / "Inexistant"])
    assert [a.path.name for a in found] == ["partie.zip"]


def test_next_savegame_dir_takes_the_first_free_slot_in_the_game_range(tmp_path: Path) -> None:
    # FS25 only shows slots 1 to 20; an empty slot holds just steam_autocloud.vdf.
    for name in ("savegame1", "savegame2", "savegame3", "savegameBackup"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "careerSavegame.xml").write_text("<x/>", encoding="utf-8")
    empty = tmp_path / "savegame4"
    empty.mkdir()
    (empty / "steam_autocloud.vdf").write_text("", encoding="utf-8")
    target = next_savegame_dir(tmp_path)
    assert target == tmp_path / "savegame4"  # an empty slot is reused
    assert (empty / "steam_autocloud.vdf").is_file()  # nothing is created or removed yet


def test_next_savegame_dir_never_goes_past_slot_20(tmp_path: Path) -> None:
    for n in range(1, 21):
        d = tmp_path / f"savegame{n}"
        d.mkdir()
        (d / "careerSavegame.xml").write_text("<x/>", encoding="utf-8")
    with pytest.raises(SaveImportError):
        next_savegame_dir(tmp_path)


def test_a_folder_with_other_files_is_not_an_empty_slot(tmp_path: Path) -> None:
    d = tmp_path / "savegame1"
    d.mkdir()
    (d / "vehicles.xml").write_text("<x/>", encoding="utf-8")  # leftovers: keep them
    assert next_savegame_dir(tmp_path) == tmp_path / "savegame2"


def test_next_savegame_dir_on_a_fresh_install(tmp_path: Path) -> None:
    assert next_savegame_dir(tmp_path) == tmp_path / "savegame1"


def test_extract_into_an_empty_slot_keeps_its_steam_file(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER})
    target = tmp_path / "savegame4"
    target.mkdir()
    (target / "steam_autocloud.vdf").write_text("cloud", encoding="utf-8")
    extract_save(read_save_archive(zip_path), target)
    assert (target / "careerSavegame.xml").is_file()
    assert (target / "steam_autocloud.vdf").read_text(encoding="utf-8") == "cloud"


def test_extract_writes_the_save_into_a_new_folder(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {
        "careerSavegame.xml": CAREER, "farms.xml": "<farms/>", "fields/x.gdm": b"\x00\x01",
    })
    archive = read_save_archive(zip_path)
    target = tmp_path / "user" / "savegame2"
    extract_save(archive, target)
    assert (target / "careerSavegame.xml").read_text(encoding="utf-8") == CAREER
    assert (target / "fields" / "x.gdm").read_bytes() == b"\x00\x01"
    assert not any(p.name.startswith(".") for p in (tmp_path / "user").iterdir())


def test_extract_strips_the_wrapping_folder(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER}, prefix="savegame9/")
    target = tmp_path / "savegame2"
    extract_save(read_save_archive(zip_path), target)
    assert (target / "careerSavegame.xml").is_file()
    assert not (target / "savegame9").exists()


def test_extract_never_overwrites_an_existing_save(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER})
    target = tmp_path / "savegame2"
    target.mkdir()
    (target / "careerSavegame.xml").write_text("ma vraie partie", encoding="utf-8")
    with pytest.raises(SaveImportError):
        extract_save(read_save_archive(zip_path), target)
    assert (target / "careerSavegame.xml").read_text(encoding="utf-8") == "ma vraie partie"


def test_extract_refuses_paths_that_leave_the_folder(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {
        "careerSavegame.xml": CAREER, "../../evil.txt": "pirate",
    })
    target = tmp_path / "user" / "savegame2"
    with pytest.raises(SaveImportError):
        extract_save(read_save_archive(zip_path), target)
    assert not (tmp_path / "user" / "evil.txt").exists()
    assert not target.exists()


def test_a_failed_extraction_leaves_nothing_behind(tmp_path: Path) -> None:
    zip_path = _zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER, "../x.txt": "x"})
    user = tmp_path / "user"
    user.mkdir()
    with pytest.raises(SaveImportError):
        extract_save(read_save_archive(zip_path), user / "savegame2")
    assert list(user.iterdir()) == []


def test_unique_profile_name() -> None:
    assert unique_profile_name("Ma partie", {"Autre"}) == "Ma partie"
    assert unique_profile_name("Ma partie", {"Ma partie"}) == "Ma partie (2)"
    assert unique_profile_name("Ma partie", {"Ma partie", "Ma partie (2)"}) == "Ma partie (3)"
    assert unique_profile_name("", set()) == "Partie importée"


LIBRARY = {"fs25_the_mechet": "FS25_The_Mechet.zip", "fs25_courseplay": "FS25_Courseplay.zip",
           "fs25_other": "FS25_Other.zip"}


def test_plan_profile_uses_the_library_map_and_mods(tmp_path: Path) -> None:
    archive = read_save_archive(_zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER}))
    plan = plan_profile(archive, LIBRARY)
    assert plan.map_mod == "FS25_The_Mechet.zip"
    assert plan.official_map is None
    assert plan.mods == ("FS25_Courseplay.zip",)  # the map is not repeated as a mod
    assert plan.missing == ("FS25_Absent",)


def test_plan_profile_recognises_an_official_map(tmp_path: Path) -> None:
    career = CAREER.replace("FS25_The_Mechet.FS25_Le_Mechet",
                            "pdlc_highlandsFishingPack.HighlandsFishingMap")
    archive = read_save_archive(_zip(tmp_path / "p.zip", {"careerSavegame.xml": career}))
    plan = plan_profile(archive, LIBRARY)
    assert plan.map_mod is None
    assert plan.official_map == "pdlc_highlandsFishingPack.HighlandsFishingMap"


def test_plan_profile_without_the_map_mod_reports_it(tmp_path: Path) -> None:
    archive = read_save_archive(_zip(tmp_path / "p.zip", {"careerSavegame.xml": CAREER}))
    plan = plan_profile(archive, {"fs25_courseplay": "FS25_Courseplay.zip"})
    assert plan.map_mod is None
    assert plan.missing == ("FS25_The_Mechet", "FS25_Absent")
