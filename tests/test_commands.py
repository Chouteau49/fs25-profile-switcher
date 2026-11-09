"""Palette de commandes (Ctrl+K) : liste et recherche."""
from __future__ import annotations

from fsmods_gui import commands as cmd

ALL = cmd.build_commands(
    [("montagne", "Montagne", 142), ("plaines", "Plaines", 96)],
    [("base", "Base FS25", 38)],
    [("FS25_Courseplay.zip", "Courseplay"), ("FS25_AutoDrive.zip", "AutoDrive")],
)


def keys(results):
    return [c.key for c in results]


def test_empty_query_lists_everything_but_mods():
    res = cmd.search(ALL, "")
    assert "play:montagne" in keys(res)
    assert "action:rescan" in keys(res)
    assert not any(c.group == cmd.GROUP_MODS for c in res)


def test_search_all_words_case_and_accent_insensitive():
    assert keys(cmd.search(ALL, "jouer plai")) == ["play:plaines"]
    assert "go:allmods" in keys(cmd.search(ALL, "TOUS les MODS"))
    assert "action:rescan" in keys(cmd.search(ALL, "bibliotheque"))  # sans accent


def test_mods_are_found_when_searched():
    assert keys(cmd.search(ALL, "course")) == ["mod:FS25_Courseplay.zip"]


def test_label_prefix_ranks_first():
    res = cmd.search(ALL, "montagne")
    assert res[0].key in ("play:montagne", "open:montagne")
    assert keys(cmd.search(ALL, "ouvrir mont"))[0] == "open:montagne"


def test_hint_mentions_mod_count_and_limit():
    play = next(c for c in ALL if c.key == "play:montagne")
    assert "142 mods" in play.hint
    assert len(cmd.search(ALL, "", limit=3)) == 3


def test_no_result():
    assert cmd.search(ALL, "zzz introuvable") == []
