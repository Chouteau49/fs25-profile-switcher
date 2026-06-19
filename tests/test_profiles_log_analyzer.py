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


def test_timestamped_lua_spam_merges_into_one_row() -> None:
    # FS prefixes each line with a unique timestamp; the per-frame Lua crash must
    # still collapse into a single counted row rather than thousands.
    lines = [
        f"2026-06-19 11:55:{37 + i // 1000}.{i % 1000:03d} "
        "Error: Running LUA method 'update'.\n"
        for i in range(50)
    ]
    issues = parse_log_text("".join(lines))
    assert len(issues) == 1
    assert issues[0].count == 50
    assert issues[0].kind == KIND_LUA
    # the timestamp must not leak into the human message
    assert "2026-06-19" not in issues[0].message_fr


def test_bare_time_prefix_is_stripped() -> None:
    text = "11:53:10.632 Error: Startup with port while already running\n"
    issues = parse_log_text(text)
    assert len(issues) == 1
    assert "11:53:10" not in issues[0].message_fr


def test_lua_callstack_attributes_culprit_mod() -> None:
    # Real-world shape: a generic "Running LUA method 'update'" error followed by
    # a non-timestamped traceback line naming the failing script, repeated every
    # frame. Must collapse into ONE row attributed to FS25_Courseplay.
    block = (
        "2026-06-19 11:55:37.286 Error: Running LUA method 'update'.\n"
        "C:/Users/x/mods/FS25_Courseplay/scripts/specializations/CpCourseManager.lua:370: "
        "attempt to index nil with 'delete'\n"
    )
    issues = parse_log_text(block * 200)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.count == 200
    assert issue.kind == KIND_LUA
    assert issue.mod == "FS25_Courseplay"
    assert "CpCourseManager.lua:370" in issue.message_fr
    # the absolute path prefix is trimmed away
    assert "C:/Users" not in issue.message_fr
    assert issue.callstack  # traceback captured


def test_basegame_callstack_captured_without_mod() -> None:
    block = (
        "11:55:00 Error: Running LUA method 'update'.\n"
        "  dataS/scripts/vehicles/Motorized.lua:120: something nil\n"
    )
    issues = parse_log_text(block)
    assert len(issues) == 1
    assert issues[0].mod is None
    assert any("Motorized.lua" in c for c in issues[0].callstack)


def test_continuation_without_preceding_error_is_ignored() -> None:
    # Boot lines have no timestamp and no preceding kept error -> not attached.
    text = (
        "Available mod: (Hash: abc) (Version: 1.0) FS25_Foo\n"
        "  CPU: some cpu\n"
    )
    assert parse_log_text(text) == []


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
