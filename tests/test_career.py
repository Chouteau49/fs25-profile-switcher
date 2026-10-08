from __future__ import annotations

import json
from pathlib import Path

import pytest

from fsmods_gui.career.objectives import (
    MODE_MANUAL_REWARDS,
    MODE_OBJECTIVES,
    MODE_REQUIRED_REWARDS,
    RW_CLAIMED,
    RW_NONE,
    RW_PENDING,
    RW_WAIVED,
    ST_COMPLETED,
    ST_LOCKED,
    ST_MANUAL,
    ST_UNAVAILABLE,
    Condition,
    Objective,
    ObjectiveError,
    Reward,
    claim_reward,
    complete_manually,
    evaluate,
    evaluate_objectives,
    level_for_xp,
    summarize,
)
from fsmods_gui.career.stats import (
    Q_AUTO,
    Q_CALC,
    Q_MANUAL,
    Q_NA,
    Stat,
    StatsSnapshot,
    apply_manual,
    extract_stats,
)
from fsmods_gui.career.store import Career
from fsmods_gui.career.sync import guess_savegame, sync_career
from fsmods_gui.career.templates import TEMPLATES, build_template

CAREER_XML = """<careerSavegame>
  <settings><savegameName>Test</savegameName><mapTitle>Les Combes</mapTitle>
    <mapId>FS25_The_Combes.Map</mapId></settings>
  <statistics><money>1</money><playTime>150</playTime></statistics>
</careerSavegame>"""

FARMS_XML = """<farms>
  <farm farmId="1" name="Moi" money="742000" loan="50000">
    <statistics>
      <playTime>9000</playTime><workedHectares>12.5</workedHectares>
      <fieldJobMissionCount>10</fieldJobMissionCount>
      <transportMissionCount>3</transportMissionCount>
      <customThing>7</customThing>
    </statistics>
    <finances>
      <stats day="1"><harvestIncome>1000</harvestIncome><missionIncome>500</missionIncome>
        <newVehiclesCost>-300</newVehiclesCost><wagePayment>100</wagePayment></stats>
      <stats day="2"><harvestIncome>200</harvestIncome><missionIncome>100</missionIncome></stats>
    </finances>
  </farm>
  <farm farmId="2" name="Autre" money="5"/>
</farms>"""

VEHICLES_XML = """<vehicles>
  <vehicle filename="data/vehicles/fendt/vario700/tractor.xml" farmId="1" price="100000"/>
  <vehicle filename="data/vehicles/fendt/ideal/combine.xml" farmId="1" price="300000"/>
  <vehicle filename="data/vehicles/john_deere/x/trailer.xml" farmId="1" price="20000"/>
  <vehicle filename="$moddir$FS25_Cool/cool.xml" modName="FS25_Cool" farmId="1" price="10"/>
  <vehicle filename="data/vehicles/claas/mission.xml" farmId="1" propertyState="MISSION"/>
  <vehicle filename="data/vehicles/other/x.xml" farmId="2" price="999"/>
</vehicles>"""

PLACEABLES_XML = """<placeables>
  <placeable filename="data/placeables/cowbarn.xml" farmId="1" price="50000">
    <husbandryAnimals><animal subType="COW_HOLSTEIN"/><animal subType="COW_ANGUS"/>
      <cluster subType="PIG_LANDRACE" numAnimals="4"/></husbandryAnimals>
  </placeable>
  <placeable filename="data/placeables/bakery.xml" farmId="1" price="10000">
    <productionPoint/>
  </placeable>
  <placeable filename="data/placeables/beehive.xml" farmId="1" price="100"/>
  <placeable filename="data/placeables/foreign.xml" farmId="2" price="1"/>
</placeables>"""

FARMLANDS_XML = """<farmlands>
  <farmland id="1" farmId="1"/><farmland id="2" farmId="1"/>
  <farmland id="3" farmId="0"/><farmland id="4" farmId="2"/>
</farmlands>"""

FIELDS_XML = """<fields>
  <field id="1" fruitType="WHEAT"/><field id="2" fruitType="WHEAT"/>
  <field id="3" plannedFruit="LAVENDER"/><field id="4" fruitType="UNKNOWN"/>
</fields>"""

ENV_XML = "<environment><currentDay>42</currentDay></environment>"


def make_save(base: Path, name: str = "savegame1") -> Path:
    sg = base / name
    sg.mkdir(parents=True)
    for fname, text in {
        "careerSavegame.xml": CAREER_XML,
        "farms.xml": FARMS_XML,
        "vehicles.xml": VEHICLES_XML,
        "placeables.xml": PLACEABLES_XML,
        "farmlands.xml": FARMLANDS_XML,
        "fields.xml": FIELDS_XML,
        "environment.xml": ENV_XML,
    }.items():
        (sg / fname).write_text(text, encoding="utf-8")
    return sg


def snap(**values: float) -> StatsSnapshot:
    s = StatsSnapshot()
    for key, v in values.items():
        k = key.replace("__", ".")
        s.stats[k] = Stat(key=k, value=v)
    return s


def leaf(stat: str, target: float, operator: str = ">=") -> Condition:
    return Condition(stat=stat, target=target, operator=operator)


def obj(oid: str, cond: Condition | None, **kw) -> Objective:
    return Objective(id=oid, name=oid, condition=cond, **kw)


# ------------------------------------------------------------------ extraction


def test_extract_stats_from_savegame(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("money") == 742000
    assert s.value("loan") == 50000
    assert s.get("money").quality == Q_AUTO
    assert s.value("playTime") == pytest.approx(2.5)  # career playTime (minutes → h)
    assert s.value("daysPlayed") == 42
    assert s.value("farms.count") == 2
    assert s.value("work.worked") == 12.5
    assert s.value("raw.customThing") == 7


def test_contracts_are_summed_and_flagged_calculated(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("contracts.completed") == 13
    assert s.get("contracts.completed").quality == Q_CALC


def test_finance_history_summed(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("finance.income") == 1000 + 500 + 200 + 100
    assert s.value("finance.expenses") == 400
    assert s.value("finance.missionIncome") == 600


def test_vehicles_exclude_missions_and_other_farms(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("vehicles.count") == 4
    assert s.value("vehicles.value") == 420010
    assert s.value("vehicles.brand.fendt") == 2
    assert s.value("vehicles.brand.fs25_cool") == 1  # dynamic brand from the mod
    assert s.value("vehicles.type.tractor") == 1
    assert s.value("vehicles.type.harvester") == 1
    assert s.get("vehicles.type.tractor").quality == Q_CALC


def test_animals_dynamic_species_and_placeables(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("animals.cow") == 2
    assert s.value("animals.pig") == 4
    assert s.value("animals.total") == 6
    assert s.value("animals.species") == 2
    assert s.value("animals.beehives") == 1
    assert s.value("placeables.count") == 3
    assert s.value("productions.count") == 1


def test_land_and_crops(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("land.count") == 2
    # No area in the savegame: explicitly unavailable, never 0.
    assert s.get("land.area").value is None
    assert s.get("land.area").quality == Q_NA
    assert s.value("crops.fields.wheat") == 2
    assert s.value("crops.fields.lavender") == 1  # mod/map crop discovered dynamically
    assert s.value("crops.growing") == 2


def test_net_worth_is_estimated(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("netWorth") == 742000 - 50000 + 420010 + 60100
    assert s.get("netWorth").quality == Q_CALC


def test_empty_savegame_yields_unavailable_not_zero(tmp_path: Path) -> None:
    sg = tmp_path / "savegame9"
    sg.mkdir()
    s = extract_stats(sg)
    assert s.value("money") is None
    assert s.get("contracts.completed").quality == Q_NA


def test_manual_overrides_only_non_auto(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    apply_manual(s, {"land.area": 86.4, "money": 1.0})
    assert s.value("land.area") == 86.4
    assert s.get("land.area").quality == Q_MANUAL
    assert s.value("money") == 742000  # auto value wins


def test_snapshot_roundtrip(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    again = StatsSnapshot.from_dict(json.loads(json.dumps(s.to_dict())))
    assert again.value("money") == 742000
    assert again.get("land.area").value is None


# ---------------------------------------------------------------------- engine


def test_leaf_progress_and_operators() -> None:
    s = snap(money=742000, cows=17)
    ev = evaluate(leaf("money", 1_000_000), s)
    assert ev.satisfied is False
    assert ev.progress == pytest.approx(0.742)
    assert evaluate(leaf("money", 700_000), s).satisfied is True
    assert evaluate(leaf("money", 742000, ">"), s).satisfied is False
    assert evaluate(leaf("cows", 20, "<="), s).satisfied is True
    assert evaluate(leaf("cows", 17, "=="), s).satisfied is True


def test_unavailable_stat_is_unknown_not_zero() -> None:
    ev = evaluate(leaf("land.area", 50), StatsSnapshot())
    assert ev.satisfied is None


def test_and_or_not() -> None:
    s = snap(a=10, b=1)
    a_ok, b_bad = leaf("a", 5), leaf("b", 5)
    assert evaluate(Condition(op="and", children=[a_ok, b_bad]), s).satisfied is False
    assert evaluate(Condition(op="or", children=[a_ok, b_bad]), s).satisfied is True
    assert evaluate(Condition(op="not", children=[b_bad]), s).satisfied is True
    and_ev = evaluate(Condition(op="and", children=[a_ok, b_bad]), s)
    assert and_ev.progress == pytest.approx((1 + 0.2) / 2)
    # unknown + false => false; unknown + true => unknown (AND)
    missing = leaf("zzz", 1)
    assert evaluate(Condition(op="and", children=[b_bad, missing]), s).satisfied is False
    assert evaluate(Condition(op="and", children=[a_ok, missing]), s).satisfied is None
    assert evaluate(Condition(op="or", children=[a_ok, missing]), s).satisfied is True


def test_condition_roundtrip_and_validation() -> None:
    cond = Condition(op="and", children=[leaf("a", 1), Condition(op="not", children=[leaf("b", 2)])])
    assert Condition.from_dict(cond.to_dict()).to_dict() == cond.to_dict()
    with pytest.raises(ObjectiveError):
        Condition.from_dict({"stat": "a", "operator": "~="})
    with pytest.raises(ObjectiveError):
        Condition.from_dict({"op": "not", "children": []})


def test_completion_is_sticky_and_reported_once() -> None:
    o = obj("o", leaf("money", 100))
    evaluate_objectives([o], snap(money=10))  # seen unsatisfied: career in progress
    res = evaluate_objectives([o], snap(money=500))
    assert [x.id for x in res.newly_completed] == ["o"]
    assert o.completed_at
    res = evaluate_objectives([o], snap(money=0))  # money drops: stays completed
    assert o.status == ST_COMPLETED
    assert res.newly_completed == []


def test_unavailable_and_manual_status() -> None:
    a = obj("a", leaf("land.area", 50))
    m = obj("m", None)
    evaluate_objectives([a, m], StatsSnapshot())
    assert a.status == ST_UNAVAILABLE
    assert m.status == ST_MANUAL
    assert m.type == "manual"
    assert complete_manually(m, MODE_OBJECTIVES)
    assert m.status == ST_COMPLETED
    assert not complete_manually(m, MODE_OBJECTIVES)
    assert not complete_manually(a, MODE_OBJECTIVES)


def test_prerequisite_chain_unlocks() -> None:
    a = obj("a", leaf("x", 10))
    b = obj("b", leaf("x", 5), requires=["a"])
    evaluate_objectives([a, b], snap(x=1))
    assert b.status == ST_LOCKED
    res = evaluate_objectives([a, b], snap(x=20))
    assert a.completed and b.completed  # whole chain resolved in one call
    assert [o.id for o in res.newly_unlocked] == ["b"]


def test_reward_flow_and_no_double_claim() -> None:
    o = obj("o", leaf("money", 100), reward=Reward(money=50_000))
    evaluate_objectives([o], snap(money=1), MODE_MANUAL_REWARDS)
    evaluate_objectives([o], snap(money=200), MODE_MANUAL_REWARDS)
    assert o.reward_state == RW_PENDING
    assert summarize([o]).money_pending == 50_000
    assert claim_reward(o) is True
    assert o.reward_state == RW_CLAIMED
    assert claim_reward(o) is False  # never twice
    evaluate_objectives([o], snap(money=300), MODE_MANUAL_REWARDS)
    assert o.reward_state == RW_CLAIMED
    s = summarize([o])
    assert (s.money_pending, s.money_claimed) == (0, 50_000)


def test_no_money_reward_when_mode_is_objectives_only() -> None:
    o = obj("o", leaf("money", 100), reward=Reward(money=50_000))
    evaluate_objectives([o], snap(money=1), MODE_OBJECTIVES)
    evaluate_objectives([o], snap(money=200), MODE_OBJECTIVES)
    assert o.reward_state == RW_WAIVED
    assert o.reward_state != RW_PENDING


def test_already_satisfied_at_start_has_no_reward_due() -> None:
    o = obj("o", leaf("money", 100), reward=Reward(money=50_000, xp=10))
    res = evaluate_objectives([o], snap(money=1000), MODE_MANUAL_REWARDS)
    assert o.completed
    assert o.reward_state == RW_WAIVED
    assert res.newly_completed == []


def test_locked_objective_satisfied_on_first_sight_is_waived() -> None:
    a = obj("a", leaf("x", 10))
    b = obj("b", leaf("y", 5), requires=["a"], reward=Reward(money=1000))
    evaluate_objectives([a, b], snap(x=1, y=99), MODE_MANUAL_REWARDS)
    evaluate_objectives([a, b], snap(x=50, y=99), MODE_MANUAL_REWARDS)
    assert b.completed and b.reward_state == RW_WAIVED


def test_locked_objective_reached_later_is_earned() -> None:
    a = obj("a", leaf("x", 10))
    b = obj("b", leaf("y", 5), requires=["a"], reward=Reward(money=1000))
    evaluate_objectives([a, b], snap(x=1, y=1), MODE_MANUAL_REWARDS)
    evaluate_objectives([a, b], snap(x=50, y=9), MODE_MANUAL_REWARDS)
    assert b.reward_state == RW_PENDING


def test_required_mode_blocks_chain_until_reward_claimed() -> None:
    a = obj("a", leaf("x", 10), reward=Reward(money=10))
    b = obj("b", leaf("x", 1), requires=["a"])
    evaluate_objectives([a, b], snap(x=0), MODE_REQUIRED_REWARDS)
    evaluate_objectives([a, b], snap(x=20), MODE_REQUIRED_REWARDS)
    assert a.completed and b.status == ST_LOCKED
    claim_reward(a)
    evaluate_objectives([a, b], snap(x=20), MODE_REQUIRED_REWARDS)
    assert b.completed


def test_reward_none_without_money() -> None:
    o = obj("o", leaf("x", 1), reward=Reward(xp=5))
    evaluate_objectives([o], snap(x=0), MODE_MANUAL_REWARDS)
    evaluate_objectives([o], snap(x=1), MODE_MANUAL_REWARDS)
    assert o.reward_state == RW_NONE


def test_summary_and_xp_levels() -> None:
    done = obj("d", leaf("x", 1), reward=Reward(xp=60, badge="B"))
    todo = obj("t", leaf("x", 10))
    opt = obj("o", leaf("x", 100), optional=True)
    evaluate_objectives([done, todo, opt], snap(x=0))
    evaluate_objectives([done, todo, opt], snap(x=5))
    s = summarize([done, todo, opt])
    assert (s.total, s.completed, s.in_progress) == (3, 1, 2)
    assert s.xp == 60 and s.badges == ["B"]
    assert s.percent == pytest.approx((1 + 0.5) / 2 * 100)  # optional excluded
    assert level_for_xp(0) == (1, 0, 100)
    assert level_for_xp(100)[0] == 2
    assert level_for_xp(99)[0] == 1


def test_objective_roundtrip() -> None:
    o = obj("o", leaf("x", 3), reward=Reward(money=5, xp=1, badge="b"), requires=["z"])
    again = Objective.from_dict(json.loads(json.dumps(o.to_dict())))
    assert again.to_dict() == o.to_dict()
    assert again.operator == ">=" and again.target == 3


# ------------------------------------------------------------ templates + store


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_templates_are_valid(key: str) -> None:
    objs = build_template(key)
    ids = {o.id for o in objs}
    assert len(ids) == len(objs)
    for o in objs:
        assert set(o.requires) <= ids
        assert Objective.from_dict(o.to_dict()).id == o.id


def test_store_roundtrip_and_no_duplicates(tmp_path: Path) -> None:
    career = Career.load(tmp_path / "careers" / "p")
    assert career.add_objectives(build_template("eta")) == len(TEMPLATES["eta"].specs)
    assert career.add_objectives(build_template("eta")) == 0
    career.settings.savegame = "savegame1"
    career.settings.manual_stats["land.area"] = 12.0
    career.save()
    again = Career.load(tmp_path / "careers" / "p")
    assert [o.id for o in again.objectives] == [o.id for o in career.objectives]
    assert again.settings.manual_stats == {"land.area": 12.0}


def test_remove_objective_drops_dangling_requirement(tmp_path: Path) -> None:
    career = Career(directory=tmp_path)
    career.add_objectives(build_template("eta"))
    assert career.remove_objective("eta.start")
    assert all("eta.start" not in o.requires for o in career.objectives)


def test_corrupt_objective_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "objectives.json").write_text(
        json.dumps({"objectives": [{"id": "ok", "name": "ok"}, {"id": "bad"}]}),
        encoding="utf-8",
    )
    career = Career.load(tmp_path)
    assert [o.id for o in career.objectives] == ["ok"]


# ------------------------------------------------------------------------ sync


def test_sync_career_end_to_end(tmp_path: Path) -> None:
    user = tmp_path / "user"
    make_save(user)
    career = Career.load(tmp_path / "careers" / "p")
    career.settings.savegame = "savegame1"
    career.settings.mode = MODE_MANUAL_REWARDS
    career.objectives = [obj("m", leaf("money", 1_000_000), reward=Reward(money=5))]
    report = sync_career(career, user)
    assert report.ok
    assert career.snapshot.value("money") == 742000
    assert career.objectives[0].progress == pytest.approx(0.742)
    assert report.detected
    assert (career.directory / "statistics.json").is_file()
    assert career.history and career.history[-1]["values"]["money"] == 742000

    # money increases → objective completes with a pending reward, reported once
    farms = (user / "savegame1" / "farms.xml")
    farms.write_text(FARMS_XML.replace('money="742000"', 'money="1200000"'), encoding="utf-8")
    report = sync_career(career, user)
    assert [o.id for o in report.newly_completed] == ["m"]
    assert career.objectives[0].reward_state == RW_PENDING
    assert sync_career(career, user).newly_completed == []


def test_sync_reports_problems_without_raising(tmp_path: Path) -> None:
    career = Career(directory=tmp_path / "c")
    assert not sync_career(career, tmp_path).ok  # no savegame linked
    career.settings.savegame = "savegame7"
    report = sync_career(career, tmp_path)
    assert not report.ok and "introuvable" in report.message
    career.settings.mode = "off"
    assert not sync_career(career, tmp_path).ok


def test_guess_savegame_only_when_unambiguous(tmp_path: Path) -> None:
    make_save(tmp_path, "savegame1")
    assert guess_savegame("FS25_The_Combes.zip", tmp_path) == "savegame1"
    make_save(tmp_path, "savegame2")
    assert guess_savegame("FS25_The_Combes.zip", tmp_path) == ""
    assert guess_savegame(None, tmp_path) == ""


def test_format_value() -> None:
    from fsmods_gui.career.formatting import format_value

    assert format_value(742000, "€") == "742 000 €"
    assert format_value(6.4, "ha") == "6,4 ha"
    assert format_value(63.42, "ha") == "63,42 ha"
    assert format_value(None) == "—"


def test_absent_dynamic_member_is_zero_only_when_source_was_read(tmp_path: Path) -> None:
    s = extract_stats(make_save(tmp_path))
    assert s.value("crops.fields.olive") == 0  # fields.xml read, no olive field
    assert s.value("vehicles.type.truck") == 0
    assert s.value("stock.wine") == 0
    assert s.value("animals.sheep") == 0
    assert s.value("animals.dog") is None  # pets are not in the savegame
    assert s.value("animals.bred.cow") is None  # not a species member
    assert s.value("vine.area") is None
    again = StatsSnapshot.from_dict(json.loads(json.dumps(s.to_dict())))
    assert again.value("crops.fields.olive") == 0

    empty = tmp_path / "savegame8"
    empty.mkdir()
    assert extract_stats(empty).value("crops.fields.olive") is None


def test_stock_and_grapes(tmp_path: Path) -> None:
    sg = make_save(tmp_path)
    (sg / "placeables.xml").write_text(
        """<placeables><placeable filename="data/placeables/cellar.xml" farmId="1">
        <storage><fillLevel fillType="WINE" fillLevel="1500"/>
        <fillLevel fillType="WINE" fillLevel="500"/></storage></placeable></placeables>""",
        encoding="utf-8",
    )
    farms = (sg / "farms.xml").read_text(encoding="utf-8")
    (sg / "farms.xml").write_text(
        farms.replace("<customThing>", "<harvestedGrapes>1200</harvestedGrapes><customThing>"),
        encoding="utf-8",
    )
    s = extract_stats(sg)
    assert s.value("stock.wine") == 2000
    assert s.get("stock.wine").quality == Q_CALC
    assert s.value("vine.grapesHarvested") == 1200


def test_history_series_sorted_and_robust() -> None:
    from fsmods_gui.career.history import series

    history = [
        {"t": "2026-01-02T10:00:00", "values": {"money": 200}},
        {"t": "2026-01-01T10:00:00", "values": {"money": 100, "land.area": 5}},
        {"t": "garbage", "values": {"money": 1}},
        {"t": "2026-01-03T10:00:00", "values": {"land.area": 6}},
        {"values": {"money": 3}},
    ]
    assert [v for _, v in series(history, "money")] == [100.0, 200.0]
    assert [v for _, v in series(history, "land.area")] == [5.0, 6.0]
    assert series(history, "nope") == []


def test_scenarios_point_to_existing_templates() -> None:
    from fsmods_gui.career.templates import SCENARIOS

    keys = [k for _label, k in SCENARIOS if k is not None]
    assert all(k in TEMPLATES for k in keys)
    assert any(k is None for _label, k in SCENARIOS)  # "Personnalisé"
    assert {"vine", "olive"} <= set(TEMPLATES)
