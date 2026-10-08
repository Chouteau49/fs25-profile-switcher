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


# ------------------------------------------------------------------- careers


def _careers(tmp_path: Path) -> Path:
    careers = tmp_path / "lib" / "careers"
    (careers / "mechet").mkdir(parents=True)
    (careers / "mechet" / "objectives.json").write_text('{"objectives": []}', encoding="utf-8")
    (careers / "mechet" / "career.json").write_text('{"mode": "objectives"}', encoding="utf-8")
    return careers


def test_export_import_careers_roundtrip(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    careers = _careers(tmp_path)
    zip_path = export_config(profiles, collections, tmp_path / "b.zip", careers)

    p2, c2 = _dirs(tmp_path / "restore")
    careers2 = tmp_path / "restore" / "lib" / "careers"
    res = import_config(zip_path, p2, c2, careers_dir=careers2)
    assert res.careers_imported == 1
    assert (careers2 / "mechet" / "career.json").read_text(encoding="utf-8") == '{"mode": "objectives"}'


def test_old_zip_without_careers_still_imports_and_keeps_careers(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    old_zip = export_config(profiles, collections, tmp_path / "old.zip")  # no careers

    p2, c2 = _dirs(tmp_path / "restore")
    careers2 = _careers(tmp_path / "restore")
    res = import_config(old_zip, p2, c2, mode=MODE_REPLACE, careers_dir=careers2)
    assert res.profiles_imported == 1 and res.careers_imported == 0
    assert (careers2 / "mechet" / "career.json").is_file()  # not wiped by an old archive


def test_import_careers_zip_slip_guard(tmp_path: Path) -> None:
    import zipfile

    profiles, collections = _dirs(tmp_path)
    careers = tmp_path / "lib" / "careers"
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("careers/../x.json", "{}")
        zf.writestr("careers/../../y/z.json", "{}")
        zf.writestr("careers/ok/career.json", "{}")
    res = import_config(bad, profiles, collections, careers_dir=careers)
    assert res.careers_imported == 1
    assert (careers / "ok" / "career.json").is_file()
    assert not (tmp_path / "lib" / "x.json").exists()
    assert not (tmp_path / "y").exists()


def test_import_replace_wipes_careers_when_archive_has_them(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    careers = _careers(tmp_path)
    zip_path = export_config(profiles, collections, tmp_path / "b.zip", careers)
    (careers / "gone").mkdir()
    (careers / "gone" / "career.json").write_text("{}", encoding="utf-8")
    import_config(zip_path, profiles, collections, mode=MODE_REPLACE, careers_dir=careers)
    assert not (careers / "gone" / "career.json").exists()
    assert (careers / "mechet" / "career.json").is_file()


# -------------------------------------------------------------------- mirror


def test_mirror_includes_careers_and_prunes_empty_folder(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    careers = _careers(tmp_path)
    backup = tmp_path / "cloud"
    mirror_config(profiles, collections, backup, careers)
    assert (backup / "careers" / "mechet" / "objectives.json").is_file()

    for f in (careers / "mechet").glob("*.json"):
        f.unlink()
    (careers / "mechet").rmdir()
    res = mirror_config(profiles, collections, backup, careers)
    assert res.pruned == 2
    assert not (backup / "careers" / "mechet").exists()


def test_mirror_never_prunes_a_folder_it_did_not_create(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    backup = tmp_path / "cloud"
    (backup / "profiles").mkdir(parents=True)
    (backup / "profiles" / "precious.json").write_text("{}", encoding="utf-8")
    res = mirror_config(profiles, collections, backup)
    assert (backup / "profiles" / "precious.json").is_file()
    assert res.warnings
    # Marker now exists: a later run may prune.
    mirror_config(profiles, collections, backup)
    assert not (backup / "profiles" / "precious.json").exists()


def test_mirror_never_prunes_when_source_is_empty(tmp_path: Path) -> None:
    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    backup = tmp_path / "cloud"
    mirror_config(profiles, collections, backup)
    (profiles / "a.json").unlink()  # e.g. library drive not mounted
    res = mirror_config(profiles, collections, backup)
    assert (backup / "profiles" / "a.json").is_file()
    assert res.warnings and res.pruned == 0


# ----------------------------------------------------------------- snapshots


def test_snapshot_retention_and_throttle(tmp_path: Path) -> None:
    from fsmods_gui.profiles.config_backup import snapshot_config

    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    backup = tmp_path / "cloud"

    first = snapshot_config(profiles, collections, None, backup, keep=2)
    assert first is not None and first.is_file()
    assert snapshot_config(profiles, collections, None, backup, keep=2) is None  # throttled

    for i in range(3):  # age the existing snapshot (distinct name), then create a new one
        for n, snap in enumerate(sorted((backup / "snapshots").glob("*.zip"))):
            snap.rename(snap.with_name(f"2000010{i}-0000{n}-old.zip"))
        assert snapshot_config(profiles, collections, None, backup, keep=2, min_interval_s=0)
    assert len(list((backup / "snapshots").glob("*.zip"))) == 2


def test_snapshot_skipped_for_empty_source(tmp_path: Path) -> None:
    from fsmods_gui.profiles.config_backup import snapshot_config

    profiles, collections = _dirs(tmp_path)
    assert snapshot_config(profiles, collections, None, tmp_path / "cloud") is None


# ----------------------------------------------------------------- multi-target


def test_backup_all_isolates_a_failing_target(tmp_path: Path) -> None:
    from fsmods_gui.profiles.config_backup import backup_all, summarize_reports

    profiles, collections = _dirs(tmp_path)
    (profiles / "a.json").write_text("{}", encoding="utf-8")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")  # a file where a folder is expected
    good = tmp_path / "drive"

    reports = backup_all([blocker / "nas", good], profiles, collections, _careers(tmp_path))
    assert [r.ok for r in reports] == [False, True]
    assert reports[0].error
    assert (good / "careers" / "mechet" / "career.json").is_file()
    assert reports[1].snapshot is not None
    text = summarize_reports(reports)
    assert text.startswith("Sauvegarde config : 1/2 OK") and "nas" in text


def test_backup_all_no_targets(tmp_path: Path) -> None:
    from fsmods_gui.profiles.config_backup import backup_all, summarize_reports

    assert backup_all([], None, None) == []
    assert summarize_reports([]) == ""
