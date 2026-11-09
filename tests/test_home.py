"""Données de l'écran d'accueil (cartes de profils)."""
from __future__ import annotations

from datetime import datetime

import pytest

from fsmods_gui import home
from fsmods_gui.profiles.profile import Profile

NOW = datetime(2026, 11, 9, 12, 0)


@pytest.mark.parametrize(
    ("iso", "expected"),
    [
        (None, "jamais joué"),
        ("", "jamais joué"),
        ("pas une date", "jamais joué"),
        ("2026-11-09T08:15:00", "aujourd'hui, 08:15"),
        ("2026-11-08T21:40:00", "hier, 21:40"),
        ("2026-11-05T10:00:00", "il y a 4 jours"),
        ("2026-11-01T10:00:00", "il y a 1 semaine"),
        ("2026-10-20T10:00:00", "il y a 2 semaines"),
        ("2026-09-01T10:00:00", "le 01/09/2026"),
    ],
)
def test_last_played_label(iso, expected):
    assert home.last_played_label(iso, NOW) == expected


def test_map_label_mod_official_dlc_none():
    p = Profile(name="A", map_mod="FS25_Alpenland.zip")
    assert home.map_label(p, {"FS25_Alpenland.zip": "Alpenland"}) == "Alpenland · carte mod"
    assert home.map_label(p, {}) == "FS25_Alpenland · carte mod"
    assert home.map_label(Profile(name="B", official_map="MapUS"), {}) == (
        "Riverbend Springs · carte officielle"
    )
    assert home.map_label(Profile(name="C"), {}) == "Aucune carte choisie"


def test_map_label_never_duplicates_kind():
    # Régression 0.10 : « Riverbend Springs (carte officielle) · carte officielle ».
    label = home.map_label(Profile(name="B", official_map="MapUS"), {})
    assert label.count("carte officielle") == 1


def test_build_cards_order_and_last_played():
    montagne = Profile(name="Montagne", last_played="2026-11-08T21:40:00", mods=["a.zip"])
    plaines = Profile(name="Plaines", last_played="2026-11-05T10:00:00")
    jamais_b = Profile(name="b jamais")
    jamais_a = Profile(name="A jamais", collections=["base", "cp"])
    cards = home.build_cards(
        [plaines, jamais_b, montagne, jamais_a],
        {"montagne": 142},
        {},
        NOW,
    )
    assert [c.name for c in cards] == ["Montagne", "Plaines", "A jamais", "b jamais"]
    assert [c.is_last_played for c in cards] == [True, False, False, False]
    assert cards[0].mods_count == 142  # nombre effectif (collections comprises)
    assert cards[1].mods_count == 0  # repli : mods propres du profil
    assert cards[2].collections_label == "2 collections"
    assert cards[1].collections_label == "aucune collection"
    assert cards[0].mods_label == "142 mods"


def test_build_cards_without_any_played_profile():
    cards = home.build_cards([Profile(name="X")], {}, {}, NOW)
    assert not cards[0].is_last_played


def test_art_palette_is_stable_and_valid():
    a = home.art_palette("Montagne")
    assert a == home.art_palette("Montagne")
    assert len(a) == 5 and all(c.startswith("#") for c in a)
