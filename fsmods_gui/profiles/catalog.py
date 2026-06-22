"""Scan the mod library and parse each ``.zip``'s ``modDesc.xml``.

The result is cached on disk under ``<library_dir>/cache/index.json`` and keyed
by ``(size, mtime_ns)`` so a full rescan only re-parses zips that actually changed.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    import logging
    logging.getLogger(__name__).warning("Pillow n'est pas installe. Les icones de mods (.dds) ne seront pas visibles.")
    HAS_PILLOW = False

CACHE_FILE_NAME = "index.json"
CACHE_SCHEMA_VERSION = 21


# Giants ``storeData/category`` (first token, lowercased) → (French family, French
# precise type). Built from the real vocabulary found across the library. The
# *family* feeds the broad category filter; the *type* is the fine label shown
# under each mod (e.g. "Véhicule · Tracteur"). Unknown categories fall back to a
# keyword heuristic (:func:`_fallback_family`).
_FS_CATEGORY_FR: dict[str, tuple[str, str]] = {
    # --- Tracteurs & automoteurs ---
    "tractorss": ("Véhicule", "Tracteur"),
    "tractorsm": ("Véhicule", "Tracteur"),
    "tractorsl": ("Véhicule", "Tracteur"),
    "tractors": ("Véhicule", "Tracteur"),
    "wheelloaders": ("Véhicule", "Chargeuse sur pneus"),
    "telehandlers": ("Véhicule", "Télescopique"),
    "skidsteers": ("Véhicule", "Chargeuse compacte"),
    "trucks": ("Véhicule", "Camion"),
    "cars": ("Véhicule", "Voiture"),
    "pickups": ("Véhicule", "Pick-up"),
    # --- Récolte ---
    "harvesters": ("Véhicule", "Moissonneuse"),
    "forageharvesters": ("Véhicule", "Ensileuse"),
    "forestryharvesters": ("Véhicule", "Abatteuse forestière"),
    "cutters": ("Véhicule", "Coupe"),
    "cuttertrailers": ("Véhicule", "Chariot de coupe"),
    "cornheaders": ("Véhicule", "Bec à maïs"),
    "forageharvestercutters": ("Véhicule", "Bec d'ensilage"),
    "potatoharvesting": ("Véhicule", "Récolteuse de pommes de terre"),
    "beetharvesting": ("Véhicule", "Récolteuse de betteraves"),
    "cottonvehicles": ("Véhicule", "Matériel coton"),
    # --- Remorques & transport ---
    "trailers": ("Véhicule", "Remorque"),
    "trailerssemi": ("Véhicule", "Semi-remorque"),
    "trailersflatbed": ("Véhicule", "Remorque plateau"),
    "trailerschangingsystem": ("Véhicule", "Remorque porte-caisson"),
    "tippers": ("Véhicule", "Benne"),
    "augerwagons": ("Véhicule", "Trémie"),
    "loaderwagons": ("Véhicule", "Autochargeuse"),
    "animaltransport": ("Véhicule", "Bétaillère"),
    "lowloaders": ("Véhicule", "Porte-engin"),
    # --- Travail du sol & semis ---
    "cultivators": ("Véhicule", "Déchaumeur"),
    "plows": ("Véhicule", "Charrue"),
    "subsoilers": ("Véhicule", "Décompacteur"),
    "rollers": ("Véhicule", "Rouleau"),
    "powerharrows": ("Véhicule", "Herse rotative"),
    "seeders": ("Véhicule", "Semoir"),
    "planters": ("Véhicule", "Planteuse"),
    "sowingmachines": ("Véhicule", "Semoir"),
    # --- Fertilisation & pulvérisation ---
    "sprayers": ("Véhicule", "Pulvérisateur"),
    "fertilizerspreaders": ("Véhicule", "Épandeur d'engrais"),
    "manurespreaders": ("Véhicule", "Épandeur à fumier"),
    "spreaders": ("Véhicule", "Épandeur"),
    "slurrytanks": ("Véhicule", "Tonne à lisier"),
    "slurrytools": ("Véhicule", "Outil à lisier"),
    # --- Fourrage / fenaison / pressage ---
    "mowers": ("Véhicule", "Faucheuse"),
    "windrowers": ("Véhicule", "Andaineur"),
    "tedders": ("Véhicule", "Faneuse"),
    "balersround": ("Véhicule", "Presse à balles rondes"),
    "balerssquare": ("Véhicule", "Presse à balles carrées"),
    "balers": ("Véhicule", "Presse"),
    "balewrappers": ("Véhicule", "Enrubanneuse"),
    "baleloaders": ("Véhicule", "Chargeur de balles"),
    "foragemixers": ("Véhicule", "Mélangeuse"),
    # --- Chargeurs & outils portés ---
    "frontloaders": ("Véhicule", "Chargeur frontal"),
    "frontloadertools": ("Véhicule", "Outil de chargeur"),
    "wheelloadertools": ("Véhicule", "Outil de chargeuse"),
    "telehandlertools": ("Véhicule", "Outil de télescopique"),
    "skidsteertools": ("Véhicule", "Outil de chargeuse compacte"),
    # --- Spécifiques ---
    "weights": ("Véhicule", "Masse"),
    "grapetools": ("Véhicule", "Outil viticole"),
    "olivetools": ("Véhicule", "Outil oléicole"),
    "woodharvesting": ("Véhicule", "Matériel forestier"),
    "woodtransport": ("Véhicule", "Transport de bois"),
    "forestrytools": ("Véhicule", "Outil forestier"),
    # --- Bâtiments / placeables ---
    "sheds": ("Bâtiment", "Hangar"),
    "farmhouses": ("Bâtiment", "Maison"),
    "silos": ("Bâtiment", "Silo"),
    "siloextensions": ("Bâtiment", "Extension de silo"),
    "storages": ("Bâtiment", "Stockage"),
    "productionpoints": ("Bâtiment", "Production"),
    "placeablefactories": ("Bâtiment", "Production"),
    "animalpens": ("Bâtiment", "Bâtiment d'élevage"),
    "sellingpoints": ("Bâtiment", "Point de vente"),
    "generators": ("Bâtiment", "Production d'énergie"),
    "windturbines": ("Bâtiment", "Éolienne"),
    "solarpanels": ("Bâtiment", "Panneau solaire"),
    "beehives": ("Bâtiment", "Rucher"),
    "fences": ("Bâtiment", "Clôture"),
    "greenhouses": ("Bâtiment", "Serre"),
    "gardening": ("Bâtiment", "Jardinage"),
    "decoration": ("Bâtiment", "Décoration"),
    "placeablemisc": ("Bâtiment", "Aménagement divers"),
    # --- Objets / consommables ---
    "pallets": ("Objet", "Palette"),
    "bales": ("Objet", "Balle"),
    "ibc": ("Objet", "Cuve IBC"),
    "barrels": ("Objet", "Fût"),
    "bigbags": ("Objet", "Big-bag"),
    "trees": ("Objet", "Arbre"),
    "misc": ("Objet", "Divers"),
}

# Pretty display names for the most common Giants brands (key = lowercased,
# spaces removed). Unknown brands keep their original spelling; "none" → no brand.
_BRAND_DISPLAY: dict[str, str] = {
    "johndeere": "John Deere",
    "caseih": "Case IH",
    "newholland": "New Holland",
    "masseyferguson": "Massey Ferguson",
    "claas": "CLAAS",
    "fendt": "Fendt",
    "valtra": "Valtra",
    "deutzfahr": "Deutz-Fahr",
    "krone": "Krone",
    "poettinger": "Pöttinger",
    "kuhn": "Kuhn",
    "kverneland": "Kverneland",
    "horsch": "Horsch",
    "lemken": "Lemken",
    "amazone": "Amazone",
    "vaederstad": "Väderstad",
    "fliegl": "Fliegl",
    "krampe": "Krampe",
    "lizard": "Lizard",
    "lizardlogistics": "Lizard Logistics",
    "lizardmotors": "Lizard Motors",
    "man": "MAN",
    "volvo": "Volvo",
    "mack": "Mack",
    "scania": "Scania",
    "iveco": "Iveco",
    "rudolfhoermann": "Rudolf Hörmann",
    "samsonagro": "Samson Agro",
    "rinoagro": "Rino Agro",
    "randon": "Randon",
    "unia": "Unia",
    "farmtech": "Farmtech",
    "fortschritt": "Fortschritt",
    "macdon": "MacDon",
    "vicon": "Vicon",
    "demco": "Demco",
    "kaweco": "Kaweco",
    "euromilk": "EuroMilk",
    "andersongroup": "Anderson Group",
    "corteva": "Corteva",
    "helm": "Helm",
}

_VEHICLE_PATH_HINTS = (
    "vehicle", "tractor", "truck", "car", "trailer", "harvest", "mower", "baler",
    "loader", "plow", "cultivator", "seeder", "planter", "sprayer", "tank",
    "header", "cutter", "weight", "tipper", "tool", "implement",
)
_PLACEABLE_PATH_HINTS = (
    "placeable", "building", "shed", "house", "barn", "silo", "production",
    "stable", "fence", "gate", "garage", "hall", "farm", "workshop", "station",
    "storage", "greenhouse", "pen",
)
_VEHICLE_CAT_KW = (
    "tractor", "truck", "car", "harvest", "mower", "trailer", "loader",
    "telehandler", "skidsteer", "wagon", "baler", "cutter", "cultivator", "plow",
    "seeder", "planter", "sprayer", "tank", "spreader", "weight", "forestry",
    "header", "roller", "tedder", "windrower", "subsoiler", "tool", "grape",
    "olive", "wood", "tipper", "transport", "pickup", "harrow",
)
_PLACEABLE_CAT_KW = (
    "placeable", "shed", "silo", "production", "factory", "animal", "stable",
    "fence", "gate", "garden", "generator", "hall", "farm", "house", "barn",
    "bee", "selling", "pen", "storage", "greenhouse", "windturbine", "solar",
    "decoration",
)
_OBJECT_CAT_KW = ("pallet", "bale", "ibc", "barrel", "bigbag", "misc", "object")


def _norm_brand(brand: str | None) -> str | None:
    """Normalize a raw brand to a display name; "none"/empty → ``None``."""
    if not brand:
        return None
    cleaned = brand.strip()
    if not cleaned or cleaned.lower() == "none":
        return None
    key = cleaned.lower().replace(" ", "")
    return _BRAND_DISPLAY.get(key, cleaned)


def _fallback_family(token: str, has_brand: bool) -> tuple[str, str | None]:
    """Best-effort family for an FS category not in :data:`_FS_CATEGORY_FR`."""
    if any(k in token for k in _PLACEABLE_CAT_KW):
        return ("Bâtiment", None)
    if any(k in token for k in _OBJECT_CAT_KW):
        return ("Objet", None)
    if has_brand or any(k in token for k in _VEHICLE_CAT_KW):
        return ("Véhicule", None)
    return ("Objet", None)


def _classify(
    fs_categories: list[str], root_node_types: set[str], has_brand: bool
) -> tuple[str, str | None]:
    """Map a mod's store categories to (French family, French precise type).

    ``fs_categories`` are raw ``storeData/category`` strings (possibly several,
    one per store item, and possibly space-separated lists). The dominant
    first-token wins; unknown tokens fall back to a keyword heuristic, and a mod
    with no parsable category leans on its ``rootNode`` / brand.
    """
    tally: Counter[str] = Counter()
    for raw in fs_categories:
        parts = raw.split()
        if parts:
            tally[parts[0]] += 1
    if tally:
        dominant = tally.most_common(1)[0][0]
        return _FS_CATEGORY_FR.get(dominant) or _fallback_family(dominant, has_brand)
    if "Véhicule" in root_node_types:
        return ("Véhicule", None)
    if "Bâtiment" in root_node_types:
        return ("Bâtiment", None)
    if has_brand:
        return ("Véhicule", None)
    return ("Objet", None)


@dataclass
class CatalogEntry:
    filename: str
    title: str
    version: str
    is_map: bool = False
    category: str = "Autre"
    brand: str | None = None
    type: str | None = None
    title_en: str | None = None
    title_fr: str | None = None
    description_en: str | None = None
    description_fr: str | None = None
    author: str | None = None
    icon_filename: str | None = None
    icon_cache_path: str | None = None
    requires: list[str] = field(default_factory=list)  # modNames declared in <dependencies>
    size_bytes: int = 0
    mtime_ns: int = 0
    error: str | None = None

    @property
    def display_title(self) -> str:
        return self.title or self.filename

    @property
    def mod_id(self) -> str:
        """FS mod identity = the ``.zip`` filename without extension.

        Farming Simulator references mods (including ``<dependencies>``) by this
        name, so it doubles as the key for dependency resolution and as the
        starting point for duplicate detection.
        """
        return Path(self.filename).stem

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CatalogEntry:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Catalog:
    mods_dir: Path
    entries: dict[str, CatalogEntry] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.entries.values())

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, filename: str) -> bool:
        return filename in self.entries

    def get(self, filename: str) -> CatalogEntry | None:
        return self.entries.get(filename)

    def maps(self) -> list[CatalogEntry]:
        return [e for e in self.entries.values() if e.is_map]

    def save_cache(self, cache_path: Path) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": CACHE_SCHEMA_VERSION,
            "mods_dir": str(self.mods_dir),
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
        }
        cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_cache(cache_path: Path) -> dict[str, CatalogEntry]:
    if not cache_path.is_file():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("schema") != CACHE_SCHEMA_VERSION:
        return {}
    raw = data.get("entries") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, CatalogEntry] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            try:
                out[key] = CatalogEntry.from_dict(value)
            except TypeError:
                continue
    return out


_ICON_EXTS = (".dds", ".png", ".jpg", ".jpeg")


def _extract_icon(
    zf: zipfile.ZipFile, icon: str, zip_stem: str, icon_cache_dir: Path
) -> str | None:
    """Extract a mod's ``iconFilename`` from ``zf`` into the icon cache.

    Returns the cached file path, or ``None`` when the icon can't be located or
    decoded. Tolerant of the usual Farming Simulator quirks: case differences,
    an extension in ``modDesc`` that doesn't match the stored file (``.png`` vs
    ``.dds``), and icons tucked away in a sub-folder of the zip.
    """
    try:
        icon_rel = icon.replace("\\", "/").strip().lstrip("/")
        if icon_rel.startswith("../") or ":" in icon_rel:
            return None
        icon_ext = Path(icon_rel).suffix.lower()
        target_ext = ".png" if HAS_PILLOW else (icon_ext or ".dds")
        target_path = icon_cache_dir / f"{zip_stem}{target_ext}"

        zip_names = {n.lower(): n for n in zf.namelist()}
        stem = Path(icon_rel).stem.lower()

        # 1. Exact path match (case-insensitive).
        real_name = zip_names.get(icon_rel.lower())
        # 2. Same path, swapped extension (icon.png declared, icon.dds stored).
        if not real_name:
            base_rel = icon_rel.rsplit(".", 1)[0].lower()
            for ext in _ICON_EXTS:
                if (alt := f"{base_rel}{ext}") in zip_names:
                    real_name = zip_names[alt]
                    break
        # 3. Same basename anywhere in the zip (icon lives in a sub-folder).
        if not real_name:
            for low, orig in zip_names.items():
                pp = Path(low)
                if pp.stem == stem and pp.suffix in _ICON_EXTS:
                    real_name = orig
                    break
        if not real_name:
            return None

        with zf.open(real_name) as src:
            if HAS_PILLOW:
                with Image.open(src) as img:
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    img.save(target_path, "PNG")
            else:
                with open(target_path, "wb") as dst:
                    dst.write(src.read())
        return str(target_path)
    except Exception:
        return None


def _read_moddesc_from_zip(zip_path: Path, icon_cache_dir: Path | None = None) -> CatalogEntry:
    stat = zip_path.stat()
    base = CatalogEntry(
        filename=zip_path.name,
        title=zip_path.stem,
        version="0.0.0.0",
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )
    try:
        with zipfile.ZipFile(zip_path) as zf:
            try:
                with zf.open("modDesc.xml") as fh:
                    raw = fh.read()
            except KeyError:
                base.error = "modDesc.xml manquant"
                return base

            try:
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                base.error = f"modDesc XML invalide : {exc}"
                return base

            title_en = (root.findtext("title/en") or "").strip() or None
            title_fr = (root.findtext("title/fr") or "").strip() or None
            title = title_fr or title_en or zip_path.stem
            
            desc_en = (root.findtext("description/en") or "").strip() or None
            desc_fr = (root.findtext("description/fr") or "").strip() or None
            
            version = (root.findtext("version") or "0.0.0.0").strip() or "0.0.0.0"
            author = (root.findtext("author") or "").strip() or None
            icon = (root.findtext("iconFilename") or "").strip() or None
            is_map = root.find("maps/map") is not None
            # Dependencies: <dependencies><dependency>FS25_OtherMod</dependency></dependencies>
            # The text is a modName (= the other mod's .zip stem).
            requires: list[str] = []
            deps_node = root.find("dependencies")
            if deps_node is not None:
                for dep in deps_node.findall("dependency"):
                    dep_name = (dep.text or "").strip()
                    if dep_name and dep_name not in requires:
                        requires.append(dep_name)
            brand = _norm_brand(
                root.findtext("brand") or root.findtext("brands/brand")
            )
            type_tag = None

            if is_map:
                category = "Carte"
            elif (store_items := root.find("storeItems")) is not None:
                # Follow each storeItem to its XML to read the real Giants store
                # category + brand, then map to a French family/type.
                fs_categories: list[str] = []
                root_node_types: set[str] = set()
                for item in store_items.findall("storeItem"):
                    rn = (item.get("rootNode") or "").lower()
                    if rn == "vehicle":
                        root_node_types.add("Véhicule")
                    elif rn == "placeable":
                        root_node_types.add("Bâtiment")
                    xml_path = item.get("xmlFilename") or item.get("filename")
                    if not xml_path:
                        continue
                    rel_path = xml_path.replace("\\", "/").strip()
                    try:
                        with zf.open(rel_path) as item_fh:
                            item_root = ET.fromstring(item_fh.read())
                    except Exception:
                        # XML unreadable → fall back to a path keyword hint.
                        xp = rel_path.lower()
                        if any(k in xp for k in _PLACEABLE_PATH_HINTS):
                            root_node_types.add("Bâtiment")
                        elif any(k in xp for k in _VEHICLE_PATH_HINTS):
                            root_node_types.add("Véhicule")
                        continue
                    cat = (item_root.findtext("storeData/category") or "").strip().lower()
                    if cat:
                        fs_categories.append(cat)
                    if not brand:
                        brand = _norm_brand(item_root.findtext("storeData/brand"))

                category, type_tag = _classify(
                    fs_categories, root_node_types, brand is not None
                )
            elif brand is not None:
                category = "Véhicule"
            elif root.find("extraSourceFiles") is not None:
                category = "Script"
            else:
                category = "Divers"

            # ---- Extract icon if requested
            if icon and icon_cache_dir:
                base.icon_cache_path = _extract_icon(
                    zf, icon, zip_path.stem, icon_cache_dir
                )

    except (zipfile.BadZipFile, OSError) as exc:
        base.error = f"zip illisible : {exc}"
        return base

    base.title = title
    base.title_en = title_en
    base.title_fr = title_fr
    base.description_en = desc_en
    base.description_fr = desc_fr
    base.version = version
    base.author = author
    base.icon_filename = icon
    base.is_map = is_map
    base.category = category
    base.brand = brand
    base.type = type_tag
    base.requires = requires
    return base


def scan_library(
    mods_dir: Path, cache_path: Path | None = None, *, use_cache: bool = True
) -> Catalog:
    """Scan ``mods_dir`` for ``.zip`` files and return a :class:`Catalog`.

    ``cache_path`` is consulted to skip re-parsing zips whose ``(size, mtime_ns)``
    hasn't changed. When the scan succeeds, the cache is rewritten in place.
    """
    if not mods_dir.is_dir():
        raise FileNotFoundError(f"Library mods dir not found: {mods_dir}")
    
    icon_cache_dir = None
    if cache_path:
        icon_cache_dir = cache_path.parent / "icons"
        icon_cache_dir.mkdir(parents=True, exist_ok=True)

    cached: dict[str, CatalogEntry] = (
        _load_cache(cache_path) if (cache_path and use_cache) else {}
    )
    fresh: dict[str, CatalogEntry] = {}
    for zip_path in sorted(mods_dir.iterdir()):
        if zip_path.suffix.lower() != ".zip" or not zip_path.is_file():
            continue
        stat = zip_path.stat()
        prior = cached.get(zip_path.name)
        if (
            prior is not None
            and prior.size_bytes == stat.st_size
            and prior.mtime_ns == stat.st_mtime_ns
        ):
            # Self-heal a stale cache: an entry may declare an icon but have no
            # (or a vanished) cached thumbnail because extraction failed in an
            # older run. Re-extract just the icon without re-parsing modDesc.
            if (
                icon_cache_dir is not None
                and prior.icon_filename
                and (
                    not prior.icon_cache_path
                    or not Path(prior.icon_cache_path).is_file()
                )
            ):
                try:
                    with zipfile.ZipFile(zip_path) as zf:
                        prior.icon_cache_path = _extract_icon(
                            zf, prior.icon_filename, zip_path.stem, icon_cache_dir
                        )
                except (zipfile.BadZipFile, OSError):
                    pass
            fresh[zip_path.name] = prior
            continue
        fresh[zip_path.name] = _read_moddesc_from_zip(zip_path, icon_cache_dir=icon_cache_dir)
    catalog = Catalog(mods_dir=mods_dir, entries=fresh)
    if cache_path is not None:
        catalog.save_cache(cache_path)
    return catalog
