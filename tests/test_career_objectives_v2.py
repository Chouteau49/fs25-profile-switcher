"""Record, point de départ et cas combinés avec statistique inconnue (moteur d'objectifs)."""
from __future__ import annotations

from fsmods_gui.career.objectives import (
    Condition,
    Objective,
    evaluate,
    evaluate_objectives,
)
from fsmods_gui.career.stats import Stat, StatsSnapshot


def _snap(**values: float | None) -> StatsSnapshot:
    snap = StatsSnapshot()
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    return snap


def _obj(stat: str, target: float, **kw) -> Objective:
    cond = Condition(stat=stat, operator=">=", target=target)
    return Objective(id="o", name="O", condition=cond, **kw)


def test_record_survives_a_drop_and_current_value_follows_it():
    obj = _obj("contracts.completed", 50)
    evaluate_objectives([obj], _snap(contracts__completed=30.0))
    evaluate_objectives([obj], _snap(contracts__completed=20.0))
    assert obj.record_value == 30.0 and obj.record_at
    assert obj.current_value == 20.0


def test_completion_is_sticky_when_the_stat_drops():
    obj = _obj("vehicles.count", 10)
    evaluate_objectives([obj], _snap(vehicles__count=10.0))
    evaluate_objectives([obj], _snap(vehicles__count=5.0))
    assert obj.completed


def test_baseline_measures_only_the_gain_since_activation():
    obj = _obj("contracts.completed", 10, baseline={"contracts.completed": 50.0})
    evaluate_objectives([obj], _snap(contracts__completed=55.0))
    assert not obj.completed
    evaluate_objectives([obj], _snap(contracts__completed=60.0))
    assert obj.completed


def test_baseline_only_applies_to_listed_stats():
    cond = Condition(op="and", children=[
        Condition(stat="contracts.completed", operator=">=", target=2),  # gain = 2
        Condition(stat="money", operator=">=", target=100),  # not baselined: 150 >= 100
    ])
    snap = _snap(contracts__completed=52.0, money=150.0)
    ev = evaluate(cond, snap, {"contracts.completed": 50.0})
    assert ev.satisfied is True


def test_record_and_baseline_round_trip_through_json():
    obj = _obj("contracts.completed", 10, baseline={"contracts.completed": 5.0})
    obj.record_value, obj.record_at = 7.0, "2027-01-01T00:00:00"
    back = Objective.from_dict(obj.to_dict())
    assert back.record_value == 7.0 and back.record_at == "2027-01-01T00:00:00"
    assert back.baseline == {"contracts.completed": 5.0}


def test_combined_conditions_with_unknown_values():
    known_false = Condition(stat="vehicles.count", operator=">=", target=10)
    known_true = Condition(stat="vehicles.count", operator=">=", target=1)
    unknown = Condition(stat="loan", operator=">=", target=0)  # absent from the snapshot
    snap = _snap(vehicles__count=5.0)

    def group(op: str, *children: Condition) -> Condition:
        return Condition(op=op, children=list(children))

    assert evaluate(group("and", unknown, known_false), snap).satisfied is False
    assert evaluate(group("and", unknown, known_true), snap).satisfied is None
    assert evaluate(group("or", unknown, known_true), snap).satisfied is True
    assert evaluate(group("or", unknown, known_false), snap).satisfied is None
    assert evaluate(group("not", unknown), snap).satisfied is None
    assert evaluate(group("not", known_false), snap).satisfied is True
