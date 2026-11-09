"""Points de contrôle, objectifs de période et point de départ.

Trois besoins qui reposent sur la même idée : mesurer une *différence* entre deux
moments plutôt que la valeur totale.

* **Période** (saison, mois) : progression entre deux :class:`Checkpoint`. Seules les
  statistiques cumulées ont une progression de période fiable ; une valeur
  instantanée (argent en banque) est refusée, car « gagner 100 000 € » n'a pas de sens
  sur un solde.
* **Point de départ** : un scénario lancé en cours de partie ne compte que ce qui se
  passe après son activation. :func:`capture_baseline` fige les valeurs cumulées au
  moment de l'activation ; le moteur soustrait ensuite cette base.

Pur, sans Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .objectives import (
    Condition,
    Evaluation,
    _leaf_progress,
    _leaf_satisfied,
)
from .regression import is_cumulative
from .stats import StatsSnapshot


@dataclass(frozen=True)
class Checkpoint:
    """Valeurs disponibles d'une sauvegarde à un instant donné (les inconnues sont omises)."""

    taken_at: str
    values: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"takenAt": self.taken_at, "values": dict(self.values)}

    @classmethod
    def from_dict(cls, data: dict) -> Checkpoint:
        if not isinstance(data, dict):
            return cls(taken_at="")
        raw = data.get("values", {})
        values = (
            {str(k): float(v) for k, v in raw.items() if isinstance(v, int | float)}
            if isinstance(raw, dict)
            else {}
        )
        return cls(taken_at=str(data.get("takenAt", "")), values=values)


def checkpoint(snapshot: StatsSnapshot) -> Checkpoint:
    values = {k: s.value for k, s in snapshot.stats.items() if s.value is not None}
    return Checkpoint(taken_at=snapshot.taken_at, values=values)


def period_gain(start: Checkpoint, end: Checkpoint, key: str) -> float | None:
    """Progression of a cumulative statistic between two checkpoints.

    None when the statistic is not cumulative, unknown at either end, or went down
    (a regression is not a progression).
    """
    if not is_cumulative(key):
        return None
    before = start.values.get(key)
    after = end.values.get(key)
    if before is None or after is None or after < before:
        return None
    return after - before


def evaluate_period(cond: Condition, start: Checkpoint, end: Checkpoint) -> Evaluation:
    """Evaluate a single-statistic condition on the gain of a period."""
    if cond.op != "leaf":
        raise ValueError("Un objectif de période porte sur une seule statistique.")
    gain = period_gain(start, end, cond.stat)
    if gain is None:
        return Evaluation(None, 0.0, None)
    ok = _leaf_satisfied(gain, cond.operator, cond.target)
    return Evaluation(ok, _leaf_progress(gain, cond.operator, cond.target, ok), gain)


def baseline_for(condition: Condition, snapshot: StatsSnapshot) -> tuple[dict[str, float], list[str]]:
    """Baseline of an objective, plus the cumulative statistics it could not be frozen on.

    A missing cumulative statistic must not be read as 0: the objective then cannot be
    measured from activation at all.
    """
    base = capture_baseline(condition, snapshot)
    missing = [
        leaf.stat for leaf in condition.leaves() if is_cumulative(leaf.stat) and leaf.stat not in base
    ]
    return base, missing


def capture_baseline(condition: Condition, snapshot: StatsSnapshot) -> dict[str, float]:
    """Freeze the cumulative values an objective measures, at activation time.

    Instantaneous statistics are not frozen: subtracting an old balance is meaningless.
    """
    base: dict[str, float] = {}
    for leaf in condition.leaves():
        if not is_cumulative(leaf.stat):
            continue
        value = snapshot.value(leaf.stat)
        if value is not None:
            base[leaf.stat] = value
    return base
