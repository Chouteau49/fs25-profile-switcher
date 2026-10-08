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


def series(history: list[dict], key: str) -> list[tuple[datetime, float]]:
    """Chronological ``(time, value)`` points for one statistic; bad entries are skipped."""
    points: list[tuple[datetime, float]] = []
    for entry in history:
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
