"""Predefined objective sets ("scenarios") — plain data, expanded into objectives.

Each template is a list of :class:`Spec`. Applying a template twice never
duplicates objectives (ids are stable: ``<template>.<key>``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .objectives import Condition, Objective, Reward, now_iso


@dataclass(frozen=True)
class Spec:
    key: str
    name: str
    category: str
    # A leaf is (stat, target, unit); several leaves are combined with AND.
    leaves: tuple[tuple[str, float, str], ...]
    difficulty: int = 2
    money: int = 0
    xp: int = 0
    badge: str = ""
    requires: tuple[str, ...] = ()
    description: str = ""
    optional: bool = False


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    description: str
    specs: tuple[Spec, ...] = field(default_factory=tuple)


def _s(key, name, cat, stat, target, unit="", **kw) -> Spec:
    return Spec(key, name, cat, ((stat, float(target), unit),), **kw)


def _and(key, name, cat, leaves, **kw) -> Spec:
    return Spec(key, name, cat, tuple((s, float(t), u) for s, t, u in leaves), **kw)


def _money_chain(prefix: str, steps: list[tuple[int, str]]) -> list[Spec]:
    specs: list[Spec] = []
    prev: tuple[str, ...] = ()
    for i, (amount, label) in enumerate(steps, 1):
        key = f"{prefix}{i}"
        specs.append(
            _s(key, f"Atteindre {label} en banque", "finance", "money", amount, "€",
               difficulty=min(5, i + 1), xp=50 * i, requires=prev)
        )
        prev = (key,)
    return specs


CLASSIC = Template(
    "classic",
    "Carrière agricole classique",
    "Des jalons de débutant à exploitant : argent, matériel, terres, contrats, temps de jeu.",
    tuple(
        _money_chain("money", [(100_000, "100 000 €"), (500_000, "500 000 €"),
                               (1_000_000, "1 000 000 €"), (5_000_000, "5 000 000 €")])
        + [
            _s("veh1", "Acheter son premier véhicule", "equipment", "vehicles.count", 1,
               difficulty=1, money=10_000, xp=10),
            _s("veh5", "Posséder 5 véhicules", "equipment", "vehicles.count", 5,
               money=25_000, xp=30, requires=("veh1",)),
            _s("veh10", "Posséder 10 véhicules", "equipment", "vehicles.count", 10,
               difficulty=3, money=50_000, xp=60, requires=("veh5",)),
            _s("veh25", "Posséder 25 véhicules", "equipment", "vehicles.count", 25,
               difficulty=4, money=100_000, xp=120, requires=("veh10",)),
            _s("land1", "Posséder son premier champ", "land", "land.count", 1,
               difficulty=1, money=10_000, xp=10),
            _s("land5", "Posséder 5 parcelles", "land", "land.count", 5,
               money=30_000, xp=30, requires=("land1",)),
            _s("land10", "Posséder 10 parcelles", "land", "land.count", 10,
               difficulty=3, money=60_000, xp=60, requires=("land5",)),
            _s("area25", "Posséder 25 ha", "land", "land.area", 25, "ha",
               money=50_000, xp=50, description="Surface à saisir à la main si non lisible."),
            _s("area50", "Posséder 50 ha", "land", "land.area", 50, "ha",
               difficulty=3, money=100_000, xp=100, requires=("area25",)),
            _s("area100", "Posséder 100 ha", "land", "land.area", 100, "ha",
               difficulty=4, money=200_000, xp=200, badge="Grand exploitant",
               requires=("area50",)),
            _s("contract1", "Réaliser son premier contrat", "eta", "contracts.completed", 1,
               difficulty=1, money=10_000, xp=10),
            _s("contract10", "Réaliser 10 contrats", "eta", "contracts.completed", 10,
               money=30_000, xp=40, requires=("contract1",)),
            _s("contract50", "Réaliser 50 contrats", "eta", "contracts.completed", 50,
               difficulty=3, money=100_000, xp=100, requires=("contract10",)),
            _s("contract100", "Réaliser 100 contrats", "eta", "contracts.completed", 100,
               difficulty=4, money=150_000, xp=200, badge="Patron ETA",
               requires=("contract50",)),
            _s("play10", "Jouer 10 heures", "time", "playTime", 10, "h", difficulty=1, xp=20),
            _s("play50", "Jouer 50 heures", "time", "playTime", 50, "h", xp=60,
               requires=("play10",)),
            _s("play100", "Jouer 100 heures", "time", "playTime", 100, "h", difficulty=3,
               xp=120, requires=("play50",)),
            _s("animals10", "Posséder 10 animaux", "animals", "animals.total", 10,
               money=20_000, xp=30),
            _s("crops3", "Cultiver 3 cultures différentes", "crops", "crops.growing", 3,
               xp=30),
            _s("prod1", "Posséder une production", "production", "productions.count", 1,
               difficulty=3, money=50_000, xp=60),
        ]
    ),
)

ETA = Template(
    "eta",
    "ETA — entreprise de travaux agricoles",
    "Monter une ETA : de la première machine à la grande entreprise de contrats.",
    (
        _s("start", "Créer l'entreprise : acheter un premier véhicule", "equipment",
           "vehicles.count", 1, difficulty=1, money=30_000, xp=20),
        _s("c10", "Première clientèle : 10 contrats", "eta", "contracts.completed", 10,
           money=50_000, xp=50, requires=("start",)),
        _s("fleet5", "Constituer un parc de 5 véhicules", "equipment", "vehicles.count", 5,
           money=40_000, xp=40, requires=("start",)),
        _s("c50", "Petite ETA : 50 contrats", "eta", "contracts.completed", 50,
           difficulty=3, money=100_000, xp=100, requires=("c10",)),
        _s("inc100k", "Gagner 100 000 € grâce aux contrats", "eta", "finance.missionIncome",
           100_000, "€", difficulty=3, money=50_000, xp=80, requires=("c10",)),
        _and("pro", "ETA professionnelle : 100 contrats et 500 000 € de revenus contrats",
             "eta", [("contracts.completed", 100, ""), ("finance.missionIncome", 500_000, "€")],
             difficulty=4, money=250_000, xp=250, badge="Patron ETA",
             requires=("c50", "inc100k")),
        _s("fleet15", "Posséder 15 véhicules", "equipment", "vehicles.count", 15,
           difficulty=4, money=100_000, xp=120, requires=("fleet5",)),
        _and("grande", "Grande ETA : 250 contrats et 1 M€ de revenus contrats", "eta",
             [("contracts.completed", 250, ""), ("finance.missionIncome", 1_000_000, "€")],
             difficulty=5, money=500_000, xp=500, badge="Empire ETA", requires=("pro",)),
    ),
)

LIVESTOCK = Template(
    "livestock",
    "Élevage",
    "Faire grossir le cheptel, jusqu'à plusieurs espèces.",
    (
        _s("a10", "Posséder 10 animaux", "animals", "animals.total", 10, difficulty=1,
           money=10_000, xp=20),
        _s("a25", "Posséder 25 animaux", "animals", "animals.total", 25, money=25_000,
           xp=40, requires=("a10",)),
        _s("a50", "Posséder 50 animaux", "animals", "animals.total", 50, difficulty=3,
           money=50_000, xp=80, requires=("a25",)),
        _s("a100", "Posséder 100 animaux", "animals", "animals.total", 100, difficulty=4,
           money=100_000, xp=150, requires=("a50",)),
        _s("a500", "Posséder 500 animaux", "animals", "animals.total", 500, difficulty=5,
           money=500_000, xp=500, badge="Éleveur industriel", requires=("a100",)),
        _s("cow10", "Posséder 10 vaches", "animals", "animals.cow", 10, money=20_000, xp=30),
        _s("cow50", "Posséder 50 vaches", "animals", "animals.cow", 50, difficulty=3,
           money=80_000, xp=100, requires=("cow10",)),
        _s("cow100", "Posséder 100 vaches", "animals", "animals.cow", 100, difficulty=4,
           money=150_000, xp=200, requires=("cow50",)),
        _s("species2", "Élever 2 espèces différentes", "animals", "animals.species", 2,
           xp=30),
        _s("species4", "Élever 4 espèces différentes", "animals", "animals.species", 4,
           difficulty=3, money=60_000, xp=100, requires=("species2",)),
        _s("hives3", "Posséder 3 ruches", "animals", "animals.beehives", 3, xp=30,
           optional=True),
        _s("bred50", "Voir naître 50 veaux", "animals", "animals.bred.cow", 50,
           difficulty=3, xp=80, optional=True),
    ),
)

EMPIRE = Template(
    "empire",
    "Empire agricole",
    "Grandes étapes d'une exploitation qui devient un groupe.",
    (
        *_money_chain("cash", [(1_000_000, "1 M€"), (5_000_000, "5 M€"), (10_000_000, "10 M€")]),
        _s("area250", "Posséder 250 ha", "land", "land.area", 250, "ha", difficulty=4,
           money=250_000, xp=250),
        _s("area500", "Posséder 500 ha", "land", "land.area", 500, "ha", difficulty=5,
           money=500_000, xp=500, badge="Empire agricole", requires=("area250",)),
        _s("farms2", "Posséder 2 fermes", "farms", "farms.count", 2, difficulty=3,
           money=100_000, xp=100),
        _s("farms3", "Créer un groupe agricole de 3 exploitations", "farms", "farms.count",
           3, difficulty=4, money=250_000, xp=250, requires=("farms2",)),
        _s("fleet25", "Posséder 25 véhicules", "equipment", "vehicles.count", 25,
           difficulty=3, money=100_000, xp=100),
        _s("fleet50", "Posséder 50 véhicules", "equipment", "vehicles.count", 50,
           difficulty=4, money=250_000, xp=200, requires=("fleet25",)),
        _s("prod3", "Exploiter 3 productions", "production", "productions.count", 3,
           difficulty=4, money=150_000, xp=150),
        _s("contract250", "Réaliser 250 contrats", "eta", "contracts.completed", 250,
           difficulty=5, money=300_000, xp=300),
        _and("combo", "Posséder 100 ha, 10 véhicules et 1 M€", "general",
             [("land.area", 100, "ha"), ("vehicles.count", 10, ""), ("money", 1_000_000, "€")],
             difficulty=4, money=200_000, xp=200),
        _s("play500", "Jouer 500 heures", "time", "playTime", 500, "h", difficulty=5,
           xp=300, badge="Vétéran"),
    ),
)

HARDCORE = Template(
    "hardcore",
    "Hardcore",
    "Des objectifs beaucoup plus difficiles.",
    (
        *_money_chain("cash", [(5_000_000, "5 M€"), (20_000_000, "20 M€"), (50_000_000, "50 M€")]),
        _s("area500", "Posséder 500 ha", "land", "land.area", 500, "ha", difficulty=5),
        _s("area1000", "Posséder 1 000 ha", "land", "land.area", 1000, "ha", difficulty=5,
           badge="Seigneur des terres", requires=("area500",)),
        _s("fleet50", "Posséder 50 véhicules", "equipment", "vehicles.count", 50,
           difficulty=4),
        _s("contract500", "Réaliser 500 contrats", "eta", "contracts.completed", 500,
           difficulty=5, badge="Légende des ETA"),
        _s("animals500", "Posséder 500 animaux", "animals", "animals.total", 500,
           difficulty=5),
        _s("play1000", "Jouer 1 000 heures", "time", "playTime", 1000, "h", difficulty=5,
           badge="Increvable"),
    ),
)

VITICULTURE = Template(
    "vine",
    "Viticulture",
    "Créer et développer un domaine viticole (volumes cumulés à saisir à la main).",
    (
        _s("domain", "Créer un domaine viticole : planter une vigne", "vine",
           "crops.fields.grape", 1, difficulty=1, money=25_000, xp=30,
           description="Compte les champs de raisin de la carte."),
        _s("area5", "Posséder 5 ha de vignes", "vine", "vine.area", 5, "ha",
           money=100_000, xp=60, requires=("domain",)),
        _s("harvest1", "Première récolte de raisin", "vine", "vine.grapesHarvested", 1, "L",
           difficulty=1, money=25_000, xp=30, requires=("domain",)),
        _s("area10", "Posséder 10 ha de vignes", "vine", "vine.area", 10, "ha",
           difficulty=3, money=150_000, xp=120, requires=("area5",)),
        _s("cellar", "Équiper une cave : posséder une production", "production",
           "productions.count", 1, difficulty=2, money=50_000, xp=50, requires=("harvest1",)),
        _s("wine10k", "Produire 10 000 L de vin", "vine", "vine.wineProduced", 10_000, "L",
           difficulty=3, money=75_000, xp=100, requires=("cellar",)),
        _s("wine100k", "Produire 100 000 L de vin", "vine", "vine.wineProduced", 100_000, "L",
           difficulty=4, money=200_000, xp=250, requires=("wine10k",)),
        _s("sold100k", "Vendre 100 000 L de vin", "vine", "vine.wineSold", 100_000, "L",
           difficulty=4, money=250_000, xp=250, requires=("wine10k",)),
        _s("rev1m", "1 M€ de revenus viticoles", "vine", "vine.revenue", 1_000_000, "€",
           difficulty=5, money=500_000, xp=500, badge="Grand vigneron", requires=("sold100k",)),
        _and("estate", "Créer mon domaine : 15 ha de vignes et 50 000 L de vin", "vine",
             [("vine.area", 15, "ha"), ("vine.wineProduced", 50_000, "L")],
             difficulty=4, money=200_000, xp=250, badge="Maître de chai",
             requires=("area10",)),
    ),
)

OLIVE = Template(
    "olive",
    "Oléiculture",
    "Planter des oliviers et produire de l'huile (volumes cumulés à saisir à la main).",
    (
        _s("grove", "Planter son premier olivier", "olive", "crops.fields.olive", 1,
           difficulty=1, money=20_000, xp=30,
           description="Compte les champs d'olives de la carte."),
        _s("area5", "Posséder 5 ha d'oliviers", "olive", "olive.area", 5, "ha",
           money=80_000, xp=60, requires=("grove",)),
        _s("harvest", "Première récolte d'olives", "olive", "olive.olivesHarvested", 1, "L",
           difficulty=1, money=20_000, xp=30, requires=("grove",)),
        _s("press", "Équiper une huilerie : posséder une production", "production",
           "productions.count", 1, money=50_000, xp=50, requires=("harvest",)),
        _s("oil1k", "Produire 1 000 L d'huile", "olive", "olive.oilProduced", 1_000, "L",
           difficulty=3, money=60_000, xp=100, requires=("press",)),
        _s("oil10k", "Produire 10 000 L d'huile", "olive", "olive.oilProduced", 10_000, "L",
           difficulty=4, money=150_000, xp=200, requires=("oil1k",)),
        _s("sold", "Vendre 5 000 L d'huile", "olive", "olive.oilSold", 5_000, "L",
           difficulty=4, money=150_000, xp=200, requires=("oil1k",)),
        _s("rev100k", "100 000 € de revenus oléicoles", "olive", "olive.revenue", 100_000, "€",
           difficulty=4, money=100_000, xp=200, badge="Oléiculteur", requires=("sold",)),
    ),
)

PRODUCTION = Template(
    "production",
    "Productions",
    "Bâtir des chaînes de production (meunerie, laiterie, scierie…).",
    (
        _s("p1", "Posséder une production", "production", "productions.count", 1,
           difficulty=2, money=50_000, xp=50),
        _s("p3", "Posséder 3 productions", "production", "productions.count", 3,
           difficulty=3, money=100_000, xp=100, requires=("p1",)),
        _s("p5", "Posséder 5 productions", "production", "productions.count", 5,
           difficulty=4, money=200_000, xp=200, requires=("p3",)),
        _s("p10", "Posséder 10 productions", "production", "productions.count", 10,
           difficulty=5, money=400_000, xp=400, badge="Industriel", requires=("p5",)),
        _s("b10", "Posséder 10 bâtiments", "buildings", "placeables.count", 10, xp=30),
        _s("b25", "Posséder 25 bâtiments", "buildings", "placeables.count", 25,
           difficulty=3, money=75_000, xp=80, requires=("b10",)),
        _s("b50", "Posséder 50 bâtiments", "buildings", "placeables.count", 50,
           difficulty=4, money=150_000, xp=150, requires=("b25",)),
        _s("bval", "1 M€ de bâtiments (valeur d'achat)", "buildings", "placeables.value",
           1_000_000, "€", difficulty=4, money=100_000, xp=150),
    ),
)

MULTIFARM = Template(
    "multifarm",
    "Multiferme",
    "Créer plusieurs exploitations et constituer un groupe agricole.",
    (
        _s("f2", "Posséder 2 fermes", "farms", "farms.count", 2, difficulty=2,
           money=50_000, xp=60),
        _s("f3", "Créer un groupe agricole de 3 exploitations", "farms", "farms.count", 3,
           difficulty=3, money=150_000, xp=150, requires=("f2",)),
        _s("f5", "Posséder 5 fermes", "farms", "farms.count", 5, difficulty=5,
           money=400_000, xp=400, badge="Groupe agricole", requires=("f3",)),
        _s("nw1m", "1 M€ de patrimoine estimé", "finance", "netWorth", 1_000_000, "€",
           difficulty=3, money=50_000, xp=80),
        _s("nw10m", "10 M€ de patrimoine estimé", "finance", "netWorth", 10_000_000, "€",
           difficulty=5, money=500_000, xp=500, requires=("nw1m",)),
    ),
)

TRANSPORT = Template(
    "transport",
    "Transport",
    "Parc de remorques et de camions, kilomètres au compteur.",
    (
        _s("km100", "Parcourir 100 km", "work", "work.distance", 100, "km", difficulty=1,
           xp=20),
        _s("km500", "Parcourir 500 km", "work", "work.distance", 500, "km", xp=60,
           requires=("km100",)),
        _s("km2000", "Parcourir 2 000 km", "work", "work.distance", 2000, "km",
           difficulty=4, money=100_000, xp=200, requires=("km500",)),
        _s("trailer", "Posséder une remorque", "equipment", "vehicles.type.trailer", 1,
           difficulty=1, money=10_000, xp=15,
           description="Catégorie déduite du nom de fichier (approximatif)."),
        _s("truck", "Posséder un camion", "equipment", "vehicles.type.truck", 1,
           difficulty=2, money=30_000, xp=40,
           description="Catégorie déduite du nom de fichier (approximatif)."),
        _s("c10", "Réaliser 10 contrats", "eta", "contracts.completed", 10, money=30_000,
           xp=40),
        _s("c50", "Réaliser 50 contrats", "eta", "contracts.completed", 50, difficulty=3,
           money=100_000, xp=100, requires=("c10",)),
    ),
)

TEMPLATES: dict[str, Template] = {
    t.key: t
    for t in (CLASSIC, ETA, LIVESTOCK, VITICULTURE, OLIVE, PRODUCTION, MULTIFARM,
              TRANSPORT, EMPIRE, HARDCORE)
}

# Career type offered when creating a profile: (label, template key or None).
SCENARIOS: tuple[tuple[str, str | None], ...] = (
    ("Agriculture classique", "classic"),
    ("ETA", "eta"),
    ("Élevage", "livestock"),
    ("Viticulture", "vine"),
    ("Oléiculture", "olive"),
    ("Production", "production"),
    ("Transport", "transport"),
    ("Multiferme", "multifarm"),
    ("Empire agricole", "empire"),
    ("Personnalisé (aucun objectif pour l'instant)", None),
)


def build_template(key: str, farm: str = "") -> list[Objective]:
    """Expand a template into fresh objectives (ids are ``<template>.<key>``).

    With ``farm`` the objectives are bound to that farm and the ids get an ``@<farm>``
    suffix, so the same template can be applied once per farm.
    """
    tpl = TEMPLATES[key]
    suffix = f"@{farm}" if farm else ""
    created = now_iso()
    out: list[Objective] = []
    for i, spec in enumerate(tpl.specs):
        leaves = [Condition(stat=s, target=t, unit=u) for s, t, u in spec.leaves]
        condition = leaves[0] if len(leaves) == 1 else Condition(op="and", children=leaves)
        out.append(
            Objective(
                id=f"{tpl.key}.{spec.key}{suffix}",
                name=spec.name,
                description=spec.description,
                category=spec.category,
                condition=condition,
                difficulty=spec.difficulty,
                priority=i,
                optional=spec.optional,
                requires=[f"{tpl.key}.{r}{suffix}" for r in spec.requires],
                farm=farm,
                reward=Reward(money=spec.money, xp=spec.xp, badge=spec.badge),
                template=tpl.key,
                created_at=created,
            )
        )
    return out
