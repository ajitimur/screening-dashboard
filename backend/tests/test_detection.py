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

import random
from datetime import date, timedelta

from screener.bars import Bar
from screener.detection import (
    DETECTOR_VERSION,
    K_MAX,
    K_MIN,
    STOP_CONVENTION_ADR,
    TIGHT_MULT,
    TOP_DECILE,
    Rank,
    _churn_l,
    _dryup,
    _find_cluster,
    detect,
    detection_gate,
    range_3bar_adr,
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


def _wandering_top_series(wander):
    """``_base_series`` with the last 7 bars alternating ``±wander`` around 100.

    Each bar keeps its own 1.0-wide range, so ADR is untouched; only the *span*
    of the trailing window moves. The knob is base tightness alone.
    """
    hlc = _base_series()[:-7]
    for i in range(7):
        p = 100.0 + (wander if i % 2 else -wander)
        hlc.append((p + 0.5, p - 0.5, p))
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


def test_proposed_stop_is_the_traders_convention_not_the_cluster_low():
    # The detector proposes the trader's own stop convention (issue #127): a fixed
    # STOP_CONVENTION_ADR multiple of the night's ADR below the trigger, NOT the
    # cluster-low distance that used to run ~4× too wide.
    d = detect("AAA", _bars(_base_series()), CAL[104])
    # stopw_adr equals the convention exactly — the a·trigger in the budget cancels.
    assert abs(d.stopw_adr - STOP_CONVENTION_ADR) < 1e-12
    assert abs(d.stop - STOP_CONVENTION_ADR * d.adr * d.trigger) < 1e-12
    # The proposed stop is *tighter* than the raw cluster low it replaced here.
    cluster_low_stopw = (d.trigger - d.cluster_low) / d.trigger / d.adr
    assert d.stopw_adr < cluster_low_stopw
    # The stop line the cards draw is the trigger less the convention budget.
    assert abs(d.stop_price - (d.trigger - d.stop)) < 1e-12
    assert d.stop_price < d.trigger


def test_stop_width_does_not_move_with_base_tightness():
    # The two quantities the domain model keeps apart (issue #147). Base tightness
    # is setup geometry — the trailing window's span in ADR, what TIGHT_MULT gates
    # and the rubric's ×2 dimension scores. Stop width is his risk — the trigger-to-
    # stop distance, fixed at the convention. Findings §3b measured them 3.8× apart
    # on the same 649 entries; here they are wired apart, so a future edit deriving
    # the stop from the base geometry again fails this test.
    tight = detect("AAA", _bars(_wandering_top_series(0.0)), CAL[104])
    loose = detect("AAA", _bars(_wandering_top_series(0.2)), CAL[104])
    assert tight is not None and loose is not None
    assert abs(tight.adr - loose.adr) < 1e-5           # the same volatility unit
    # Base tightness moves ...
    assert loose.cluster_range_adr > tight.cluster_range_adr * 1.3
    assert loose.cluster_low < tight.cluster_low       # and so does the cluster low
    # ... stop width does not.
    assert abs(tight.stopw_adr - STOP_CONVENTION_ADR) < 1e-12
    assert abs(loose.stopw_adr - STOP_CONVENTION_ADR) < 1e-12


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


def test_range_3bar_adr_reports_the_trailing_3_bar_range():
    # The read-only diagnostic behind the #132 study: the trailing 3-bar range in
    # ADR, taken *regardless* of whether it clears TIGHT_MULT, so a ``no_cluster``
    # rejection can still be quantified against the condition's window. Here the
    # last three bars span 110 − 104 = 6, which at adr_abs = 4.0 is 1.5 ADR; every
    # wider window drags in the low-90 bars.
    high = [100.0, 100.0, 110.0, 110.0, 110.0]
    low = [90.0, 90.0, 104.0, 104.0, 104.0]
    assert range_3bar_adr(high, low, 4, 4.0) == 1.5
    # A window genuinely in motion reads far over the 1.5 window.
    wide_low = [90.0, 90.0, 100.0, 98.0, 102.0]
    assert range_3bar_adr(high, wide_low, 4, 4.0) == (110.0 - 98.0) / 4.0
    # Non-positive ADR is undefined, not a range.
    assert range_3bar_adr(high, low, 4, 0.0) is None
    # A window running off the front of the series has nothing to measure.
    assert range_3bar_adr(high, low, 1, 4.0) is None


def test_range_3bar_adr_is_the_minimum_over_every_cluster_k():
    # The rename rests on a proof, not a measurement: trailing range is monotone
    # in k, so the min over k in [K_MIN, K_MAX] is *always* the K_MIN window. This
    # pins the identity the docstring argues for — if a future K_MIN/K_MAX change
    # or a scan rewrite broke it, the diagnostic's name would start lying. The
    # oracle below is the scan `range_3bar_adr` used to run before #146 collapsed
    # it; this is now the only place that loop lives.
    def min_over_k(high, low, as_of, adr_abs):
        best = None
        for k in range(K_MIN, K_MAX + 1):
            lo = as_of - k + 1
            if lo < 0:
                continue
            rng = (max(high[lo:as_of + 1]) - min(low[lo:as_of + 1])) / adr_abs
            best = rng if best is None or rng < best else best
        return best

    rng = random.Random(146)
    for _ in range(200):
        close = [rng.uniform(5.0, 200.0) for _ in range(12)]
        high = [c * (1.0 + rng.uniform(0.0, 0.08)) for c in close]
        low = [c * (1.0 - rng.uniform(0.0, 0.08)) for c in close]
        for as_of in range(2, 12):
            assert range_3bar_adr(high, low, as_of, 4.0) == min_over_k(
                high, low, as_of, 4.0
            )


# -- the star score's derived signals (spec §4.7) -----------------------------


def test_detection_carries_the_star_score_signal_vector():
    d = detect("AAA", _bars(_base_series()), CAL[104])
    # churn/L over the 30-bar flat top: 30 unit ranges over a unit span ÷ 30 = 1.0.
    assert abs(d.churn_l - 1.0) < 1e-9
    # Constant volume → no dry-up (base median == pre-base median).
    assert abs(d.dryup - 1.0) < 1e-9
    assert isinstance(d.sma20_rising, bool)


def test_churn_l_separates_smooth_drift_from_a_barcode():
    # Barcode: 10 bars oscillating in [99, 100], span 1.0, per-bar range 1.0.
    barcode_hi = [100.0] * 10
    barcode_lo = [99.0] * 10
    assert abs(_churn_l(barcode_hi, barcode_lo, 0, 9) - 1.0) < 1e-9
    # Smooth drift up: same 10 bars, tight 0.2 ranges over a 2.0 net span.
    drift_hi = [90.0 + 0.2 * i + 0.2 for i in range(10)]
    drift_lo = [90.0 + 0.2 * i for i in range(10)]
    assert _churn_l(drift_hi, drift_lo, 0, 9) < 0.2


def test_dryup_is_base_volume_over_the_preceding_fifty_bars():
    vol = [100] * 50 + [40] * 10   # a quiet base after a busy run-up
    assert abs(_dryup(vol, 50, 59) - 0.4) < 1e-9


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


# -- TIGHT_MULT injected for the #141 sweep ---------------------------------
#
# The cluster gate's cut is a module constant, and it stays one: the live value
# is ``TIGHT_MULT = 1.5`` and no measurement may move it. Issue #141 needs to
# *price* a widen — how much the detected field inflates per real entry a wider
# gate recovers — which means running the detector at 1.75 / 2.0 / 2.25 without
# ever mutating the constant. So the cut becomes an argument that defaults to it.


def _marginal_cluster_series():
    """A base whose tightest window sits just *past* the 1.5× gate.

    60 flat bars at 100, a tight run-up to 110, a 12-bar shelf at 110 (which sets
    a small ADR), then three bars spanning 110 ± 1.1. The trailing 3-bar range
    reads **1.85 ADR** — the median of the 113 marginal `cluster` misses in
    findings §3a, against a 1.5× gate. A widen to 2.0 recovers it; the live gate
    declines it.
    """
    hlc = [(100.5, 99.5, 100.0)] * 60
    for i in range(1, 16):  # tight run-up 100 -> 110
        p = 100.0 + (110.0 - 100.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(110.5, 109.5, 110.0)] * 12   # the shelf that sets ADR
    hlc += [(111.1, 108.9, 110.0)] * 3    # 1.85 ADR — marginal, not in motion
    return hlc


def test_the_marginal_fixture_sits_between_the_live_gate_and_a_widen():
    """The fixture's premise, pinned: 1.85 ADR, over 1.5 and under 2.0."""
    bars = _bars(_marginal_cluster_series())
    idx = len(bars) - 1
    from screener.indicators import adr as _adr

    adr_abs = _adr(bars) * bars[idx].close
    r3 = range_3bar_adr([b.high for b in bars], [b.low for b in bars], idx, adr_abs)
    assert 1.8 < r3 < 1.9
    assert TIGHT_MULT < r3 < 2.0


def test_a_marginal_cluster_miss_is_recovered_by_a_widened_tight_mult():
    bars = _bars(_marginal_cluster_series())
    as_of = bars[-1].session
    assert detect("AAA", bars, as_of) is None            # the live gate declines it
    assert detect("AAA", bars, as_of, tight_mult=1.75) is None   # still over 1.75
    widened = detect("AAA", bars, as_of, tight_mult=2.0)
    assert widened is not None
    assert widened.cluster_range_adr <= 2.0


def test_tight_mult_defaults_to_the_module_constant():
    # Passing the constant explicitly is the same call as not passing it — the
    # sweep's baseline point is the live detector, not a near-copy of it.
    bars = _bars(_base_series())
    as_of = CAL[104]
    assert detect("AAA", bars, as_of) == detect("AAA", bars, as_of, tight_mult=TIGHT_MULT)


def test_sweeping_tight_mult_never_mutates_the_live_constant():
    bars = _bars(_marginal_cluster_series())
    for mult in (1.5, 1.75, 2.0, 2.25):
        detect("AAA", bars, bars[-1].session, tight_mult=mult)
    assert TIGHT_MULT == 1.5


def test_find_cluster_takes_the_cut_as_an_argument():
    # The gate is one comparison and it reads the argument, not the constant.
    high = [100.0, 100.0, 110.0, 110.0, 110.0]
    low = [90.0, 90.0, 104.0, 104.0, 104.0]  # trailing 3-bar range = 1.5 ADR at 4.0
    assert _find_cluster(high, low, 4, 4.0, tight_mult=1.4) is None
    k, ch, cl, r = _find_cluster(high, low, 4, 4.0, tight_mult=1.5)
    assert (k, ch, cl, r) == (3, 110.0, 104.0, 1.5)
