from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from fsmods_gui.profiles.testrunner import (
    STATUS_KO,
    STATUS_OK,
    STATUS_WARN,
    validate_mod,
    validate_mods,
)


def _dds(width: int, height: int) -> bytes:
    """A minimal DDS blob with the given dimensions (height@12, width@16)."""
    return b"DDS " + b"\x00" * 8 + struct.pack("<I", height) + struct.pack("<I", width) + b"\x00" * 100


_GOOD_MODDESC = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<modDesc descVersion="80">'
    b"<version>1.0.0.0</version>"
    b"<title><en>Good</en></title>"
    b"<iconFilename>icon.dds</iconFilename>"
    b"</modDesc>"
)


def _write_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_valid_mod_is_ok(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "FS25_GoodMod.zip",
        {"modDesc.xml": _GOOD_MODDESC, "icon.dds": _dds(256, 256)},
    )
    result = validate_mod(zip_path)
    assert result.status == STATUS_OK
    assert result.error_count == 0


def test_bad_filename_is_error(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "FS25 Bad Name!.zip",
        {"modDesc.xml": _GOOD_MODDESC, "icon.dds": _dds(256, 256)},
    )
    result = validate_mod(zip_path)
    assert result.status == STATUS_KO
    assert any("Nom de fichier" in c.label for c in result.checks)


def test_missing_moddesc_is_error(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "FS25_NoDesc.zip", {"data/foo.txt": b"x"})
    result = validate_mod(zip_path)
    assert result.status == STATUS_KO
    assert any("modDesc.xml manquant" in c.label for c in result.checks)


def test_malformed_moddesc_is_error(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "FS25_BadXml.zip", {"modDesc.xml": b"<modDesc><oops"})
    result = validate_mod(zip_path)
    assert result.status == STATUS_KO
    assert any("invalide" in c.label for c in result.checks)


def test_non_power_of_two_texture_is_warning(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "FS25_OddTex.zip",
        {"modDesc.xml": _GOOD_MODDESC, "icon.dds": _dds(256, 256), "t.dds": _dds(300, 256)},
    )
    result = validate_mod(zip_path)
    assert result.status == STATUS_WARN
    assert any("puissance de 2" in c.label for c in result.checks)


def test_array_textures_are_not_flagged(tmp_path: Path) -> None:
    # *Array.dds are data/lookup textures — non-pow2 is expected and harmless.
    zip_path = _write_zip(
        tmp_path / "FS25_Arrays.zip",
        {
            "modDesc.xml": _GOOD_MODDESC,
            "icon.dds": _dds(256, 256),
            "fruitArray.dds": _dds(28, 12),
            "plantArray.dds": _dds(8, 12),
        },
    )
    result = validate_mod(zip_path)
    assert result.status == STATUS_OK
    assert not any("puissance de 2" in c.label for c in result.checks)


def test_missing_icon_is_warning(tmp_path: Path) -> None:
    moddesc = _GOOD_MODDESC.replace(b"icon.dds", b"missing.dds")
    zip_path = _write_zip(tmp_path / "FS25_NoIcon.zip", {"modDesc.xml": moddesc})
    result = validate_mod(zip_path)
    assert result.status == STATUS_WARN
    assert any("Icône introuvable" in c.label for c in result.checks)


def test_corrupt_zip_is_error(tmp_path: Path) -> None:
    zip_path = tmp_path / "FS25_Corrupt.zip"
    zip_path.write_bytes(b"this is not a zip file")
    result = validate_mod(zip_path)
    assert result.status == STATUS_KO


def test_validate_mods_reports_progress(tmp_path: Path) -> None:
    paths = [
        _write_zip(tmp_path / "FS25_A.zip", {"modDesc.xml": _GOOD_MODDESC, "icon.dds": _dds(64, 64)}),
        _write_zip(tmp_path / "FS25_B.zip", {"data/x.txt": b"x"}),
    ]
    seen: list[tuple[int, int]] = []
    results = validate_mods(paths, progress=lambda d, t, n: seen.append((d, t)))
    assert len(results) == 2
    assert (2, 2) in seen  # final tick
    assert results[0].status == STATUS_OK
    assert results[1].status == STATUS_KO
