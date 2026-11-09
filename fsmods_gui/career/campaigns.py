"""Campagnes écrites à la main : objectifs propres à une partie, hors modèles génériques.

* « L'héritage des Highlands » (Kinlaig) : campagne de clôture. Surtout validée à la main
  (constructions, dernières récoltes, bilan) ; l'objectif final attend tous les autres.
* « Pisciculture » : élevages de saumon et de truite. Les nombres d'élevages sont saisis
  avec « Statistique manuelle… » : la sauvegarde ne les expose pas (encore) de façon vérifiée.
* « Objectifs répétables » : les paliers de :mod:`repeats`, exposés comme une campagne.

Pur, sans Qt.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .objectives import Condition, Objective, now_iso
from .repeats import repeatable_objectives


def _suffix(farm: str) -> str:
    return f"@{farm}" if farm else ""


def _manual(
    template: str, key: str, name: str, category: str, description: str, *,
    requires: tuple[str, ...] = (), farm: str = "", difficulty: int = 2,
) -> Objective:
    """Objective validated by the player (no condition)."""
    sfx = _suffix(farm)
    return Objective(
        id=f"{template}.{key}{sfx}",
        name=name,
        category=category,
        description=description,
        requires=[f"{template}.{r}{sfx}" for r in requires],
        difficulty=difficulty,
        farm=farm,
        template=template,
        created_at=now_iso(),
    )


def _at_least(
    template: str, key: str, name: str, category: str, stat: str, target: float, *,
    requires: tuple[str, ...] = (), farm: str = "", difficulty: int = 2,
) -> Objective:
    """Objective measured on a statistic: ``stat >= target``."""
    sfx = _suffix(farm)
    return Objective(
        id=f"{template}.{key}{sfx}",
        name=name,
        category=category,
        condition=Condition(stat=stat, operator=">=", target=target),
        requires=[f"{template}.{r}{sfx}" for r in requires],
        difficulty=difficulty,
        farm=farm,
        template=template,
        created_at=now_iso(),
    )


def build_kinlaig(farm: str = "") -> list[Objective]:
    """« L'héritage des Highlands » : 12 étapes de clôture + un objectif final."""
    t = "kinlaig"

    def m(key: str, name: str, desc: str, *requires: str) -> Objective:
        return _manual(t, key, name, "general", desc, requires=requires, farm=farm, difficulty=3)

    steps = [
        m("castle", "Construire le château", "Domaine : achever le château."),
        m("windmill", "Construire le moulin à vent", "Domaine : achever le moulin."),
        m("onions", "Première récolte d'oignons", "Nouvelle culture intégrée à l'exploitation."),
        m("onionProcessing", "Transformer une production d'oignons",
          "Usine de transformation des légumes, produits dérivés.", "onions"),
        m("onionSales", "Vendre la production d'oignons",
          "Produits transformés ou vrac.", "onionProcessing"),
        m("cropsEnd", "Terminer les cultures en cours", "Dernière récolte de la campagne."),
        m("highlandSold", "Vendre 100 % des vaches Highland",
          "Plus aucun cheptel Highland à la fin de la campagne."),
        m("zeroAnimals", "Atteindre zéro animal",
          "Aucun animal dans l'exploitation.", "highlandSold"),
        m("hay", "Valoriser tout le foin restant",
          "Foin, fourrage et stocks alimentaires.", "zeroAnimals"),
        m("productionsEnd", "Terminer les productions en cours", "Plus rien en cours de fabrication."),
        m("stocksEmpty", "Vider les stocks à liquider",
          "Ceux qui ne serviront plus.", "hay", "productionsEnd"),
        m("balance", "Établir le bilan financier final",
          "Patrimoine et trésorerie de clôture.", "stocksEmpty"),
    ]
    final = Objective(
        id=f"{t}.closure{_suffix(farm)}",
        name="L'héritage des Highlands — le dernier fermier de Kinlaig",
        category="general",
        description="Objectif ultime : tous les objectifs de clôture sont validés.",
        requires=[o.id for o in steps],
        difficulty=3,
        priority=len(steps),
        farm=farm,
        template=t,
        created_at=now_iso(),
    )
    return [*steps, final]


def build_fish(farm: str = "") -> list[Objective]:
    """Pisciculture : élevages de saumon et de truite (chiffres saisis à la main)."""
    t = "fish"

    def n(key: str, name: str, stat: str, target: float, *requires: str) -> Objective:
        return _at_least(t, key, name, "production", stat, target,
                         requires=requires, farm=farm)

    return [
        n("salmon", "Ouvrir un élevage de saumon", "fish.salmon.farms", 1),
        n("trout", "Ouvrir un élevage de truite", "fish.trout.farms", 1),
        n("two", "Pisciculture double : 2 élevages", "fish.farms", 2, "salmon", "trout"),
        n("five", "Entreprise piscicole : 5 élevages", "fish.farms", 5, "two"),
    ]


@dataclass(frozen=True)
class Campaign:
    key: str
    name: str
    summary: str  # for the picker's list
    description: str  # for the confirmation message
    build: Callable[[str], list[Objective]]


CAMPAIGNS: tuple[Campaign, ...] = (
    Campaign("kinlaig", "L'héritage des Highlands", "campagne de clôture Kinlaig",
             "campagne de clôture Kinlaig", build_kinlaig),
    Campaign("fish", "Pisciculture", "élevages de saumon et de truite",
             "élevages de saumon et de truite", build_fish),
    Campaign("repeatable", "Objectifs répétables", "paliers réguliers",
             "objectifs répétables", repeatable_objectives),
)
