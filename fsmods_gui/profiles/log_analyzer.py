"""Parse the FS25/FS22 ``log.txt`` and surface problems in French.

Giants does not document the log format, so parsing is *best-effort* and pattern
based: every line we don't recognise as an error/warning is simply ignored, and
recognised lines we can't classify fall back to a generic French label. Coverage
is meant to grow as new real-world cases appear.

Pure logic, no Qt — the GUI renders :class:`LogIssue` rows in a table.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Severity / kind taxonomy
# --------------------------------------------------------------------------- #
SEV_ERROR = "error"
SEV_WARNING = "warning"

KIND_LUA = "lua"
KIND_MISSING = "missing_mod"
KIND_CONFLICT = "conflict"
KIND_DUPLICATE = "duplicate"
KIND_LOAD = "load"
KIND_XML = "xml"
KIND_OTHER = "other"

# French labels for the *kind* column.
KIND_LABELS_FR: dict[str, str] = {
    KIND_LUA: "Erreur Lua",
    KIND_MISSING: "Mod introuvable",
    KIND_CONFLICT: "Conflit",
    KIND_DUPLICATE: "Doublon",
    KIND_LOAD: "Chargement",
    KIND_XML: "Fichier XML",
    KIND_OTHER: "Autre",
}

SEVERITY_LABELS_FR: dict[str, str] = {
    SEV_ERROR: "Erreur",
    SEV_WARNING: "Avertissement",
}


@dataclass
class LogIssue:
    severity: str          # SEV_ERROR | SEV_WARNING
    kind: str              # KIND_*
    message_fr: str        # human French summary
    raw: str               # original log line(s)
    mod: str | None = None # mod name if we could attribute it
    line_no: int = 0       # 1-based line where it first appeared
    count: int = 1         # number of identical occurrences
    callstack: list[str] = field(default_factory=list)  # trimmed traceback lines

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS_FR.get(self.severity, self.severity)

    @property
    def kind_label(self) -> str:
        return KIND_LABELS_FR.get(self.kind, self.kind)


# --------------------------------------------------------------------------- #
# Classification rules
# --------------------------------------------------------------------------- #
# Each rule: (compiled pattern on the *lower-cased* line, kind, French template).
# ``{mod}`` in a template is filled when a mod name was extracted.
_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"running lua method|lua method '|\.lua:\d+|stack traceback|callstack"),
     KIND_LUA, "Erreur d'exécution d'un script Lua."),
    (re.compile(r"could not (find|load|open) .*mod|mod .* not found|failed to load mod|missing mod"),
     KIND_MISSING, "Mod requis introuvable ou impossible à charger."),
    (re.compile(r"requires .*mod|depends on|dependency"),
     KIND_MISSING, "Dépendance de mod manquante."),
    (re.compile(r"already (defined|registered|loaded|exists)|conflict|registered twice|name collision"),
     KIND_CONFLICT, "Conflit : un élément est défini plusieurs fois."),
    (re.compile(r"duplicate|loaded more than once|same mod"),
     KIND_DUPLICATE, "Mod ou ressource chargé en double."),
    (re.compile(r"failed to (open|parse|read) .*xml|invalid xml|xml .*(error|invalid)|schema"),
     KIND_XML, "Fichier XML invalide ou illisible."),
    (re.compile(r"failed to load|could not load|error loading|unable to load|texture|i3d|shader"),
     KIND_LOAD, "Échec de chargement d'une ressource."),
]

# Extract a mod name. FS logs reference mods as ``FS25_Something`` / ``FS22_...``,
# sometimes inside a path ``.../mods/FS25_Something.zip`` or ``[FS25_Something]``.
_MOD_RE = re.compile(r"\b(FS2[25]_[A-Za-z0-9_]+)", re.IGNORECASE)

# A line is "interesting" only if it announces an error or warning.
_ERROR_RE = re.compile(r"^\s*error\b", re.IGNORECASE)
_WARNING_RE = re.compile(r"^\s*warning\b", re.IGNORECASE)

# Some lines embed the marker mid-line, e.g. "  Error: ...".
_INLINE_ERROR_RE = re.compile(r"\berror\s*[:\(]", re.IGNORECASE)
_INLINE_WARNING_RE = re.compile(r"\bwarning\s*[:\(]", re.IGNORECASE)


def _severity_of(line: str) -> str | None:
    if _ERROR_RE.search(line) or _INLINE_ERROR_RE.search(line):
        return SEV_ERROR
    if _WARNING_RE.search(line) or _INLINE_WARNING_RE.search(line):
        return SEV_WARNING
    return None


def _classify(line_lower: str) -> tuple[str, str]:
    for pattern, kind, template in _RULES:
        if pattern.search(line_lower):
            return kind, template
    return KIND_OTHER, "Problème signalé par le jeu."


# FS prefixes most lines with a timestamp, e.g. "2026-06-19 11:55:37.286 " or a
# bare "11:55:37.286 ". It's unique per line, so it must be stripped *before*
# building the dedup key — otherwise identical errors (the per-frame Lua
# ``update`` crash) never merge and flood the report with thousands of rows.
_TIMESTAMP_RE = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}\s+)?\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?\s*"
)


def _strip_timestamp(line: str) -> str:
    return _TIMESTAMP_RE.sub("", line, count=1)


def _strip_marker(line: str) -> str:
    """Remove a leading timestamp then an ``Error:`` / ``Warning (xxx):`` marker."""
    line = _strip_timestamp(line)
    return re.sub(r"^\s*(error|warning)\b\s*(\([^)]*\))?\s*:?\s*", "", line, flags=re.IGNORECASE).strip()


# A real FS log entry always starts with a timestamp. Lines that don't (Lua
# error details, ``LUA call stack`` traceback frames) belong to the preceding
# entry — that's where the culprit ``.../mods/FS25_Xxx/....lua`` lives.
_HAS_TIMESTAMP_RE = re.compile(r"^\s*(?:\d{4}-\d{2}-\d{2}\s+)?\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?\b")

# Owning mod of a script path, e.g. ".../mods/FS25_Courseplay/scripts/X.lua".
_MOD_PATH_RE = re.compile(r"[\\/]mods[\\/](FS2[25]_[A-Za-z0-9_]+)", re.IGNORECASE)


def _trim_callstack_line(line: str) -> str:
    """Drop the absolute prefix of a traceback frame for readable display.

    ``C:/.../mods/FS25_Courseplay/scripts/X.lua:370: boom`` becomes
    ``FS25_Courseplay/scripts/X.lua:370: boom``; base-game frames are kept from
    their ``dataS/`` root. Otherwise the line is returned trimmed.
    """
    s = line.strip().lstrip("=").strip()
    m = re.search(r"[\\/]mods[\\/](.*)$", s, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(dataS?[\\/].*)$", s)
    return m.group(1) if m else s


def _attach_continuation(issue: LogIssue, line: str) -> None:
    """Fold a non-timestamped traceback line into ``issue`` and grab its mod."""
    issue.callstack.append(_trim_callstack_line(line))
    if issue.mod is None:
        m = _MOD_PATH_RE.search(line)
        if m:
            issue.mod = m.group(1)


def _finalize(issue: LogIssue) -> None:
    """Fold the captured traceback into the message before de-duplication.

    For a Lua crash the error line itself is generic (``Running LUA method
    'update'``); the useful part — *which* script failed and why — is the first
    traceback frame. Appending it both informs the reader and lets thousands of
    identical per-frame crashes collapse into a single counted row.
    """
    if not issue.callstack:
        return
    reason = next((c for c in issue.callstack if ".lua" in c.lower()), issue.callstack[0])
    if reason and reason.lower() not in issue.message_fr.lower():
        snippet = reason if len(reason) <= 200 else reason[:197] + "…"
        issue.message_fr = f"{issue.message_fr} — {snippet}"


def parse_log_text(text: str) -> list[LogIssue]:
    """Parse raw log text into a de-duplicated list of :class:`LogIssue`.

    Each error/warning entry absorbs the non-timestamped lines that follow it
    (its Lua traceback), which is how the culprit mod gets attributed. Identical
    (kind, message, mod) issues are then merged with a ``count``. Ordered by
    severity (errors first) then first appearance.
    """
    raw_issues: list[LogIssue] = []
    current: LogIssue | None = None  # last error/warning, to attach traceback to

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip():
            current = None  # a blank line ends a traceback block
            continue

        severity = _severity_of(line)
        if severity is None:
            # Not an error/warning announcement. A non-timestamped line here is a
            # traceback frame of the preceding entry; a timestamped info/data line
            # ends the block.
            if current is not None and not _HAS_TIMESTAMP_RE.match(line):
                _attach_continuation(current, line)
            else:
                current = None
            continue
        line_lower = line.lower()
        kind, template = _classify(line_lower)
        mod_match = _MOD_RE.search(line)
        mod = mod_match.group(1) if mod_match else None

        detail = _strip_marker(line)
        message = template
        if detail and detail.lower() not in template.lower():
            # Append a trimmed snippet of the original so context isn't lost.
            snippet = detail if len(detail) <= 200 else detail[:197] + "…"
            message = f"{template} — {snippet}"

        current = LogIssue(
            severity=severity,
            kind=kind,
            message_fr=message,
            raw=line.strip(),
            mod=mod,
            line_no=idx,
        )
        raw_issues.append(current)

    merged: dict[tuple[str, str, str | None], LogIssue] = {}
    order: list[tuple[str, str, str | None]] = []
    for issue in raw_issues:
        _finalize(issue)
        key = (issue.kind, issue.message_fr, issue.mod)
        existing = merged.get(key)
        if existing is None:
            merged[key] = issue
            order.append(key)
        else:
            existing.count += 1
            if issue.severity == SEV_ERROR:
                existing.severity = SEV_ERROR

    issues = [merged[k] for k in order]
    issues.sort(key=lambda i: (0 if i.severity == SEV_ERROR else 1, i.line_no))
    return issues


def log_path_for(mods_dir: Path) -> Path:
    """FS writes ``log.txt`` in the user data folder — the parent of ``mods``."""
    return Path(mods_dir).parent / "log.txt"


def analyze_log(log_path: Path) -> list[LogIssue]:
    """Read and parse a log file. Returns ``[]`` if the file is absent/unreadable."""
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return []
    return parse_log_text(text)


@dataclass
class LogSummary:
    issues: list[LogIssue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(i.count for i in self.issues if i.severity == SEV_ERROR)

    @property
    def warnings(self) -> int:
        return sum(i.count for i in self.issues if i.severity == SEV_WARNING)


def summarize(issues: list[LogIssue]) -> LogSummary:
    return LogSummary(issues=issues)
