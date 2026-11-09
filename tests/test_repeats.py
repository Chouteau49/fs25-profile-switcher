from __future__ import annotations

import pytest

from fsmods_gui.career.objectives import (
    MODE_REQUIRED_REWARDS,
    RW_PENDING,
    ST_COMPLETED,
    Condition,
    Objective,
    ObjectiveError,
    Reward,
    evaluate_objectives,
)
from fsmods_gui.career.repeats import build_occurrences, completed_occurrences
from fsmods_gui.career.stats import Stat, StatsSnapshot


def _snap(**values: float) -> StatsSnapshot:
    snap = StatsSnapshot()
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    return snap


def _base() -> Objective:
    return Objective(
        id="harvest",
        name="Récolter",
        condition=Condition(stat="work.harvested", operator=">=", target=100, unit="ha"),
        reward=Reward(money=10_000),
    )


def test_occurrences_have_stepped_targets_distinct_ids_and_chain():
    occ = build_occurrences(_base(), 100, 3)
    assert [o.id for o in occ] == ["harvest#1", "harvest#2", "harvest#3"]
    assert [o.condition.target for o in occ] == [100.0, 200.0, 300.0]
    assert occ[1].requires == ["harvest#1"] and occ[2].requires == ["harvest#2"]


def test_occurrence_reward_is_an_independent_copy():
    base = _base()
    occ = build_occurrences(base, 100, 2)
    occ[0].reward.money = 999
    assert base.reward.money == 10_000 and occ[1].reward.money == 10_000


def test_each_occurrence_pays_once_and_chain_unlocks_in_order():
    occ = build_occurrences(_base(), 100, 3)
    evaluate_objectives(occ, _snap(work__harvested=50.0), MODE_REQUIRED_REWARDS)
    result = evaluate_objectives(occ, _snap(work__harvested=150.0), MODE_REQUIRED_REWARDS)
    assert occ[0].status == ST_COMPLETED and occ[0].reward_state == RW_PENDING
    assert occ[1].status != ST_COMPLETED and occ[2].status != ST_COMPLETED
    assert [o.id for o in result.newly_completed] == ["harvest#1"]
    assert completed_occurrences(occ, "harvest") == 1


@pytest.mark.parametrize(
    "base, step, count",
    [
        (_base(), 0, 1),
        (_base(), 100, 0),
        (Objective(id="m", name="Manuel"), 100, 1),
        (Objective(id="d", name="Baisse", condition=Condition(
            stat="money", operator="<=", target=5)), 100, 1),
    ],
)
def test_rejects_invalid_repeatable_definitions(base, step, count):
    with pytest.raises(ObjectiveError):
        build_occurrences(base, step, count)
