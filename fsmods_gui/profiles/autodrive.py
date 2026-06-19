"""Install an AutoDrive route pack into a FS25 savegame.

Some FS25 mods ship a community **AutoDrive route network** as a small ``.zip``
that is *not* a mod (no ``modDesc.xml``). Instead it contains the two XML files
AutoDrive reads from a savegame folder:

  * ``AutoDrive_config.xml``     — the route network for the map.
  * ``AutoDriveUsersData.xml``   — per-user markers / group data.

The manual procedure players follow is:

  1. Open the target ``savegameN`` folder.
  2. Delete any existing ``AutoDrive_config.xml`` / ``AutoDriveUsersData.xml``.
  3. Unzip the downloaded pack and drop both XML files in.
  4. Load the game.

This module automates steps 2–3. Instead of *deleting* the existing XML it
renames them to ``<name>.bak`` (non-clobbering: ``.bak``, ``.bak.1``, …) so a
player who already had AutoDrive routes can roll back. Pure file/zip logic, no
Qt — the GUI (:mod:`fsmods_gui.widgets.autodrive_dialog`) drives it.

The savegame folder is found exactly like the audit feature does
(:func:`fsmods_gui.profiles.savegame_audit.list_savegames`), so this composes
with the rest of the app.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# The savegame-level files AutoDrive reads. Compared case-insensitively against
# zip entries; the canonical casing here is what we write into the savegame.
AUTODRIVE_FILES: tuple[str, ...] = (
    "AutoDrive_config.xml",
    "AutoDriveUsersData.xml",
)


@dataclass
class AutoDrivePack:
    """A downloaded ``.zip`` holding AutoDrive savegame XML, awaiting install."""

    source_path: Path
    # canonical filename -> entry name inside the zip (preserves zip casing/path)
    members: dict[str, str] = field(default_factory=dict)

    @property
    def filename(self) -> str:
        return self.source_path.name

    @property
    def source_label(self) -> str:
        """Human-friendly name of the folder the zip was found in."""
        return self.source_path.parent.name or str(self.source_path.parent)

    @property
    def provided(self) -> list[str]:
        """Canonical AutoDrive filenames this pack will install, ordered."""
        return [f for f in AUTODRIVE_FILES if f in self.members]


def _autodrive_members(zip_path: Path) -> dict[str, str]:
    """Map each canonical AutoDrive filename to its entry name inside the zip.

    Matches by *basename*, case-insensitively, so a pack that nests the files in
    a subfolder still works. When the same file appears twice, the first entry
    in the archive wins.
    """
    canonical = {f.lower(): f for f in AUTODRIVE_FILES}
    members: dict[str, str] = {}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                base = name.rsplit("/", 1)[-1].lower()
                canon = canonical.get(base)
                if canon is not None and canon not in members:
                    members[canon] = name
    except (zipfile.BadZipFile, OSError):
        return {}
    return members


def detect_pack(zip_path: Path) -> AutoDrivePack | None:
    """Return an :class:`AutoDrivePack` if the zip holds AutoDrive XML, else None."""
    members = _autodrive_members(zip_path)
    if not members:
        return None
    return AutoDrivePack(source_path=zip_path, members=members)


def _list_zip_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    try:
        return [
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() == ".zip"
        ]
    except OSError:
        return []


def scan_packs(source_dirs: list[Path]) -> list[AutoDrivePack]:
    """Find AutoDrive route packs across ``source_dirs`` (Downloads + inbox).

    De-duplicated by filename in ``source_dirs`` order, sorted by name.
    """
    packs: list[AutoDrivePack] = []
    seen: set[str] = set()
    for folder in source_dirs:
        for zip_path in sorted(_list_zip_files(folder), key=lambda p: p.name.lower()):
            if zip_path.name in seen:
                continue
            pack = detect_pack(zip_path)
            if pack is None:
                continue
            seen.add(zip_path.name)
            packs.append(pack)
    return packs


def _backup_path(target: Path) -> Path:
    """First free ``<name>.bak`` / ``<name>.bak.N`` next to ``target``."""
    candidate = target.with_name(target.name + ".bak")
    n = 1
    while candidate.exists():
        candidate = target.with_name(f"{target.name}.bak.{n}")
        n += 1
    return candidate


@dataclass
class InstallResult:
    savegame: Path
    installed: list[str] = field(default_factory=list)   # canonical filenames written
    backed_up: list[str] = field(default_factory=list)   # "old -> old.bak" notes
    errors: list[str] = field(default_factory=list)


def install_pack(
    pack: AutoDrivePack,
    savegame_dir: Path,
    backup: bool = True,
) -> InstallResult:
    """Extract the pack's AutoDrive XML into ``savegame_dir``.

    Existing target files are renamed to ``<name>.bak`` first (when ``backup`` is
    True) so the player can roll back; with ``backup`` False they are deleted —
    matching the manual procedure literally. Each file is written independently:
    one failure is recorded in ``errors`` and the others still proceed.
    """
    result = InstallResult(savegame=savegame_dir)
    if not savegame_dir.is_dir():
        result.errors.append(f"Dossier de sauvegarde introuvable : {savegame_dir}")
        return result

    try:
        with zipfile.ZipFile(pack.source_path) as zf:
            for canon in pack.provided:
                member = pack.members[canon]
                target = savegame_dir / canon
                try:
                    data = zf.read(member)
                except (KeyError, zipfile.BadZipFile, OSError) as exc:
                    result.errors.append(f"{canon} : lecture du zip impossible ({exc}).")
                    continue
                try:
                    if target.exists():
                        if backup:
                            bak = _backup_path(target)
                            target.replace(bak)
                            result.backed_up.append(f"{target.name} → {bak.name}")
                        else:
                            target.unlink()
                    target.write_bytes(data)
                    result.installed.append(canon)
                except OSError as exc:
                    result.errors.append(f"{canon} : écriture impossible ({exc}).")
    except (zipfile.BadZipFile, OSError) as exc:
        result.errors.append(f"Archive illisible : {exc}")
    return result
