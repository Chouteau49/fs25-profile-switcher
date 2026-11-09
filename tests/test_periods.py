from __future__ import annotations

import pytest

from fsmods_gui.career.objectives import Condition
from fsmods_gui.career.periods import (
    Checkpoint,
    capture_baseline,
    checkpoint,
    evaluate_period,
    period_gain,
)
from fsmods_gui.career.stats import Stat, StatsSnapshot


def _cp(**values: float) -> Checkpoint:
    return Checkpoint(taken_at="2027-01-01", values={k.replace("__", "."): v for k, v in values.items()})


def _leaf(stat: str, op: str, target: float) -> Condition:
    return Condition(stat=stat, operator=op, target=target)


def test_checkpoint_keeps_only_available_values():
    snap = StatsSnapshot(taken_at="t1")
    snap.stats["money"] = Stat(key="money", value=5.0)
    snap.stats["loan"] = Stat(key="loan", value=None)
    cp = checkpoint(snap)
    assert cp.values == {"money": 5.0}
    assert Checkpoint.from_dict(cp.to_dict()) == cp


def test_period_gain_of_cumulative_stat():
    start, end = _cp(contracts__completed=100.0), _cp(contracts__completed=130.0)
    assert period_gain(start, end, "contracts.completed") == 30.0


def test_period_gain_refuses_instantaneous_and_regressions():
    start = _cp(money=100.0, contracts__completed=100.0)
    end = _cp(money=500.0, contracts__completed=80.0)
    assert period_gain(start, end, "money") is None
    assert period_gain(start, end, "contracts.completed") is None


def test_period_gain_unknown_when_missing_at_either_end():
    assert period_gain(_cp(), _cp(contracts__completed=3.0), "contracts.completed") is None


def test_evaluate_period_satisfied_and_partial():
    start, end = _cp(contracts__completed=100.0), _cp(contracts__completed=130.0)
    ok = evaluate_period(_leaf("contracts.completed", ">=", 25), start, end)
    assert ok.satisfied is True and ok.current == 30.0
    part = evaluate_period(_leaf("contracts.completed", ">=", 60), start, end)
    assert part.satisfied is False and part.progress == pytest.approx(0.5)


def test_evaluate_period_rejects_groups():
    group = Condition(op="and", children=[_leaf("contracts.completed", ">=", 1)])
    with pytest.raises(ValueError):
        evaluate_period(group, _cp(), _cp())


def test_capture_baseline_freezes_cumulative_leaves_only():
    snap = StatsSnapshot()
    snap.stats["contracts.completed"] = Stat(key="contracts.completed", value=50.0)
    snap.stats["money"] = Stat(key="money", value=900.0)
    cond = Condition(op="and", children=[
        _leaf("contracts.completed", ">=", 10), _leaf("money", ">=", 1000),
    ])
    assert capture_baseline(cond, snap) == {"contracts.completed": 50.0}
