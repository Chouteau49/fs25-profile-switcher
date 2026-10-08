"""Normalised career statistics extracted from a FS25 savegame folder.

The savegame does not expose every number a player would like. Each statistic
therefore carries a *quality* so the UI never pretends a value is exact:

* ``auto``   — read directly from the savegame.
* ``calc``   — computed / estimated from several data points (or a heuristic).
* ``manual`` — typed in by the user (see :func:`apply_manual`).
* ``na``     — cannot be determined reliably (``value`` is ``None``).

Statistic keys are dotted strings (``money``, ``animals.cow``, ``vehicles.brand.fendt``…).
Dynamic families (animal species, brands, crops, raw farm statistics) are
discovered from the data, never hard-coded.

Pure logic, no Qt.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

Q_AUTO = "auto"
Q_CALC = "calc"
Q_MANUAL = "manual"
Q_NA = "na"

QUALITY_LABELS_FR = {
    Q_AUTO: "🟢 Automatique",
    Q_CALC: "🟠 Calculée",
    Q_MANUAL: "🔵 Manuelle",
    Q_NA: "🔴 Non disponible",
}

CATEGORIES_FR = {
    "finance": "💰 Finances",
    "equipment": "🚜 Matériel",
    "land": "🌾 Terres / champs",
    "crops": "🌱 Cultures",
    "work": "🛠 Travaux agricoles",
    "eta": "🚛 ETA / contrats",
    "animals": "🐄 Animaux",
    "production": "🏭 Productions",
    "vine": "🍇 Viticulture",
    "olive": "🫒 Oléiculture",
    "buildings": "🏗 Bâtiments",
    "farms": "🏦 Fermes",
    "time": "⏱ Temps de jeu",
    "general": "🎯 Général",
}


@dataclass
class Stat:
    key: str
    value: float | None
    quality: str = Q_AUTO
    label: str = ""
    unit: str = ""
    category: str = "general"
    note: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass
class StatsSnapshot:
    savegame: str = ""
    taken_at: str = ""
    stats: dict[str, Stat] = field(default_factory=dict)
    # Dynamic families whose source file was read completely: a member that is
    # absent really is zero (e.g. no wheat field), not "unknown".
    complete_prefixes: set[str] = field(default_factory=set)

    def get(self, key: str) -> Stat | None:
        return self.stats.get(key)

    def value(self, key: str) -> float | None:
        stat = self.stats.get(key)
        if stat is not None:
            return stat.value
        if key not in UNDETECTABLE:
            for prefix in self.complete_prefixes:
                if key.startswith(prefix) and "." not in key[len(prefix):]:
                    return 0.0
        return None

    def keys_by_prefix(self, prefix: str) -> list[str]:
        return sorted(k for k in self.stats if k.startswith(prefix))

    def to_dict(self) -> dict:
        return {
            "savegame": self.savegame,
            "taken_at": self.taken_at,
            "complete_prefixes": sorted(self.complete_prefixes),
            "stats": {
                k: {
                    "value": s.value,
                    "quality": s.quality,
                    "label": s.label,
                    "unit": s.unit,
                    "category": s.category,
                    "note": s.note,
                }
                for k, s in sorted(self.stats.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> StatsSnapshot:
        snap = cls(
            savegame=str(data.get("savegame", "")), taken_at=str(data.get("taken_at", ""))
        )
        prefixes = data.get("complete_prefixes", [])
        if isinstance(prefixes, list):
            snap.complete_prefixes = {p for p in prefixes if isinstance(p, str)}
        raw = data.get("stats", {})
        if isinstance(raw, dict):
            for key, d in raw.items():
                if not isinstance(d, dict):
                    continue
                value = d.get("value")
                snap.stats[key] = Stat(
                    key=key,
                    value=float(value) if isinstance(value, int | float) else None,
                    quality=str(d.get("quality", Q_AUTO)),
                    label=str(d.get("label", "")),
                    unit=str(d.get("unit", "")),
                    category=str(d.get("category", "general")),
                    note=str(d.get("note", "")),
                )
        return snap


# Family members the savegame can never reveal (so "absent" must stay unknown).
UNDETECTABLE = frozenset({"animals.dog"})

# --------------------------------------------------------------- stat catalog

# Well-known statistics: key -> (label, unit, category). Anything not listed
# here but discovered in the savegame gets a generated label.
STAT_DEFS: dict[str, tuple[str, str, str]] = {
    "money": ("Argent en banque", "€", "finance"),
    "loan": ("Emprunt", "€", "finance"),
    "netWorth": ("Patrimoine estimé", "€", "finance"),
    "finance.income": ("Revenus cumulés", "€", "finance"),
    "finance.expenses": ("Dépenses cumulées", "€", "finance"),
    "finance.profit": ("Bénéfices cumulés", "€", "finance"),
    "finance.missionIncome": ("Revenus des contrats", "€", "eta"),
    "vehicles.count": ("Véhicules", "", "equipment"),
    "vehicles.value": ("Valeur d'achat des véhicules", "€", "equipment"),
    "vehicles.brands": ("Marques de véhicules différentes", "", "equipment"),
    "vehicles.types": ("Catégories de véhicules différentes", "", "equipment"),
    "land.count": ("Parcelles possédées", "", "land"),
    "land.area": ("Surface possédée", "ha", "land"),
    "crops.growing": ("Cultures différentes en cours", "", "crops"),
    "contracts.completed": ("Contrats réalisés", "", "eta"),
    "animals.total": ("Animaux", "", "animals"),
    "animals.species": ("Espèces animales différentes", "", "animals"),
    "animals.beehives": ("Ruches", "", "animals"),
    "placeables.count": ("Bâtiments / placeables", "", "buildings"),
    "placeables.value": ("Valeur d'achat des bâtiments", "€", "buildings"),
    "productions.count": ("Bâtiments de production", "", "production"),
    "farms.count": ("Fermes", "", "farms"),
    "playTime": ("Temps de jeu", "h", "time"),
    # Cumulative vine/olive figures are not in the savegame: manual entry only.
    "vine.area": ("Vignes possédées", "ha", "vine"),
    "vine.grapesHarvested": ("Raisin récolté", "L", "vine"),
    "vine.wineProduced": ("Vin produit", "L", "vine"),
    "vine.wineSold": ("Vin vendu", "L", "vine"),
    "vine.revenue": ("Revenus viticoles", "€", "vine"),
    "olive.area": ("Oliviers possédés", "ha", "olive"),
    "olive.olivesHarvested": ("Olives récoltées", "L", "olive"),
    "olive.oilProduced": ("Huile produite", "L", "olive"),
    "olive.oilSold": ("Huile vendue", "L", "olive"),
    "olive.revenue": ("Revenus oléicoles", "€", "olive"),
    "daysPlayed": ("Jours de jeu (in-game)", "j", "time"),
}

# Raw <statistics> children of a farm -> (key, label, unit, category, scale).
FARM_STAT_MAP: dict[str, tuple[str, str, str, str, float]] = {
    "workedHectares": ("work.worked", "Hectares travaillés", "ha", "work", 1.0),
    "cultivatedHectares": ("work.cultivated", "Hectares cultivés", "ha", "work", 1.0),
    "plowedHectares": ("work.plowed", "Hectares labourés", "ha", "work", 1.0),
    "sownHectares": ("work.sown", "Hectares semés", "ha", "work", 1.0),
    "sprayedHectares": ("work.sprayed", "Hectares pulvérisés", "ha", "work", 1.0),
    "threshedHectares": ("work.harvested", "Hectares récoltés", "ha", "work", 1.0),
    "baleCount": ("work.bales", "Balles pressées", "", "work", 1.0),
    "traveledDistance": ("work.distance", "Distance parcourue", "km", "work", 1.0),
    "plantedTreeCount": ("work.treesPlanted", "Arbres plantés", "", "work", 1.0),
    "cutTreeCount": ("work.treesCut", "Arbres abattus", "", "work", 1.0),
    "woodTonsSold": ("commerce.woodTons", "Bois vendu", "t", "finance", 1.0),
    "breedCowsCount": ("animals.bred.cow", "Veaux nés", "", "animals", 1.0),
    "breedSheepCount": ("animals.bred.sheep", "Agneaux nés", "", "animals", 1.0),
    "breedPigsCount": ("animals.bred.pig", "Porcelets nés", "", "animals", 1.0),
    "breedChickenCount": ("animals.bred.chicken", "Poussins nés", "", "animals", 1.0),
    "harvestedGrapes": ("vine.grapesHarvested", "Raisin récolté", "L", "vine", 1.0),
    "harvestedOlives": ("olive.olivesHarvested", "Olives récoltées", "L", "olive", 1.0),
    "breedHorsesCount": ("animals.bred.horse", "Poulains nés", "", "animals", 1.0),
}

# Vehicle categories guessed from the file path / type name. Heuristic only
# (the savegame has no vehicle type), so the result is flagged "calculated".
VEHICLE_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("forageHarvester", ("forageharvester", "forage_harvester", "chopper")),
    ("harvester", ("combine", "harvester", "moissonneuse")),
    ("tractor", ("tractor", "traktor", "tracteur")),
    ("sprayer", ("sprayer", "spray")),
    ("seeder", ("seeder", "drill", "semoir")),
    ("planter", ("planter",)),
    ("trailer", ("trailer", "remorque")),
    ("loader", ("loader", "telehandler", "chargeur")),
    ("truck", ("truck", "lorry", "camion")),
]

_INCOME_TAG_RE = re.compile(r"(Income|^sold[A-Z])")
_EXPENSE_TAG_RE = re.compile(r"(Cost|Costs|Maintenance|Payment|Interest|Purchase|Expenses)$")
_MISSION_COUNT_RE = re.compile(r"MissionCount$")


def label_for(key: str) -> tuple[str, str, str]:
    """Label/unit/category for a statistic key (known or dynamic family)."""
    if key in STAT_DEFS:
        return STAT_DEFS[key]
    family, _, rest = key.partition(".")
    pretty = rest.split(".")[-1].replace("_", " ")
    if key.startswith("animals.") and rest:
        return (f"Animaux : {pretty.lower()}", "", "animals")
    if key.startswith("vehicles.brand."):
        return (f"Véhicules {pretty}", "", "equipment")
    if key.startswith("vehicles.type."):
        return (f"Véhicules de type {pretty}", "", "equipment")
    if key.startswith("stock."):
        return (f"Stock actuel : {pretty.lower()}", "L", "production")
    if key.startswith("crops.fields."):
        return (f"Champs de {pretty}", "", "crops")
    if family == "raw":
        return (f"Statistique FS25 : {rest}", "", "general")
    return (key, "", "general")


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text.strip())
    except ValueError:
        return None


def _parse_xml(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ET.ParseError):
        return None


@dataclass
class _Collector:
    stats: dict[str, Stat] = field(default_factory=dict)
    complete_prefixes: set[str] = field(default_factory=set)

    def put(
        self,
        key: str,
        value: float | None,
        quality: str = Q_AUTO,
        note: str = "",
        *,
        label: str | None = None,
        unit: str | None = None,
        category: str | None = None,
    ) -> None:
        d_label, d_unit, d_cat = label_for(key)
        self.stats[key] = Stat(
            key=key,
            value=value,
            quality=quality if value is not None else Q_NA,
            label=label or d_label,
            unit=d_unit if unit is None else unit,
            category=category or d_cat,
            note=note,
        )


# ------------------------------------------------------------------ extraction


def _farm_ids_and_main(
    root: ET.Element | None,
) -> tuple[set[str], ET.Element | None]:
    if root is None:
        return set(), None
    farms = [f for f in root.iter("farm") if f.get("farmId")]
    ids = {f.get("farmId", "") for f in farms}
    main = next((f for f in farms if f.get("farmId") == "1"), farms[0] if farms else None)
    return ids, main


def _extract_farms(c: _Collector, root: ET.Element | None) -> tuple[set[str], str | None]:
    farm_ids, main = _farm_ids_and_main(root)
    if main is None:
        return set(), None
    main_id = main.get("farmId")
    c.put("farms.count", float(len(farm_ids)))
    money = _num(main.get("money"))
    if money is not None:
        c.put("money", money)
    loan = _num(main.get("loan"))
    if loan is not None:
        c.put("loan", loan)

    stats_el = main.find("statistics")
    if stats_el is not None:
        mission_sum = 0.0
        mission_parts = 0
        exact_missions: float | None = None
        for child in stats_el:
            value = _num(child.text)
            if value is None:
                continue
            if child.tag == "playTime":
                c.put("playTime.farm", value / 60.0, unit="h", category="time")
            if child.tag == "missionCount":
                exact_missions = value
            elif _MISSION_COUNT_RE.search(child.tag):
                mission_sum += value
                mission_parts += 1
            mapped = FARM_STAT_MAP.get(child.tag)
            if mapped:
                key, label, unit, cat, scale = mapped
                c.put(key, value * scale, label=label, unit=unit, category=cat)
            else:
                c.put(f"raw.{child.tag}", value)
        if exact_missions is not None:
            c.put("contracts.completed", exact_missions)
        elif mission_parts:
            c.put(
                "contracts.completed",
                mission_sum,
                Q_CALC,
                "Somme des compteurs de missions par type.",
            )

    income = expenses = 0.0
    mission_income = 0.0
    finance_seen = False
    for stats in main.iter("stats"):
        for child in stats:
            value = _num(child.text)
            if value is None:
                continue
            finance_seen = True
            if child.tag == "missionIncome":
                mission_income += value
            if _INCOME_TAG_RE.search(child.tag):
                income += value
            elif _EXPENSE_TAG_RE.search(child.tag):
                expenses += abs(value)
    if finance_seen:
        note = "Somme de l'historique financier de la ferme."
        c.put("finance.income", income, Q_CALC, note)
        c.put("finance.expenses", expenses, Q_CALC, note)
        c.put("finance.profit", income - expenses, Q_CALC, note)
        c.put("finance.missionIncome", mission_income, Q_CALC, note)
    return farm_ids, main_id


def _is_owned(el: ET.Element, farm_ids: set[str], main_id: str | None) -> bool:
    if (el.get("propertyState") or "").upper() == "MISSION":
        return False
    farm_id = el.get("farmId")
    if farm_id is None or not farm_ids:
        return True
    return farm_id == main_id


def _vehicle_brand(filename: str) -> str | None:
    """Brand folder of a base-game path (``data/vehicles/<brand>/<model>/…``)."""
    parts = filename.replace("\\", "/").split("/")
    lowered = [p.lower() for p in parts]
    if "vehicles" in lowered:
        idx = lowered.index("vehicles")
        if idx + 1 < len(parts) - 1:
            return parts[idx + 1].lower()
    return None


def _vehicle_type(filename: str, type_name: str) -> str | None:
    haystack = f"{filename} {type_name}".lower()
    for vtype, words in VEHICLE_TYPE_KEYWORDS:
        if any(w in haystack for w in words):
            return vtype
    return None


def _extract_vehicles(
    c: _Collector, root: ET.Element | None, farm_ids: set[str], main_id: str | None
) -> None:
    if root is None:
        return
    c.complete_prefixes.update({"vehicles.type.", "vehicles.brand."})
    count = 0
    value = 0.0
    brands: dict[str, int] = {}
    types: dict[str, int] = {}
    for veh in root.iter("vehicle"):
        filename = veh.get("filename") or ""
        if not filename or not _is_owned(veh, farm_ids, main_id):
            continue
        count += 1
        value += _num(veh.get("price")) or 0.0
        brand = _vehicle_brand(filename)
        if brand is None and veh.get("modName"):
            brand = (veh.get("modName") or "").lower()
        if brand:
            brands[brand] = brands.get(brand, 0) + 1
        vtype = _vehicle_type(filename, veh.get("typeName") or veh.get("type") or "")
        if vtype:
            types[vtype] = types.get(vtype, 0) + 1
    c.put("vehicles.count", float(count))
    c.put("vehicles.value", value, Q_CALC, "Somme des prix d'achat (sans dépréciation).")
    heur = "Catégorie déduite du nom de fichier : approximatif."
    for brand, n in sorted(brands.items()):
        c.put(f"vehicles.brand.{brand}", float(n), Q_CALC, "Marque déduite du chemin du véhicule.")
    c.put("vehicles.brands", float(len(brands)), Q_CALC, "Marques déduites des chemins.")
    for vtype, n in sorted(types.items()):
        c.put(f"vehicles.type.{vtype}", float(n), Q_CALC, heur)
    c.put("vehicles.types", float(len(types)), Q_CALC, heur)


def _extract_placeables(
    c: _Collector, root: ET.Element | None, farm_ids: set[str], main_id: str | None
) -> None:
    if root is None:
        return
    c.complete_prefixes.update({"animals.", "stock."})
    count = 0
    value = 0.0
    productions = 0
    beehives = 0
    species: dict[str, float] = {}
    stock: dict[str, float] = {}
    for placeable in root.iter("placeable"):
        filename = placeable.get("filename") or ""
        if not filename or not _is_owned(placeable, farm_ids, main_id):
            continue
        count += 1
        value += _num(placeable.get("price")) or 0.0
        if "beehive" in filename.lower():
            beehives += 1
        if next(placeable.iter("productionPoint"), None) is not None:
            productions += 1
        for fill in placeable.iter("fillLevel"):
            fill_type = (fill.get("fillType") or "").strip().lower()
            level = _num(fill.get("fillLevel") or fill.get("level"))
            if fill_type and level:
                stock[fill_type] = stock.get(fill_type, 0.0) + level
        for animal in placeable.iter():
            if animal.tag not in ("animal", "cluster"):
                continue
            sub = animal.get("subType")
            if not sub:
                continue
            sp = sub.split("_", 1)[0].lower()
            n = _num(animal.get("numAnimals")) if animal.tag == "cluster" else None
            species[sp] = species.get(sp, 0.0) + (n if n is not None else 1.0)

    c.put("placeables.count", float(count))
    c.put("placeables.value", value, Q_CALC, "Somme des prix d'achat (sans dépréciation).")
    c.put(
        "productions.count",
        float(productions),
        Q_CALC,
        "Placeables contenant un point de production.",
    )
    c.put("animals.beehives", float(beehives), Q_CALC, "Ruches déduites du nom du placeable.")
    for fill_type, level in sorted(stock.items()):
        c.put(
            f"stock.{fill_type}",
            level,
            Q_CALC,
            "Quantité actuellement stockée dans tes bâtiments (pas un cumul de production).",
        )
    for sp, n in sorted(species.items()):
        c.put(f"animals.{sp}", n)
    c.put("animals.total", sum(species.values()))
    c.put("animals.species", float(len(species)))


def _extract_land(
    c: _Collector, root: ET.Element | None, farm_ids: set[str], main_id: str | None
) -> None:
    if root is None:
        return
    owned = [
        fl for fl in root.iter("farmland") if fl.get("farmId") not in (None, "", "0")
        and (not farm_ids or fl.get("farmId") == main_id)
    ]
    c.put("land.count", float(len(owned)))
    area = 0.0
    found = False
    for fl in owned:
        for attr in ("areaInHa", "areaHa", "hectares"):
            v = _num(fl.get(attr))
            if v is not None:
                area += v
                found = True
                break
    if found:
        c.put("land.area", area, Q_CALC, "Somme des surfaces des parcelles possédées.")


def _extract_crops(c: _Collector, root: ET.Element | None) -> None:
    if root is None:
        return
    c.complete_prefixes.add("crops.fields.")
    fields: dict[str, int] = {}
    for fld in root.iter("field"):
        fruit = fld.get("fruitType") or fld.get("plannedFruit") or ""
        fruit = fruit.strip()
        if fruit and fruit.upper() not in ("UNKNOWN", "NONE", "FALLOW"):
            fields[fruit.lower()] = fields.get(fruit.lower(), 0) + 1
    note = "Champs de toute la carte (la propriété d'un champ n'est pas lisible)."
    for fruit, n in sorted(fields.items()):
        c.put(f"crops.fields.{fruit}", float(n), Q_CALC, note)
    c.put("crops.growing", float(len(fields)), Q_CALC, note)


def _extract_time(c: _Collector, career: ET.Element | None, env: ET.Element | None) -> None:
    if career is not None:
        play = career.find("statistics/playTime")
        minutes = _num(play.text) if play is not None else None
        if minutes is not None:
            c.put("playTime", minutes / 60.0)
        money = career.find("statistics/money")
        if money is not None and "money" not in c.stats:
            value = _num(money.text)
            if value is not None:
                c.put("money", value)
    if "playTime" not in c.stats and "playTime.farm" in c.stats:
        farm_time = c.stats["playTime.farm"]
        c.put("playTime", farm_time.value)
    c.stats.pop("playTime.farm", None)
    if env is not None:
        day = _num(env.findtext("currentDay"))
        if day is not None:
            c.put("daysPlayed", day)


def _finalise(c: _Collector) -> None:
    money = c.stats.get("money")
    if money and money.value is not None:
        loan = c.stats.get("loan")
        veh = c.stats.get("vehicles.value")
        plc = c.stats.get("placeables.value")
        total = money.value - (loan.value if loan and loan.value else 0.0)
        total += (veh.value if veh and veh.value else 0.0)
        total += (plc.value if plc and plc.value else 0.0)
        c.put(
            "netWorth",
            total,
            Q_CALC,
            "Argent − emprunt + prix d'achat des véhicules et bâtiments. "
            "La valeur des terres n'est pas incluse.",
        )
    # Statistics the savegame cannot provide reliably are listed explicitly
    # so objectives on them show as "non disponible" rather than 0.
    if "land.area" not in c.stats:
        c.put(
            "land.area",
            None,
            note="La surface n'est pas écrite dans la sauvegarde : saisie manuelle possible.",
        )
    for key in ("vine.area", "vine.grapesHarvested", "olive.olivesHarvested", "vine.wineProduced", "vine.wineSold", "vine.revenue",
                "olive.area", "olive.oilProduced", "olive.oilSold", "olive.revenue"):
        if key not in c.stats:
            c.put(key, None, note="Non écrit dans la sauvegarde : saisie manuelle possible.")
    if "contracts.completed" not in c.stats:
        c.put(
            "contracts.completed",
            None,
            note="Compteur de contrats introuvable dans la sauvegarde.",
        )


def extract_stats(savegame_dir: Path) -> StatsSnapshot:
    """Read every available statistic from a savegame folder."""
    c = _Collector()
    career = _parse_xml(savegame_dir / "careerSavegame.xml")
    farm_ids, main_id = _extract_farms(c, _parse_xml(savegame_dir / "farms.xml"))
    _extract_vehicles(c, _parse_xml(savegame_dir / "vehicles.xml"), farm_ids, main_id)
    _extract_placeables(c, _parse_xml(savegame_dir / "placeables.xml"), farm_ids, main_id)
    _extract_land(c, _parse_xml(savegame_dir / "farmlands.xml"), farm_ids, main_id)
    _extract_crops(c, _parse_xml(savegame_dir / "fields.xml"))
    _extract_time(c, career, _parse_xml(savegame_dir / "environment.xml"))
    _finalise(c)
    return StatsSnapshot(
        savegame=savegame_dir.name,
        taken_at=datetime.now().isoformat(timespec="seconds"),
        stats=c.stats,
        complete_prefixes=c.complete_prefixes,
    )


def apply_manual(
    snapshot: StatsSnapshot, manual: dict[str, float]
) -> StatsSnapshot:
    """Overlay user-typed values on statistics the savegame cannot provide.

    A manual value never overrides a statistic read from the savegame
    (``auto``); it replaces ``calc`` / ``na`` ones.
    """
    for key, value in manual.items():
        existing = snapshot.stats.get(key)
        if existing is not None and existing.quality == Q_AUTO:
            continue
        label, unit, category = label_for(key)
        snapshot.stats[key] = Stat(
            key=key,
            value=float(value),
            quality=Q_MANUAL,
            label=existing.label if existing and existing.label else label,
            unit=existing.unit if existing else unit,
            category=existing.category if existing else category,
            note="Valeur saisie manuellement.",
        )
    return snapshot
