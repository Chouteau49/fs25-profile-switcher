"""Tableau de bord Diagnostic : un outil par carte, avec un état en une ligne.

Pourquoi : en 0.11, les six outils de maintenance étaient des sous-onglets sans
indication de ce qui méritait un coup d'œil. L'espace Diagnostic (0.14) les
présente en cartes avec un état coloré (« 2 erreurs dans le log de la dernière
partie », « 4 groupes de doublons »…) calculé ici, sans Qt.

Les états se calculent sur des données déjà en mémoire (catalogue, statistiques,
log) : rien de coûteux n'est lancé tant qu'on n'ouvre pas l'outil.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import navigation as nav

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_INFO = "info"


@dataclass(frozen=True)
class ToolCard:
    key: str  # vue de navigation.py
    title: str
    description: str
    icon: str


TOOLS: tuple[ToolCard, ...] = (
    ToolCard(
        nav.FEATURE_LOG,
        "Log FS25",
        "Analyse le log.txt de la dernière partie : mods en erreur, scripts manquants.",
        "file-text",
    ),
    ToolCard(
        nav.FEATURE_AUDIT,
        "Audit de sauvegarde",
        "Compare les mods utilisés par la sauvegarde avec ceux du profil choisi.",
        "shield",
    ),
    ToolCard(
        nav.FEATURE_DUPLICATES,
        "Doublons",
        "Même mod présent sous plusieurs noms ou plusieurs versions.",
        "copy",
    ),
    ToolCard(
        nav.FEATURE_AUTODRIVE,
        "Routes AutoDrive",
        "Sauvegarde et réinstallation des réseaux de routes AutoDrive.",
        "route",
    ),
    ToolCard(
        nav.FEATURE_TESTRUNNER,
        "Tester les mods",
        "Charge chaque mod dans le jeu pour repérer ceux qui plantent.",
        "flask",
    ),
    ToolCard(
        nav.FEATURE_STATS,
        "Statistiques",
        "Taille, catégories, marques et mods qui ne servent à aucun profil.",
        "chart",
    ),
)


@dataclass(frozen=True)
class Status:
    level: str
    text: str


def log_status(errors: int | None, warnings: int | None) -> Status:
    """État du log FS25. ``None`` = pas de log trouvé (jeu jamais lancé ici)."""
    if errors is None or warnings is None:
        return Status(LEVEL_INFO, "Aucun log de partie trouvé")
    if errors == 0 and warnings == 0:
        return Status(LEVEL_OK, "Dernière partie : aucun problème")
    parts = []
    if errors:
        parts.append(f"{errors} erreur" + ("s" if errors > 1 else ""))
    if warnings:
        parts.append(f"{warnings} avertissement" + ("s" if warnings > 1 else ""))
    return Status(LEVEL_WARN if errors else LEVEL_INFO, "Dernière partie : " + ", ".join(parts))


def duplicates_status(groups: int | None, files: int = 0) -> Status:
    if groups is None:
        return Status(LEVEL_INFO, "Scan de la bibliothèque en cours…")
    if groups == 0:
        return Status(LEVEL_OK, "Aucun doublon")
    return Status(
        LEVEL_WARN,
        f"{groups} groupe" + ("s" if groups > 1 else "") + f" ({files} fichiers)",
    )


def stats_status(total: int | None, orphans: int) -> Status:
    if not total:
        return Status(LEVEL_INFO, "Scan de la bibliothèque en cours…" if total is None
                      else "Bibliothèque vide")
    if orphans == 0:
        return Status(LEVEL_OK, f"{total} mods, tous utilisés")
    pct = round(orphans * 100 / total)
    return Status(LEVEL_INFO, f"{orphans} mods sur {total} ({pct} %) ne servent à aucun profil")


def audit_status(profile_name: str | None) -> Status:
    if not profile_name:
        return Status(LEVEL_INFO, "Choisis un profil dans la liste")
    return Status(LEVEL_INFO, f"Profil : {profile_name}")


def generic_status(text: str) -> Status:
    return Status(LEVEL_INFO, text)
