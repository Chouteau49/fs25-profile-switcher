from __future__ import annotations

import zipfile
from pathlib import Path

from fsmods_gui.profiles.autodrive import (
    AUTODRIVE_FILES,
    detect_pack,
    install_pack,
    scan_packs,
)

CONFIG_XML = b'<?xml version="1.0"?><AutoDrive><mapName>Judith</mapName></AutoDrive>'
USERS_XML = b'<?xml version="1.0"?><AutoDriveUsersData/>'


def _make_pack_zip(path: Path, *, nested: bool = False, only_config: bool = False) -> Path:
    prefix = "JudithPlainsAutoDrive/" if nested else ""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{prefix}AutoDrive_config.xml", CONFIG_XML)
        if not only_config:
            zf.writestr(f"{prefix}AutoDriveUsersData.xml", USERS_XML)
    return path


def test_detect_pack_flat(tmp_path: Path) -> None:
    z = _make_pack_zip(tmp_path / "JudithPlainsAutoDrive1-1.zip")
    pack = detect_pack(z)
    assert pack is not None
    assert pack.provided == list(AUTODRIVE_FILES)


def test_detect_pack_nested_subfolder(tmp_path: Path) -> None:
    z = _make_pack_zip(tmp_path / "pack.zip", nested=True)
    pack = detect_pack(z)
    assert pack is not None
    assert set(pack.provided) == set(AUTODRIVE_FILES)


def test_detect_pack_rejects_regular_mod(tmp_path: Path) -> None:
    z = tmp_path / "FS25_CoolTractor.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("modDesc.xml", b"<modDesc/>")
    assert detect_pack(z) is None


def test_detect_pack_rejects_non_zip(tmp_path: Path) -> None:
    bogus = tmp_path / "not.zip"
    bogus.write_text("nope")
    assert detect_pack(bogus) is None


def test_scan_packs_dedups_and_skips_mods(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    inbox = tmp_path / "inbox"
    downloads.mkdir()
    inbox.mkdir()
    _make_pack_zip(downloads / "routes.zip")
    _make_pack_zip(inbox / "routes.zip")  # same name -> deduped
    _make_pack_zip(inbox / "other-routes.zip")
    with zipfile.ZipFile(downloads / "FS25_Mod.zip", "w") as zf:
        zf.writestr("modDesc.xml", b"<modDesc/>")

    packs = scan_packs([downloads, inbox])
    names = sorted(p.filename for p in packs)
    assert names == ["other-routes.zip", "routes.zip"]


def test_install_pack_backs_up_existing(tmp_path: Path) -> None:
    sg = tmp_path / "savegame1"
    sg.mkdir()
    (sg / "AutoDrive_config.xml").write_bytes(b"OLD CONFIG")
    (sg / "AutoDriveUsersData.xml").write_bytes(b"OLD USERS")
    z = _make_pack_zip(tmp_path / "routes.zip")

    result = install_pack(detect_pack(z), sg, backup=True)

    assert not result.errors
    assert set(result.installed) == set(AUTODRIVE_FILES)
    assert (sg / "AutoDrive_config.xml").read_bytes() == CONFIG_XML
    assert (sg / "AutoDriveUsersData.xml").read_bytes() == USERS_XML
    # old content preserved under .bak
    assert (sg / "AutoDrive_config.xml.bak").read_bytes() == b"OLD CONFIG"
    assert (sg / "AutoDriveUsersData.xml.bak").read_bytes() == b"OLD USERS"
    assert len(result.backed_up) == 2


def test_install_pack_backup_non_clobbering(tmp_path: Path) -> None:
    sg = tmp_path / "savegame1"
    sg.mkdir()
    (sg / "AutoDrive_config.xml").write_bytes(b"V1")
    (sg / "AutoDrive_config.xml.bak").write_bytes(b"OLDER")
    z = _make_pack_zip(tmp_path / "routes.zip", only_config=True)

    install_pack(detect_pack(z), sg, backup=True)

    assert (sg / "AutoDrive_config.xml.bak").read_bytes() == b"OLDER"
    assert (sg / "AutoDrive_config.xml.bak.1").read_bytes() == b"V1"
    assert (sg / "AutoDrive_config.xml").read_bytes() == CONFIG_XML


def test_install_pack_no_backup_deletes(tmp_path: Path) -> None:
    sg = tmp_path / "savegame1"
    sg.mkdir()
    (sg / "AutoDrive_config.xml").write_bytes(b"OLD")
    z = _make_pack_zip(tmp_path / "routes.zip", only_config=True)

    install_pack(detect_pack(z), sg, backup=False)

    assert (sg / "AutoDrive_config.xml").read_bytes() == CONFIG_XML
    assert not (sg / "AutoDrive_config.xml.bak").exists()


def test_install_pack_missing_savegame(tmp_path: Path) -> None:
    z = _make_pack_zip(tmp_path / "routes.zip")
    result = install_pack(detect_pack(z), tmp_path / "nope", backup=True)
    assert result.errors
    assert not result.installed
