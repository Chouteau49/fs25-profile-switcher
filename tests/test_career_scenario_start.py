"""Démarrage d'un scénario en cours de partie : mesure depuis l'activation ou depuis le début."""
from __future__ import annotations

from pathlib import Path

import pytest

from fsmods_gui.career.stats import Stat, StatsSnapshot
from fsmods_gui.career.store import Career, CareerError


def _career(tmp_path: Path, **values: float) -> Career:
    snap = StatsSnapshot(taken_at="t1", farm_id="1", savegame="savegame1")
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    career = Career(directory=tmp_path)
    career.snapshot = snap
    return career


def test_default_start_measures_from_the_save_total(tmp_path: Path):
    career = _career(tmp_path, contracts__completed=50.0, finance__missionIncome=1.0)
    added, skipped = career.start_scenario("eta")
    assert added > 0 and skipped == []
    assert all(o.baseline == {} for o in career.objectives)


def test_from_activation_freezes_cumulative_values(tmp_path: Path):
    career = _career(tmp_path, contracts__completed=50.0, finance__missionIncome=1.0)
    career.start_scenario("eta", from_activation=True)
    c10 = career.get("eta.c10")
    assert c10 is not None and c10.baseline == {"contracts.completed": 50.0}


def test_objective_without_baseline_is_skipped_with_its_dependents(tmp_path: Path):
    # finance.missionIncome is unknown here: every objective measuring it cannot start
    # from activation (its total would be counted as a gain), nor can what requires it.
    career = _career(tmp_path, contracts__completed=50.0)
    added, skipped = career.start_scenario("eta", from_activation=True)
    assert "Gagner 100 000 € grâce aux contrats" in skipped
    assert career.get("eta.inc100k") is None
    assert career.get("eta.pro") is None
    assert career.get("eta.c10") is not None


def test_from_activation_requires_a_synchronised_save(tmp_path: Path):
    career = Career(directory=tmp_path)
    with pytest.raises(CareerError):
        career.start_scenario("eta", from_activation=True)
    assert career.objectives == []
