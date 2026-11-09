"""Catalogue des objectifs répétables (modèle « Objectifs répétables »)."""
from __future__ import annotations

from pathlib import Path

from fsmods_gui.career.objectives import (
    MODE_REQUIRED_REWARDS,
    ST_COMPLETED,
    evaluate_objectives,
)
from fsmods_gui.career.repeats import REPEATABLE_SPECS, repeatable_objectives
from fsmods_gui.career.stats import Stat, StatsSnapshot
from fsmods_gui.career.store import Career


def _by_key(key: str) -> list:
    return [o for o in repeatable_objectives() if o.id.startswith(f"rep.{key}#")]


def test_steps_match_the_agreed_values():
    steps = {s.key: (s.step, s.count) for s in REPEATABLE_SPECS}
    assert steps["missionIncome"] == (50_000, 20)  # palier de 50 k€ jusqu'à 1 M€
    assert steps["playTime"] == (4, 250)  # palier de 4 h jusqu'à 1 000 h
    assert steps["land"] == (5, 100)  # palier de 5 ha en 5 ha jusqu'à 500 ha


def test_contract_revenue_targets_are_50k_steps():
    targets = [o.condition.target for o in _by_key("missionIncome")]
    assert targets[:3] == [50_000.0, 100_000.0, 150_000.0]
    assert targets[-1] == 1_000_000.0


def test_playtime_paliers_chain_in_order():
    occ = _by_key("playTime")
    assert occ[0].requires == [] and occ[1].requires == [occ[0].id]
    assert occ[0].condition.stat == "playTime" and occ[0].unit == "h"


def test_farm_bound_catalog_gets_distinct_ids():
    ids_a = {o.id for o in repeatable_objectives("1")}
    ids_b = {o.id for o in repeatable_objectives("2")}
    assert ids_a.isdisjoint(ids_b)
    assert all(o.farm == "1" for o in repeatable_objectives("1"))


def test_each_palier_pays_once_when_evaluated(tmp_path: Path):
    career = Career(directory=tmp_path)
    career.start_repeatable()
    snap = StatsSnapshot(taken_at="t", farm_id="1")
    snap.stats["finance.missionIncome"] = Stat(key="finance.missionIncome", value=10_000.0)
    career.snapshot = snap
    career.evaluate()  # first sight: below the first palier
    snap.stats["finance.missionIncome"] = Stat(key="finance.missionIncome", value=60_000.0)
    result = career.evaluate()  # reached during the career: counts
    first = career.get("rep.missionIncome#1")
    assert first is not None and first.status == ST_COMPLETED
    assert [o.id for o in result.newly_completed] == ["rep.missionIncome#1"]
    # Re-evaluating must not re-announce the same palier.
    again = evaluate_objectives(career.objectives, snap, MODE_REQUIRED_REWARDS)
    assert again.newly_completed == []
