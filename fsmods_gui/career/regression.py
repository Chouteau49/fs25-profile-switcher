"""Détection des régressions de statistiques cumulées.

Une statistique cumulée (contrats réalisés, hectares travaillés, revenus cumulés…) ne
doit jamais baisser dans une même partie. Si elle baisse après une restauration de
sauvegarde, une modification du fichier ou un changement de ferme, on le signale comme
anomalie au lieu de considérer que le joueur a « perdu » des contrats.

Les statistiques instantanées (argent en banque, nombre de véhicules) peuvent monter
ou baisser normalement : elles ne sont jamais des régressions.

Pur, sans Qt.
"""
from __future__ import annotations

from dataclasses import dataclass

from .stats import StatsSnapshot

# Statistiques dont la valeur ne doit que croître dans une partie.
CUMULATIVE_KEYS = frozenset(
    {
        "playTime",
        "daysPlayed",
        "contracts.completed",
        "finance.income",
        "finance.expenses",
        "finance.profit",
        "finance.missionIncome",
        "commerce.woodTons",
        "vine.grapesHarvested",
        "vine.wineProduced",
        "vine.wineSold",
        "vine.revenue",
        "olive.olivesHarvested",
        "olive.oilProduced",
        "olive.oilSold",
        "olive.revenue",
    }
)
CUMULATIVE_PREFIXES = ("work.", "animals.bred.")
# Une baisse plus petite que cette part est ignorée (arrondis, relecture partielle).
TOLERANCE = 0.01


@dataclass(frozen=True)
class Regression:
    key: str
    before: float
    after: float

    def to_dict(self) -> dict:
        return {"key": self.key, "before": self.before, "after": self.after}


def is_cumulative(key: str) -> bool:
    return key in CUMULATIVE_KEYS or key.startswith(CUMULATIVE_PREFIXES)


def detect_regressions(previous: StatsSnapshot, current: StatsSnapshot) -> list[Regression]:
    """Cumulative statistics that dropped between two readings of the same career.

    An unknown value on either side proves nothing and is never reported.
    """
    out: list[Regression] = []
    for key in sorted(previous.stats):
        if not is_cumulative(key):
            continue
        before = previous.value(key)
        after = current.value(key)
        if before is None or after is None or before <= 0:
            continue
        if after < before * (1 - TOLERANCE):
            out.append(Regression(key, before, after))
    return out
