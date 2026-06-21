"""Validate mods (OK / WARN / KO) before they go into the game.

Two complementary engines, both pure-Python (no Qt):

* **Built-in static checks** — always available, no external dependency. They
  open the ``.zip`` and verify the things Giants' ModHub scanner rejects most
  often: archive integrity, a sane filename, a present + well-formed
  ``modDesc.xml`` (optionally schema-validated against the game's ``modDesc.xsd``),
  the declared icon, power-of-two ``.dds`` textures and oversized files.
* **Giants TestRunner** — optional. If the user points us at ``TestRunner.exe``
  (from the Giants Developer Network) we run it on each mod and fold its exit
  code + output into the verdict. Its CLI/report format isn't publicly stable,
  so we stay defensive: capture everything, never crash on it.

The GUI layer (``widgets/testrunner_dialog.py``) renders :class:`ModTestResult`.
"""
from __future__ import annotations

import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# ---- check severities (ordered: OK < WARN < ERROR)
LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"

# ---- overall mod verdicts
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_KO = "ko"

STATUS_LABELS_FR = {
    STATUS_OK: "✅ OK",
    STATUS_WARN: "⚠ À vérifier",
    STATUS_KO: "❌ KO",
}

# A mod ZIP whose name (without .zip) contains anything else won't load in FS.
_VALID_STEM_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)

_DEFAULT_MAX_FILE_MB = 256
_DEFAULT_MAX_ZIP_MB = 1024
_TESTRUNNER_TIMEOUT_S = 180


@dataclass
class Check:
    """One validation result line."""

    level: str  # LEVEL_OK / LEVEL_WARN / LEVEL_ERROR
    label: str
    detail: str = ""


@dataclass
class ModTestResult:
    """All checks for a single mod, plus optional TestRunner output."""

    filename: str
    title: str
    checks: list[Check] = field(default_factory=list)
    testrunner_returncode: int | None = None
    testrunner_output: str | None = None

    @property
    def status(self) -> str:
        levels = {c.level for c in self.checks}
        if LEVEL_ERROR in levels or (
            self.testrunner_returncode is not None
            and self.testrunner_returncode != 0
        ):
            return STATUS_KO
        if LEVEL_WARN in levels:
            return STATUS_WARN
        return STATUS_OK

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if c.level == LEVEL_ERROR)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.level == LEVEL_WARN)

    def summary(self) -> str:
        """One-line French summary of the worst findings."""
        if self.status == STATUS_OK:
            return "Aucun problème détecté."
        bits: list[str] = []
        if self.error_count:
            bits.append(f"{self.error_count} erreur(s)")
        if self.warn_count:
            bits.append(f"{self.warn_count} avertissement(s)")
        if self.testrunner_returncode not in (None, 0):
            bits.append(f"TestRunner code {self.testrunner_returncode}")
        return ", ".join(bits) or "Problème détecté."


# ============================================================ built-in checks


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _dds_dimensions(header: bytes) -> tuple[int, int] | None:
    """Return ``(width, height)`` from a DDS header, or ``None`` if not DDS.

    DDS layout: 4-byte magic ``b"DDS "`` then a 124-byte header whose height is
    at offset 12 and width at offset 16 (little-endian uint32).
    """
    if len(header) < 20 or header[:4] != b"DDS ":
        return None
    height = struct.unpack_from("<I", header, 12)[0]
    width = struct.unpack_from("<I", header, 16)[0]
    return width, height


def _validate_xsd(raw: bytes, xsd_path: Path, checks: list[Check]) -> None:
    """Validate ``modDesc.xml`` bytes against ``modDesc.xsd`` (needs lxml).

    Silently skips when lxml isn't installed — the static checks already cover
    the essentials, this is just a bonus when the game install is configured.
    """
    try:
        from lxml import etree  # local import: optional dependency
    except ImportError:
        return
    try:
        schema = etree.XMLSchema(etree.parse(str(xsd_path)))
    except etree.LxmlError:
        return  # broken/unsupported schema — don't penalise the mod for it
    try:
        doc = etree.fromstring(raw)
    except etree.LxmlError:
        return  # the well-formedness check already reported this
    if schema.validate(doc):
        checks.append(Check(LEVEL_OK, "Schéma modDesc", "Conforme au modDesc.xsd du jeu."))
        return
    errors = [str(e.message) for e in schema.error_log][:5]
    checks.append(
        Check(
            LEVEL_WARN,
            "Schéma modDesc",
            "Non conforme au modDesc.xsd : " + " ; ".join(errors),
        )
    )


def validate_mod(
    zip_path: Path,
    *,
    xsd_path: Path | None = None,
    max_file_mb: int = _DEFAULT_MAX_FILE_MB,
    max_zip_mb: int = _DEFAULT_MAX_ZIP_MB,
) -> ModTestResult:
    """Run the built-in static checks on a single mod ``.zip``."""
    result = ModTestResult(filename=zip_path.name, title=zip_path.stem)
    checks = result.checks

    # ---- filename convention (FS won't load a zip with spaces/odd chars)
    stem = zip_path.stem
    bad_chars = sorted({c for c in stem if c not in _VALID_STEM_CHARS})
    if bad_chars:
        checks.append(
            Check(
                LEVEL_ERROR,
                "Nom de fichier invalide",
                "Le jeu n'accepte que lettres/chiffres/_ ; caractères interdits : "
                + " ".join(repr(c) for c in bad_chars),
            )
        )

    if not zip_path.is_file():
        checks.append(Check(LEVEL_ERROR, "Fichier introuvable", str(zip_path)))
        return result

    # ---- archive size
    try:
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        if size_mb > max_zip_mb:
            checks.append(
                Check(
                    LEVEL_WARN,
                    "Archive volumineuse",
                    f"{size_mb:.0f} Mo (> {max_zip_mb} Mo).",
                )
            )
    except OSError:
        pass

    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                checks.append(
                    Check(LEVEL_ERROR, "Archive corrompue", f"Fichier illisible : {bad}")
                )

            names = zf.namelist()
            lower = {n.lower(): n for n in names}

            # ---- modDesc.xml
            moddesc_name = lower.get("moddesc.xml")
            if moddesc_name is None:
                checks.append(
                    Check(LEVEL_ERROR, "modDesc.xml manquant", "Aucun modDesc.xml à la racine du zip.")
                )
            else:
                raw = zf.read(moddesc_name)
                root = _check_moddesc(raw, lower, checks)
                if root is not None and xsd_path is not None and xsd_path.is_file():
                    _validate_xsd(raw, xsd_path, checks)

            # ---- DDS textures: power-of-two dimensions
            _check_textures(zf, names, checks)

            # ---- oversized inner files
            _check_big_files(zf, max_file_mb, checks)

    except zipfile.BadZipFile as exc:
        checks.append(Check(LEVEL_ERROR, "Archive ZIP invalide", str(exc)))
        return result
    except OSError as exc:
        checks.append(Check(LEVEL_ERROR, "Lecture impossible", str(exc)))
        return result

    if not checks:
        checks.append(Check(LEVEL_OK, "Validation", "Tous les contrôles de base sont passés."))
    return result


def _check_moddesc(
    raw: bytes, lower: dict[str, str], checks: list[Check]
) -> ET.Element | None:
    """Parse modDesc.xml and append checks; return the root or None on failure."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        checks.append(Check(LEVEL_ERROR, "modDesc.xml invalide", f"XML mal formé : {exc}"))
        return None

    if not root.get("descVersion"):
        checks.append(
            Check(LEVEL_WARN, "descVersion manquant", "L'attribut descVersion du modDesc est absent.")
        )

    version = (root.findtext("version") or "").strip()
    if not version:
        checks.append(Check(LEVEL_WARN, "Version manquante", "Aucune balise <version> dans le modDesc."))

    title = (
        (root.findtext("title/fr") or "").strip()
        or (root.findtext("title/en") or "").strip()
    )
    if not title:
        checks.append(Check(LEVEL_WARN, "Titre manquant", "Aucun <title> exploitable dans le modDesc."))

    icon = (root.findtext("iconFilename") or "").strip()
    if not icon:
        checks.append(Check(LEVEL_WARN, "Icône manquante", "Aucun <iconFilename> déclaré."))
    else:
        if not _icon_present(icon, lower):
            checks.append(
                Check(
                    LEVEL_WARN,
                    "Icône introuvable",
                    f"Le fichier d'icône « {icon} » déclaré n'est pas dans le zip.",
                )
            )
    return root


def _icon_present(icon: str, lower: dict[str, str]) -> bool:
    """True if the declared icon (or its .dds/.png twin) exists in the zip."""
    rel = icon.replace("\\", "/").strip().lstrip("/").lower()
    if rel in lower:
        return True
    base = rel.rsplit(".", 1)[0]
    return any(f"{base}{ext}" in lower for ext in (".dds", ".png", ".jpg", ".jpeg"))


def _check_textures(zf: zipfile.ZipFile, names: list[str], checks: list[Check]) -> None:
    offenders: list[str] = []
    for name in names:
        low = name.lower()
        if not low.endswith(".dds"):
            continue
        # ``*Array.dds`` are data/lookup textures (fruitArray, plantArray…), not
        # displayed bitmaps: their dimensions are deliberately arbitrary and the
        # power-of-two rule doesn't apply. The game loads them fine.
        if low.endswith("array.dds"):
            continue
        try:
            with zf.open(name) as fh:
                dims = _dds_dimensions(fh.read(20))
        except (OSError, zipfile.BadZipFile):
            continue
        if dims is None:
            continue
        w, h = dims
        if not (_is_power_of_two(w) and _is_power_of_two(h)):
            offenders.append(f"{Path(name).name} ({w}×{h})")
    if offenders:
        preview = ", ".join(offenders[:8])
        extra = f" … (+{len(offenders) - 8})" if len(offenders) > 8 else ""
        checks.append(
            Check(
                LEVEL_WARN,
                "Textures non puissance de 2",
                f"{len(offenders)} texture(s) DDS aux dimensions non power-of-2 : "
                f"{preview}{extra}",
            )
        )


def _check_big_files(zf: zipfile.ZipFile, max_file_mb: int, checks: list[Check]) -> None:
    limit = max_file_mb * 1024 * 1024
    big: list[str] = []
    for info in zf.infolist():
        if info.file_size > limit:
            big.append(f"{Path(info.filename).name} ({info.file_size / (1024 * 1024):.0f} Mo)")
    if big:
        preview = ", ".join(big[:5])
        extra = f" … (+{len(big) - 5})" if len(big) > 5 else ""
        checks.append(
            Check(
                LEVEL_WARN,
                "Fichiers volumineux",
                f"{len(big)} fichier(s) > {max_file_mb} Mo : {preview}{extra}",
            )
        )


# ========================================================== Giants TestRunner


def run_testrunner(
    exe_path: Path, mod_path: Path, *, timeout_s: int = _TESTRUNNER_TIMEOUT_S
) -> tuple[int | None, str]:
    """Run Giants ``TestRunner.exe`` on a mod; return ``(returncode, output)``.

    Defensive on purpose: the exact CLI/output format isn't publicly stable, so
    we just pass the mod path, capture stdout+stderr, and let the caller fold the
    exit code into the verdict. Returns ``(None, message)`` if it can't be run.
    """
    if not exe_path.is_file():
        return None, f"TestRunner introuvable : {exe_path}"
    try:
        completed = subprocess.run(
            [str(exe_path), str(mod_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(exe_path.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if sys.platform == "win32"
            else 0,
        )
    except subprocess.TimeoutExpired:
        return None, f"TestRunner : délai dépassé (> {timeout_s} s)."
    except OSError as exc:
        return None, f"TestRunner : exécution impossible ({exc})."
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def validate_mods(
    zip_paths: list[Path],
    *,
    xsd_path: Path | None = None,
    testrunner_exe: Path | None = None,
    progress=None,
) -> list[ModTestResult]:
    """Validate several mods. ``progress(done, total, filename)`` is optional."""
    total = len(zip_paths)
    results: list[ModTestResult] = []
    for i, zip_path in enumerate(zip_paths):
        if progress is not None:
            progress(i, total, zip_path.name)
        result = validate_mod(zip_path, xsd_path=xsd_path)
        if testrunner_exe is not None:
            code, output = run_testrunner(testrunner_exe, zip_path)
            result.testrunner_returncode = code
            result.testrunner_output = output
        results.append(result)
    if progress is not None:
        progress(total, total, "")
    return results
