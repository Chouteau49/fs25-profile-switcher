"""Back up / restore the *config* (profiles, collections, careers), not the mods.

Mods live in the library as multi-GB ``.zip`` files; only the small JSON files
are worth syncing to a cloud-synced or network folder. Pure logic (stdlib only):

* :func:`export_config` / :func:`import_config` — bundle to / restore from a zip.
* :func:`mirror_config` — copy into a plain folder (Google Drive for desktop, a
  NAS share, OneDrive…), kept in sync including deletions.
* :func:`snapshot_config` — timestamped zip snapshots with bounded retention.
* :func:`backup_all` — mirror (+ snapshot) to several targets; a failing target
  (e.g. an unreachable NAS) never prevents the others.

Safety rules: a mirror only prunes files in a folder it created itself (marker
file), never when the source is empty, and every copy is atomic.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MODE_MERGE = "merge"      # add/overwrite, keep existing entries not in the zip
MODE_REPLACE = "replace"  # wipe existing *.json first, then restore

_FLAT_SECTIONS = ("profiles", "collections")
CAREERS_SECTION = "careers"  # careers/<profile-slug>/<file>.json
MARKER_NAME = ".fsmods-backup.json"
SNAPSHOT_DIR = "snapshots"
DEFAULT_KEEP_SNAPSHOTS = 10
DEFAULT_SNAPSHOT_INTERVAL_S = 3600


@dataclass
class ImportResult:
    profiles_imported: int = 0
    collections_imported: int = 0
    careers_imported: int = 0
    replaced: bool = False


def _safe_name(raw: str) -> str | None:
    """Basename usable as a path component (zip-slip guard), or ``None``."""
    name = Path(raw).name
    return name if name and name not in (".", "..") else None


def _atomic_copy(src: Path, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _career_files(careers_dir: Path | None) -> list[Path]:
    if not careers_dir or not careers_dir.is_dir():
        return []
    return sorted(p for d in careers_dir.iterdir() if d.is_dir() for p in d.glob("*.json"))


def export_config(
    profiles_dir: Path | None,
    collections_dir: Path | None,
    dest_zip: Path,
    careers_dir: Path | None = None,
) -> Path:
    """Write a zip with ``profiles/*.json``, ``collections/*.json``, ``careers/<slug>/*.json``."""
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    sources = {"profiles": profiles_dir, "collections": collections_dir}
    tmp = dest_zip.with_name(dest_zip.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for section, src in sources.items():
            if src and src.is_dir():
                for p in sorted(src.glob("*.json")):
                    zf.write(p, f"{section}/{p.name}")
        for p in _career_files(careers_dir):
            zf.write(p, f"{CAREERS_SECTION}/{p.parent.name}/{p.name}")
    os.replace(tmp, dest_zip)
    return dest_zip


def import_config(
    src_zip: Path,
    profiles_dir: Path,
    collections_dir: Path,
    *,
    mode: str = MODE_MERGE,
    careers_dir: Path | None = None,
) -> ImportResult:
    """Restore profiles + collections (+ careers when ``careers_dir`` is given).

    ``mode`` is :data:`MODE_MERGE` (default) or :data:`MODE_REPLACE`. Entries are
    matched by filename; zip paths are sanitised (basename only) to avoid writing
    outside the target directories. Archives without ``careers/`` (older exports)
    restore as before.
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
        careers_in_zip = [
            n for n in zf.namelist()
            if n.replace("\\", "/").startswith(f"{CAREERS_SECTION}/")
        ]
        if mode == MODE_REPLACE and careers_dir is not None and careers_in_zip:
            for p in _career_files(careers_dir):
                p.unlink()
        imported_careers: set[str] = set()
        for name in zf.namelist():
            parts = name.replace("\\", "/").split("/")
            if not parts[-1].lower().endswith(".json"):
                continue
            if len(parts) == 2 and parts[0] in targets:
                base = _safe_name(parts[1])
                if base is None:
                    continue
                _write_bytes(targets[parts[0]] / base, zf.read(name))
                if parts[0] == "profiles":
                    result.profiles_imported += 1
                else:
                    result.collections_imported += 1
            elif len(parts) == 3 and parts[0] == CAREERS_SECTION and careers_dir is not None:
                slug, base = _safe_name(parts[1]), _safe_name(parts[2])
                if slug is None or base is None:
                    continue
                _write_bytes(careers_dir / slug / base, zf.read(name))
                imported_careers.add(slug)
        result.careers_imported = len(imported_careers)
    return result


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@dataclass
class MirrorResult:
    copied: int = 0
    pruned: int = 0
    warnings: list[str] = field(default_factory=list)


def _read_marker(backup_dir: Path) -> dict | None:
    try:
        data = json.loads((backup_dir / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def mirror_config(
    profiles_dir: Path | None,
    collections_dir: Path | None,
    backup_dir: Path,
    careers_dir: Path | None = None,
) -> MirrorResult:
    """Mirror the config into ``backup_dir`` (overwrite + guarded prune).

    Files removed from the source are also removed from the mirror, but only
    when (1) ``backup_dir`` already carries our marker file (so a folder we did
    not create is never pruned on its first run) and (2) the source is not
    empty (an unmounted drive or a wrong path must not wipe the backup).
    """
    result = MirrorResult()
    backup_dir.mkdir(parents=True, exist_ok=True)
    marker_known = _read_marker(backup_dir) is not None

    wanted: dict[Path, Path] = {}  # relative target path -> source file
    for section, src in (("profiles", profiles_dir), ("collections", collections_dir)):
        if src and src.is_dir():
            for p in src.glob("*.json"):
                wanted[Path(section) / p.name] = p
    for p in _career_files(careers_dir):
        wanted[Path(CAREERS_SECTION) / p.parent.name / p.name] = p

    for rel, src_file in wanted.items():
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(src_file, dst)
        result.copied += 1

    existing = [
        p for section in (*_FLAT_SECTIONS, CAREERS_SECTION)
        for p in (backup_dir / section).rglob("*.json")
    ]
    stale = [p for p in existing if p.relative_to(backup_dir) not in wanted]
    if stale and not wanted:
        result.warnings.append(
            "Source vide : aucune suppression dans la cible (dossier non monté ou mauvais chemin ?)."
        )
    elif stale and not marker_known:
        result.warnings.append(
            "Dossier de sauvegarde non créé par l'application : fichiers existants conservés."
        )
    else:
        for p in stale:
            p.unlink()
            result.pruned += 1
            if p.parent != backup_dir and not any(p.parent.iterdir()):
                p.parent.rmdir()  # empty career folder

    marker = {
        "app": "fs25-profile-switcher",
        "host": socket.gethostname(),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    _write_bytes(backup_dir / MARKER_NAME, json.dumps(marker, indent=2).encode("utf-8"))
    return result


def snapshot_config(
    profiles_dir: Path | None,
    collections_dir: Path | None,
    careers_dir: Path | None,
    backup_dir: Path,
    *,
    keep: int = DEFAULT_KEEP_SNAPSHOTS,
    min_interval_s: float = DEFAULT_SNAPSHOT_INTERVAL_S,
) -> Path | None:
    """Write ``snapshots/<date>-<host>.zip`` unless a recent one exists; keep the last ``keep``.

    Returns the new snapshot path, or ``None`` when skipped (too recent / empty source).
    """
    snap_dir = backup_dir / SNAPSHOT_DIR
    existing = sorted(snap_dir.glob("*.zip")) if snap_dir.is_dir() else []
    if existing and time.time() - existing[-1].stat().st_mtime < min_interval_s:
        return None
    has_source = any(
        d and d.is_dir() and any(d.glob("*.json")) for d in (profiles_dir, collections_dir)
    ) or bool(_career_files(careers_dir))
    if not has_source:
        return None
    host = "".join(c for c in socket.gethostname() if c.isalnum() or c in "-_") or "pc"
    dest = snap_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{host}.zip"
    export_config(profiles_dir, collections_dir, dest, careers_dir)
    snapshots = sorted(snap_dir.glob("*.zip"))
    for old in snapshots[: max(0, len(snapshots) - max(1, keep))]:
        old.unlink(missing_ok=True)
    return dest


@dataclass
class TargetReport:
    target: Path
    ok: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    copied: int = 0
    pruned: int = 0
    snapshot: Path | None = None
    seconds: float = 0.0


def backup_all(
    targets: list[Path],
    profiles_dir: Path | None,
    collections_dir: Path | None,
    careers_dir: Path | None = None,
    *,
    keep_snapshots: int = DEFAULT_KEEP_SNAPSHOTS,
) -> list[TargetReport]:
    """Mirror + snapshot to every target. One report per target; failures are isolated."""
    reports: list[TargetReport] = []
    for target in targets:
        report = TargetReport(target=target)
        started = time.monotonic()
        try:
            mirrored = mirror_config(profiles_dir, collections_dir, target, careers_dir)
            report.copied, report.pruned = mirrored.copied, mirrored.pruned
            report.warnings = list(mirrored.warnings)
            report.snapshot = snapshot_config(
                profiles_dir, collections_dir, careers_dir, target, keep=keep_snapshots
            )
            report.ok = True
        except OSError as exc:
            report.error = str(exc)
        report.seconds = time.monotonic() - started
        reports.append(report)
    return reports


def summarize_reports(reports: list[TargetReport]) -> str:
    """One-line status, e.g. ``Sauvegarde config : 1/2 OK (NAS : …)``."""
    if not reports:
        return ""
    ok = sum(1 for r in reports if r.ok)
    text = f"Sauvegarde config : {ok}/{len(reports)} OK"
    problems = [
        f"{r.target.name or r.target} : {r.error}" if not r.ok else
        f"{r.target.name or r.target} : {r.warnings[0]}"
        for r in reports if not r.ok or r.warnings
    ]
    return text + (f" ({' ; '.join(problems)})" if problems else "")
