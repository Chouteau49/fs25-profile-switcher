"""Données de l'écran d'accueil : une carte par profil, prête à afficher.

Pourquoi un module pur : l'accueil (0.12) remplace la liste de profils comme
point d'entrée. Ce qu'une carte affiche (carte du jeu, nombre de mods, date de
dernière partie, ordre des profils) se calcule sans Qt et se teste ici ; le
widget ``widgets/home_page.py`` ne fait que dessiner.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from .profiles.official_maps import OFFICIAL_MAPS
from .profiles.profile import Profile


@dataclass(frozen=True)
class ProfileCard:
    slug: str
    name: str
    map_label: str
    mods_count: int
    collections_count: int
    last_played_label: str
    is_last_played: bool

    @property
    def mods_label(self) -> str:
        return f"{self.mods_count} mod" + ("s" if self.mods_count > 1 else "")

    @property
    def collections_label(self) -> str:
        n = self.collections_count
        if n == 0:
            return "aucune collection"
        return f"{n} collection" + ("s" if n > 1 else "")


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None  # valeur illisible = « jamais », pas d'exception jusqu'à l'UI


def last_played_label(iso: str | None, now: datetime) -> str:
    """« aujourd'hui, 21:40 », « hier, 21:40 », « il y a 4 jours », « le 12/10/2026 »."""
    when = _parse(iso)
    if when is None:
        return "jamais joué"
    days = (now.date() - when.date()).days
    if days <= 0:
        return f"aujourd'hui, {when:%H:%M}"
    if days == 1:
        return f"hier, {when:%H:%M}"
    if days < 7:
        return f"il y a {days} jours"
    if days < 14:
        return "il y a 1 semaine"
    if days < 31:
        return f"il y a {days // 7} semaines"
    return f"le {when:%d/%m/%Y}"


def map_label(profile: Profile, map_titles: dict[str, str]) -> str:
    """Nom lisible de la carte d'un profil et sa nature (mod, officielle)."""
    if profile.map_mod:
        title = map_titles.get(profile.map_mod) or profile.map_mod.removesuffix(".zip")
        return f"{title} · carte mod"
    if profile.official_map:
        for m in OFFICIAL_MAPS:
            if m.map_id == profile.official_map:
                return f"{m.title} · " + ("carte DLC" if m.is_dlc else "carte officielle")
        return f"{profile.official_map} · carte officielle"
    return "Aucune carte choisie"


def build_cards(
    profiles: list[Profile],
    effective_counts: dict[str, int],
    map_titles: dict[str, str],
    now: datetime,
) -> list[ProfileCard]:
    """Cartes de l'accueil : la dernière partie d'abord, puis par date décroissante,
    les profils jamais joués à la fin (ordre alphabétique)."""
    played = [p for p in profiles if _parse(p.last_played)]
    last = max(played, key=lambda p: _parse(p.last_played) or now) if played else None

    def order(p: Profile) -> tuple[int, float, str]:
        when = _parse(p.last_played)
        return (0 if when else 1, -(when.timestamp() if when else 0.0), p.name.lower())

    return [
        ProfileCard(
            slug=p.slug,
            name=p.name,
            map_label=map_label(p, map_titles),
            mods_count=effective_counts.get(p.slug, len(p.mods)),
            collections_count=len(p.collections),
            last_played_label=last_played_label(p.last_played, now),
            is_last_played=last is not None and p.slug == last.slug,
        )
        for p in sorted(profiles, key=order)
    ]


# Vignette de secours (profil sans image de carte) : champs stylisés dont les
# couleurs dépendent du nom, pour que chaque profil reste reconnaissable.
_ART_PALETTES: tuple[tuple[str, str, str, str, str], ...] = (
    ("#C9D7C4", "#A9BFA0", "#8DB27C", "#B5C788", "#6E9A5E"),  # prairie
    ("#DCE3CC", "#D3C68C", "#C9B566", "#A9C27A", "#D6C27C"),  # blé
    ("#D3CDB8", "#A89A74", "#B9A57E", "#8E8A5A", "#A68E62"),  # terre
    ("#C4CFBE", "#8FA27F", "#7C9070", "#B5B48C", "#5E7458"),  # lande
    ("#CFE3DA", "#7FB7A4", "#9CCB9A", "#6FB07E", "#BFD9A0"),  # rizière
)


def art_palette(name: str) -> tuple[str, str, str, str, str]:
    """Palette (ciel, horizon, trois champs) stable pour un nom de profil."""
    digest = hashlib.sha1(name.encode("utf-8")).digest()
    return _ART_PALETTES[digest[0] % len(_ART_PALETTES)]
