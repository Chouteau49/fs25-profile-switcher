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
    """A ``.zip`` holding AutoDrive savegame XML, awaiting install.

    ``in_library`` is True when the pack lives in the dedicated AutoDrive library
    folder (already imported), False when it is still in a download/inbox folder.
    """

    source_path: Path
    # canonical filename -> entry name inside the zip (preserves zip casing/path)
    members: dict[str, str] = field(default_factory=dict)
    in_library: bool = False

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


def scan_packs(
    source_dirs: list[Path], library_dir: Path | None = None
) -> list[AutoDrivePack]:
    """Find AutoDrive route packs in ``source_dirs`` (Downloads + inbox) and in
    the dedicated ``library_dir`` (already imported).

    De-duplicated by filename. The library is scanned first so an imported pack
    is reported as ``in_library`` even if a same-named copy lingers elsewhere.
    Sorted: library packs first, then by name.
    """
    packs: list[AutoDrivePack] = []
    seen: set[str] = set()
    folders: list[tuple[Path, bool]] = []
    if library_dir is not None:
        folders.append((library_dir, True))
    folders.extend((d, False) for d in source_dirs)
    for folder, in_library in folders:
        for zip_path in sorted(_list_zip_files(folder), key=lambda p: p.name.lower()):
            if zip_path.name in seen:
                continue
            pack = detect_pack(zip_path)
            if pack is None:
                continue
            pack.in_library = in_library
            seen.add(zip_path.name)
            packs.append(pack)
    packs.sort(key=lambda p: (not p.in_library, p.filename.lower()))
    return packs


def import_pack(pack: AutoDrivePack, library_dir: Path) -> Path:
    """Move ``pack``'s zip into the AutoDrive library folder (cut). Returns the dest.

    Overwrites a same-named pack already in the library (the freshly downloaded
    one wins). Raises ``FileNotFoundError`` if the source is gone.
    """
    import shutil

    library_dir.mkdir(parents=True, exist_ok=True)
    src = pack.source_path
    if not src.is_file():
        raise FileNotFoundError(f"{src.name} introuvable dans le dossier source.")
    dst = library_dir / src.name
    if dst.resolve() == src.resolve():
        return dst  # already in the library
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))
    return dst


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
