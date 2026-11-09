"""Journal de lecture et détection de régressions au niveau de la carrière (store)."""
from __future__ import annotations

from pathlib import Path

from fsmods_gui.career.stats import Stat, StatsSnapshot
from fsmods_gui.career.store import Career


def _snap(taken_at: str, farm: str = "1", savegame: str = "savegame1", **values: float) -> StatsSnapshot:
    snap = StatsSnapshot(taken_at=taken_at, farm_id=farm, savegame=savegame)
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    return snap


def test_first_reading_is_logged_without_regressions(tmp_path: Path):
    career = Career(directory=tmp_path)
    found = career.log_reading(StatsSnapshot(), _snap("t1", contracts__completed=150.0))
    assert found == []
    assert len(career.analysis_log) == 1


def test_contract_drop_on_same_farm_is_reported(tmp_path: Path):
    career = Career(directory=tmp_path)
    career.log_reading(StatsSnapshot(), _snap("t1", contracts__completed=150.0))
    found = career.log_reading(
        _snap("t1", contracts__completed=150.0), _snap("t2", contracts__completed=80.0)
    )
    assert [r.key for r in found] == ["contracts.completed"]
    assert career.analysis_log[-1]["anomalies"][0]["after"] == 80.0


def test_switching_farm_does_not_fake_a_regression(tmp_path: Path):
    career = Career(directory=tmp_path)
    previous = _snap("t1", farm="1", contracts__completed=150.0)
    current = _snap("t2", farm="2", contracts__completed=12.0)
    assert career.log_reading(previous, current) == []
    assert career.analysis_log[-1]["changes"] == {}


def test_savegame_change_does_not_compare_readings(tmp_path: Path):
    career = Career(directory=tmp_path)
    previous = _snap("t1", savegame="savegame1", contracts__completed=150.0)
    current = _snap("t2", savegame="savegame2", contracts__completed=12.0)
    assert career.log_reading(previous, current) == []


def test_analysis_log_survives_save_and_load(tmp_path: Path):
    career = Career(directory=tmp_path)
    career.log_reading(StatsSnapshot(), _snap("t1", money=10.0))
    career.log_reading(_snap("t1", money=10.0), _snap("t2", money=20.0))
    career.save()
    reloaded = Career.load(tmp_path)
    assert [e["takenAt"] for e in reloaded.analysis_log] == ["t1", "t2"]
    assert reloaded.analysis_log[-1]["changes"] == {"money": 10.0}
