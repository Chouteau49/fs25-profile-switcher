"""Discover freshly downloaded mods and import them into the library.

The user drops (or downloads) ``.zip`` mods into one of the *source* folders —
typically the Windows Downloads folder and/or a dedicated ``new_mods`` inbox
(see :meth:`fsmods_gui.config.GameProfile.new_mod_source_dirs`). This module:

  * scans those folders for ``.zip`` files **not yet in the library** and parses
    each one's ``modDesc.xml`` (reusing :func:`catalog._read_moddesc_from_zip`)
    so the GUI can show a thumbnail + title gallery, and
  * imports a chosen mod by **moving** (cutting) its zip into ``library/mods``
    and refreshing the catalog entry.

Classifying the imported mod into profiles/collections is handled by the caller
(:class:`fsmods_gui.state.AppState`) — this module only deals with the files.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .catalog import Catalog, CatalogEntry, _read_moddesc_from_zip

# Status of a downloaded zip relative to what's already in the library.
STATUS_NEW = "new"            # no file of this name in the library yet
STATUS_UPDATE = "update"      # same name in library but a different size (newer build)
STATUS_DUPLICATE = "duplicate"  # same name + same size: already imported

_STATUS_LABELS = {
    STATUS_NEW: "nouveau",
    STATUS_UPDATE: "mise à jour",
    STATUS_DUPLICATE: "déjà dans la bibliothèque",
}
# New + updates first, already-imported last; then alphabetical.
_STATUS_RANK = {STATUS_NEW: 0, STATUS_UPDATE: 1, STATUS_DUPLICATE: 2}


@dataclass
class PendingMod:
    """A downloaded ``.zip`` sitting in a source folder, awaiting import."""

    source_path: Path
    entry: CatalogEntry  # parsed modDesc (title, icon, category, is_map, …)
    status: str = STATUS_NEW

    @property
    def filename(self) -> str:
        return self.source_path.name

    @property
    def status_label(self) -> str:
        return _STATUS_LABELS.get(self.status, self.status)

    @property
    def is_in_library(self) -> bool:
        return self.status != STATUS_NEW

    @property
    def source_label(self) -> str:
        """Human-friendly name of the folder the zip was found in."""
        return self.source_path.parent.name or str(self.source_path.parent)


def _list_zip_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    out: list[Path] = []
    try:
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() == ".zip":
                out.append(p)
    except OSError:
        return []
    return out


def scan_sources(
    source_dirs: list[Path],
    library_mods_dir: Path | None,
    icon_cache_dir: Path | None = None,
) -> list[PendingMod]:
    """Return every mod found in ``source_dirs``, tagged with its library status.

    Each zip is classified relative to the library by **filename + size**:
    :data:`STATUS_NEW` (absent), :data:`STATUS_UPDATE` (present, different size)
    or :data:`STATUS_DUPLICATE` (present, same size → already imported). Showing
    duplicates — rather than hiding them — lets the user clean up the download
    folder or (re)classify a mod that's already in the library. When the same
    filename appears in several source folders, only the first occurrence (in
    ``source_dirs`` order) is kept.

    ``icon_cache_dir`` — when provided — is where thumbnails are extracted, so
    the gallery can show them; pass the library's ``cache/icons`` dir to reuse
    the same cache after import. Results are ordered new → update → duplicate,
    then alphabetically.
    """
    if icon_cache_dir is not None:
        icon_cache_dir.mkdir(parents=True, exist_ok=True)

    existing: dict[str, int] = {}
    if library_mods_dir is not None and library_mods_dir.is_dir():
        for p in library_mods_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".zip":
                try:
                    existing[p.name] = p.stat().st_size
                except OSError:
                    existing[p.name] = -1

    pending: list[PendingMod] = []
    seen: set[str] = set()
    for folder in source_dirs:
        for zip_path in _list_zip_files(folder):
            name = zip_path.name
            if name in seen:
                continue
            seen.add(name)
            if name not in existing:
                status = STATUS_NEW
            else:
                try:
                    size = zip_path.stat().st_size
                except OSError:
                    size = -1
                status = STATUS_DUPLICATE if size == existing[name] else STATUS_UPDATE
            entry = _read_moddesc_from_zip(zip_path, icon_cache_dir=icon_cache_dir)
            pending.append(PendingMod(source_path=zip_path, entry=entry, status=status))

    pending.sort(key=lambda pm: (_STATUS_RANK.get(pm.status, 9), pm.filename.lower()))
    return pending


def import_pending(
    pending: PendingMod,
    library_mods_dir: Path,
    catalog: Catalog | None = None,
    icon_cache_dir: Path | None = None,
) -> str:
    """Move ``pending``'s zip into the library and refresh the catalog entry.

    The source file is **removed** (cut) once moved. If a file of the same name
    already exists in the library it is overwritten — the freshly downloaded
    version wins. Returns the imported filename.
    """
    library_mods_dir.mkdir(parents=True, exist_ok=True)
    src = pending.source_path
    if not src.is_file():
        raise FileNotFoundError(f"{src.name} introuvable dans le dossier source.")
    dst = library_mods_dir / src.name
    if dst.exists():
        dst.unlink()
    # shutil.move handles the cross-volume case (Downloads on C:, library on D:)
    # by copying then deleting the source — i.e. a true "cut".
    shutil.move(str(src), str(dst))
    if catalog is not None:
        catalog.entries[dst.name] = _read_moddesc_from_zip(
            dst, icon_cache_dir=icon_cache_dir
        )
    return dst.name


def delete_source(pending: PendingMod) -> None:
    """Delete the downloaded ``.zip`` from its source folder (Downloads / inbox).

    This only removes the *download*; a copy already imported into the library is
    untouched. No-op if the file is already gone.
    """
    p = pending.source_path
    if p.is_file():
        p.unlink()
