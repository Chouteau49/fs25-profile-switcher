from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "verify_build", Path(__file__).parent.parent / "packaging" / "verify_build.py"
)
assert _SPEC is not None and _SPEC.loader is not None
verify_build = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_build)


def make_build(root: Path, code: bytes, program: bytes, exe: bytes) -> Path:
    (root / "fsmods_gui_entry.build" / "blobs").mkdir(parents=True)
    (root / "fsmods_gui_entry.dist").mkdir()
    (root / "fsmods_gui_entry.build" / "blobs" / "__constant.bin").write_bytes(code)
    (root / "fsmods_gui_entry.dist" / "fsmods_gui_entry.dll").write_bytes(program)
    (root / "fsmods-gui.exe").write_bytes(exe)
    return root / "fsmods-gui.exe"


def test_a_build_holding_the_compiled_code_is_accepted(tmp_path: Path) -> None:
    exe = make_build(tmp_path, b"NEW", b"dll[NEW]", b"exe[dll[NEW]]")
    assert verify_build.build_errors(tmp_path, exe) == []
    assert verify_build.main(["verify", str(tmp_path), str(exe)]) == 0


def test_a_program_built_from_the_cached_old_code_is_refused(tmp_path: Path) -> None:
    exe = make_build(tmp_path, b"NEW", b"dll[OLD]", b"exe[dll[OLD]]")
    errors = verify_build.build_errors(tmp_path, exe)
    assert len(errors) == 1 and "fsmods_gui_entry.dll" in errors[0]
    assert verify_build.main(["verify", str(tmp_path), str(exe)]) == 1


def test_an_exe_embedding_the_cached_old_program_is_refused(tmp_path: Path) -> None:
    # What really happened: new version number on the exe, previous program inside.
    exe = make_build(tmp_path, b"NEW", b"dll[NEW]", b"exe[dll[OLD]]")
    errors = verify_build.build_errors(tmp_path, exe)
    assert len(errors) == 1 and "fsmods-gui.exe" in errors[0]


def test_missing_build_files_are_refused(tmp_path: Path) -> None:
    errors = verify_build.build_errors(tmp_path)
    assert errors and all("introuvable" in e for e in errors)


@pytest.mark.parametrize("name", ["fsmods-gui.exe"])
def test_standalone_build_has_an_exe_instead_of_a_dll(tmp_path: Path, name: str) -> None:
    make_build(tmp_path, b"NEW", b"", b"")
    (tmp_path / "fsmods_gui_entry.dist" / "fsmods_gui_entry.dll").unlink()
    (tmp_path / "fsmods_gui_entry.dist" / name).write_bytes(b"prog[NEW]")
    assert verify_build.build_errors(tmp_path) == []
