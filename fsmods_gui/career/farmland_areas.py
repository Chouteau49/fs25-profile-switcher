"""Farmland areas computed from the map's ``farmlands`` info layer.

The savegame only says *which* farmlands a farm owns (``farmland.xml``: ``id`` +
``farmId``). The area lives in the map: ``infoLayer_farmlands.grle`` stores one
byte per pixel, the farmland id. Pixels × pixel size gives the hectares the game
itself shows on the map screen.

Readable maps: base-game maps (``<install>/data/maps/…``) and mod maps (zip or
folder, in the game's mods folder or the library). DLC maps (``pdlc_…``) ship
encrypted in a ``.dlc`` file: their areas cannot be read, the player types them
per parcel instead (see :class:`~fsmods_gui.career.store.CareerSettings`).

GRLE layout (checked against the base maps and Le Mechet)::

    0  "GRLE"           4  uint16 version (1)
    6  uint16 width/256 10 uint16 height/256
    13 uint8 bytes per pixel (1)
    17 uint32 compressed size, RLE data from offset 21

RLE: each byte is a value; when a value is immediately repeated, the following
bytes are an extra repeat count (``255`` means "add 255 and keep reading").

Pure logic, no Qt.
"""
from __future__ import annotations

import posixpath
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath

_GRLE_HEADER = 21


def grle_value_counts(data: bytes) -> tuple[int, int, list[int]] | None:
    """``(width, height, pixel count per value 0..255)`` of a 1-byte GRLE, else None."""
    if len(data) < _GRLE_HEADER or data[:4] != b"GRLE":
        return None
    width = struct.unpack_from("<H", data, 6)[0] * 256
    height = struct.unpack_from("<H", data, 10)[0] * 256
    if data[13] != 1 or not width or not height:
        return None  # >255 farmlands (2 bytes per pixel): not supported
    total = width * height
    counts = [0] * 256
    done = 0
    i = _GRLE_HEADER
    end = len(data)
    try:
        while done < total and i < end:
            value = data[i]
            i += 1
            run = 1
            if i < end and data[i] == value:
                i += 1
                run = 2
                while True:
                    extra = data[i]
                    i += 1
                    run += extra
                    if extra != 255:
                        break
            counts[value] += run
            done += run
    except IndexError:
        return None
    if done != total:
        return None
    return width, height, counts


# ------------------------------------------------------------------ map files


class _Files:
    """Read files of a map, from a folder or a zip, by forward-slash relative path."""

    def __init__(self, root: Path, *, searchable: bool = True) -> None:
        self.root = root
        self._searchable = searchable  # never rglob the whole game install
        self._zip = zipfile.ZipFile(root) if root.is_file() else None
        self._lower: dict[str, str] = {}
        if self._zip is not None:
            self._lower = {n.lower(): n for n in self._zip.namelist()}

    def read(self, rel: str) -> bytes | None:
        rel = rel.replace("\\", "/").lstrip("/")
        try:
            if self._zip is not None:
                name = self._lower.get(rel.lower())
                return self._zip.read(name) if name else None
            path = self.root / rel
            return path.read_bytes() if path.is_file() else None
        except (OSError, KeyError, zipfile.BadZipFile):
            return None

    def find(self, suffix: str) -> str | None:
        """The only file whose path ends with ``suffix`` (case-insensitive), if any."""
        suffix = suffix.lower()
        if not self._searchable:
            return None
        if self._zip is not None:
            hits = [n for low, n in self._lower.items() if low.endswith(suffix)]
        else:
            hits = [
                p.relative_to(self.root).as_posix()
                for p in self.root.rglob("*")
                if p.as_posix().lower().endswith(suffix)
            ]
        return hits[0] if len(hits) == 1 else None

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()


def _xml(data: bytes | None) -> ET.Element | None:
    if not data:
        return None
    try:
        return ET.fromstring(data.decode("utf-8-sig", errors="replace"))
    except ET.ParseError:
        return None


@dataclass
class MapAreas:
    """Area (ha) of every farmland of a map, plus where it was read."""

    areas: dict[str, float] = field(default_factory=dict)
    source: str = ""


def is_dlc_map(map_id: str) -> bool:
    return map_id.lower().startswith("pdlc_")


def _find_mod(mod_name: str, mod_dirs: Sequence[Path]) -> Path | None:
    for base in mod_dirs:
        for candidate in (base / f"{mod_name}.zip", base / mod_name):
            if candidate.exists():
                return candidate
    return None


class _Resolver:
    """Resolves ``$data/…`` against the install and plain paths against the map's mod."""

    def __init__(self, own: _Files | None, install: _Files | None) -> None:
        self.own = own
        self.install = install

    def read(self, ref: str, relative_to: str = "") -> tuple[bytes | None, str, _Files | None]:
        """``(content, path inside its container, container)`` of a map file reference."""
        ref = ref.replace("\\", "/")
        if ref.startswith("$data/"):
            rel = "data/" + ref[len("$data/"):]
            files = self.install
        else:
            joined = str(PurePosixPath(relative_to).parent / ref) if relative_to else ref
            rel = posixpath.normpath(joined).lstrip("/")
            files = self.own
        if files is None:
            return None, rel, None
        return files.read(rel), rel, files


def _grle_for(resolver: _Resolver, config: ET.Element, farmlands: ET.Element) -> bytes | None:
    """Locate and read the farmlands GRLE referenced by the map config.

    Candidates, in order: ``densityMapFilename`` (mod-root relative or ``$data``),
    the file the map ``.i3d`` declares for the info layer (relative to the i3d),
    then any ``infoLayer_<name>.grle`` in the map mod.
    """
    candidates: list[tuple[str, str]] = []  # (reference, i3d path it is relative to)
    search: list[str] = []
    density = farmlands.get("densityMapFilename")
    if density:
        candidates.append((density, ""))
    else:
        layer = farmlands.get("infoLayer") or "farmlands"
        i3d_ref = (config.findtext("filename") or "").strip()
        if i3d_ref:
            raw, i3d_rel, _files = resolver.read(i3d_ref)
            text = raw.decode("utf-8", errors="replace") if raw else ""
            m = re.search(rf'<InfoLayer\b[^>]*\bname="{re.escape(layer)}"[^>]*>', text)
            fid = re.search(r'\bfileId="(\d+)"', m.group(0)) if m else None
            f = (
                re.search(rf'<File\b[^>]*\bfileId="{fid.group(1)}"[^>]*>', text) if fid else None
            )
            name = re.search(r'\bfilename="([^"]+)"', f.group(0)) if f else None
            if name:
                ref = name.group(1)
                candidates.append((ref, "" if ref.startswith("$") else i3d_rel))
        search.append(f"infoLayer_{layer}.grle")
    for ref, i3d_rel in candidates:
        grle_ref = re.sub(r"\.(png|grle|gdm)$", ".grle", ref, flags=re.IGNORECASE)
        data, _rel, _f = resolver.read(grle_ref, i3d_rel)
        if data:
            return data
    for filename in search:  # last resort: by convention, inside the map mod only
        found = resolver.own.find(filename) if resolver.own is not None else None
        data = resolver.own.read(found) if found and resolver.own is not None else None
        if data:
            return data
    return None


def _compute(map_id: str, install_dir: Path | None, mod_dirs: tuple[Path, ...]) -> MapAreas | None:
    if not map_id or is_dlc_map(map_id):
        return None
    install = (
        _Files(install_dir, searchable=False) if install_dir and install_dir.is_dir() else None
    )
    own: _Files | None = None
    try:
        mod_name, dot, inner_id = map_id.partition(".")
        if dot:  # mod map: "<modName>.<mapId>"
            mod_path = _find_mod(mod_name, mod_dirs)
            if mod_path is None:
                return None
            own = _Files(mod_path)
            desc = _xml(own.read("modDesc.xml"))
            if desc is None:
                return None
            maps = [m for m in desc.iter("map") if m.get("configFilename")]
            chosen = next((m for m in maps if m.get("id") == inner_id), None)
            chosen = chosen if chosen is not None else (maps[0] if len(maps) == 1 else None)
            if chosen is None:
                return None
            config_ref = chosen.get("configFilename", "")
            source = mod_path.name
        else:  # base-game map: "MapEU" -> data/maps/mapEU/mapEU.xml
            if install is None:
                return None
            maps_dir = install.root / "data" / "maps"
            folder = next(
                (p.name for p in maps_dir.iterdir() if p.is_dir() and p.name.lower() == map_id.lower()),
                None,
            ) if maps_dir.is_dir() else None
            if folder is None:
                return None
            own = install
            config_ref = f"$data/maps/{folder}/{folder}.xml"
            source = f"carte officielle {folder}"
        resolver = _Resolver(own, install)
        raw, _config_rel, _f = resolver.read(config_ref)
        config = _xml(raw)
        if config is None:
            return None
        width = float(config.get("width") or 0)
        height = float(config.get("height") or 0)
        fl_ref = config.find("farmlands")
        if fl_ref is None or not fl_ref.get("filename") or not width or not height:
            return None
        fl_raw, fl_rel, _f = resolver.read(fl_ref.get("filename", ""))
        fl_root = _xml(fl_raw)
        farmlands = fl_root.find("farmlands") if fl_root is not None else None
        if farmlands is None:
            return None
        grle = _grle_for(resolver, config, farmlands)
        decoded = grle_value_counts(grle) if grle else None
        if decoded is None:
            return None
        gw, gh, counts = decoded
        pixel_m2 = (width / gw) * (height / gh)
        # Only ids declared by the map are farmlands: 255 (and 0) mean "no farmland".
        declared = {f.get("id") for f in farmlands.iter("farmland") if f.get("id")}
        areas = {
            str(value): n * pixel_m2 / 10_000
            for value, n in enumerate(counts)
            if n and (str(value) in declared if declared else value not in (0, 255))
        }
        return MapAreas(areas=areas, source=source)
    finally:
        if own is not None and own is not install:
            own.close()
        if install is not None:
            install.close()


@lru_cache(maxsize=16)
def _cached(map_id: str, install_dir: Path | None, mod_dirs: tuple[Path, ...]) -> MapAreas | None:
    try:
        return _compute(map_id, install_dir, mod_dirs)
    except (OSError, ValueError, zipfile.BadZipFile, struct.error):
        return None


def map_farmland_areas(
    map_id: str, install_dir: Path | None = None, mod_dirs: Sequence[Path] = ()
) -> MapAreas | None:
    """Hectares of every farmland of the map, or None when the map is unreadable
    (DLC, map mod not found, unexpected layout). Cached per session."""
    return _cached(map_id, install_dir, tuple(mod_dirs))
