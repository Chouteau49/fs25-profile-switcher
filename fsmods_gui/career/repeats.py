"""Objectifs répétables : un objectif numérique découpé en paliers.

« Récolter 100 ha, puis tous les 100 ha supplémentaires » devient les paliers 100, 200,
300… ha. Chaque palier est un objectif ordinaire avec son propre identifiant
(``<id>#<k>``) : donc sa propre récompense, son propre état et aucun double versement.
Le moteur de règles ne change pas : les paliers sont simplement chaînés par ``requires``.

Pur, sans Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .objectives import (
    RW_NONE,
    ST_COMPLETED,
    ST_NOT_STARTED,
    Condition,
    Objective,
    ObjectiveError,
)


def _check_repeatable(base: Objective, step: float) -> Condition:
    if base.condition is None or not base.is_leaf:
        raise ObjectiveError("Seul un objectif numérique peut être répétable.")
    if base.operator not in (">=", ">"):
        raise ObjectiveError("Un objectif répétable doit viser une hausse (>= ou >).")
    if step <= 0:
        raise ObjectiveError("Le pas de répétition doit être positif.")
    return base.condition


def occurrence(
    base: Objective, step: float, k: int, previous_id: str | None = None
) -> Objective:
    """Palier ``k`` (1-based) : cible ``step * k``, validé une seule fois."""
    cond = _check_repeatable(base, step)
    if k < 1:
        raise ObjectiveError("Le numéro de palier commence à 1.")
    requires = list(base.requires) if previous_id is None else [previous_id]
    return replace(
        base,
        id=f"{base.id}#{k}",
        name=f"{base.name} — palier {k}",
        condition=Condition(
            stat=cond.stat, operator=base.operator, target=step * k, unit=base.unit
        ),
        requires=requires,
        reward=replace(base.reward),
        baseline=dict(base.baseline),
        status=ST_NOT_STARTED,
        progress=0.0,
        current_value=None,
        evaluated=False,
        reward_state=RW_NONE,
        completed_at=None,
        reward_claimed_at=None,
        record_value=None,
        record_at=None,
    )


def build_occurrences(base: Objective, step: float, count: int) -> list[Objective]:
    """The first ``count`` paliers, each one requiring the previous one."""
    if count < 1:
        raise ObjectiveError("Il faut au moins un palier.")
    out: list[Objective] = []
    previous: str | None = None
    for k in range(1, count + 1):
        item = occurrence(base, step, k, previous)
        out.append(item)
        previous = item.id
    return out


def completed_occurrences(objectives: list[Objective], base_id: str) -> int:
    prefix = f"{base_id}#"
    return sum(1 for o in objectives if o.id.startswith(prefix) and o.status == ST_COMPLETED)


@dataclass(frozen=True)
class RepeatSpec:
    """One repeatable family: a palier every ``step`` units, ``count`` paliers offered."""

    key: str  # identifiant : rep.<key>
    name: str
    category: str
    stat: str
    unit: str
    step: float
    count: int


# Valeurs validées par Julien : revenus des contrats par 50 k€, heures de jeu par 4 h,
# surface par 5 ha. Les autres pas sont des propositions à ajuster.
REPEATABLE_SPECS: tuple[RepeatSpec, ...] = (
    RepeatSpec("contracts", "Réaliser des contrats", "eta",
               "contracts.completed", "", 10, 10),
    RepeatSpec("missionIncome", "Gagner des revenus de contrats", "eta",
               "finance.missionIncome", "€", 50_000, 20),
    RepeatSpec("playTime", "Jouer", "time", "playTime", "h", 4, 250),
    RepeatSpec("animals", "Posséder des animaux", "animals", "animals.total", "", 50, 10),
    RepeatSpec("vehicles", "Posséder des véhicules", "equipment",
               "vehicles.count", "", 5, 10),
    RepeatSpec("land", "Posséder des hectares", "land", "land.area", "ha", 5, 100),
    RepeatSpec("netWorth", "Patrimoine estimé", "finance", "netWorth", "€", 1_000_000, 10),
)


def repeatable_objectives(farm: str = "") -> list[Objective]:
    """Every palier of the repeatable catalogue, optionally bound to one farm."""
    suffix = f"@{farm}" if farm else ""
    out: list[Objective] = []
    for spec in REPEATABLE_SPECS:
        base = Objective(
            id=f"rep.{spec.key}{suffix}",
            name=spec.name,
            category=spec.category,
            description=f"Un palier tous les {spec.step:,.0f} {spec.unit}".rstrip(),
            condition=Condition(stat=spec.stat, operator=">=", target=spec.step, unit=spec.unit),
            farm=farm,
            template="repeatable",
        )
        out.extend(build_occurrences(base, spec.step, spec.count))
    return out
