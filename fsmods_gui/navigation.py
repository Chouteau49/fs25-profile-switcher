"""Structure de navigation de la fenêtre principale et libellés de la barre de session.

Pourquoi ce module : jusqu'en 0.10, neuf onglets au même niveau mélangeaient ce
qui dépend du profil choisi (Carrière, Audit), ce qui concerne toute la
bibliothèque (Doublons, Nouveaux mods) et ce qui concerne une session de jeu
(Log). La 0.11 regroupe ces vues en quelques espaces dans une barre latérale.
La structure et les textes sont décrits ici, sans Qt, pour être testés.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# ---- espaces (barre latérale)
SECTION_PROFILES = "profiles"
SECTION_LIBRARY = "library"
SECTION_CAREER = "career"
SECTION_DIAGNOSTIC = "diagnostic"

# ---- vues (contenu d'un espace)
FEATURE_EDITOR = "editor"
FEATURE_NEWMODS = "newmods"
FEATURE_CAREER = "career"
FEATURE_LOG = "log"
FEATURE_AUDIT = "audit"
FEATURE_DUPLICATES = "duplicates"
FEATURE_AUTODRIVE = "autodrive"
FEATURE_TESTRUNNER = "testrunner"
FEATURE_STATS = "stats"


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    icon: str


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    icon: str
    features: tuple[Feature, ...]
    tooltip: str = ""


SECTIONS: tuple[Section, ...] = (
    Section(
        SECTION_PROFILES,
        "Profils",
        "home",
        (Feature(FEATURE_EDITOR, "Éditeur", "pencil"),),
        "Le profil ou la collection choisi(e) dans la liste : carte, mods, lancement.",
    ),
    Section(
        SECTION_LIBRARY,
        "Bibliothèque",
        "library",
        (Feature(FEATURE_NEWMODS, "À ranger", "download"),),
        "Mods téléchargés ou mis à l'abri qui attendent d'être rangés.",
    ),
    Section(
        SECTION_CAREER,
        "Carrière",
        "target",
        (Feature(FEATURE_CAREER, "Carrière", "target"),),
        "Objectifs et tableau de bord du profil choisi.",
    ),
    Section(
        SECTION_DIAGNOSTIC,
        "Diagnostic",
        "activity",
        (
            Feature(FEATURE_LOG, "Log FS25", "file-text"),
            Feature(FEATURE_AUDIT, "Audit sauvegarde", "shield"),
            Feature(FEATURE_DUPLICATES, "Doublons", "copy"),
            Feature(FEATURE_AUTODRIVE, "Routes AutoDrive", "route"),
            Feature(FEATURE_TESTRUNNER, "Tester les mods", "flask"),
            Feature(FEATURE_STATS, "Statistiques", "chart"),
        ),
        "Outils de maintenance : log du jeu, audit, doublons, tests…",
    ),
)


def section(key: str) -> Section:
    for s in SECTIONS:
        if s.key == key:
            return s
    raise KeyError(key)


def section_of(feature_key: str) -> Section:
    """Espace qui contient une vue."""
    for s in SECTIONS:
        if any(f.key == feature_key for f in s.features):
            return s
    raise KeyError(feature_key)


def all_features() -> list[Feature]:
    return [f for s in SECTIONS for f in s.features]


# ---------------------------------------------------------- barre de session

GAME_CLOSED = "closed"
GAME_ACTIVATING = "activating"
GAME_RUNNING = "running"

_GAME_LABELS = {
    GAME_CLOSED: "FS25 fermé",
    GAME_ACTIVATING: "Activation en cours…",
    GAME_RUNNING: "FS25 en cours",
}
# Niveau de la pastille : « off » (neutre), « warn » (en cours), « ok » (en jeu).
_GAME_LEVELS = {GAME_CLOSED: "off", GAME_ACTIVATING: "warn", GAME_RUNNING: "ok"}


def game_label(state: str) -> str:
    return _GAME_LABELS.get(state, _GAME_LABELS[GAME_CLOSED])


def game_level(state: str) -> str:
    return _GAME_LEVELS.get(state, "off")


def active_profile_label(name: str | None) -> str:
    return f"Dans le dossier du jeu : {name}" if name else "Dans le dossier du jeu : aucun profil"


def library_label(count: int | None) -> str:
    if count is None:
        return "Bibliothèque : scan en cours…"
    return f"Bibliothèque : {count} mod" + ("s" if count > 1 else "")


def format_age(when: datetime | None, now: datetime) -> str:
    """« à l'instant », « il y a 5 min », « il y a 2 h », « le 08/11 »."""
    if when is None:
        return "jamais"
    seconds = (now - when).total_seconds()
    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {int(seconds // 60)} min"
    if seconds < 86400:
        return f"il y a {int(seconds // 3600)} h"
    return f"le {when:%d/%m}"


def backup_label(ok: bool | None, when: datetime | None, now: datetime) -> str:
    """Texte de l'état de la sauvegarde de la config dans la barre de session."""
    if ok is None:
        return "Sauvegarde de la config : non configurée"
    if not ok:
        return "Sauvegarde de la config : échec, voir l'info-bulle"
    return f"Config sauvegardée · {format_age(when, now)}"


def badge_text(count: int) -> str:
    """Pastille d'un élément de navigation (vide si rien à signaler)."""
    if count <= 0:
        return ""
    return "99+" if count > 99 else str(count)
