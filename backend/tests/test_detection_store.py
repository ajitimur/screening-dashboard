"""Seam 7b: the append-only ``detections`` table (spec §4.5 / §7.2).

Detections are dated rows keyed ``(market, session, symbol)`` carrying the
trigger, the stop, the signal vector and a ``detector_version`` column. Like
every derived stream they are written once and never rewritten.
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


def _det(symbol, *, trigger=100.5, cluster_low=99.5, line_ok=True):
    return Detection(
        symbol=symbol, session=date(2026, 8, 5), detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=trigger - cluster_low,
        stopw_adr=(trigger - cluster_low) / trigger / 0.01,
        base_len=30, move_gain=103.0, adr=0.01, close=100.0,
        cluster_k=7, cluster_high=trigger, cluster_low=cluster_low,
        cluster_range_adr=0.99, line_ok=line_ok, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=100.4, base_low=99.5,
    )


def test_append_and_read_back_detection_rows(store: Store):
    rows = [_det("AAA"), _det("BBB", trigger=50.0, cluster_low=49.0, line_ok=False)]
    store.append_detections("US", date(2026, 8, 5), rows)

    read = store.detections("US", date(2026, 8, 5))
    assert {r.symbol for r in read} == {"AAA", "BBB"}
    assert all(isinstance(r, Detection) for r in read)
    # The signal vector and the version column survive the round trip.
    bbb = next(r for r in read if r.symbol == "BBB")
    assert bbb.trigger == 50.0 and bbb.cluster_low == 49.0
    assert bbb.line_ok is False
    assert bbb.detector_version == DETECTOR_VERSION


def test_rewriting_a_session_of_detections_is_refused(store: Store):
    store.append_detections("US", date(2026, 8, 5), [_det("AAA")])
    with pytest.raises(SessionExistsError):
        store.append_detections("US", date(2026, 8, 5), [_det("AAA", trigger=1.0)])
    # The original row survives untouched.
    assert store.detections("US", date(2026, 8, 5))[0].trigger == 100.5


def test_detections_are_kept_per_market_and_session(store: Store):
    store.append_detections("US", date(2026, 8, 5), [_det("AAA")])
    store.append_detections("IDX", date(2026, 8, 5), [_det("ZZZ")])
    assert [r.symbol for r in store.detections("US", date(2026, 8, 5))] == ["AAA"]
    assert [r.symbol for r in store.detections("IDX", date(2026, 8, 5))] == ["ZZZ"]
    assert store.detections("US", date(2026, 8, 4)) == []


def test_a_session_with_no_detections_writes_no_rows(store: Store):
    # A quiet night: the universe was published but nothing sits in a base.
    store.append_detections("US", date(2026, 8, 5), [])
    assert store.detections("US", date(2026, 8, 5)) == []
