"""Compteur de mods en attente dans ``_inbox`` (badge de la barre latérale)."""
from __future__ import annotations

from fsmods_gui.profiles.inbox import count_waiting


def test_count_waiting_counts_only_zip_files(tmp_path):
    (tmp_path / "a.zip").write_bytes(b"x")
    (tmp_path / "B.ZIP").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "dossier.zip").mkdir()
    assert count_waiting(tmp_path) == 2


def test_count_waiting_missing_or_none(tmp_path):
    assert count_waiting(tmp_path / "absent") == 0
    assert count_waiting(None) == 0
