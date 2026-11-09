"""Assistant / Paramètres : détection, même disque, écriture de config.yaml."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

import yaml

from fsmods_gui import config as cfgmod
from fsmods_gui import config_setup as cs


def test_detect_mods_dir_prefers_existing_documents(tmp_path):
    assert cs.detect_mods_dir("fs25", tmp_path) is None
    game = tmp_path / "OneDrive" / "Documents" / "My Games" / "FarmingSimulator2025"
    game.mkdir(parents=True)
    assert cs.detect_mods_dir("fs25", tmp_path) == game / "mods"
    plain = tmp_path / "Documents" / "My Games" / "FarmingSimulator2025" / "mods"
    plain.mkdir(parents=True)
    assert cs.detect_mods_dir("fs25", tmp_path) == plain


def test_detect_install_dir(tmp_path):
    pf = tmp_path / "Program Files (x86)"
    assert cs.detect_install_dir("fs25", [pf]) is None
    inst = pf / "Steam" / "steamapps" / "common" / "Farming Simulator 25"
    inst.mkdir(parents=True)
    assert cs.detect_install_dir("fs25", [tmp_path / "x", pf]) == inst


def test_same_volume_windows_paths():
    a = Path(str(PureWindowsPath("D:/Documents/My Games/FarmingSimulator2025/mods")))
    assert cs.volume_of(Path("D:/FS25-Library")) in ("d:", "")  # "" hors Windows
    if cs.volume_of(a):
        assert cs.same_volume(a, Path("D:/FS25-Library"))
        assert cs.same_volume(a, Path("d:/autre"))
        assert not cs.same_volume(a, Path("E:/Jeux/FS25-Library"))


def test_library_check_messages():
    mods = Path("D:/Documents/My Games/FarmingSimulator2025/mods")
    assert not cs.library_check(mods, None).ok
    if cs.volume_of(mods):  # Windows uniquement
        ok = cs.library_check(mods, Path("D:/FS25-Library"))
        assert ok.ok and "Même disque" in ok.text
        bad = cs.library_check(mods, Path("E:/Jeux/FS25-Library"))
        assert not bad.ok and "copiés" in bad.text


def test_suggested_library_dir():
    mods = Path("D:/Documents/My Games/FarmingSimulator2025/mods")
    assert cs.suggested_library_dir("fs25", mods).name == "FS25-Library"
    assert cs.suggested_library_dir("fs22", mods).name == "FS22-Library"


def test_default_config_path(tmp_path):
    assert cs.default_config_path(tmp_path, tmp_path / "app") == (
        tmp_path / "fsmods-gui" / "config.yaml"
    )
    assert cs.default_config_path(None, tmp_path) == tmp_path / "config.yaml"


def test_updated_config_from_scratch_is_loadable(tmp_path):
    settings = cs.GameSettings(
        "fs25", tmp_path / "game" / "mods", tmp_path / "lib", 2300320,
        backup_dirs=(tmp_path / "drive",),
    )
    text = cs.updated_config_text(None, settings)
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    cfg = cfgmod.load(path)
    game = cfg.profile("fs25")
    assert cfg.default_game == "fs25"
    assert game.library_dir == tmp_path / "lib"
    assert game.steam_app_id == 2300320
    assert game.config_backup_dirs == (tmp_path / "drive",)


def test_updated_config_keeps_unknown_keys_and_other_games(tmp_path):
    old = yaml.safe_dump({
        "default_game": "fs22",
        "games": {
            "fs22": {"mods_dir": "C:/fs22/mods", "library_dir": "C:/lib22"},
            "fs25": {"mods_dir": "C:/old", "testrunner_exe": "C:/tr.exe",
                     "config_backup_dirs": ["G:/x"]},
        },
        "extra": 1,
    })
    settings = cs.GameSettings("fs25", Path("D:/game/mods"), Path("D:/FS25-Library"))
    data = yaml.safe_load(cs.updated_config_text(old, settings))
    assert data["default_game"] == "fs22"  # le jeu par défaut n'est pas changé
    assert data["extra"] == 1
    assert data["games"]["fs22"]["library_dir"] == "C:/lib22"
    fs25 = data["games"]["fs25"]
    assert fs25["testrunner_exe"] == "C:/tr.exe"
    assert fs25["mods_dir"] == "D:/game/mods"
    assert "config_backup_dirs" not in fs25  # liste vidée dans l'interface


def test_initial_import_plan(tmp_path):
    mods, lib = tmp_path / "mods", tmp_path / "lib"
    mods.mkdir()
    lib.mkdir()
    for name in ("B.zip", "a.zip", "notes.txt"):
        (mods / name).write_bytes(b"x")
    (lib / "A.ZIP").write_bytes(b"x")
    assert [p.name for p in cs.initial_import_plan(mods, lib)] == ["B.zip"]
    assert cs.initial_import_plan(tmp_path / "absent", lib) == []


def test_load_remembers_source_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(cs.updated_config_text(
        None, cs.GameSettings("fs25", tmp_path / "m", tmp_path / "l")), encoding="utf-8")
    assert cfgmod.load(path).source_path == path


def test_import_into_library_links_or_copies_and_never_touches_game(tmp_path):
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "a.zip").write_bytes(b"aaa")
    (mods / "b.zip").write_bytes(b"bbb")
    lib = tmp_path / "lib" / "mods"
    seen = []
    res = cs.import_into_library(
        cs.initial_import_plan(mods, lib), lib, lambda i, n, name: seen.append((i, n, name))
    )
    assert sorted(res.added) == ["a.zip", "b.zip"] and res.errors == []
    assert (lib / "a.zip").read_bytes() == b"aaa"
    assert sorted(p.name for p in mods.iterdir()) == ["a.zip", "b.zip"]  # jeu intact
    assert seen[-1][:2] == (2, 2)
    # Deuxième passage : rien à refaire.
    assert cs.initial_import_plan(mods, lib) == []


def test_program_files_dirs_case_insensitive():
    env = {"ProgramFiles(x86)": "C:/PF86", "ProgramFiles": "C:/PF", "OTHER": "x"}
    assert cs.program_files_dirs(env) == [Path("C:/PF86"), Path("C:/PF")]
    assert cs.program_files_dirs({}) == []
