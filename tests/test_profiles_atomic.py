from __future__ import annotations

import os
from pathlib import Path

import pytest

from fsmods_gui.profiles import atomic
from fsmods_gui.profiles.atomic import atomic_write_bytes, atomic_write_text


def test_write_creates_parents_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "a.json"
    atomic_write_text(target, "é")
    assert target.read_bytes() == "é".encode()
    assert [p.name for p in target.parent.iterdir()] == ["a.json"]


def test_failed_write_keeps_the_old_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.json"
    target.write_text("old", encoding="utf-8")

    def crash(*_args: object) -> None:
        raise OSError("disque plein")

    monkeypatch.setattr(atomic.os, "fsync", crash)
    with pytest.raises(OSError):
        atomic_write_bytes(target, b"new")
    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_replace_waits_for_a_file_briefly_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On Windows the backup thread reading the target makes os.replace fail for a moment.
    real_replace = os.replace
    calls: list[int] = []

    def locked_twice(src: Path, dst: Path) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("utilisé par un autre processus")
        real_replace(src, dst)

    monkeypatch.setattr(atomic.os, "replace", locked_twice)
    monkeypatch.setattr(atomic, "RETRY_DELAY_S", 0)
    target = tmp_path / "a.json"
    atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"new" and len(calls) == 3


def test_replace_gives_up_on_a_file_locked_for_good(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_locked(*_args: object) -> None:
        raise PermissionError("utilisé par un autre processus")

    monkeypatch.setattr(atomic.os, "replace", always_locked)
    monkeypatch.setattr(atomic, "RETRY_DELAY_S", 0)
    target = tmp_path / "a.json"
    with pytest.raises(PermissionError):
        atomic_write_bytes(target, b"new")
    assert list(tmp_path.iterdir()) == []
