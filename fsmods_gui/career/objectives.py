"""Generic rule engine for career objectives.

An objective is a *condition tree* evaluated against a :class:`StatsSnapshot`:

* a leaf compares one statistic with a target (``stat operator target``);
* ``and`` / ``or`` / ``not`` groups combine children.

Adding a new kind of objective means adding data (a stat key + operator +
target), never a new branch of code. Evaluation is tri-state: when a needed
statistic is unavailable the objective is *unavailable*, never silently 0.

Pure logic, no Qt.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from .stats import StatsSnapshot

OPERATORS = (">=", ">", "<=", "<", "==")

# ---- objective status
ST_LOCKED = "locked"            # a prerequisite is not completed yet
ST_NOT_STARTED = "not_started"
ST_IN_PROGRESS = "in_progress"
ST_COMPLETED = "completed"
ST_UNAVAILABLE = "unavailable"  # a needed statistic cannot be read
ST_MANUAL = "manual"            # waiting for the player to validate it

STATUS_LABELS_FR = {
    ST_LOCKED: "🔒 Verrouillé",
    ST_NOT_STARTED: "⚪ Non commencé",
    ST_IN_PROGRESS: "🟠 En cours",
    ST_COMPLETED: "🟢 Terminé",
    ST_UNAVAILABLE: "🔴 Non disponible",
    ST_MANUAL: "🔵 À valider",
}

# ---- reward state (a money reward is never applied twice)
RW_NONE = "none"        # no reward on this objective
RW_PENDING = "pending"  # earned, waiting for the player to apply it
RW_CLAIMED = "claimed"
RW_WAIVED = "waived"    # nothing due (already satisfied at start, or rewards off)

# ---- career modes
MODE_OFF = "off"
MODE_OBJECTIVES = "objectives"
MODE_MANUAL_REWARDS = "manual_rewards"
MODE_REQUIRED_REWARDS = "required_rewards"

MODE_LABELS_FR = {
    MODE_OFF: "⚪ Désactivé",
    MODE_OBJECTIVES: "🟢 Objectifs uniquement",
    MODE_MANUAL_REWARDS: "🟡 Objectifs + récompenses manuelles",
    MODE_REQUIRED_REWARDS: "🔴 Objectifs + récompenses obligatoires",
}

DIFFICULTY_LABELS_FR = {
    1: "⭐ Facile",
    2: "⭐⭐ Normal",
    3: "⭐⭐⭐ Difficile",
    4: "⭐⭐⭐⭐ Expert",
    5: "⭐⭐⭐⭐⭐ Légendaire",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rewards_enabled(mode: str) -> bool:
    return mode in (MODE_MANUAL_REWARDS, MODE_REQUIRED_REWARDS)


class ObjectiveError(ValueError):
    """Raised on malformed objective data."""


# ------------------------------------------------------------------ conditions


@dataclass
class Condition:
    """Leaf (``op == "leaf"``) or group (``op`` in ``and`` / ``or`` / ``not``)."""

    stat: str = ""
    operator: str = ">="
    target: float = 0.0
    unit: str = ""
    op: str = "leaf"
    children: list[Condition] = field(default_factory=list)

    def to_dict(self) -> dict:
        if self.op == "leaf":
            return {
                "stat": self.stat,
                "operator": self.operator,
                "target": self.target,
                "unit": self.unit,
            }
        return {"op": self.op, "children": [c.to_dict() for c in self.children]}

    @classmethod
    def from_dict(cls, data: dict) -> Condition:
        if not isinstance(data, dict):
            raise ObjectiveError("Condition must be an object.")
        op = data.get("op", "leaf")
        if op == "leaf":
            operator = data.get("operator", ">=")
            if operator not in OPERATORS:
                raise ObjectiveError(f"Unknown operator {operator!r}.")
            stat = data.get("stat")
            if not isinstance(stat, str) or not stat:
                raise ObjectiveError("Leaf condition needs a 'stat'.")
            try:
                target = float(data.get("target", 0))
            except (TypeError, ValueError) as exc:
                raise ObjectiveError("Condition 'target' must be a number.") from exc
            return cls(stat=stat, operator=operator, target=target, unit=str(data.get("unit", "")))
        if op not in ("and", "or", "not"):
            raise ObjectiveError(f"Unknown group operator {op!r}.")
        children = [cls.from_dict(c) for c in data.get("children", [])]
        if not children:
            raise ObjectiveError("A group needs at least one child.")
        if op == "not" and len(children) != 1:
            raise ObjectiveError("'not' needs exactly one child.")
        return cls(op=op, children=children)

    def leaves(self) -> list[Condition]:
        if self.op == "leaf":
            return [self]
        return [leaf for child in self.children for leaf in child.leaves()]


@dataclass
class Evaluation:
    """Result of evaluating a condition: tri-state ``satisfied`` + progress 0..1."""

    satisfied: bool | None
    progress: float
    current: float | None = None


def _leaf_satisfied(cur: float, operator: str, target: float) -> bool:
    return {
        ">=": cur >= target,
        ">": cur > target,
        "<=": cur <= target,
        "<": cur < target,
        "==": math.isclose(cur, target, abs_tol=1e-9),
    }[operator]


def _leaf_progress(cur: float, operator: str, target: float, satisfied: bool) -> float:
    if satisfied:
        return 1.0
    if operator in (">=", ">"):
        return max(0.0, min(cur / target, 1.0)) if target > 0 else 0.0
    if operator in ("<=", "<"):
        return max(0.0, min(target / cur, 1.0)) if cur > 0 and target > 0 else 0.0
    return 0.0


def evaluate(cond: Condition, snapshot: StatsSnapshot) -> Evaluation:
    if cond.op == "leaf":
        cur = snapshot.value(cond.stat)
        if cur is None:
            return Evaluation(None, 0.0, None)
        ok = _leaf_satisfied(cur, cond.operator, cond.target)
        return Evaluation(ok, _leaf_progress(cur, cond.operator, cond.target, ok), cur)

    results = [evaluate(c, snapshot) for c in cond.children]
    if cond.op == "not":
        inner = results[0]
        if inner.satisfied is None:
            return Evaluation(None, 0.0, inner.current)
        return Evaluation(not inner.satisfied, 0.0 if inner.satisfied else 1.0, inner.current)

    states = [r.satisfied for r in results]
    progresses = [r.progress for r in results]
    if cond.op == "and":
        if any(s is False for s in states):
            satisfied: bool | None = False
        elif all(s is True for s in states):
            satisfied = True
        else:
            satisfied = None
        progress = sum(progresses) / len(progresses)
    else:  # or
        if any(s is True for s in states):
            satisfied = True
        elif all(s is False for s in states):
            satisfied = False
        else:
            satisfied = None
        progress = max(progresses)
    if satisfied is True:
        progress = 1.0
    return Evaluation(satisfied, progress, results[0].current)


# ------------------------------------------------------------------- objective


@dataclass
class Reward:
    money: int = 0
    xp: int = 0
    badge: str = ""

    @property
    def empty(self) -> bool:
        return not (self.money or self.xp or self.badge)

    def to_dict(self) -> dict:
        return {"money": self.money, "xp": self.xp, "badge": self.badge}

    @classmethod
    def from_dict(cls, data: dict | None) -> Reward:
        if not isinstance(data, dict):
            return cls()
        try:
            return cls(
                money=max(0, int(data.get("money", 0))),
                xp=max(0, int(data.get("xp", 0))),
                badge=str(data.get("badge", "")),
            )
        except (TypeError, ValueError) as exc:
            raise ObjectiveError("Reward amounts must be integers.") from exc


@dataclass
class Objective:
    id: str
    name: str
    category: str = "general"
    description: str = ""
    condition: Condition | None = None  # None => manual (validated by the player)
    difficulty: int = 2
    priority: int = 0
    optional: bool = False
    hidden: bool = False
    requires: list[str] = field(default_factory=list)
    reward: Reward = field(default_factory=Reward)
    # Farm whose statistics the objective measures ("" = the career's tracked farm).
    farm: str = ""
    template: str = ""
    created_at: str = ""
    completed_at: str | None = None
    # computed on every sync, persisted so the UI works offline
    status: str = ST_NOT_STARTED
    progress: float = 0.0
    current_value: float | None = None
    evaluated: bool = False
    reward_state: str = RW_NONE
    reward_claimed_at: str | None = None

    @property
    def type(self) -> str:
        if self.condition is None:
            return "manual"
        return "numeric" if self.condition.op == "leaf" else "combined"

    @property
    def is_leaf(self) -> bool:
        return self.condition is not None and self.condition.op == "leaf"

    @property
    def operator(self) -> str:
        return self.condition.operator if self.condition and self.is_leaf else ""

    @property
    def target(self) -> float | None:
        return self.condition.target if self.condition and self.is_leaf else None

    @property
    def unit(self) -> str:
        return self.condition.unit if self.condition and self.is_leaf else ""

    @property
    def completed(self) -> bool:
        return self.status == ST_COMPLETED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "type": self.type,
            "condition": self.condition.to_dict() if self.condition else None,
            "operator": self.operator,
            "target": self.target,
            "unit": self.unit,
            "currentValue": self.current_value,
            "progress": round(self.progress, 4),
            "status": self.status,
            "priority": self.priority,
            "difficulty": self.difficulty,
            "optional": self.optional,
            "hidden": self.hidden,
            "requires": list(self.requires),
            "farm": self.farm,
            "reward": self.reward.to_dict(),
            "rewardState": self.reward_state,
            "rewardClaimedAt": self.reward_claimed_at,
            "template": self.template,
            "createdAt": self.created_at,
            "completedAt": self.completed_at,
            "evaluated": self.evaluated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Objective:
        if not isinstance(data, dict):
            raise ObjectiveError("Objective must be an object.")
        oid = data.get("id")
        name = data.get("name")
        if not isinstance(oid, str) or not oid:
            raise ObjectiveError("Objective needs an 'id'.")
        if not isinstance(name, str) or not name.strip():
            raise ObjectiveError(f"Objective {oid!r} needs a 'name'.")
        raw_cond = data.get("condition")
        status = data.get("status", ST_NOT_STARTED)
        if status not in STATUS_LABELS_FR:
            status = ST_NOT_STARTED
        try:
            difficulty = min(5, max(1, int(data.get("difficulty", 2))))
            priority = int(data.get("priority", 0))
            progress = float(data.get("progress", 0.0))
        except (TypeError, ValueError) as exc:
            raise ObjectiveError(f"Objective {oid!r}: invalid number.") from exc
        current = data.get("currentValue")
        reward_state = data.get("rewardState", RW_NONE)
        if reward_state not in (RW_NONE, RW_PENDING, RW_CLAIMED, RW_WAIVED):
            reward_state = RW_NONE
        return cls(
            id=oid,
            name=name,
            category=str(data.get("category", "general")),
            description=str(data.get("description", "")),
            condition=Condition.from_dict(raw_cond) if raw_cond else None,
            difficulty=difficulty,
            priority=priority,
            optional=bool(data.get("optional", False)),
            hidden=bool(data.get("hidden", False)),
            requires=[str(r) for r in data.get("requires", [])],
            reward=Reward.from_dict(data.get("reward")),
            farm=str(data.get("farm") or ""),
            template=str(data.get("template", "")),
            created_at=str(data.get("createdAt", "")),
            completed_at=data.get("completedAt"),
            status=status,
            progress=progress,
            current_value=float(current) if isinstance(current, int | float) else None,
            evaluated=bool(data.get("evaluated", False)),
            reward_state=reward_state,
            reward_claimed_at=data.get("rewardClaimedAt"),
        )


# --------------------------------------------------------------------- engine


@dataclass
class EvaluationResult:
    newly_completed: list[Objective] = field(default_factory=list)
    newly_unlocked: list[Objective] = field(default_factory=list)


def _prerequisite_met(dep: Objective, mode: str) -> bool:
    if not dep.completed:
        return False
    # "Required rewards" mode: the chain only advances once the reward was applied.
    return not (mode == MODE_REQUIRED_REWARDS and dep.reward_state == RW_PENDING)


def evaluate_objectives(
    objectives: list[Objective],
    snapshot: StatsSnapshot,
    mode: str = MODE_OBJECTIVES,
    farm_snapshots: Mapping[str, StatsSnapshot] | None = None,
) -> EvaluationResult:
    """Recompute status/progress of every objective in place.

    An objective bound to a farm (``obj.farm``) is measured on that farm's snapshot
    from ``farm_snapshots``; a missing snapshot means "unavailable", never 0. The
    others use ``snapshot`` (the career's tracked farm).

    Completion is sticky: once completed an objective stays completed (a later
    drop of a statistic does not take it back). Objectives already satisfied the
    first time they are evaluated are completed without a due reward (they were
    not earned during the career). Prerequisite chains can complete in a single
    call.
    """
    result = EvaluationResult()
    by_id = {o.id: o for o in objectives}
    previously_locked = {o.id for o in objectives if o.status == ST_LOCKED}

    for _ in range(len(objectives) + 1):
        changed = False
        for obj in objectives:
            if obj.completed:
                continue
            source = snapshot
            if obj.farm:
                source = (farm_snapshots or {}).get(obj.farm) or StatsSnapshot()
            ev = evaluate(obj.condition, source) if obj.condition else None
            if ev is not None:
                obj.progress = ev.progress
                obj.current_value = ev.current

            deps = [by_id[r] for r in obj.requires if r in by_id]
            if any(not _prerequisite_met(d, mode) for d in deps):
                obj.status = ST_LOCKED
                _mark_first_sight(obj, ev)
                continue

            if ev is None:
                obj.status = ST_MANUAL
            elif ev.satisfied is True:
                _complete(obj, mode, result)
                changed = True
            elif ev.satisfied is None:
                obj.status = ST_UNAVAILABLE
            else:
                obj.status = ST_IN_PROGRESS if ev.progress > 0 else ST_NOT_STARTED
            _mark_first_sight(obj, ev)
        if not changed:
            break

    result.newly_unlocked = [
        o for o in objectives if o.id in previously_locked and o.status != ST_LOCKED
    ]
    return result


def _mark_first_sight(obj: Objective, ev: Evaluation | None) -> None:
    """Remember whether the objective was already satisfied when first evaluated.

    Such an objective was not earned during the career, so its reward is waived
    (stored as ``RW_WAIVED`` until completion sets the final state).
    """
    if not obj.evaluated and ev is not None and ev.satisfied is True:
        obj.reward_state = RW_WAIVED
    obj.evaluated = True


def _complete(obj: Objective, mode: str, result: EvaluationResult) -> None:
    earned = obj.evaluated and obj.reward_state != RW_WAIVED
    obj.status = ST_COMPLETED
    obj.progress = 1.0
    obj.completed_at = obj.completed_at or now_iso()
    obj.evaluated = True
    _set_reward_state(obj, mode, due=earned)
    if earned:
        result.newly_completed.append(obj)


def _set_reward_state(obj: Objective, mode: str, *, due: bool) -> None:
    if obj.reward.money <= 0:
        obj.reward_state = RW_NONE
    elif due and rewards_enabled(mode):
        obj.reward_state = RW_PENDING
    else:
        obj.reward_state = RW_WAIVED


def complete_manually(obj: Objective, mode: str) -> bool:
    """Player validates a manual objective. False if it is locked, done or automatic."""
    if obj.condition is not None or obj.completed or obj.status == ST_LOCKED:
        return False
    obj.status = ST_COMPLETED
    obj.progress = 1.0
    obj.completed_at = now_iso()
    obj.evaluated = True
    _set_reward_state(obj, mode, due=True)
    return True


def claim_reward(obj: Objective) -> bool:
    """Mark a pending money reward as applied. Idempotent: never applies twice."""
    if obj.reward_state != RW_PENDING:
        return False
    obj.reward_state = RW_CLAIMED
    obj.reward_claimed_at = now_iso()
    return True


# --------------------------------------------------------------- xp / summary


def level_for_xp(xp: int) -> tuple[int, int, int]:
    """Return ``(level, xp_into_level, xp_for_next_level)``; level n starts at 50·n·(n−1) XP."""
    level = 1
    while xp >= 50 * (level + 1) * level:
        level += 1
    floor_xp = 50 * level * (level - 1)
    next_xp = 50 * (level + 1) * level
    return level, xp - floor_xp, next_xp - floor_xp


@dataclass
class CareerSummary:
    total: int = 0
    completed: int = 0
    in_progress: int = 0
    not_started: int = 0
    locked: int = 0
    unavailable: int = 0
    manual: int = 0
    percent: float = 0.0
    xp: int = 0
    badges: list[str] = field(default_factory=list)
    money_pending: int = 0
    money_claimed: int = 0


def summarize(objectives: list[Objective]) -> CareerSummary:
    """Aggregate career progress. Optional objectives don't weigh in the percentage."""
    s = CareerSummary()
    counted = [o for o in objectives if not o.optional]
    for o in objectives:
        s.total += 1
        if o.status == ST_COMPLETED:
            s.completed += 1
            s.xp += o.reward.xp
            if o.reward.badge:
                s.badges.append(o.reward.badge)
            if o.reward_state == RW_PENDING:
                s.money_pending += o.reward.money
            elif o.reward_state == RW_CLAIMED:
                s.money_claimed += o.reward.money
        elif o.status == ST_IN_PROGRESS:
            s.in_progress += 1
        elif o.status == ST_LOCKED:
            s.locked += 1
        elif o.status == ST_UNAVAILABLE:
            s.unavailable += 1
        elif o.status == ST_MANUAL:
            s.manual += 1
        else:
            s.not_started += 1
    if counted:
        s.percent = sum(1.0 if o.completed else o.progress for o in counted) / len(counted) * 100
    return s
