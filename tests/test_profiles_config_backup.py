from __future__ import annotations

from pathlib import Path

import pytest

from fsmods_gui.profiles.config_backup import (
    MODE_MERGE,
    MODE_REPLACE,
    export_config,
    import_config,
    mirror_config,
)


def _dirs(tmp_path: Path):
    profiles = tmp_path / "lib" / "profiles"
    collections = tmp_path / "lib" / "collections"
    profiles.mkdir(parents=True)
    collections.mkdir(parents=True)
    return profiles, collections


def test_export_then_import_merge(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text('{"name":"A"}', encoding="utf-8")
    (collections / "viti.json").write_text('{"name":"Viti"}', encoding="utf-8")

    zip_path = export_config(profiles, collections, tmp_path / "backup.zip")
    assert zip_path.is_file()

    # Fresh target.
    p2, c2 = _dirs(tmp_path / "restore")
    res = import_config(zip_path, p2, c2, mode=MODE_MERGE)
    assert res.profiles_imported == 1
    assert res.collections_imported == 1
    assert (p2 / "a.json").is_file()
    assert (c2 / "viti.json").is_file()


def test_import_merge_keeps_existing(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text('{"name":"A"}', encoding="utf-8")
    zip_path = export_config(profiles, collections, tmp_path / "b.zip")

    p2, c2 = _dirs(tmp_path / "restore")
    (p2 / "keep.json").write_text('{"name":"Keep"}', encoding="utf-8")
    import_config(zip_path, p2, c2, mode=MODE_MERGE)
    assert (p2 / "keep.json").is_file()  # untouched
    assert (p2 / "a.json").is_file()     # added


def test_import_replace_wipes_existing(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text('{"name":"A"}', encoding="utf-8")
    zip_path = export_config(profiles, collections, tmp_path / "b.zip")

    p2, c2 = _dirs(tmp_path / "restore")
    (p2 / "old.json").write_text('{"name":"Old"}', encoding="utf-8")
    res = import_config(zip_path, p2, c2, mode=MODE_REPLACE)
    assert res.replaced is True
    assert not (p2 / "old.json").exists()  # wiped
    assert (p2 / "a.json").is_file()


def test_import_rejects_bad_mode(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    zip_path = export_config(profiles, collections, tmp_path / "b.zip")
    with pytest.raises(ValueError):
        import_config(zip_path, profiles, collections, mode="nope")


def test_import_ignores_paths_outside_sections(tmp_path: Path) -> None:
    import zipfile

    profiles, collections = _dirs(tmp_path)
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("profiles/../../escape.json", "{}")
        zf.writestr("other/x.json", "{}")
        zf.writestr("profiles/ok.json", '{"name":"ok"}')
    res = import_config(bad, profiles, collections, mode=MODE_MERGE)
    # Only the well-formed profiles/ok.json is imported; escape stays inside.
    assert res.profiles_imported == 1
    assert (profiles / "ok.json").is_file()
    assert not (tmp_path / "escape.json").exists()


def test_mirror_copies_and_prunes(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    backup = tmp_path / "cloud"

    mirror_config(profiles, collections, backup)
    assert (backup / "profiles" / "a.json").is_file()

    # Remove source file, mirror again -> pruned from backup.
    (profiles / "a.json").unlink()
    (profiles / "b.json").write_text("{}", encoding="utf-8")
    mirror_config(profiles, collections, backup)
    assert not (backup / "profiles" / "a.json").exists()
    assert (backup / "profiles" / "b.json").is_file()
