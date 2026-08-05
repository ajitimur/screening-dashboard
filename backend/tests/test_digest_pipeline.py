"""Stage 10: writing the dated digest file, store-driven end to end (spec §6).

``write_digest`` reads yesterday's detections and today's bars off the store,
reports every name whose today close cleared its yesterday trigger, persists the
reported breaks (for the repeat marker) and writes one dated Markdown file per
market per session — an explicit no-breaks file on a quiet night.
"""

from datetime import date

import pytest

from screener.detection import DETECTOR_VERSION, Detection
from screener.bars import Bar
from screener.pipeline import write_digest
from screener.store import Store

YESTERDAY = date(2026, 8, 4)
TODAY = date(2026, 8, 5)


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def _det(symbol, *, session=YESTERDAY, trigger=100.0):
    return Detection(
        symbol=symbol, session=session, detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=3.0, stopw_adr=0.5, base_len=10, move_gain=103.0,
        adr=0.06, close=98.0, cluster_k=5, cluster_high=trigger, cluster_low=97.0,
        cluster_range_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=trigger - 0.1, base_low=97.0,
        churn_l=0.45, sma20_rising=True, dryup=0.90,
    )


def _bar(session, close):
    return Bar(session, close, close + 1, close - 1, close, close, 1_000_000)


def test_write_digest_reports_the_break_and_writes_the_file(store, tmp_path):
    store.append_detections("US", YESTERDAY, [_det("UP"), _det("FLAT")])
    store.append_bars("US", "UP", [_bar(TODAY, 101.0)])       # cleared its trigger
    store.append_bars("US", "FLAT", [_bar(TODAY, 99.0)])      # did not
    store.upsert_label("US", "UP", "Technology", "Semiconductors", TODAY)

    path = write_digest(store, "US", TODAY, digests_dir=tmp_path)

    assert path == tmp_path / "US" / "2026-08-05.md"
    text = path.read_text()
    assert "UP" in text and "Semiconductors" in text
    assert "FLAT" not in text  # never cleared its trigger
    # The break is persisted so a later night can mark it a repeat.
    assert store.digest_reports_before("US", date(2026, 8, 6)) == {"UP": TODAY}


def test_write_digest_marks_a_repeat_from_a_prior_report(store, tmp_path):
    store.append_digest_breaks("US", date(2026, 7, 28), ["RPT"])
    store.append_detections("US", YESTERDAY, [_det("RPT")])
    store.append_bars("US", "RPT", [_bar(TODAY, 101.0)])

    path = write_digest(store, "US", TODAY, digests_dir=tmp_path)
    text = path.read_text()
    assert "↺" in text and "2026-07-28" in text


def test_an_empty_night_still_writes_a_no_breaks_file(store, tmp_path):
    # No detections yesterday → nothing can break → the file still exists, with the
    # explicit no-breaks line, so a *missing* file means the run failed.
    path = write_digest(store, "IDX", TODAY, digests_dir=tmp_path)
    assert path.exists()
    assert "no breaks" in path.read_text().lower()
    assert store.digest_reports_before("IDX", date(2026, 8, 6)) == {}


def test_write_digest_is_dated_with_the_session_not_the_wall_clock(store, tmp_path):
    # The file is named for the market's session date, whatever day it is written.
    path = write_digest(store, "US", date(2026, 8, 3), digests_dir=tmp_path)
    assert path.name == "2026-08-03.md"
    assert "2026-08-03" in path.read_text()
