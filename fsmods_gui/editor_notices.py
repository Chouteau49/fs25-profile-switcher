"""Encadrés d'information de la page Profil (dépendances, mods absents).

Pourquoi : avant 0.13, ajouter un mod qui en exige d'autres ouvrait une fenêtre
« Dépendances requises » (Oui / Non), puis une autre pour les dépendances
introuvables. Ces informations deviennent des encadrés dans la page, avec un
bouton d'action, qui n'interrompent pas l'ajout. Le texte et l'action se
décident ici, sans Qt.
"""
from __future__ import annotations

from dataclasses import dataclass

from .profiles.dependencies import DependencyResolution

KIND_INFO = "info"
KIND_ERROR = "error"

ACTION_ADD = "add"  # ajouter les fichiers au profil
ACTION_REMOVE = "remove"  # retirer les fichiers du profil


@dataclass(frozen=True)
class Notice:
    kind: str
    text: str
    action: str | None = None
    action_label: str = ""
    filenames: tuple[str, ...] = ()


def _list(names: list[str], limit: int = 3) -> str:
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return f"{shown} et {extra} autre(s)" if extra > 0 else shown


def dependency_notices(
    res: DependencyResolution, titles: dict[str, str], added_titles: list[str]
) -> list[Notice]:
    """Encadrés après l'ajout de mods : dépendances à ajouter, dépendances introuvables."""
    notices: list[Notice] = []
    who = _list(added_titles) if added_titles else "Ce mod"
    plural = len(added_titles) > 1
    if res.to_add:
        names = [titles.get(f, f) for f in res.to_add]
        notices.append(
            Notice(
                KIND_INFO,
                f"{who} {'ont' if plural else 'a'} besoin de {_list(names)}, "
                "présent(s) dans ta bibliothèque.",
                ACTION_ADD,
                "Ajouter aussi",
                tuple(res.to_add),
            )
        )
    if res.missing:
        notices.append(
            Notice(
                KIND_ERROR,
                f"{who} {'ont' if plural else 'a'} besoin de {_list(res.missing)}, "
                "absent(s) de la bibliothèque : télécharge-les puis rescanne.",
            )
        )
    return notices


def missing_notice(missing: list[str]) -> Notice | None:
    """Encadré des mods du profil introuvables dans la bibliothèque."""
    if not missing:
        return None
    n = len(missing)
    head = "1 mod du profil est absent" if n == 1 else f"{n} mods du profil sont absents"
    return Notice(
        KIND_ERROR,
        f"{head} de la bibliothèque : {_list(missing)}. "
        "Ils seront ignorés au lancement.",
        ACTION_REMOVE,
        "Retirer du profil",
        tuple(missing),
    )
