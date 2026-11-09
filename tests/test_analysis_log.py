from __future__ import annotations

from fsmods_gui.career.analysis_log import ANALYSIS_LIMIT, append_entry, record_analysis
from fsmods_gui.career.stats import Stat, StatsSnapshot


def _snap(taken_at: str, **values: float | None) -> StatsSnapshot:
    snap = StatsSnapshot(taken_at=taken_at)
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    return snap


def test_first_reading_has_no_changes_or_anomalies():
    entry = record_analysis(None, _snap("t1", money=10.0, loan=None), game_version="1.14")
    assert entry.available == 1 and entry.total == 2
    assert entry.changes == {} and entry.anomalies == []
    assert entry.game_version == "1.14"


def test_second_reading_reports_changes_and_regression():
    before = _snap("t1", money=10.0, contracts__completed=150.0)
    after = _snap("t2", money=25.0, contracts__completed=80.0)
    entry = record_analysis(before, after)
    assert entry.changes == {"money": 15.0, "contracts.completed": -70.0}
    assert [a.key for a in entry.anomalies] == ["contracts.completed"]
    assert entry.to_dict()["anomalies"][0]["before"] == 150.0


def test_log_keeps_only_most_recent_entries():
    log: list[dict] = []
    for i in range(5):
        entry = record_analysis(None, _snap(f"t{i}", money=float(i)))
        log = append_entry(log, entry, limit=3)
    assert [e["takenAt"] for e in log] == ["t2", "t3", "t4"]
    assert ANALYSIS_LIMIT == 100
