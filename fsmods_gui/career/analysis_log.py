"""Journal des lectures de sauvegarde : ce qui a été lu, ce qui a changé, les anomalies.

Chaque analyse laisse une trace bornée (les plus récentes), pour pouvoir expliquer
plus tard pourquoi un objectif a bougé ou pourquoi une régression a été signalée.
Pur, sans Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .regression import Regression, detect_regressions
from .stats import StatsSnapshot

ANALYSIS_LIMIT = 100


@dataclass(frozen=True)
class AnalysisEntry:
    taken_at: str
    game_version: str
    available: int  # statistiques lues avec une valeur
    total: int  # statistiques trouvées (lues ou inconnues)
    changes: dict[str, float] = field(default_factory=dict)  # key -> variation
    anomalies: list[Regression] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "takenAt": self.taken_at,
            "gameVersion": self.game_version,
            "available": self.available,
            "total": self.total,
            "changes": dict(self.changes),
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


def record_analysis(
    previous: StatsSnapshot | None,
    current: StatsSnapshot,
    *,
    game_version: str = "",
) -> AnalysisEntry:
    """Summarise one reading against the previous one (no previous: first reading)."""
    changes: dict[str, float] = {}
    anomalies: list[Regression] = []
    if previous is not None:
        for key in sorted(current.stats):
            before = previous.value(key)
            after = current.value(key)
            if before is not None and after is not None and before != after:
                changes[key] = after - before
        anomalies = detect_regressions(previous, current)
    return AnalysisEntry(
        taken_at=current.taken_at,
        game_version=game_version,
        available=sum(1 for s in current.stats.values() if s.available),
        total=len(current.stats),
        changes=changes,
        anomalies=anomalies,
    )


def append_entry(
    log: list[dict], entry: AnalysisEntry, limit: int = ANALYSIS_LIMIT
) -> list[dict]:
    """Return the log with ``entry`` appended, keeping only the ``limit`` most recent."""
    return [*log, entry.to_dict()][-limit:]
