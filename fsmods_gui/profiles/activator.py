"""Apply a :class:`Profile` to a game's ``mods/`` folder.

Activation = wipe the game ``mods/`` folder of ``.zip``\\ s, then **hardlink** each
mod listed in the profile from the library to the game folder. Hardlinks are
instantaneous and use no extra disk space, but only work when source and
destination live on the **same NTFS volume**. If hardlinking fails (cross-volume
or non-NTFS), we transparently fall back to a copy.

The wipe must never lose anything: a zip of the game folder that exists nowhere
else (downloaded in game while the app was closed, ModHub update, local patch) is
first moved to the inbox, where the "new mods" dialog offers to import it.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..config import Config, GameProfile
from .catalog import Catalog
from .profile import Profile

_PROCESS_MARKERS = {"fs25": "farmingsimulator2025", "fs22": "farmingsimulator2022"}


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
    rescued: list[Path] = field(default_factory=list)  # where at-risk zips were moved
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


def same_content(a: Path, b: Path) -> bool:
    """True when both paths hold the same bytes; a missing file means False.

    Hardlinks and ``copy2`` copies (same size + mtime) are recognised without
    reading them: a whole profile weighs several GB. A file edited while keeping both
    its exact size and its exact timestamp would pass for identical: accepted, as
    reading every copied mod on each activation is the alternative.
    """
    try:
        if os.path.samefile(a, b):
            return True
        stat_a, stat_b = a.stat(), b.stat()
        if stat_a.st_size != stat_b.st_size:
            return False
        return stat_a.st_mtime_ns == stat_b.st_mtime_ns or filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def mods_at_risk(mods_dir: Path, library_mods_dir: Path) -> list[Path]:
    """Zips of the game folder that the library cannot restore.

    Either absent from the library, or different from its copy. Wiping them would
    lose them for good.
    """
    if not mods_dir.is_dir():
        return []
    return [
        entry
        for entry in sorted(mods_dir.iterdir())
        if entry.is_file()
        and entry.suffix.lower() == ".zip"
        and not same_content(entry, library_mods_dir / entry.name)
    ]


def rescue_mod(zip_path: Path, rescue_dir: Path) -> Path:
    """Move ``zip_path`` into ``rescue_dir`` and return where it now is.

    What the folder already holds is never overwritten: a different file of that
    name goes to a dated sub-folder instead. Raises ``OSError`` on failure.
    """
    rescue_dir.mkdir(parents=True, exist_ok=True)
    target = rescue_dir / zip_path.name
    if target.exists():
        if same_content(zip_path, target):
            zip_path.unlink()
            return target
        target = rescue_dir / f"mis-de-cote-{datetime.now():%Y%m%d-%H%M%S}" / zip_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(zip_path), str(target))
    return target


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
    mod_filenames: list[str] | None = None,
) -> ActivationReport:
    """Activate ``profile`` into ``game_profile.mods_dir``.

    The library mods folder is read from ``catalog.mods_dir``. The game folder
    is wiped of zips first, then each profile mod is hardlinked (or copied) in.

    ``mod_filenames`` overrides which mods to activate — pass the profile's
    *effective* list (own mods + inherited collections − exclusions). When
    omitted, the profile's own mods are used.
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

    selection = mod_filenames if mod_filenames is not None else profile.all_mod_filenames()
    total = len(selection) + 1  # +1 for the wipe step
    cb(0, total, "Mise à l'abri des mods absents de la bibliothèque…")
    rescue_dir = game_profile.inbox_dir_effective or game_profile.library_dir / "_inbox"
    for zip_path in mods_at_risk(mods_dir, catalog.mods_dir):
        try:
            report.rescued.append(rescue_mod(zip_path, rescue_dir))
        except OSError as exc:
            report.errors.append((zip_path.name, f"mise à l'abri impossible : {exc}"))
    if report.errors:
        return report  # nothing is wiped unless everything is safe (game still running?)

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


def game_process_running(game_key: str | None = None) -> bool:
    """True when Farming Simulator runs; with ``game_key``, that game's version only.

    The real process is ``FarmingSimulator2025Game.exe``, started by the launcher
    ``FarmingSimulator2025.exe``. Without psutil the answer is False: never blocking.
    """
    try:
        import psutil  # local import: keeps this module importable without psutil
    except ImportError:
        return False
    marker = _PROCESS_MARKERS.get(game_key or "", "farmingsimulator")
    for process in psutil.process_iter(["name"]):
        name = (process.info.get("name") or "").lower()
        if marker in name and name.endswith(".exe"):
            return True
    return False


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
