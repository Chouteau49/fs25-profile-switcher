"""French-style number formatting and parsing for career values."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .stats import Stat


def format_value(value: float | None, unit: str = "") -> str:
    """``742000`` → ``742 000``, ``6.4`` → ``6,4``; ``None`` → ``—``."""
    if value is None:
        return "—"
    text = f"{value:,.0f}" if abs(value - round(value)) < 1e-9 else f"{value:,.2f}".rstrip("0")
    text = text.replace(",", " ").replace(".", ",")
    return f"{text} {unit}".strip()


def format_stat(stat: Stat) -> str:
    """A statistic for display; an incomplete one shows its known minimum (``≥ 8,5 ha``)."""
    if stat.value is None and stat.partial is not None:
        return f"≥ {format_value(stat.partial, stat.unit)}"
    return format_value(stat.value, stat.unit)


def parse_area(text: str) -> float | None:
    """Area typed by the player: ``2,05``, ``2.05``, ``2,05 ha`` or ``1 234,5``.

    Blank means "not known yet" (``None``), which is different from ``0``. Raises
    ``ValueError`` on anything else, so a typo is reported rather than dropped.
    """
    cleaned = "".join(text.lower().split()).removesuffix("ha").replace(",", ".")
    if not cleaned:
        return None
    value = float(cleaned)
    if value < 0 or not math.isfinite(value):
        raise ValueError(f"Surface invalide : {text!r}")
    return value
