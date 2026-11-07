"""Check that a Nuitka build really contains the code that was just compiled.

Nuitka embeds the compiled Python in the program through ``#embed``, and the onefile
exe embeds that program the same way. Zig's compiler cache tracks these embedded files
by path: when an older build folder still holds a file at the recorded path, the cache
serves the previous object file. The build then reports success, with the new version
number on the exe and the old code inside it.

Usage: ``python packaging/verify_build.py <nuitka output dir> [<onefile exe>]``
"""
from __future__ import annotations

import sys
from pathlib import Path

ENTRY = "fsmods_gui_entry"


def build_errors(output_dir: Path, exe: Path | None = None) -> list[str]:
    """Why the build output is not what was compiled; empty when it is."""
    blob = output_dir / f"{ENTRY}.build" / "blobs" / "__constant.bin"
    program = output_dir / f"{ENTRY}.dist" / f"{ENTRY}.dll"
    if not program.is_file():  # standalone builds produce an exe instead of a dll
        program = output_dir / f"{ENTRY}.dist" / "fsmods-gui.exe"
    missing = [str(p) for p in (blob, program) if not p.is_file()]
    if missing:
        return [f"Fichier de build introuvable : {p}" for p in missing]

    errors = []
    program_data = program.read_bytes()
    if blob.read_bytes() not in program_data:
        errors.append(f"{program.name} ne contient pas le code compilé (cache du compilateur ?).")
    if exe is not None and program_data not in exe.read_bytes():
        errors.append(f"{exe.name} ne contient pas {program.name} (cache du compilateur ?).")
    return errors


def main(argv: list[str]) -> int:
    exe = Path(argv[2]) if len(argv) > 2 else None
    errors = build_errors(Path(argv[1]), exe)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
