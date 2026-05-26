"""Per-savegame profile: a named selection of mod ``.zip`` filenames.

Profiles are JSON files under ``<library_dir>/profiles/<slug>.json``. They reference
mods by *filename* (e.g. ``FS25_Courseplay.zip``) — never by absolute path — so a
profile stays valid even if the library moves.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .catalog import Catalog

PROFILE_SCHEMA_VERSION = 1


class ProfileError(ValueError):
    """Raised on malformed or invalid profile files."""


_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def slugify(name: str) -> str:
    """Turn a profile display name into a safe filename slug."""
    cleaned = _SLUG_RE.sub("-", name.strip().lower()).strip("-._")
    return cleaned or "profile"


@dataclass
class Profile:
    name: str
    game: str = "fs25"
    mods: list[str] = field(default_factory=list)
    map_mod: str | None = None  # filename of the .zip that provides the map
    description: str = ""
    created_at: str = ""
    last_played: str | None = None
    path: Path | None = None  # set after load/save; not serialized

    @property
    def slug(self) -> str:
        if self.path is not None:
            return self.path.stem
        return slugify(self.name)

    def all_mod_filenames(self) -> list[str]:
        """Mods + map (if present and not already listed), de-duplicated, ordered."""
        seen: set[str] = set()
        ordered: list[str] = []
        if self.map_mod and self.map_mod not in seen:
            ordered.append(self.map_mod)
            seen.add(self.map_mod)
        for fname in self.mods:
            if fname not in seen:
                ordered.append(fname)
                seen.add(fname)
        return ordered

    def missing_against(self, catalog: Catalog) -> list[str]:
        return [f for f in self.all_mod_filenames() if f not in catalog]

    def to_dict(self) -> dict:
        return {
            "schema": PROFILE_SCHEMA_VERSION,
            "name": self.name,
            "game": self.game,
            "map_mod": self.map_mod,
            "mods": list(self.mods),
            "description": self.description,
            "created_at": self.created_at,
            "last_played": self.last_played,
        }

    @classmethod
    def from_dict(cls, data: dict, *, path: Path | None = None) -> Profile:
        if not isinstance(data, dict):
            raise ProfileError("Profile JSON root must be an object.")
        schema = data.get("schema", 1)
        if schema != PROFILE_SCHEMA_VERSION:
            raise ProfileError(
                f"Unsupported profile schema {schema!r} "
                f"(expected {PROFILE_SCHEMA_VERSION})."
            )
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError("Profile must have a non-empty 'name'.")
        mods = data.get("mods", [])
        if not isinstance(mods, list) or not all(isinstance(m, str) for m in mods):
            raise ProfileError("'mods' must be a list of filenames (strings).")
        map_mod = data.get("map_mod")
        if map_mod is not None and not isinstance(map_mod, str):
            raise ProfileError("'map_mod' must be a string filename or null.")
        return cls(
            name=name,
            game=data.get("game", "fs25"),
            mods=mods,
            map_mod=map_mod,
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            last_played=data.get("last_played"),
            path=path,
        )

    @classmethod
    def load(cls, path: Path) -> Profile:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path.name}: invalid JSON ({exc}).") from exc
        return cls.from_dict(data, path=path)

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ProfileError("Profile.save() needs a path (or self.path set).")
        if not self.created_at:
            self.created_at = date.today().isoformat()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.path = target
        return target


def list_profiles(profiles_dir: Path) -> list[Profile]:
    """Load every ``*.json`` profile in ``profiles_dir`` (sorted by name).

    Files that fail to parse are skipped silently — the GUI surfaces errors when
    the user clicks a broken profile.
    """
    if not profiles_dir.is_dir():
        return []
    out: list[Profile] = []
    for p in sorted(profiles_dir.iterdir()):
        if p.suffix.lower() != ".json" or not p.is_file():
            continue
        try:
            out.append(Profile.load(p))
        except ProfileError:
            continue
    out.sort(key=lambda prof: prof.name.lower())
    return out


def profile_path_for(profiles_dir: Path, name: str) -> Path:
    return profiles_dir / f"{slugify(name)}.json"
