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
import os
from dataclasses import dataclass, field
from pathlib import Path

from .objectives import (
    MODE_OBJECTIVES,
    EvaluationResult,
    Objective,
    ObjectiveError,
    evaluate_objectives,
)
from .stats import StatsSnapshot

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


class CareerError(ValueError):
    """Raised when career files are unreadable."""


@dataclass
class CareerSettings:
    mode: str = MODE_OBJECTIVES
    savegame: str = ""  # folder name, e.g. "savegame3"
    farm: str = ""  # tracked farm id ("" = farm 1 / first farm of the savegame)
    # Manual values: ``"<key>"`` applies to the tracked farm, ``"<farmId>|<key>"`` to that farm.
    manual_stats: dict[str, float] = field(default_factory=dict)

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
        }

    @classmethod
    def from_dict(cls, data: dict) -> CareerSettings:
        manual = data.get("manual_stats", {})
        return cls(
            mode=str(data.get("mode", MODE_OBJECTIVES)),
            savegame=str(data.get("savegame", "")),
            farm=str(data.get("farm", "")),
            manual_stats={
                str(k): float(v)
                for k, v in (manual.items() if isinstance(manual, dict) else [])
                if isinstance(v, int | float)
            },
        )


def _write_json(path: Path, data: object) -> None:
    """Atomic write so a crash never leaves a half-written career file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


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
            },
        )

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

    def record_history(self) -> None:
        values = {
            k: self.snapshot.value(k) for k in HISTORY_KEYS if self.snapshot.value(k) is not None
        }
        if not values:
            return
        if self.history and self.history[-1].get("values") == values:
            return
        self.history.append({"t": self.snapshot.taken_at, "values": values})
        del self.history[:-HISTORY_LIMIT]


def career_dir_for(careers_dir: Path, profile_slug: str) -> Path:
    return careers_dir / profile_slug


def load_career(careers_dir: Path, profile_slug: str) -> Career:
    return Career.load(career_dir_for(careers_dir, profile_slug))
