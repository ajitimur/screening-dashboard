"""Seam 7a: the detector — base, cluster, envelope, trigger and stop (spec §4.5).

Detection emits **a base, not a state**: every name currently sitting in a valid
base, with its trigger and stop. The load-bearing identities this seam pins:

- **The trigger is the cluster high**, never the fitted line. The envelope is
  anchored at the cluster's max high and searched over non-positive slopes only,
  so ``line_end`` can never exceed the trigger.
- **``line_ok`` is not a gate.** A name whose fit is poor is still emitted.
- **Piercing bars do not invalidate a base** — the boundaries are fits, not
  monotonic tests, so a bar poking above the envelope is an overshoot, not a
  rejection.

Everything here is pure over an oldest-first ``list[Bar]`` — no store, no network.
"""

from datetime import date, timedelta

from screener.bars import Bar
from screener.detection import (
    DETECTOR_VERSION,
    TOP_DECILE,
    Rank,
    detect,
    detection_gate,
)

CAL = [date(2026, 1, 1) + timedelta(days=i) for i in range(200)]


def _bars(hlc):
    """Bars from a list of ``(high, low, close)`` triples, one per CAL day.
    ``adj_close`` mirrors ``close`` (the detector reads unadjusted OHLC only)."""
    return [
        Bar(CAL[i], close, high, low, close, close, 1000)
        for i, (high, low, close) in enumerate(hlc)
    ]


def _base_series():
    """A textbook setup: 60 flat bars, a run-up 50→99, then a 30-bar tight
    consolidation at 100 ending today. The last 7 bars are a clean cluster."""
    hlc = [(50.5, 49.5, 50.0)] * 60
    for i in range(1, 16):  # run-up 50 -> 99
        p = 50.0 + (99.0 - 50.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(100.5, 99.5, 100.0)] * 30  # the flat top / cluster
    return hlc


# -- the trigger is the cluster high, never the fitted line -------------------


def test_a_clean_base_is_detected():
    d = detect("AAA", _bars(_base_series()), CAL[104])
    assert d is not None
    assert d.symbol == "AAA"
    assert d.session == CAL[104]
    assert d.detector_version == DETECTOR_VERSION
    assert d.cluster_k == 7               # the largest tight trailing window
    assert d.base_len == 30               # peak of the flat top -> today


def test_trigger_is_the_cluster_high_by_identity():
    d = detect("AAA", _bars(_base_series()), CAL[104])
    assert d.trigger == d.cluster_high == 100.5


def test_the_fitted_line_never_sets_the_trigger():
    # The envelope is anchored at the cluster high and slopes down going forward,
    # so its value at today is at or below the trigger — every detection.
    d = detect("AAA", _bars(_base_series()), CAL[104])
    assert d.slope <= 0.0
    assert d.line_end <= d.trigger        # the line never reaches the trigger


def test_stop_is_the_cluster_range():
    d = detect("AAA", _bars(_base_series()), CAL[104])
    assert abs(d.stop - (d.trigger - d.cluster_low)) < 1e-12
    assert abs(d.stop - 1.0) < 1e-9       # 100.5 - 99.5


# -- line_ok is a verdict, not a gate; piercing bars do not invalidate --------


def test_a_piercing_bar_is_an_overshoot_not_a_rejection():
    # Insert a bar whose high spikes far above the envelope near the base start.
    # The base still ends today and is still emitted — the fit just fails line_ok.
    hlc = _base_series()
    hlc[80] = (120.0, 99.5, 100.0)        # a tall wick that pierces the envelope
    d = detect("AAA", _bars(hlc), CAL[104])
    assert d is not None                  # NOT rejected by the pierce
    assert d.line_ok is False             # the overshoot fails the fit's quality
    assert d.overshoot_adr > 1.0          # measured in ADR, well past the ceiling
    assert d.base_len == 25               # the spike is the peak -> base starts there


def test_line_ok_is_true_for_a_clean_flat_base():
    d = detect("AAA", _bars(_base_series()), CAL[104])
    assert d.line_ok is True


# -- the per-name gates: history, catch-up, cluster ---------------------------


def test_too_little_history_is_not_a_detection():
    hlc = [(100.5, 99.5, 100.0)] * 50     # only 50 bars, need >= 80
    assert detect("AAA", _bars(hlc), CAL[49]) is None


def test_a_name_not_caught_up_to_the_ma_is_not_a_detection():
    # 100 flat bars, then a sharp final leg — price is far above the 10/20 MA, so
    # it has not "caught up" and is not sitting in a base.
    hlc = [(100.5, 99.5, 100.0)] * 100
    hlc += [(h, h - 1, h) for h in (110.0, 120.0, 130.0)]
    assert detect("AAA", _bars(hlc), CAL[102]) is None


def test_a_name_with_no_tight_cluster_is_not_a_detection():
    # A wide, ragged top: no trailing 3-7 bar window is tight enough.
    hlc = [(50.5, 49.5, 50.0)] * 90
    for h in (60, 55, 62, 54, 63, 56, 61):  # last bars swing ~15% of price
        hlc.append((h + 0.5, h - 0.5, h))
    assert detect("AAA", _bars(hlc), CAL[96]) is None


# -- the decile gate reads only 1m / 3m / 6m ----------------------------------


def test_detection_gate_reads_only_1m_3m_6m():
    rows = [
        Rank("BURST", "1w", percentile=0.99, raw_return=0.5),   # 1w excluded
        Rank("STALE", "12m", percentile=0.99, raw_return=2.0),  # 12m excluded
        Rank("REAL", "3m", percentile=0.95, raw_return=0.8),    # counts
        Rank("MID", "3m", percentile=0.50, raw_return=0.1),
    ]
    assert detection_gate(rows) == {"REAL"}


def test_detection_gate_is_inclusive_at_the_threshold():
    rows = [
        Rank("AT", "1m", percentile=TOP_DECILE, raw_return=0.3),
        Rank("BELOW", "6m", percentile=TOP_DECILE - 1e-9, raw_return=0.2),
    ]
    assert detection_gate(rows) == {"AT"}
