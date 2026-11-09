from __future__ import annotations

from fsmods_gui.career.regression import detect_regressions, is_cumulative
from fsmods_gui.career.stats import Stat, StatsSnapshot


def _snap(**values: float | None) -> StatsSnapshot:
    snap = StatsSnapshot()
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    return snap


def test_contract_drop_after_restore_is_a_regression():
    before = _snap(contracts__completed=150.0)
    after = _snap(contracts__completed=80.0)
    found = detect_regressions(before, after)
    assert [(r.key, r.before, r.after) for r in found] == [("contracts.completed", 150.0, 80.0)]


def test_instantaneous_stat_drop_is_not_a_regression():
    assert detect_regressions(_snap(money=1000.0), _snap(money=10.0)) == []


def test_increase_is_not_a_regression():
    assert detect_regressions(_snap(contracts__completed=10.0), _snap(contracts__completed=12.0)) == []


def test_tiny_drop_within_tolerance_is_ignored():
    assert detect_regressions(_snap(contracts__completed=1000.0), _snap(contracts__completed=995.0)) == []


def test_unknown_value_on_either_side_proves_nothing():
    assert detect_regressions(_snap(contracts__completed=150.0), _snap(contracts__completed=None)) == []
    assert detect_regressions(_snap(contracts__completed=None), _snap(contracts__completed=0.0)) == []


def test_work_family_is_cumulative():
    assert is_cumulative("work.harvested")
    assert is_cumulative("animals.bred.cow")
    assert not is_cumulative("vine.area")
