"""Défi « gagner X en 24 h de jeu » (fenêtre sur playTime)."""
from __future__ import annotations

from fsmods_gui.career.periods import Checkpoint
from fsmods_gui.career.time_window import (
    ST_IMPRECISE,
    ST_LOST,
    ST_OPEN,
    ST_UNAVAILABLE,
    ST_WON,
    WindowChallenge,
    evaluate_window,
)

CHALLENGE = WindowChallenge("2 M€ en 24 h", "finance.missionIncome", 2_000_000.0)


def _cp(hours: float, income: float | None) -> Checkpoint:
    values = {"playTime": hours}
    if income is not None:
        values["finance.missionIncome"] = income
    return Checkpoint(taken_at="t", values=values)


def test_open_window_reports_progress_and_elapsed_time():
    res = evaluate_window(CHALLENGE, _cp(100.0, 0.0), _cp(106.0, 500_000.0))
    assert res.state == ST_OPEN
    assert res.elapsed_hours == 6.0 and res.gain == 500_000.0
    assert res.progress == 0.25


def test_target_reached_inside_the_window_is_won():
    res = evaluate_window(CHALLENGE, _cp(100.0, 0.0), _cp(118.0, 2_100_000.0))
    assert res.state == ST_WON and res.progress == 1.0


def test_reached_within_the_tolerance_margin_is_still_won():
    res = evaluate_window(CHALLENGE, _cp(100.0, 0.0), _cp(124.5, 2_000_000.0))
    assert res.state == ST_WON


def test_overrun_with_target_reached_is_imprecise_not_won():
    res = evaluate_window(CHALLENGE, _cp(100.0, 0.0), _cp(160.0, 2_500_000.0))
    assert res.state == ST_IMPRECISE


def test_overrun_without_target_is_lost():
    res = evaluate_window(CHALLENGE, _cp(100.0, 0.0), _cp(160.0, 1_000_000.0))
    assert res.state == ST_LOST


def test_unknown_income_is_unavailable_never_zero():
    res = evaluate_window(CHALLENGE, _cp(100.0, None), _cp(110.0, 500_000.0))
    assert res.state == ST_UNAVAILABLE and res.gain is None


def test_playtime_going_backwards_is_unavailable():
    res = evaluate_window(CHALLENGE, _cp(100.0, 0.0), _cp(90.0, 500_000.0))
    assert res.state == ST_UNAVAILABLE


def test_non_cumulative_stat_is_refused():
    bad = WindowChallenge("Solde", "money", 1000.0)
    res = evaluate_window(bad, _cp(0.0, 0.0), _cp(1.0, 2000.0))
    assert res.state == ST_UNAVAILABLE
