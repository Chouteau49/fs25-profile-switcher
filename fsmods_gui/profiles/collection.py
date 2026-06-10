"""A named, reusable set of mod ``.zip`` filenames.

Collections group mods by theme (e.g. "Vieux matériel", "Viticulture") so a
profile can *inherit* several of them instead of re-picking every mod. The link
is dynamic: a profile references collections by slug, and the effective mod list
is recomputed from the current collections at activation time
(see :meth:`fsmods_gui.profiles.profile.Profile.effective_mod_filenames`).

Stored as JSON under ``<library_dir>/collections/<slug>.json``. Like profiles,
mods are referenced by *filename* and there is no map (a map stays a per-profile
choice).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .profile import ProfileError, slugify  # reuse slug + error helpers

COLLECTION_SCHEMA_VERSION = 1


@dataclass
class Collection:
    name: str
    game: str = "fs25"
    mods: list[str] = field(default_factory=list)
    description: str = ""
    created_at: str = ""
    path: Path | None = None  # set after load/save; not serialized

    @property
    def slug(self) -> str:
        if self.path is not None:
            return self.path.stem
        return slugify(self.name)

    def to_dict(self) -> dict:
        return {
            "schema": COLLECTION_SCHEMA_VERSION,
            "name": self.name,
            "game": self.game,
            "mods": list(self.mods),
            "description": self.description,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict, *, path: Path | None = None) -> Collection:
        if not isinstance(data, dict):
            raise ProfileError("Collection JSON root must be an object.")
        schema = data.get("schema", 1)
        if schema != COLLECTION_SCHEMA_VERSION:
            raise ProfileError(
                f"Unsupported collection schema {schema!r} "
                f"(expected {COLLECTION_SCHEMA_VERSION})."
            )
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError("Collection must have a non-empty 'name'.")
        mods = data.get("mods", [])
        if not isinstance(mods, list) or not all(isinstance(m, str) for m in mods):
            raise ProfileError("'mods' must be a list of filenames (strings).")
        return cls(
            name=name,
            game=data.get("game", "fs25"),
            mods=mods,
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            path=path,
        )

    @classmethod
    def load(cls, path: Path) -> Collection:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path.name}: invalid JSON ({exc}).") from exc
        return cls.from_dict(data, path=path)

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ProfileError("Collection.save() needs a path (or self.path set).")
        if not self.created_at:
            self.created_at = date.today().isoformat()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.path = target
        return target


def list_collections(collections_dir: Path) -> list[Collection]:
    """Load every ``*.json`` collection in ``collections_dir`` (sorted by name)."""
    if not collections_dir.is_dir():
        return []
    out: list[Collection] = []
    for p in sorted(collections_dir.iterdir()):
        if p.suffix.lower() != ".json" or not p.is_file():
            continue
        try:
            out.append(Collection.load(p))
        except ProfileError:
            continue
    out.sort(key=lambda c: c.name.lower())
    return out


def collection_path_for(collections_dir: Path, name: str) -> Path:
    return collections_dir / f"{slugify(name)}.json"
