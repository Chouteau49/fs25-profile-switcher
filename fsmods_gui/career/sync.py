"""Synchronise a career with its FS25 savegame (read stats → recompute objectives → save)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..profiles.official_maps import official_map
from ..profiles.savegame_audit import list_savegames, parse_savegame
from .formatting import format_stat
from .objectives import MODE_OFF, Objective
from .stats import Q_NA, StatsSnapshot, apply_manual, extract_stats, savegame_map_id
from .store import Career, CareerError


@dataclass
class SyncReport:
    ok: bool = False
    message: str = ""
    snapshot: StatsSnapshot | None = None
    detected: list[str] = field(default_factory=list)
    newly_completed: list[Objective] = field(default_factory=list)
    newly_unlocked: list[Objective] = field(default_factory=list)


def _detected_lines(snapshot: StatsSnapshot) -> list[str]:
    lines = []
    for key in ("land.area", "land.count", "vehicles.count", "animals.total",
                "contracts.completed", "productions.count"):
        stat = snapshot.get(key)
        if stat and (stat.value is not None or stat.partial is not None):
            suffix = " (incomplète)" if stat.value is None else ""
            lines.append(f"{format_stat(stat)} — {stat.label.lower()}{suffix}")
    return lines


def sync_career(
    career: Career,
    user_dir: Path,
    install_dir: Path | None = None,
    library_mods_dir: Path | None = None,
) -> SyncReport:
    """Run the full sync. Never raises on missing data: the report explains why.

    The tracked farm (``settings.farm``) feeds the dashboard; every other farm an
    objective is bound to gets its own snapshot. ``install_dir`` (game folder) and
    ``library_mods_dir`` let vehicle types / brands and the map's parcel areas be read
    even when the profile's mods are not currently in the game's mods folder.
    """
    if career.settings.mode == MODE_OFF:
        return SyncReport(message="Carrière désactivée pour ce profil.")
    if not career.settings.savegame:
        return SyncReport(message="Aucune sauvegarde associée à ce profil.")
    savegame = user_dir / career.settings.savegame
    if not (savegame / "careerSavegame.xml").is_file():
        return SyncReport(message=f"Sauvegarde introuvable : {savegame}")

    def read(farm: str) -> StatsSnapshot:
        return extract_stats(
            savegame,
            farm or None,
            install_dir=install_dir,
            mod_dirs=[d for d in (user_dir / "mods", library_mods_dir) if d is not None],
            parcel_areas=career.settings.parcel_areas,
        )

    snapshot = read(career.settings.farm)
    tracked = snapshot.farm_id
    apply_manual(snapshot, career.settings.manual_for(tracked, tracked))
    others: dict[str, StatsSnapshot] = {}
    for farm in sorted({o.farm for o in career.objectives if o.farm} - {tracked}):
        other = read(farm)
        if other.farm_id != farm:  # that farm no longer exists in the savegame
            continue
        apply_manual(other, career.settings.manual_for(farm, tracked))
        others[farm] = other
    career.snapshot = snapshot
    career.farm_snapshots = others
    result = career.evaluate()
    career.record_history()
    career.save()

    unavailable = sum(1 for s in snapshot.stats.values() if s.quality == Q_NA)
    message = f"Synchronisé avec {savegame.name}"
    if snapshot.farm_name:
        message += f" — ferme « {snapshot.farm_name} »"
    message += "."
    if career.settings.farm and tracked != career.settings.farm:
        message += f" ⚠ La ferme {career.settings.farm} n'existe plus : ferme {tracked} utilisée."
    if unavailable:
        message += f" {unavailable} statistique(s) non disponible(s)."
    missing = [p for p, ha in snapshot.parcels.items() if ha is None
               and p not in career.settings.parcel_areas.get(snapshot.map_id, {})]
    if missing and snapshot.value("land.area") is None:
        listed = ", ".join(f"n° {p}" for p in missing[:10])
        message += (
            f" 🌾 {len(missing)} parcelle(s) sans surface : {listed}. "
            "Renseigne-les via « Surfaces des parcelles… »."
        )
    return SyncReport(
        ok=True,
        message=message,
        snapshot=snapshot,
        detected=_detected_lines(snapshot),
        newly_completed=result.newly_completed,
        newly_unlocked=result.newly_unlocked,
    )


def linked_official_map(career_dir: Path, user_dir: Path) -> str | None:
    """Id of the official map of the savegame a career is linked to, if it is one."""
    try:
        savegame = Career.load(career_dir).settings.savegame
    except CareerError:
        return None
    found = official_map(savegame_map_id(user_dir / savegame)) if savegame else None
    return found.map_id if found else None


def guess_savegame(
    map_mod_filename: str | None, user_dir: Path, official_map: str | None = None
) -> str:
    """Pick the savegame folder matching the profile's map, only if unambiguous.

    ``official_map`` (savegame ``<mapId>`` of a base-game / DLC map) is used when the
    profile has no map mod.
    """
    if not map_mod_filename:
        if not official_map:
            return ""
        hits = [
            sg.name for sg in list_savegames(user_dir)
            if savegame_map_id(sg).lower() == official_map.lower()
        ]
        return hits[0] if len(hits) == 1 else ""
    map_id = Path(map_mod_filename).stem.lower()
    matches = [
        sg.name
        for sg in list_savegames(user_dir)
        if (info := parse_savegame(sg)).map_mod_id and info.map_mod_id.lower() == map_id
    ]
    return matches[0] if len(matches) == 1 else ""
