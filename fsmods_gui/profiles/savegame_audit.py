"""Audit a FS25 savegame to find which profile mods it actually uses.

A FS25 savegame folder (``savegameN/``) tells us two different things:

* ``careerSavegame.xml`` has a ``<mods>`` block listing every mod that was
  *loaded* when the game was saved (modName, title, version, required). This is
  the "was present" set — it does not prove a mod is used.
* ``vehicles.xml`` / ``placeables.xml`` / ``items.xml`` … reference mods by
  ``modName="…"`` attribute and ``$moddir$ModName/…`` paths for content that is
  *physically placed in the world* (owned vehicles, built placeables). This is
  the real "in use" signal.

From these we classify each mod of a profile:

* **used**   — placed in the world, or it is the map → keep.
* **loaded** — in the save's mod list but with no world object (often scripts,
  packs, decoration) → examine before removing.
* **absent** — not even in the save's mod list → wasn't loaded for this save.

Coverage caveat: a mod can be needed without placing an object (scripts, map
dependencies). We therefore never delete anything — the GUI only proposes
removing mods *from the profile*, and pre-checks only the safest tier.

Pure logic, no Qt. Relies on the FS mod identity ``mod_id`` = ``.zip`` stem (#2).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog
from .dependencies import build_modid_index
from .profile import Profile

STATUS_USED = "used"
STATUS_LOADED = "loaded"
STATUS_ABSENT = "absent"

STATUS_LABELS_FR = {
    STATUS_USED: "Utilisé",
    STATUS_LOADED: "Chargé, sans objet placé",
    STATUS_ABSENT: "Absent de cette sauvegarde",
}

CAREER_FILE = "careerSavegame.xml"

# modName="FS25_Foo" attribute, and $moddir$FS25_Foo path token.
_MODNAME_ATTR_RE = re.compile(r'modName="([^"]+)"')
_MODDIR_RE = re.compile(r"\$moddir\$([A-Za-z0-9_]+)")


@dataclass
class ModRef:
    mod_id: str
    title: str = ""
    version: str = ""
    required: bool = False


@dataclass
class SavegameInfo:
    directory: Path
    name: str = ""
    map_title: str = ""
    map_mod_id: str | None = None
    save_date: str = ""
    loaded: dict[str, ModRef] = field(default_factory=dict)  # key: lower mod_id
    used: set[str] = field(default_factory=set)              # lower mod_ids placed in world

    @property
    def label(self) -> str:
        parts = [self.directory.name]
        if self.name:
            parts.append(self.name)
        if self.map_title:
            parts.append(self.map_title)
        if self.save_date:
            parts.append(self.save_date)
        return " — ".join(parts)


def list_savegames(user_dir: Path) -> list[Path]:
    """Return ``savegame*`` folders that contain a ``careerSavegame.xml``.

    Sorted naturally (savegame2 before savegame10); non-numeric ones (e.g.
    ``savegameBackup``) come last.
    """
    if not user_dir.is_dir():
        return []
    out: list[Path] = []
    for child in user_dir.iterdir():
        if not child.is_dir() or not child.name.lower().startswith("savegame"):
            continue
        if (child / CAREER_FILE).is_file():
            out.append(child)

    def sort_key(p: Path) -> tuple[int, int, str]:
        m = re.search(r"(\d+)$", p.name)
        if m:
            return (0, int(m.group(1)), "")
        return (1, 0, p.name.lower())

    out.sort(key=sort_key)
    return out


def _parse_career(career_path: Path, info: SavegameInfo) -> None:
    try:
        root = ET.fromstring(career_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ET.ParseError):
        return
    settings = root.find("settings")
    if settings is not None:
        info.name = (settings.findtext("savegameName") or "").strip()
        info.map_title = (settings.findtext("mapTitle") or "").strip()
        info.save_date = (
            settings.findtext("saveDateFormatted")
            or settings.findtext("saveDate")
            or ""
        ).strip()
        map_id = (settings.findtext("mapId") or "").strip()
        if map_id:
            # mapId looks like "FS25_The_Combes.SampleModMap" → the mod is the
            # part before the first dot.
            info.map_mod_id = map_id.split(".", 1)[0] or None

    # <mod modName="…" title="…" version="…" required="true|false"/>
    for mod in root.iter("mod"):
        name = (mod.get("modName") or "").strip()
        if not name:
            continue
        info.loaded[name.lower()] = ModRef(
            mod_id=name,
            title=(mod.get("title") or "").strip(),
            version=(mod.get("version") or "").strip(),
            required=(mod.get("required") or "").strip().lower() == "true",
        )


def _scan_world_usage(savegame_dir: Path, info: SavegameInfo) -> None:
    """Collect mod_ids referenced by world content (every xml except career)."""
    for xml_file in savegame_dir.glob("*.xml"):
        if xml_file.name == CAREER_FILE:
            continue
        try:
            text = xml_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in _MODNAME_ATTR_RE.findall(text):
            info.used.add(name.strip().lower())
        for name in _MODDIR_RE.findall(text):
            info.used.add(name.strip().lower())


def parse_savegame(savegame_dir: Path) -> SavegameInfo:
    """Parse a savegame folder into a :class:`SavegameInfo`."""
    info = SavegameInfo(directory=savegame_dir)
    career = savegame_dir / CAREER_FILE
    if career.is_file():
        _parse_career(career, info)
    _scan_world_usage(savegame_dir, info)
    if info.map_mod_id:
        info.used.add(info.map_mod_id.lower())
    return info


@dataclass
class AuditRow:
    filename: str
    mod_id: str
    title: str
    status: str
    is_map: bool = False
    is_script: bool = False
    suggested_remove: bool = False


@dataclass
class MissingRow:
    """A mod the save used that the profile lacks."""

    mod_id: str
    title: str
    filename: str | None = None  # set if present in the library (=> addable)

    @property
    def in_library(self) -> bool:
        return self.filename is not None


@dataclass
class AuditReport:
    savegame_label: str
    rows: list[AuditRow] = field(default_factory=list)
    missing_in_profile: list[MissingRow] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        c = {STATUS_USED: 0, STATUS_LOADED: 0, STATUS_ABSENT: 0}
        for r in self.rows:
            c[r.status] = c.get(r.status, 0) + 1
        return c


def audit_profile(
    profile: Profile,
    info: SavegameInfo,
    catalog: Catalog | None,
) -> AuditReport:
    """Classify every profile mod against the savegame (prudent pre-selection).

    Pre-checks for removal only the **absent** tier (mods not even loaded in the
    save), never the map. ``loaded`` and ``used`` rows are left unchecked.
    """
    report = AuditReport(savegame_label=info.label)

    profile_ids: set[str] = set()
    for filename in profile.all_mod_filenames():
        mod_id = Path(filename).stem
        key = mod_id.lower()
        profile_ids.add(key)

        entry = catalog.get(filename) if catalog else None
        is_script = bool(entry and entry.category == "Script")
        is_map = filename == profile.map_mod or (
            info.map_mod_id is not None and key == info.map_mod_id.lower()
        )

        if is_map or key in info.used:
            status = STATUS_USED
        elif key in info.loaded:
            status = STATUS_LOADED
        else:
            status = STATUS_ABSENT

        report.rows.append(
            AuditRow(
                filename=filename,
                mod_id=mod_id,
                title=entry.display_title if entry else mod_id,
                status=status,
                is_map=is_map,
                is_script=is_script,
                suggested_remove=(status == STATUS_ABSENT and not is_map),
            )
        )

    report.rows.sort(key=lambda r: (_status_order(r.status), r.title.lower()))

    # ---- bidirectional: mods the save USED but the profile lacks
    index = build_modid_index(catalog)  # lower mod_id -> filename
    for key in sorted(info.used):
        if key in profile_ids:
            continue
        ref = info.loaded.get(key)
        title = ref.title if ref and ref.title else key
        report.missing_in_profile.append(
            MissingRow(
                mod_id=ref.mod_id if ref else key,
                title=title,
                filename=index.get(key),
            )
        )

    return report


def _status_order(status: str) -> int:
    return {STATUS_ABSENT: 0, STATUS_LOADED: 1, STATUS_USED: 2}.get(status, 3)
