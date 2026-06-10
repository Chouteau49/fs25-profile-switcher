from __future__ import annotations

from pathlib import Path

from fsmods_gui.profiles.log_analyzer import (
    KIND_CONFLICT,
    KIND_LUA,
    KIND_MISSING,
    KIND_OTHER,
    SEV_ERROR,
    SEV_WARNING,
    analyze_log,
    log_path_for,
    parse_log_text,
    summarize,
)


def test_empty_log_no_issues() -> None:
    assert parse_log_text("") == []
    assert parse_log_text("Starting game\nLoaded map\n") == []


def test_detects_error_and_warning_severity() -> None:
    text = "Error: something broke\nWarning: minor thing\nInfo: ignore me\n"
    issues = parse_log_text(text)
    severities = {i.severity for i in issues}
    assert severities == {SEV_ERROR, SEV_WARNING}


def test_classifies_lua_error() -> None:
    text = "Error: Running LUA method 'update'.\n"
    issues = parse_log_text(text)
    assert len(issues) == 1
    assert issues[0].kind == KIND_LUA
    assert issues[0].severity == SEV_ERROR
    assert "Lua" in issues[0].message_fr


def test_classifies_missing_mod() -> None:
    text = "Error: Could not find mod FS25_RequiredMod\n"
    issues = parse_log_text(text)
    assert issues[0].kind == KIND_MISSING
    assert issues[0].mod == "FS25_RequiredMod"


def test_classifies_conflict() -> None:
    text = "Warning: object 'foo' already defined\n"
    issues = parse_log_text(text)
    assert issues[0].kind == KIND_CONFLICT


def test_unclassified_error_falls_back_to_other() -> None:
    text = "Error: totally unexpected gibberish xyz\n"
    issues = parse_log_text(text)
    assert issues[0].kind == KIND_OTHER
    assert issues[0].severity == SEV_ERROR


def test_mod_extraction_from_path() -> None:
    text = "Warning: failed to load .../mods/FS25_CoolTruck.zip texture\n"
    issues = parse_log_text(text)
    assert issues[0].mod == "FS25_CoolTruck"


def test_duplicate_lines_are_merged_with_count() -> None:
    text = "Error: Running LUA method 'x'.\n" * 3
    issues = parse_log_text(text)
    assert len(issues) == 1
    assert issues[0].count == 3


def test_errors_sorted_before_warnings() -> None:
    text = "Warning: minor\nError: Running LUA method 'x'.\n"
    issues = parse_log_text(text)
    assert issues[0].severity == SEV_ERROR


def test_summarize_counts() -> None:
    text = "Error: a problem\nError: a problem\nWarning: heads up\n"
    summary = summarize(parse_log_text(text))
    assert summary.errors == 2
    assert summary.warnings == 1


def test_analyze_log_missing_file_returns_empty(tmp_path: Path) -> None:
    assert analyze_log(tmp_path / "nope.txt") == []


def test_analyze_log_reads_file(tmp_path: Path) -> None:
    log = tmp_path / "log.txt"
    log.write_text("Error: Running LUA method 'x'.\n", encoding="utf-8")
    issues = analyze_log(log)
    assert len(issues) == 1
    assert issues[0].kind == KIND_LUA


def test_log_path_for_uses_parent_of_mods() -> None:
    mods = Path("C:/Users/x/Documents/My Games/FarmingSimulator2025/mods")
    assert log_path_for(mods) == mods.parent / "log.txt"
