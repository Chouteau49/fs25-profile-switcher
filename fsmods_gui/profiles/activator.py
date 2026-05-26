"""Apply a :class:`Profile` to a game's ``mods/`` folder.

Activation = wipe the game ``mods/`` folder of ``.zip``\\ s, then **hardlink** each
mod listed in the profile from the library to the game folder. Hardlinks are
instantaneous and use no extra disk space, but only work when source and
destination live on the **same NTFS volume**. If hardlinking fails (cross-volume
or non-NTFS), we transparently fall back to a copy.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from ..config import Config, GameProfile
from .catalog import Catalog
from .profile import Profile


@dataclass
class ModActivation:
    filename: str
    method: str  # "hardlink" | "copy"
    src: Path
    dst: Path


@dataclass
class ActivationReport:
    profile_name: str
    activated: list[ModActivation] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.missing


class ProgressCallback(Protocol):
    def __call__(self, current: int, total: int, message: str) -> None: ...


def _noop_progress(current: int, total: int, message: str) -> None:  # pragma: no cover
    return None


def _safe_link_or_copy(src: Path, dst: Path) -> str:
    """Return ``"hardlink"`` on success, ``"copy"`` if we had to fall back."""
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def clear_game_mods(mods_dir: Path) -> list[Path]:
    """Delete every ``*.zip`` in ``mods_dir``. Returns the paths that were removed.

    Non-``.zip`` files (e.g. ``modSettings.xml``, FS-generated subfolders) are left
    untouched so the game's own state isn't disturbed.
    """
    removed: list[Path] = []
    if not mods_dir.is_dir():
        return removed
    for entry in mods_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".zip":
            try:
                entry.unlink()
                removed.append(entry)
            except OSError:
                continue
    return removed


def activate_profile(
    profile: Profile,
    game_profile: GameProfile,
    catalog: Catalog,
    *,
    progress: ProgressCallback | None = None,
) -> ActivationReport:
    """Activate ``profile`` into ``game_profile.mods_dir``.

    The library mods folder is read from ``catalog.mods_dir``. The game folder
    is wiped of zips first, then each profile mod is hardlinked (or copied) in.
    """
    cb: ProgressCallback = progress or _noop_progress
    report = ActivationReport(profile_name=profile.name)

    if game_profile.library_dir is None:
        report.errors.append(
            ("config", "library_dir non configuré pour ce jeu — impossible d'activer.")
        )
        return report

    mods_dir = game_profile.mods_dir
    if not mods_dir.is_dir():
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            report.errors.append(("mods_dir", f"impossible de créer {mods_dir} : {exc}"))
            return report

    selection = profile.all_mod_filenames()
    total = len(selection) + 1  # +1 for the wipe step
    cb(0, total, "Nettoyage du dossier mods du jeu…")
    report.removed = clear_game_mods(mods_dir)

    for idx, filename in enumerate(selection, start=1):
        entry = catalog.get(filename)
        if entry is None:
            report.missing.append(filename)
            cb(idx, total, f"{filename} : absent de la bibliothèque (ignoré)")
            continue
        src = catalog.mods_dir / filename
        dst = mods_dir / filename
        cb(idx, total, f"Activation {filename}")
        try:
            method = _safe_link_or_copy(src, dst)
            report.activated.append(
                ModActivation(filename=filename, method=method, src=src, dst=dst)
            )
        except OSError as exc:
            report.errors.append((filename, str(exc)))

    cb(total, total, "Activation terminée")
    return report


def launch_game(game_profile: GameProfile) -> bool:
    """Start the game via Steam if a ``steam_app_id`` is configured.

    Returns True if the launch command was dispatched. Returns False when no
    ``steam_app_id`` is set or when no usable launcher exists on the current OS.
    Cross-platform: uses ``cmd /c start`` on Windows and ``xdg-open`` elsewhere.
    """
    url = game_profile.steam_launch_url()
    if url is None:
        return False
    try:
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", "start", "", url], close_fds=True)
        else:
            launcher = shutil.which("xdg-open") or shutil.which("open")
            if launcher is None:
                return False
            subprocess.Popen([launcher, url], close_fds=True)
    except OSError:
        return False
    return True


def activate_and_launch(
    profile: Profile,
    cfg: Config,
    catalog: Catalog,
    *,
    progress: ProgressCallback | None = None,
    launcher: Callable[[GameProfile], bool] = launch_game,
) -> tuple[ActivationReport, bool]:
    """Convenience: run :func:`activate_profile` then start the game.

    The game is only launched when activation has no errors (missing mods are
    not blocking — the user is warned but the game still starts).
    """
    game_profile = cfg.profile(profile.game)
    report = activate_profile(profile, game_profile, catalog, progress=progress)
    launched = launcher(game_profile) if not report.errors else False
    return report, launched
