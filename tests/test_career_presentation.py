"""Présentation des objectifs en cartes (groupes, textes) et libellés sans emojis."""
from __future__ import annotations

import re

from fsmods_gui.career import presentation as pr
from fsmods_gui.career.objectives import (
    DIFFICULTY_LABELS_FR,
    MODE_LABELS_FR,
    RW_CLAIMED,
    RW_PENDING,
    ST_COMPLETED,
    ST_IN_PROGRESS,
    ST_LOCKED,
    ST_MANUAL,
    ST_NOT_STARTED,
    STATUS_LABELS_FR,
    Condition,
    Objective,
    Reward,
)
from fsmods_gui.career.stats import CATEGORIES_FR, QUALITY_LABELS_FR

EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿⭐]")


def obj(name: str, status: str, **kw) -> Objective:
    return Objective(id=name, name=name, status=status, **kw)


def test_labels_have_no_emoji():
    for labels in (STATUS_LABELS_FR, MODE_LABELS_FR, DIFFICULTY_LABELS_FR,
                   QUALITY_LABELS_FR, CATEGORIES_FR):
        for text in labels.values():
            assert not EMOJI.search(text), text


def test_group_order_and_empty_groups_skipped():
    objs = [
        obj("fini", ST_COMPLETED),
        obj("a", ST_IN_PROGRESS),
        obj("verrou", ST_LOCKED),
        obj("manuel", ST_MANUAL),
    ]
    groups = pr.group_objectives(objs)
    assert [t for t, _ in groups] == ["En cours", "Terminés", "Verrouillés"]
    assert [o.name for o in groups[0][1]] == ["a", "manuel"]  # ordre d'origine conservé


def test_progress_text_leaf_combined_manual():
    leaf = obj("100 ha", ST_IN_PROGRESS,
               condition=Condition(stat="land.area", target=100, unit="ha"),
               current_value=86.4)
    assert pr.progress_text(leaf) == "86,4 ha / >= 100 ha"
    combined = obj("c", ST_IN_PROGRESS, condition=Condition(
        op="and", children=[Condition(stat="a"), Condition(stat="b")]))
    assert pr.progress_text(combined) == "combiné (2 conditions)"
    assert pr.progress_text(obj("m", ST_MANUAL)) == "à valider à la main"


def test_reward_texts():
    o = obj("x", ST_COMPLETED, reward=Reward(money=50000, xp=20, badge="Pionnier"))
    assert pr.reward_text(o) == "50 000 € · 20 XP · badge Pionnier"
    assert pr.reward_text(obj("y", ST_NOT_STARTED)) == ""
    o.reward_state = RW_PENDING
    assert pr.reward_state_text(o) == "à verser"
    o.reward_state = RW_CLAIMED
    assert pr.reward_state_text(o) == "versée"


def test_subtitle_and_percent():
    o = obj("x", ST_IN_PROGRESS, difficulty=3, optional=True, progress=0.864)
    assert pr.subtitle(o, "Terres", "Ferme 2") == "Terres · Difficile · Ferme 2 · optionnel"
    assert pr.subtitle(obj("y", ST_IN_PROGRESS), "Général") == "Général · Normal"
    assert pr.percent_text(o) == "86 %"
