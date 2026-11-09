"""Campagnes écrites à la main : Kinlaig (clôture) et pisciculture."""
from __future__ import annotations

from fsmods_gui.career.campaigns import CAMPAIGNS, build_fish, build_kinlaig
from fsmods_gui.career.objectives import (
    MODE_OBJECTIVES,
    ST_COMPLETED,
    complete_manually,
    evaluate_objectives,
)
from fsmods_gui.career.stats import Stat, StatsSnapshot


def _snap(**values: float) -> StatsSnapshot:
    snap = StatsSnapshot()
    for key, value in values.items():
        snap.stats[key.replace("__", ".")] = Stat(key=key, value=value)
    return snap


def test_kinlaig_has_twelve_steps_and_a_final_objective_needing_all_of_them():
    objs = build_kinlaig()
    steps, final = objs[:-1], objs[-1]
    assert len(steps) == 12
    assert final.id == "kinlaig.closure"
    assert sorted(final.requires) == sorted(o.id for o in steps)


def test_kinlaig_is_completed_step_by_step_then_the_final_objective():
    objs = build_kinlaig()
    empty_barn = _snap(stock__drygrass_windrow=0.0)  # the hay step is measured on the save
    evaluate_objectives(objs, empty_barn)
    final = objs[-1]
    assert complete_manually(final, MODE_OBJECTIVES) is False  # locked until the steps are done
    for obj in objs[:-1]:
        evaluate_objectives(objs, empty_barn)  # unlock the next steps
        if obj.condition is not None:
            assert obj.status == ST_COMPLETED, obj.id  # measured, not validated by hand
            continue
        assert complete_manually(obj, MODE_OBJECTIVES), obj.id
    evaluate_objectives(objs, empty_barn)
    assert complete_manually(final, MODE_OBJECTIVES)
    assert final.status == ST_COMPLETED


def test_kinlaig_farm_bound_ids_do_not_collide():
    ids_a = {o.id for o in build_kinlaig("1")}
    ids_b = {o.id for o in build_kinlaig("2")}
    assert ids_a.isdisjoint(ids_b)


def test_fish_counts_come_from_manual_stats_and_need_both_farm_types():
    objs = {o.id: o for o in build_fish()}
    evaluate_objectives(list(objs.values()), _snap(fish__salmon__farms=1.0))
    assert objs["fish.salmon"].completed
    assert not objs["fish.trout"].completed
    assert objs["fish.two"].status != ST_COMPLETED  # trout still missing


def test_fish_two_farms_then_five():
    objs = {o.id: o for o in build_fish()}
    values = _snap(fish__salmon__farms=1.0, fish__trout__farms=1.0, fish__farms=2.0)
    evaluate_objectives(list(objs.values()), values)
    assert objs["fish.two"].completed and not objs["fish.five"].completed


def test_campaign_registry_is_consistent():
    keys = [c.key for c in CAMPAIGNS]
    assert len(keys) == len(set(keys))
    for campaign in CAMPAIGNS:
        assert campaign.build("")  # every campaign builds at least one objective


def test_hay_step_is_measured_on_the_remaining_stock():
    from fsmods_gui.career.objectives import evaluate

    hay = next(o for o in build_kinlaig() if o.id == "kinlaig.hay")
    assert hay.condition is not None and hay.condition.stat == "stock.drygrass_windrow"
    assert evaluate(hay.condition, _snap(stock__drygrass_windrow=22500.0)).satisfied is False
    assert evaluate(hay.condition, _snap(stock__drygrass_windrow=0.0)).satisfied is True


def test_hay_absent_from_the_save_counts_as_empty():
    from fsmods_gui.career.objectives import evaluate

    hay = next(o for o in build_kinlaig() if o.id == "kinlaig.hay")
    snap = StatsSnapshot()
    snap.complete_prefixes.add("stock.")  # the save lists every stock it has
    assert evaluate(hay.condition, snap).satisfied is True


def test_castle_step_says_it_is_entered_by_hand():
    castle = next(o for o in build_kinlaig() if o.id == "kinlaig.castle")
    assert castle.condition is None
    assert "Saisie manuelle" in castle.description
