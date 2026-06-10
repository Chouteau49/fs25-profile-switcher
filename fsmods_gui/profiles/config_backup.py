"""Back up / restore the *config* (profiles + collections), not the mods.

Mods live in the library as multi-GB ``.zip`` files; only the small JSON
profiles and collections are worth syncing to a cloud-synced folder. This module
provides three operations, all pure (no Qt):

* :func:`export_config` — bundle ``profiles/`` + ``collections/`` JSON into a zip.
* :func:`import_config` — restore them from a zip, merging or replacing.
* :func:`mirror_config` — copy them into a plain folder (e.g. a OneDrive/Drive
  synced directory), kept in sync including deletions.
"""
from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

MODE_MERGE = "merge"      # add/overwrite, keep existing entries not in the zip
MODE_REPLACE = "replace"  # wipe existing *.json first, then restore

_SECTIONS = ("profiles", "collections")


@dataclass
class ImportResult:
    profiles_imported: int = 0
    collections_imported: int = 0
    replaced: bool = False


def export_config(
    profiles_dir: Path | None,
    collections_dir: Path | None,
    dest_zip: Path,
) -> Path:
    """Write a zip containing ``profiles/*.json`` and ``collections/*.json``."""
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    sources = {"profiles": profiles_dir, "collections": collections_dir}
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for section, src in sources.items():
            if src and src.is_dir():
                for p in sorted(src.glob("*.json")):
                    zf.write(p, f"{section}/{p.name}")
    return dest_zip


def import_config(
    src_zip: Path,
    profiles_dir: Path,
    collections_dir: Path,
    *,
    mode: str = MODE_MERGE,
) -> ImportResult:
    """Restore profiles + collections from ``src_zip``.

    ``mode`` is :data:`MODE_MERGE` (default) or :data:`MODE_REPLACE`. Entries are
    matched by filename; zip paths are sanitised (basename only) to avoid writing
    outside the target directories.
    """
    if mode not in (MODE_MERGE, MODE_REPLACE):
        raise ValueError(f"Unknown import mode: {mode!r}")
    targets = {"profiles": profiles_dir, "collections": collections_dir}
    for d in targets.values():
        d.mkdir(parents=True, exist_ok=True)
    if mode == MODE_REPLACE:
        for d in targets.values():
            for p in d.glob("*.json"):
                p.unlink()

    result = ImportResult(replaced=mode == MODE_REPLACE)
    with zipfile.ZipFile(src_zip) as zf:
        for name in zf.namelist():
            parts = name.replace("\\", "/").split("/")
            if len(parts) != 2 or not parts[1].lower().endswith(".json"):
                continue
            section, raw = parts
            target_dir = targets.get(section)
            if target_dir is None:
                continue
            base = Path(raw).name  # strip any path components (zip-slip guard)
            if not base:
                continue
            (target_dir / base).write_bytes(zf.read(name))
            if section == "profiles":
                result.profiles_imported += 1
            else:
                result.collections_imported += 1
    return result


def mirror_config(
    profiles_dir: Path | None,
    collections_dir: Path | None,
    backup_dir: Path,
) -> Path:
    """Mirror profiles + collections into ``backup_dir`` (overwrite + prune).

    Files removed from the source are also removed from the mirror, so a
    cloud-synced ``backup_dir`` stays an exact copy.
    """
    sources = {"profiles": profiles_dir, "collections": collections_dir}
    for section, src in sources.items():
        dst = backup_dir / section
        dst.mkdir(parents=True, exist_ok=True)
        existing = {p.name for p in dst.glob("*.json")}
        current: set[str] = set()
        if src and src.is_dir():
            for p in src.glob("*.json"):
                shutil.copy2(p, dst / p.name)
                current.add(p.name)
        for stale in existing - current:
            (dst / stale).unlink()
    return backup_dir
