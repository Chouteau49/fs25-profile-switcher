from __future__ import annotations

from pathlib import Path

from fsmods_gui import main as mainmod


def test_select_qt_plugin_root_prefers_candidate_with_platforms(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    (b / "platforms").mkdir(parents=True)
    (b / "platforms" / "qwindows.dll").write_text("stub")

    selected = mainmod._select_qt_plugin_root([a, b])
    assert selected == b


def test_configure_qt_plugin_paths_sets_env(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "PySide6" / "qt-plugins"
    (root / "platforms").mkdir(parents=True)
    (root / "platforms" / "qwindows.dll").write_text("stub")

    monkeypatch.setenv("QT_PLUGIN_PATH", "")
    monkeypatch.delenv("QT_QPA_PLATFORM_PLUGIN_PATH", raising=False)
    monkeypatch.setattr(mainmod.sys, "path", [str(tmp_path)])
    monkeypatch.setattr(mainmod.sys, "executable", str(tmp_path / "dummy.exe"))

    mainmod._configure_qt_plugin_paths()

    assert mainmod.os.environ["QT_PLUGIN_PATH"] == str(root.resolve())
    assert mainmod.os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] == str(
        (root / "platforms").resolve()
    )
