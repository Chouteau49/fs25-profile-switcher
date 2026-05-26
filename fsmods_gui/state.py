"""Shared in-memory state for the GUI: config, catalog, profiles, selection.

Plain Python — no Qt imports — so it stays testable and the lower layers don't
depend on PySide6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, GameProfile
from .profiles.catalog import Catalog, scan_library
from .profiles.profile import Profile, list_profiles, profile_path_for


@dataclass
class AppState:
    cfg: Config
    game_key: str
    catalog: Catalog | None = None
    profiles: list[Profile] = field(default_factory=list)
    current_profile: Profile | None = None

    @property
    def game(self) -> GameProfile:
        return self.cfg.profile(self.game_key)

    def refresh_catalog(self) -> Catalog:
        game = self.game
        if game.library_mods_dir is None:
            raise ValueError(
                "library_dir non configuré pour ce jeu. Renseigne games."
                f"{self.game_key}.library_dir dans config.yaml."
            )
        game.library_mods_dir.mkdir(parents=True, exist_ok=True)
        cache = (
            game.library_cache_dir / "index.json"
            if game.library_cache_dir
            else None
        )
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
        self.catalog = scan_library(game.library_mods_dir, cache_path=cache)
        return self.catalog

    def refresh_profiles(self) -> list[Profile]:
        game = self.game
        if game.library_profiles_dir is None:
            self.profiles = []
            return self.profiles
        game.library_profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profiles = list_profiles(game.library_profiles_dir)
        # Try to keep the same current_profile selected if still present.
        if self.current_profile is not None:
            slug = self.current_profile.slug
            self.current_profile = next(
                (p for p in self.profiles if p.slug == slug),
                self.profiles[0] if self.profiles else None,
            )
        elif self.profiles:
            self.current_profile = self.profiles[0]
        return self.profiles

    def new_profile(self, name: str) -> Profile:
        game = self.game
        if game.library_profiles_dir is None:
            raise ValueError("library_dir non configuré.")
        path = profile_path_for(game.library_profiles_dir, name)
        if path.exists():
            raise FileExistsError(f"Un profil existe déjà : {path.name}")
        prof = Profile(name=name, game=self.game_key, path=path)
        prof.save(path)
        self.profiles = sorted(self.profiles + [prof], key=lambda p: p.name.lower())
        self.current_profile = prof
        return prof

    def delete_profile(self, profile: Profile) -> None:
        if profile.path and profile.path.is_file():
            profile.path.unlink()
        self.profiles = [p for p in self.profiles if p.slug != profile.slug]
        if self.current_profile and self.current_profile.slug == profile.slug:
            self.current_profile = self.profiles[0] if self.profiles else None

    def save_current(self) -> Path | None:
        if self.current_profile is None or self.current_profile.path is None:
            return None
        return self.current_profile.save()
