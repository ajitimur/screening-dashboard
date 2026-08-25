"""Unit check for the one new measurement, `base_age`.

§3c's `measure_base.py` computes it with list indices over a bar list; this
prototype computes it over a `DatetimeIndex` frame. Two different paths to the
same definition is exactly where a transcription slips, so the definition is
pinned here on hand-built frames before it is let near the trade record.

Run: backend/.venv/bin/python -m pytest .scratch/screening-dashboard/\
prototypes/prior-move-at-entry/test_base_age.py -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from prior_move_at_entry import BASE_LOOKBACK, age_bucket, base_age


def frame(highs: list[float]) -> pd.DataFrame:
    """A frame of `len(highs)` consecutive business days ending 2021-06-30."""
    idx = pd.bdate_range(end="2021-06-30", periods=len(highs))
    return pd.DataFrame({"High": highs, "Low": [h * 0.9 for h in highs],
                         "Adj": highs}, index=idx)


def test_counts_sessions_back_to_the_highest_high():
    # Peak four sessions before the last bar, nothing higher since.
    f = frame([10, 11, 20, 12, 13, 14, 15])
    assert base_age(f, f.index[-1]) == (4, False)


def test_the_evaluation_session_itself_can_be_the_pivot():
    f = frame([10, 11, 12, 13, 99])
    assert base_age(f, f.index[-1]) == (0, False)


def test_ties_resolve_to_the_earliest_high_the_older_base():
    # `max(range(...), key=...)` in §3c returns the first maximum. A base that
    # was tagged twice at the same price started at the first tag.
    f = frame([10, 20, 15, 20, 16])
    assert base_age(f, f.index[-1]) == (3, False)


def test_window_is_the_trailing_120_sessions_and_an_edge_pivot_is_censored():
    # The all-time high sits outside the window; the highest high inside it is
    # on the window's own left edge, so the age is a floor, not a measurement.
    highs = [500.0] * 10 + [40.0] + [2.0] * BASE_LOOKBACK
    f = frame(highs)
    assert base_age(f, f.index[-1]) == (BASE_LOOKBACK, True)


def test_short_history_censors_against_the_available_bars_not_120():
    f = frame([30, 10, 11, 12])
    assert base_age(f, f.index[-1]) == (3, True)


def test_measures_through_as_of_and_ignores_later_bars():
    # A higher high *after* the evaluation session must not move the pivot —
    # the entry day's own high is not on screen at the click.
    f = frame([10, 30, 11, 12, 999])
    assert base_age(f, f.index[-2]) == (2, False)


def test_absent_when_the_frame_has_nothing_at_or_before_as_of():
    f = frame([10, 11, 12])
    assert base_age(f, pd.Timestamp("2019-01-02")) == (None, False)


@pytest.mark.parametrize("age,label", [
    (0, "<=5"), (5, "<=5"), (6, "6-30"), (30, "6-30"),
    (31, "31-60"), (60, "31-60"), (61, ">60"), (120, ">60"),
])
def test_bucket_edges_match_the_issue(age, label):
    assert age_bucket(age) == label


def test_bucket_of_a_missing_age_is_missing():
    assert age_bucket(np.nan) is None
