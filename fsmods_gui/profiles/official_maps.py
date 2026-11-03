"""Official FS25 maps (base game + DLC): names and thumbnails.

A profile normally points at its map through ``map_mod`` (a mod zip, whose icon
comes from the catalog). Official maps are not mods, so a profile can name one
with ``official_map`` (the savegame ``<mapId>``), and its thumbnail is found here:

* base-game maps: ``<install>/data/maps/<map>/textures/ui/preview.dds``;
* DLC maps: the ``.dlc`` is encrypted, so the picture comes from the image Steam
  caches for the DLC (``<steam>/appcache/librarycache/<appid>/…/header.jpg``),
  cropped to its scenery (the right part carries the logo / title).

Thumbnails are converted once to PNG in the library cache. Best effort: no
Pillow, no Steam, unexpected layout → ``None`` (the GUI shows its default icon).

Pure logic, no Qt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image

    HAS_PILLOW = True
except ImportError:  # pragma: no cover - Pillow is a hard dependency
    HAS_PILLOW = False

log = logging.getLogger(__name__)

THUMB_SIZE = 256


@dataclass(frozen=True)
class OfficialMap:
    map_id: str  # careerSavegame <mapId> (MapUS seen in a real savegame)
    title: str
    folder: str = ""  # base game: data/maps/<folder>
    dlc: str = ""  # DLC file stem in <install>/pdlc
    steam_appid: int = 0
    # Scenery of the DLC Steam header (fractions of width/height), away from
    # the purple "download" ribbon and the title block.
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    @property
    def is_dlc(self) -> bool:
        return bool(self.dlc)

    @property
    def label(self) -> str:
        return f"{self.title} (DLC)" if self.is_dlc else f"{self.title} (carte officielle)"


OFFICIAL_MAPS: tuple[OfficialMap, ...] = (
    OfficialMap("MapUS", "Riverbend Springs", folder="mapUS"),
    OfficialMap("MapEU", "Zielonka", folder="mapEU"),
    OfficialMap("MapAS", "Hutan Pantai", folder="mapAS"),
    OfficialMap(
        "pdlc_highlandsFishingPack.HighlandsFishingMap",
        "Kinlaig",
        dlc="highlandsFishingPack",
        steam_appid=3453970,  # FS25 – Highlands Fishing Expansion
        crop=(0.272, 0.14, 0.576, 0.79),
    ),
)


def official_map(map_id: str | None) -> OfficialMap | None:
    """The official map with this savegame id (case-insensitive), if it is one."""
    if not map_id:
        return None
    low = map_id.lower()
    return next(
        (m for m in OFFICIAL_MAPS if m.map_id.lower() == low or (m.folder and m.folder.lower() == low)),
        None,
    )


def steam_root(install_dir: Path | None) -> Path | None:
    """``<steam>`` for an install under ``<steam>/steamapps/common/<game>``."""
    if install_dir is None:
        return None
    parts = install_dir.parts
    if len(parts) >= 3 and parts[-3].lower() == "steamapps" and parts[-2].lower() == "common":
        return install_dir.parents[2]
    return None


def _source_image(m: OfficialMap, install_dir: Path | None) -> Path | None:
    if m.folder and install_dir is not None:
        for name in ("preview.dds", "preview.png"):
            path = install_dir / "data" / "maps" / m.folder / "textures" / "ui" / name
            if path.is_file():
                return path
        return None
    root = steam_root(install_dir)
    if m.steam_appid and root is not None:
        cache = root / "appcache" / "librarycache" / str(m.steam_appid)
        if cache.is_dir():
            hits = sorted(cache.rglob("header.jpg"))
            return hits[0] if hits else None
    return None


def official_map_thumbnail(
    map_id: str | None, install_dir: Path | None, cache_dir: Path | None
) -> Path | None:
    """PNG thumbnail of an official map (created once in ``cache_dir``), or None."""
    m = official_map(map_id)
    if m is None or cache_dir is None or not HAS_PILLOW:
        return None
    target = cache_dir / "official_maps" / f"{m.map_id}.png"
    if target.is_file():
        return target
    source = _source_image(m, install_dir)
    if source is None:
        return None
    try:
        with Image.open(source) as img:
            img = img.convert("RGB")
            if m.crop != (0.0, 0.0, 1.0, 1.0):
                w, h = img.size
                left, top, right, bottom = m.crop
                img = img.crop((round(left * w), round(top * h), round(right * w), round(bottom * h)))
            scale = THUMB_SIZE / max(img.size)  # down- or up-scale (Steam crop is small)
            img = img.resize(
                (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                Image.Resampling.LANCZOS,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target, "PNG")
    except (OSError, ValueError) as exc:
        log.warning("Vignette de %s illisible : %s", m.title, exc)
        return None
    return target
