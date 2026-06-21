"""Detect duplicate mods in the library.

Two kinds of duplicates show up in a real FS mod library:

* **Re-downloads / copies** — the same file downloaded twice, e.g.
  ``FS25_Courseplay.zip`` and ``FS25_Courseplay (1).zip``, or a version-suffixed
  copy ``FS25_Courseplay_v1.2.zip`` alongside ``FS25_Courseplay.zip``.
* **Same mod, different packaging** — distinct filenames that carry the same
  ``title`` + ``author`` (often two versions of the same mod).

The logic here is pure (no Qt) and works off the already-scanned
:class:`~fsmods_gui.profiles.catalog.Catalog`, so it costs almost nothing.
Results are *indicative*: badly packaged mods may be over- or under-detected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .catalog import Catalog, CatalogEntry

# Markers appended by browsers/users when a file is duplicated, plus trailing
# version tags. Stripping them reveals the underlying mod identity.
#
# These patterns are deliberately conservative: a bare trailing number (``Mod1``
# vs ``Mod2``) or a two-part dotted number (``MAN_TGX_18.500``, a model name)
# is NOT a copy/version marker — stripping those merged genuinely different
# mods. We only strip what unambiguously marks a copy or a version.
_COPY_SUFFIX_RE = re.compile(r"\s*\((\d+)\)$")  # " (1)", " (2)"
# Explicit version tag with a "v": "_v1", "_v1.2.3", " v2_0".
_VERSION_V_RE = re.compile(r"[\s_-]*v\d+(?:[._]\d+)*$", re.IGNORECASE)
# Bare dotted version with 3+ components: "1.0.0.0", "1.2.3" — but NOT a
# two-part number like "18.500" (truck/engine model), which stays part of the name.
_VERSION_BARE_RE = re.compile(r"[\s_-]*\d+(?:[._]\d+){2,}$")
# Words users append when keeping an extra copy. No bare "\d+" and no
# "new/final" here — those are too often part of the real mod name.
_WORD_SUFFIX_RE = re.compile(
    r"[\s_-]*(copy\d*|copie\d*|old|ancien|backup|bak)$",
    re.IGNORECASE,
)

DUP_FILENAME = "filename"  # same base name, copy/version markers stripped
DUP_CONTENT = "content"    # same title + author, different filenames


def normalize_stem(filename: str) -> str:
    """Collapse a ``.zip`` filename to its underlying mod identity.

    Strips copy markers (`` (1)``), trailing version tags (``_v1.2.3``) and a few
    common suffix words (``copy``, ``old``…). Lower-cased so matching is
    case-insensitive.
    """
    stem = Path(filename).stem.lower().strip()
    # Apply repeatedly: "FS25_Mod_old (1)" -> "FS25_Mod".
    for _ in range(4):
        before = stem
        stem = _COPY_SUFFIX_RE.sub("", stem)
        stem = _VERSION_V_RE.sub("", stem)
        stem = _VERSION_BARE_RE.sub("", stem)
        stem = _WORD_SUFFIX_RE.sub("", stem)
        stem = stem.strip(" _-")
        if stem == before:
            break
    return stem or Path(filename).stem.lower()


def _content_key(entry: CatalogEntry) -> str | None:
    """A (title, author) identity, or ``None`` when too weak to be reliable.

    Both a real title *and* a real author are required: a title alone is too
    weak — two unrelated mods sharing a generic title ("Trailer", "Pack") and
    carrying no author would otherwise be grouped as a false duplicate.
    """
    title = (entry.title or "").strip().lower()
    author = (entry.author or "").strip().lower()
    if not title or title == entry.filename.lower():
        return None
    if len(title) < 3:
        return None
    if not author:
        return None
    return f"{title}\x00{author}"


@dataclass
class DuplicateGroup:
    """A set of catalog entries that look like the same mod."""

    key: str
    kind: str  # DUP_FILENAME | DUP_CONTENT
    entries: list[CatalogEntry]

    @property
    def label(self) -> str:
        """Human-friendly group heading."""
        if self.kind == DUP_CONTENT:
            return self.entries[0].display_title
        return self.key

    def filenames(self) -> list[str]:
        return [e.filename for e in self.entries]


def find_duplicate_groups(catalog: Catalog | None) -> list[DuplicateGroup]:
    """Return groups of >1 entries that appear to be the same mod.

    A filename-based group always wins over a content-based one for the same set
    of files, so an entry never shows up in two groups for the same reason.
    Groups are sorted by size (largest first) then label.
    """
    if catalog is None or len(catalog) == 0:
        return []

    entries = list(catalog.entries.values())

    by_stem: dict[str, list[CatalogEntry]] = {}
    for entry in entries:
        by_stem.setdefault(normalize_stem(entry.filename), []).append(entry)

    groups: list[DuplicateGroup] = []
    claimed: set[str] = set()  # filenames already reported in a filename group

    for key, members in by_stem.items():
        if len(members) > 1:
            members.sort(key=lambda e: e.filename.lower())
            groups.append(DuplicateGroup(key=key, kind=DUP_FILENAME, entries=members))
            claimed.update(e.filename for e in members)

    by_content: dict[str, list[CatalogEntry]] = {}
    for entry in entries:
        if entry.filename in claimed:
            continue
        ckey = _content_key(entry)
        if ckey is not None:
            by_content.setdefault(ckey, []).append(entry)

    for key, members in by_content.items():
        if len(members) > 1:
            members.sort(key=lambda e: e.filename.lower())
            groups.append(DuplicateGroup(key=key, kind=DUP_CONTENT, entries=members))

    groups.sort(key=lambda g: (-len(g.entries), g.label.lower()))
    return groups


def duplicate_filenames(catalog: Catalog | None) -> set[str]:
    """Flat set of every filename involved in any duplicate group."""
    names: set[str] = set()
    for group in find_duplicate_groups(catalog):
        names.update(group.filenames())
    return names
