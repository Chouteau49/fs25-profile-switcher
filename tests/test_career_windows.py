"""Défis à fenêtre de temps de jeu, suivis dans la carrière (store)."""
from __future__ import annotations

from pathlib import Path

import pytest

from fsmods_gui.career.stats import Stat, StatsSnapshot
from fsmods_gui.career.store import Career, CareerError
from fsmods_gui.career.time_window import (
    ST_OPEN,
    ST_UNAVAILABLE,
    ST_WON,
    WINDOW_PRESETS,
    WindowChallenge,
    window_line,
)

CHALLENGE = WindowChallenge("2 M€ en 24 h", "finance.missionIncome", 2_000_000.0)


def _set(career: Career, hours: float, income: float) -> None:
    snap = StatsSnapshot(taken_at="t", farm_id="1", savegame="savegame1")
    snap.stats["playTime"] = Stat(key="playTime", value=hours)
    snap.stats["finance.missionIncome"] = Stat(key="finance.missionIncome", value=income)
    career.snapshot = snap


def test_a_window_needs_a_synchronised_save(tmp_path: Path):
    with pytest.raises(CareerError):
        Career(directory=tmp_path).start_window(CHALLENGE)


def test_won_window_stays_won_and_is_reported_once(tmp_path: Path):
    career = Career(directory=tmp_path)
    _set(career, 100.0, 0.0)
    window = career.start_window(CHALLENGE)
    _set(career, 110.0, 500_000.0)
    assert career.refresh_windows() == [] and window.state == ST_OPEN
    _set(career, 118.0, 2_100_000.0)
    assert [w.id for w in career.refresh_windows()] == [window.id]
    assert window.state == ST_WON
    _set(career, 130.0, 3_000_000.0)
    assert career.refresh_windows() == [] and window.state == ST_WON


def test_regression_suspends_the_window_without_closing_it(tmp_path: Path):
    career = Career(directory=tmp_path)
    _set(career, 100.0, 0.0)
    window = career.start_window(CHALLENGE)
    _set(career, 90.0, 0.0)  # playtime going backwards: restored save
    career.refresh_windows()
    assert window.state == ST_UNAVAILABLE and not window.final


def test_preset_can_be_started_and_shown(tmp_path: Path):
    career = Career(directory=tmp_path)
    _set(career, 100.0, 0.0)
    window = career.start_window(WINDOW_PRESETS[0])
    line = window_line(window)
    assert "En cours" in line and WINDOW_PRESETS[0].name in line


def test_windows_survive_save_and_load(tmp_path: Path):
    career = Career(directory=tmp_path)
    _set(career, 100.0, 0.0)
    career.start_window(CHALLENGE)
    _set(career, 118.0, 2_100_000.0)
    career.refresh_windows()
    career.save()
    loaded = Career.load(tmp_path)
    assert len(loaded.windows) == 1
    assert loaded.windows[0].state == ST_WON
    assert loaded.windows[0].start.values["playTime"] == 100.0
    assert loaded.windows[0].challenge == CHALLENGE
