"""On-disk career data, kept independent of the FS25 savegame.

Layout (one folder per profile, under ``<library_dir>/careers/<profile-slug>/``)::

    career.json      settings: mode, linked savegame, manual statistic overrides
    objectives.json  the objectives with their computed state and reward state
    statistics.json  last statistics snapshot + a bounded history

A game update or a savegame edit therefore never destroys the career.
Pure logic, no Qt.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..profiles.atomic import atomic_write_text
from .analysis_log import ANALYSIS_LIMIT, append_entry, record_analysis
from .objectives import (
    MODE_OBJECTIVES,
    EvaluationResult,
    Objective,
    ObjectiveError,
    evaluate_objectives,
)
from .periods import baseline_for, checkpoint
from .regression import Regression
from .repeats import repeatable_objectives
from .stats import StatsSnapshot
from .templates import build_template
from .time_window import ActiveWindow, WindowChallenge, open_window

SCHEMA_VERSION = 1
HISTORY_LIMIT = 500
# Statistics worth charting later (V3); only these are kept in the history.
HISTORY_KEYS = (
    "money",
    "netWorth",
    "land.area",
    "land.count",
    "animals.total",
    "vehicles.count",
    "contracts.completed",
    "finance.income",
    "productions.count",
)

CAREER_FILE = "career.json"
OBJECTIVES_FILE = "objectives.json"
STATISTICS_FILE = "statistics.json"
WINDOWS_FILE = "challenges.json"


class CareerError(ValueError):
    """Raised when career files are unreadable."""


@dataclass
class CareerSettings:
    mode: str = MODE_OBJECTIVES
    savegame: str = ""  # folder name, e.g. "savegame3"
    farm: str = ""  # tracked farm id ("" = farm 1 / first farm of the savegame)
    # Manual values: ``"<key>"`` applies to the tracked farm, ``"<farmId>|<key>"`` to that farm.
    manual_stats: dict[str, float] = field(default_factory=dict)
    # Areas (ha) typed per parcel for maps whose areas cannot be read (DLC):
    # ``{map_id: {farmland_id: ha}}``.
    parcel_areas: dict[str, dict[str, float]] = field(default_factory=dict)

    def manual_for(self, farm_id: str, default_farm: str) -> dict[str, float]:
        """Manual values that apply to ``farm_id`` (unprefixed ones only to the tracked farm)."""
        out: dict[str, float] = {}
        for key, value in self.manual_stats.items():
            owner, sep, stat = key.partition("|")
            if sep:
                if owner == farm_id:
                    out[stat] = value
            elif farm_id == default_farm:
                out[key] = value
        return out

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "mode": self.mode,
            "savegame": self.savegame,
            "farm": self.farm,
            "manual_stats": dict(self.manual_stats),
            "parcel_areas": {m: dict(a) for m, a in self.parcel_areas.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> CareerSettings:
        manual = data.get("manual_stats", {})
        raw_parcels = data.get("parcel_areas", {})
        parcel_areas = {
            str(map_id): {
                str(pid): float(ha) for pid, ha in areas.items() if isinstance(ha, int | float)
            }
            for map_id, areas in (raw_parcels.items() if isinstance(raw_parcels, dict) else [])
            if isinstance(areas, dict)
        }
        return cls(
            mode=str(data.get("mode", MODE_OBJECTIVES)),
            savegame=str(data.get("savegame", "")),
            farm=str(data.get("farm", "")),
            manual_stats={
                str(k): float(v)
                for k, v in (manual.items() if isinstance(manual, dict) else [])
                if isinstance(v, int | float)
            },
            parcel_areas=parcel_areas,
        )


def _write_json(path: Path, data: object) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def _read_json(path: Path) -> object | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CareerError(f"{path.name}: fichier illisible ({exc}).") from exc


@dataclass
class Career:
    directory: Path
    settings: CareerSettings = field(default_factory=CareerSettings)
    objectives: list[Objective] = field(default_factory=list)
    snapshot: StatsSnapshot = field(default_factory=StatsSnapshot)
    # Snapshots of the other farms that at least one objective is bound to.
    farm_snapshots: dict[str, StatsSnapshot] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    # One entry per savegame reading: what was read, what changed, anomalies.
    analysis_log: list[dict] = field(default_factory=list)
    # Défis à fenêtre de temps de jeu (2 M€ en 24 h…), suivis sur la ferme suivie.
    windows: list[ActiveWindow] = field(default_factory=list)

    @classmethod
    def load(cls, directory: Path) -> Career:
        career = cls(directory=directory)
        data = _read_json(directory / CAREER_FILE)
        if isinstance(data, dict):
            career.settings = CareerSettings.from_dict(data)

        data = _read_json(directory / OBJECTIVES_FILE)
        if isinstance(data, dict):
            for raw in data.get("objectives", []):
                try:
                    career.objectives.append(Objective.from_dict(raw))
                except ObjectiveError:
                    continue  # skip a corrupt entry, keep the rest of the career

        data = _read_json(directory / STATISTICS_FILE)
        if isinstance(data, dict):
            career.snapshot = StatsSnapshot.from_dict(data.get("snapshot", {}))
            raw_farms = data.get("farm_snapshots", {})
            if isinstance(raw_farms, dict):
                career.farm_snapshots = {
                    str(k): StatsSnapshot.from_dict(v)
                    for k, v in raw_farms.items()
                    if isinstance(v, dict)
                }
            history = data.get("history", [])
            career.history = [h for h in history if isinstance(h, dict)]
            log = data.get("analysis_log", [])
            career.analysis_log = [e for e in log if isinstance(e, dict)]

        data = _read_json(directory / WINDOWS_FILE)
        if isinstance(data, dict):
            for raw in data.get("windows", []):
                try:
                    career.windows.append(ActiveWindow.from_dict(raw))
                except (KeyError, TypeError, ValueError):
                    continue  # a corrupt challenge is skipped, the others are kept
        return career

    def save(self) -> None:
        _write_json(self.directory / CAREER_FILE, self.settings.to_dict())
        _write_json(
            self.directory / OBJECTIVES_FILE,
            {"schema": SCHEMA_VERSION, "objectives": [o.to_dict() for o in self.objectives]},
        )
        _write_json(
            self.directory / STATISTICS_FILE,
            {
                "schema": SCHEMA_VERSION,
                "snapshot": self.snapshot.to_dict(),
                "farm_snapshots": {k: s.to_dict() for k, s in self.farm_snapshots.items()},
                "history": self.history[-HISTORY_LIMIT:],
                "analysis_log": self.analysis_log[-ANALYSIS_LIMIT:],
            },
        )
        _write_json(
            self.directory / WINDOWS_FILE,
            {"schema": SCHEMA_VERSION, "windows": [w.to_dict() for w in self.windows]},
        )

    def set_tracked_farm(self, farm: str) -> int:
        """Change the tracked farm; returns how many objectives stayed on the previous one.

        An objective or a manual value without an explicit farm belongs to the tracked
        farm. Completion is final, so letting them follow the selector would complete
        them on whichever farm is merely being looked at: they are pinned to the farm
        they were measured on.
        """
        previous = self.snapshot.farm_id
        self.settings.farm = farm
        if not previous or farm == previous:
            return 0
        pinned = [o for o in self.objectives if not o.farm]
        for objective in pinned:
            objective.farm = previous
        self.settings.manual_stats = {
            key if "|" in key else f"{previous}|{key}": value
            for key, value in self.settings.manual_stats.items()
        }
        return len(pinned)

    def snapshots_by_farm(self) -> dict[str, StatsSnapshot]:
        """Every known snapshot keyed by farm id (tracked farm included)."""
        out = dict(self.farm_snapshots)
        if self.snapshot.farm_id:
            out[self.snapshot.farm_id] = self.snapshot
        return out

    def snapshot_for(self, objective: Objective) -> StatsSnapshot:
        if not objective.farm or objective.farm == self.snapshot.farm_id:
            return self.snapshot
        return self.farm_snapshots.get(objective.farm) or StatsSnapshot()

    def evaluate(self) -> EvaluationResult:
        """Recompute every objective against the stored snapshots."""
        return evaluate_objectives(
            self.objectives, self.snapshot, self.settings.mode, self.snapshots_by_farm()
        )

    def get(self, objective_id: str) -> Objective | None:
        return next((o for o in self.objectives if o.id == objective_id), None)

    def add_objectives(self, new: list[Objective]) -> int:
        """Append objectives whose id is not already present. Returns how many were added."""
        known = {o.id for o in self.objectives}
        added = 0
        for obj in new:
            if obj.id in known:
                continue
            self.objectives.append(obj)
            known.add(obj.id)
            added += 1
        return added

    def remove_objective(self, objective_id: str) -> bool:
        before = len(self.objectives)
        self.objectives = [o for o in self.objectives if o.id != objective_id]
        for obj in self.objectives:
            if objective_id in obj.requires:
                obj.requires.remove(objective_id)
        return len(self.objectives) != before

    def start_scenario(
        self, template_key: str, farm: str = "", *, from_activation: bool = False
    ) -> tuple[int, list[str]]:
        """Add a scenario. Returns ``(added, skipped)``: skipped names could not be baselined.

        ``from_activation`` measures the cumulative statistics from now on: each objective
        keeps the values read at this moment as its baseline. Without it, the scenario
        counts the whole savegame history (the historical behaviour).
        """
        objectives = build_template(template_key, farm)
        if not from_activation:
            return self.add_objectives(objectives), []
        source = self.snapshots_by_farm().get(farm or self.snapshot.farm_id)
        if source is None or not source.stats:
            raise CareerError("Synchronise la sauvegarde avant de démarrer depuis l'activation.")
        skipped_ids: set[str] = set()
        kept: list[Objective] = []
        for obj in objectives:
            if obj.condition is None:
                kept.append(obj)
                continue
            baseline, missing = baseline_for(obj.condition, source)
            if missing:
                skipped_ids.add(obj.id)
                continue
            obj.baseline = baseline
            kept.append(obj)
        # Whatever requires a skipped objective cannot be reached either.
        changed = True
        while changed:
            changed = False
            for obj in list(kept):
                if any(r in skipped_ids for r in obj.requires):
                    kept.remove(obj)
                    skipped_ids.add(obj.id)
                    changed = True
        names = [o.name for o in objectives if o.id in skipped_ids]
        return self.add_objectives(kept), names

    def start_window(self, challenge: WindowChallenge) -> ActiveWindow:
        """Open a time-window challenge now, measured on the tracked farm's statistics."""
        if not self.snapshot.stats:
            raise CareerError("Synchronise la sauvegarde avant de lancer un défi.")
        window = open_window(challenge, checkpoint(self.snapshot), f"win.{uuid.uuid4().hex[:8]}")
        self.windows.append(window)
        return window

    def refresh_windows(self) -> list[ActiveWindow]:
        """Re-evaluate the open challenges; returns those that just reached a final state."""
        now = checkpoint(self.snapshot)
        closed: list[ActiveWindow] = []
        for window in self.windows:
            was_final = window.final
            window.refresh(now)
            if window.final and not was_final:
                closed.append(window)
        return closed

    def start_repeatable(self, farm: str = "") -> int:
        """Add the repeatable catalogue (paliers). Returns how many paliers were added."""
        return self.add_objectives(repeatable_objectives(farm))

    def log_reading(self, previous: StatsSnapshot, current: StatsSnapshot) -> list[Regression]:
        """Journalise une lecture et renvoie les régressions détectées.

        Une comparaison n'a de sens qu'entre deux lectures de la même ferme d'une même
        sauvegarde : changer de ferme ferait apparaître de fausses régressions.
        """
        comparable = (
            previous
            if previous.stats
            and previous.farm_id == current.farm_id
            and previous.savegame == current.savegame
            else None
        )
        entry = record_analysis(comparable, current)
        self.analysis_log = append_entry(self.analysis_log, entry)
        return list(entry.anomalies)

    def record_history(self) -> None:
        values = {
            k: self.snapshot.value(k) for k in HISTORY_KEYS if self.snapshot.value(k) is not None
        }
        if not values:
            return
        farm = self.snapshot.farm_id
        last = next((h for h in reversed(self.history) if h.get("farm") == farm), None)
        if last is not None and last.get("values") == values:
            return
        self.history.append({"t": self.snapshot.taken_at, "farm": farm, "values": values})
        del self.history[:-HISTORY_LIMIT]


def career_dir_for(careers_dir: Path, profile_slug: str) -> Path:
    return careers_dir / profile_slug


def load_career(careers_dir: Path, profile_slug: str) -> Career:
    return Career.load(career_dir_for(careers_dir, profile_slug))
