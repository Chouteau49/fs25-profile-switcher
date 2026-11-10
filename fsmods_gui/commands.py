"""Commandes de la palette (Ctrl+K) : profils à lancer ou ouvrir, actions, mods.

Pourquoi : tout atteindre au clavier, sans chercher dans quel écran se trouve
une fonction. La liste et la recherche (tous les mots tapés doivent apparaître,
sans tenir compte des accents ni de la casse) se décident ici, sans Qt ; la
fenêtre principale exécute la commande choisie d'après sa ``key``.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

GROUP_PROFILES = "Profils"
GROUP_ACTIONS = "Actions"
GROUP_PLACES = "Aller à"
GROUP_COLLECTIONS = "Collections"
GROUP_MODS = "Mods"


@dataclass(frozen=True)
class Command:
    key: str  # « play:<slug> », « open:<slug> », « action:rescan », « mod:<fichier> »…
    group: str
    label: str
    hint: str = ""


ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("action:new_profile", "Nouveau profil", "Nom, carte, collections et carrière"),
    ("action:new_collection", "Nouvelle collection", "Regrouper des mods communs"),
    ("action:rescan", "Rescanner la bibliothèque", "Relire les zips du dossier mods"),
    ("action:export", "Exporter la configuration", "Profils, collections, carrières (ZIP)"),
    ("action:import", "Importer une configuration", "Depuis un export ZIP"),
    ("action:import_save", "Importer une partie", "Partie téléchargée (zip de sauvegarde)"),
    ("action:log", "Ouvrir le journal de l'appli", "Erreurs internes et plantages"),
    ("action:theme", "Changer de thème", "Clair, sombre ou comme Windows"),
)

PLACES: tuple[tuple[str, str], ...] = (
    ("go:home", "Accueil"),
    ("go:newmods", "Mods à ranger"),
    ("go:allmods", "Tous les mods"),
    ("go:collections", "Collections"),
    ("go:career", "Carrière"),
    ("go:diagnostic", "Diagnostic"),
    ("go:settings", "Paramètres"),
)


def build_commands(
    profiles: list[tuple[str, str, int]],
    collections: list[tuple[str, str, int]],
    mods: list[tuple[str, str]],
) -> list[Command]:
    """``profiles`` / ``collections`` : (slug, nom, nb de mods) ; ``mods`` : (fichier, titre)."""
    out: list[Command] = []
    for slug, name, count in profiles:
        out.append(Command(f"play:{slug}", GROUP_PROFILES, f"Jouer · {name}",
                           f"Activer les {count} mods et lancer FS25"))
        out.append(Command(f"open:{slug}", GROUP_PROFILES, f"Ouvrir · {name}",
                           "Page du profil"))
    out += [Command(key, GROUP_ACTIONS, label, hint) for key, label, hint in ACTIONS]
    out += [Command(key, GROUP_PLACES, label) for key, label in PLACES]
    for slug, name, count in collections:
        out.append(Command(f"collection:{slug}", GROUP_COLLECTIONS, name, f"{count} mods"))
    for filename, title in mods:
        out.append(Command(f"mod:{filename}", GROUP_MODS, title, filename))
    return out


def _fold(text: str) -> str:
    """Minuscules sans accents : « Bibliothèque » → « bibliotheque »."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search(commands: list[Command], query: str, limit: int = 40) -> list[Command]:
    """Commandes dont le libellé, l'indication ou le groupe contient tous les mots.

    Sans requête : tout sauf les mods (trop nombreux pour une liste d'accueil).
    Les mods n'apparaissent que si la recherche les cible.
    """
    words = _fold(query).split()
    if not words:
        return [c for c in commands if c.group != GROUP_MODS][:limit]
    hits = []
    for c in commands:
        haystack = _fold(f"{c.label} {c.hint} {c.group}")
        if all(w in haystack for w in words):
            starts = _fold(c.label).startswith(words[0])
            hits.append((0 if starts else 1, c))
    hits.sort(key=lambda h: h[0])  # tri stable : l'ordre des groupes est gardé
    return [c for _, c in hits][:limit]
