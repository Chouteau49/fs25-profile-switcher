"""Présentation des objectifs en cartes : regroupement par statut et textes courts.

Pourquoi : jusqu'en 0.14, les objectifs tenaient dans un tableau de neuf colonnes
avec des emojis pour le statut, la difficulté et la récompense. La vue Objectifs
(0.15) les montre en cartes regroupées « En cours », « À commencer »,
« Terminés »… ; les textes et l'ordre se décident ici, sans Qt.
"""
from __future__ import annotations

from .formatting import format_value
from .objectives import (
    DIFFICULTY_LABELS_FR,
    RW_CLAIMED,
    RW_PENDING,
    ST_COMPLETED,
    ST_IN_PROGRESS,
    ST_LOCKED,
    ST_MANUAL,
    ST_NOT_STARTED,
    ST_UNAVAILABLE,
    Objective,
)

# (titre du groupe, statuts) dans l'ordre d'affichage.
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("En cours", (ST_IN_PROGRESS, ST_MANUAL)),
    ("À commencer", (ST_NOT_STARTED,)),
    ("Non disponibles", (ST_UNAVAILABLE,)),
    ("Terminés", (ST_COMPLETED,)),
    ("Verrouillés", (ST_LOCKED,)),
)

# Niveau de couleur d'un statut (pastille de la carte).
STATUS_LEVEL = {
    ST_IN_PROGRESS: "warn",
    ST_MANUAL: "info",
    ST_NOT_STARTED: "off",
    ST_UNAVAILABLE: "error",
    ST_COMPLETED: "ok",
    ST_LOCKED: "off",
}


def group_objectives(objectives: list[Objective]) -> list[tuple[str, list[Objective]]]:
    """Groupes non vides, dans l'ordre de :data:`GROUPS` ; l'ordre interne est conservé."""
    out: list[tuple[str, list[Objective]]] = []
    for title, statuses in GROUPS:
        items = [o for o in objectives if o.status in statuses]
        if items:
            out.append((title, items))
    return out


def progress_text(o: Objective) -> str:
    """« 86,4 / ≥ 100 ha », « combiné (3 conditions) », « à valider à la main »."""
    if o.is_leaf:
        cur = format_value(o.current_value, o.unit)
        return f"{cur} / {o.operator} {format_value(o.target, o.unit)}"
    if o.condition is not None:
        return f"combiné ({len(o.condition.leaves())} conditions)"
    return "à valider à la main"


def percent_text(o: Objective) -> str:
    return f"{o.progress * 100:.0f} %"


def reward_text(o: Objective) -> str:
    """« 50 000 € · 20 XP · badge Pionnier », ou chaîne vide sans récompense."""
    parts: list[str] = []
    if o.reward.money:
        parts.append(format_value(o.reward.money, "€"))
    if o.reward.xp:
        parts.append(f"{o.reward.xp} XP")
    if o.reward.badge:
        parts.append(f"badge {o.reward.badge}")
    return " · ".join(parts)


def reward_state_text(o: Objective) -> str:
    if o.reward_state == RW_PENDING:
        return "à verser"
    if o.reward_state == RW_CLAIMED:
        return "versée"
    return ""


def difficulty_text(level: int) -> str:
    return DIFFICULTY_LABELS_FR.get(level, "")


def subtitle(o: Objective, category_label: str, farm_label: str = "") -> str:
    """« Terres · Difficile · Ferme 2 » (les éléments vides sont omis)."""
    bits = [category_label, difficulty_text(o.difficulty), farm_label]
    if o.optional:
        bits.append("optionnel")
    return " · ".join(b for b in bits if b)
