"""Scan the mod library and parse each ``.zip``'s ``modDesc.xml``.

The result is cached on disk under ``<library_dir>/cache/index.json`` and keyed
by ``(size, mtime_ns)`` so a full rescan only re-parses zips that actually changed.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
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
CACHE_SCHEMA_VERSION = 19


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
    size_bytes: int = 0
    mtime_ns: int = 0
    error: str | None = None

    @property
    def display_title(self) -> str:
        return self.title or self.filename

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
            brand = (root.findtext("brand") or root.findtext("brands/brand") or "").strip() or None
            has_brands = brand is not None
            type_tag = None

            if is_map:
                category = "Carte"
            elif (store_items := root.find("storeItems")) is not None:
                # Deep scan: follow storeItems to find real category tags
                found_fs_categories = set()
                found_types = set()
                for item in store_items.findall("storeItem"):
                    xml_path = item.get("xmlFilename") or item.get("filename")
                    root_node = (item.get("rootNode") or "").lower()
                    
                    if root_node == "vehicle":
                        found_types.add("Véhicule")
                    elif root_node == "placeable":
                        found_types.add("Bâtiment")

                    if xml_path:
                        # Canonicalize path in zip
                        rel_path = xml_path.replace("\\", "/").strip()
                        try:
                            with zf.open(rel_path) as item_fh:
                                item_root = ET.fromstring(item_fh.read())
                                cat = item_root.findtext("storeData/category")
                                if cat:
                                    found_fs_categories.add(cat.lower())
                                    if not type_tag:
                                        type_tag = cat.lower()
                                
                                # Try to get brand from item XML if modDesc didn't have it
                                if not brand:
                                    brand = (item_root.findtext("storeData/brand") or "").strip() or None
                        except Exception:
                            # Fallback to path-based hints if XML reading fails
                            xp = xml_path.lower()
                            if any(k in xp for k in ("vehicle", "tool", "implement", "car", "tractor", "truck", "trailer", "harvester", "mower", "baler", "loader", "plow", "cultivator", "seeder", "planter", "sprayer", "tanker", "header", "cutter", "weight", "fork", "tipper", "defender", "jeep", "pickup", "magnum", "fendt", "deere", "claas", "massey", "valtra", "holland", "jcb", "kubota", "man", "scania", "iveco", "volvo")):
                                found_types.add("Véhicule")
                            elif any(k in xp for k in ("placeable", "building", "shed", "house", "barn", "silo", "production", "stable", "cow", "pig", "sheep", "chicken", "greenhouse", "fence", "gate", "garage", "hall", "farm", "workshop", "station", "storage", "tank")):
                                found_types.add("Bâtiment")

                # Decision making
                if found_fs_categories:
                    category = "Objet"  # default
                    for fs_cat in found_fs_categories:
                        fsc = fs_cat.lower()
                        # 1. Véhicules & Outils (très large pour couvrir les catégories combinées)
                        if any(k in fsc for k in (
                            "tractor", "truck", "car", "harvester", "mower", "trailer", "loader", 
                            "telehandler", "skidsteer", "animaltransport", "wagon", "baler", "cutter",
                            "cultivator", "plow", "seeder", "planter", "sprayer", "tanker", "spreader", 
                            "weight", "forestry", "winter", "leveler", "tool", "implement", "harrow",
                            "subsoiler", "roller", "grape", "olive", "pick", "wood", "header", 
                            "potato", "slurry", "tank", "barrel", "transport"
                        )):
                            category = "Véhicule"
                            break
                        # 2. Bâtiments & Ferme
                        if any(k in fsc for k in (
                            "placeable", "shed", "silo", "production", "factory", "animalhouse", 
                            "stable", "fence", "gate", "garden", "generator", "hall", "farm", 
                            "workshop", "storage", "house", "barn", "bee", "selling", "pen"
                        )):
                            category = "Bâtiment"
                    
                    # Special case for misc/objects which should stay in "Objet" 
                    # unless a vehicle keyword was already found above
                    if category == "Objet" and any(k in fsc for k in ("misc", "object", "pallet", "decoration")):
                        category = "Objet"
                    
                    # If still "Objet" but we have a brand or a fallback type said it's a vehicle
                    if category == "Objet" and (has_brands or "Véhicule" in found_types):
                        category = "Véhicule"

                elif "Véhicule" in found_types:
                    category = "Véhicule"
                elif "Bâtiment" in found_types:
                    category = "Bâtiment"
                elif has_brands:
                    category = "Véhicule"
                else:
                    category = "Objet"
            elif has_brands:
                category = "Véhicule"
            elif root.find("extraSourceFiles") is not None:
                category = "Script"
            else:
                category = "Divers"

            # ---- Extract icon if requested
            if icon and icon_cache_dir:
                try:
                    icon_rel = icon.replace("\\", "/").strip().lstrip("/")
                    if not (icon_rel.startswith("../") or ":" in icon_rel):
                        icon_ext = Path(icon_rel).suffix.lower()
                        target_ext = ".png" if HAS_PILLOW else icon_ext
                        target_path = icon_cache_dir / f"{zip_path.stem}{target_ext}"
                        
                        # Try to find the file (handling case sensitivity and common extensions)
                        zip_names = {n.lower(): n for n in zf.namelist()}
                        
                        # 1. Try exact match (case insensitive)
                        real_name = zip_names.get(icon_rel.lower())
                        
                        # 2. Try swapping common extensions if not found (e.g. icon.png -> icon.dds)
                        if not real_name:
                            stem = Path(icon_rel).stem.lower()
                            for ext in (".dds", ".png", ".jpg", ".jpeg"):
                                if (alt := f"{stem}{ext}") in zip_names:
                                    real_name = zip_names[alt]
                                    break
                        
                        if real_name:
                            try:
                                with zf.open(real_name) as src:
                                    if HAS_PILLOW:
                                        with Image.open(src) as img:
                                            if img.mode != "RGBA":
                                                img = img.convert("RGBA")
                                            img.save(target_path, "PNG")
                                    else:
                                        with open(target_path, "wb") as dst:
                                            dst.write(src.read())
                                base.icon_cache_path = str(target_path)
                            except Exception:
                                pass
                except Exception:
                    pass

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
            fresh[zip_path.name] = prior
            continue
        fresh[zip_path.name] = _read_moddesc_from_zip(zip_path, icon_cache_dir=icon_cache_dir)
    catalog = Catalog(mods_dir=mods_dir, entries=fresh)
    if cache_path is not None:
        catalog.save_cache(cache_path)
    return catalog
