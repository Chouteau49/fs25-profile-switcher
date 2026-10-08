"""Synchronise a career with its FS25 savegame (read stats → recompute objectives → save)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..profiles.savegame_audit import list_savegames, parse_savegame
from .formatting import format_value
from .objectives import MODE_OFF, Objective
from .stats import Q_NA, StatsSnapshot, apply_manual, extract_stats
from .store import Career


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
        if stat and stat.value is not None:
            lines.append(f"{format_value(stat.value, stat.unit)} — {stat.label.lower()}")
    return lines


def sync_career(career: Career, user_dir: Path, install_dir: Path | None = None) -> SyncReport:
    """Run the full sync. Never raises on missing data: the report explains why.

    The tracked farm (``settings.farm``) feeds the dashboard; every other farm an
    objective is bound to gets its own snapshot. ``install_dir`` (game folder) lets
    vehicle types / brands be read from the base-game vehicle XMLs.
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
            savegame, farm or None, install_dir=install_dir, mods_dir=user_dir / "mods"
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
    return SyncReport(
        ok=True,
        message=message,
        snapshot=snapshot,
        detected=_detected_lines(snapshot),
        newly_completed=result.newly_completed,
        newly_unlocked=result.newly_unlocked,
    )


def guess_savegame(map_mod_filename: str | None, user_dir: Path) -> str:
    """Pick the savegame folder matching the profile's map, only if unambiguous."""
    if not map_mod_filename:
        return ""
    map_id = Path(map_mod_filename).stem.lower()
    matches = [
        sg.name
        for sg in list_savegames(user_dir)
        if (info := parse_savegame(sg)).map_mod_id and info.map_mod_id.lower() == map_id
    ]
    return matches[0] if len(matches) == 1 else ""
