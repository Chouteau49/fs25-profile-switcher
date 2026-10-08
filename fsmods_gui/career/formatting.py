"""French-style number formatting for career values."""
from __future__ import annotations


def format_value(value: float | None, unit: str = "") -> str:
    """``742000`` → ``742 000``, ``6.4`` → ``6,4``; ``None`` → ``—``."""
    if value is None:
        return "—"
    text = f"{value:,.0f}" if abs(value - round(value)) < 1e-9 else f"{value:,.2f}".rstrip("0")
    text = text.replace(",", " ").replace(".", ",")
    return f"{text} {unit}".strip()
