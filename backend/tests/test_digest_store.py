"""Seam: the append-only ``digest_breaks`` table + the reads the digest needs.

The digest reports yesterday's setup broken by today's close, so it reads
``detections_before`` (yesterday's triggers). Repeats are marked with the date a
name was last reported, so each reported break is persisted — append-only, dated,
never rewritten like every derived stream — and ``digest_reports_before`` gives the
most recent prior report per symbol.
"""

from datetime import date

import pytest

from screener.detection import DETECTOR_VERSION, Detection
from screener.store import SessionExistsError, Store


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def _det(symbol, *, trigger=100.0):
    return Detection(
        symbol=symbol, session=date(2026, 8, 4), detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=3.0, stopw_adr=0.5, base_len=10, move_gain=103.0,
        adr=0.06, close=98.0, cluster_k=5, cluster_high=trigger, cluster_low=97.0,
        cluster_range_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=trigger - 0.1, base_low=97.0,
        churn_l=0.45, sma20_rising=True, dryup=0.90,
    )


def test_detections_before_returns_the_prior_sessions_rows(store: Store):
    store.append_detections("US", date(2026, 8, 3), [_det("OLD")])
    store.append_detections("US", date(2026, 8, 4), [_det("AAA"), _det("BBB")])
    prior = store.detections_before("US", date(2026, 8, 5))
    assert {d.symbol for d in prior} == {"AAA", "BBB"}  # the 8-04 session, not 8-03


def test_detections_before_is_empty_with_no_prior_session(store: Store):
    store.append_detections("US", date(2026, 8, 5), [_det("AAA")])
    assert store.detections_before("US", date(2026, 8, 5)) == []


def test_append_and_read_reported_breaks(store: Store):
    store.append_digest_breaks("US", date(2026, 7, 28), ["RPT", "SOLO"])
    store.append_digest_breaks("US", date(2026, 8, 5), ["RPT"])
    before = store.digest_reports_before("US", date(2026, 8, 5))
    # RPT was reported on 7-28 (strictly before 8-05); today's own 8-05 row is not
    # a *prior* report, so it is excluded.
    assert before == {"RPT": date(2026, 7, 28), "SOLO": date(2026, 7, 28)}


def test_reports_before_takes_the_most_recent_prior_session_per_symbol(store: Store):
    store.append_digest_breaks("US", date(2026, 7, 20), ["RPT"])
    store.append_digest_breaks("US", date(2026, 7, 28), ["RPT"])
    before = store.digest_reports_before("US", date(2026, 8, 5))
    assert before == {"RPT": date(2026, 7, 28)}  # the latest of the two


def test_reported_breaks_are_append_only(store: Store):
    store.append_digest_breaks("US", date(2026, 8, 5), ["AAA"])
    with pytest.raises(SessionExistsError):
        store.append_digest_breaks("US", date(2026, 8, 5), ["BBB"])


def test_an_empty_night_records_no_reported_breaks(store: Store):
    store.append_digest_breaks("US", date(2026, 8, 5), [])
    assert store.digest_reports_before("US", date(2026, 8, 6)) == {}
