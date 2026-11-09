"""Encadrés de la page Profil : dépendances et mods absents."""
from __future__ import annotations

from fsmods_gui.editor_notices import (
    ACTION_ADD,
    ACTION_REMOVE,
    KIND_ERROR,
    KIND_INFO,
    dependency_notices,
    missing_notice,
)
from fsmods_gui.profiles.dependencies import DependencyResolution


def test_no_dependency_no_notice():
    assert dependency_notices(DependencyResolution(), {}, ["Silo"]) == []


def test_dependency_to_add_offers_action_with_titles():
    res = DependencyResolution(to_add=["FS25_FarmLights.zip"])
    (notice,) = dependency_notices(res, {"FS25_FarmLights.zip": "Lumières de ferme"}, ["Silo"])
    assert notice.kind == KIND_INFO
    assert notice.text.startswith("Silo a besoin de Lumières de ferme")
    assert notice.action == ACTION_ADD and notice.action_label == "Ajouter aussi"
    assert notice.filenames == ("FS25_FarmLights.zip",)


def test_missing_dependency_is_an_error_without_action():
    res = DependencyResolution(missing=["FS25_Unknown"])
    (notice,) = dependency_notices(res, {}, ["A", "B"])
    assert notice.kind == KIND_ERROR and notice.action is None
    assert notice.text.startswith("A, B ont besoin de FS25_Unknown")


def test_long_lists_are_shortened():
    res = DependencyResolution(to_add=[f"m{i}.zip" for i in range(6)])
    (notice,) = dependency_notices(res, {}, ["X"])
    assert "et 3 autre(s)" in notice.text
    assert len(notice.filenames) == 6  # l'action porte sur toutes


def test_missing_notice():
    assert missing_notice([]) is None
    one = missing_notice(["FS25_LongTrailers.zip"])
    assert one is not None and one.text.startswith("1 mod du profil est absent")
    assert one.action == ACTION_REMOVE and one.filenames == ("FS25_LongTrailers.zip",)
    two = missing_notice(["a.zip", "b.zip"])
    assert two is not None and two.text.startswith("2 mods du profil sont absents")
