"""Time series extracted from the career history (for charts)."""
from __future__ import annotations

from datetime import datetime

# (statistic key, label, unit) offered in the history chart.
CHART_SERIES: tuple[tuple[str, str, str], ...] = (
    ("netWorth", "Patrimoine estimé", "€"),
    ("money", "Argent", "€"),
    ("finance.income", "Revenus cumulés", "€"),
    ("land.area", "Surface possédée", "ha"),
    ("land.count", "Parcelles", ""),
    ("animals.total", "Animaux", ""),
    ("vehicles.count", "Véhicules", ""),
    ("contracts.completed", "Contrats réalisés", ""),
    ("productions.count", "Productions", ""),
)


def series(
    history: list[dict], key: str, farm: str | None = None
) -> list[tuple[datetime, float]]:
    """Chronological ``(time, value)`` points for one statistic; bad entries are skipped.

    With ``farm``, entries of the other farms are left out. Entries older than 0.8.1
    name no farm: they cannot be attributed, so they stay visible.
    """
    points: list[tuple[datetime, float]] = []
    for entry in history:
        if farm is not None and entry.get("farm", farm) != farm:
            continue
        values = entry.get("values")
        if not isinstance(values, dict) or not isinstance(values.get(key), int | float):
            continue
        try:
            when = datetime.fromisoformat(str(entry.get("t", "")))
        except ValueError:
            continue
        points.append((when, float(values[key])))
    points.sort(key=lambda p: p[0])
    return points
