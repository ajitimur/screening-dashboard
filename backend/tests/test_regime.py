"""Seam 6e: the market regime — the three-state filter and breadth (spec §4.9).

One index per market drives a three-state regime: ``HOSTILE`` when both the 10
and 20 are falling and the 10 is below the 20, ``FRIENDLY`` when the close is
above both and both are rising, ``CHOPPY`` as **the residual**. The two named
states are not complements — the gap between them *is* chop — so the three
partition the space exactly and no precedence rule is needed.

Slope is **sign-only** (``SMA[t] > SMA[t−5]``), so the whole filter has zero
tunable parameters. Below 25 index bars the state is **undefined**, not defaulted.

Every function is pure over a clean, oldest-first ``list[Bar]`` — no store, no
network.
"""

from datetime import date, timedelta

from screener.bars import Bar
from screener.indicators import sma
from screener.regime import (
    REGIME_WARMUP,
    breadth,
    index_broke_out,
    posture,
    regime_state,
)


def _bars(adj_closes: list[float]) -> list[Bar]:
    d0 = date(2026, 1, 1)
    return [
        Bar(d0 + timedelta(days=i), c, c, c, c, c, 1000)
        for i, c in enumerate(adj_closes)
    ]


# -- warm-up: below 25 index bars the state is undefined (§4.9) ----------------


def test_state_is_undefined_below_the_warmup():
    assert REGIME_WARMUP == 25  # SMA20 + the 5-session slope lookback
    # 24 bars is one short of a rising SMA20; the state is None, not defaulted.
    assert regime_state(_bars([100.0 + i for i in range(REGIME_WARMUP - 1)])) is None
    # 25 bars is enough to decide.
    assert regime_state(_bars([100.0 + i for i in range(REGIME_WARMUP)])) is not None


# -- the three states (§4.9) ---------------------------------------------------


def test_friendly_when_close_above_both_and_both_rising():
    # A clean uptrend: close above SMA10/20 and both rising.
    bars = _bars([100.0 + i for i in range(30)])
    assert regime_state(bars) == "FRIENDLY"


def test_hostile_when_both_falling_and_ten_below_twenty():
    # A clean downtrend: both SMAs falling and the fast below the slow.
    bars = _bars([200.0 - i for i in range(30)])
    state = regime_state(bars)
    assert state == "HOSTILE"
    # sanity: the fast SMA really is below the slow in a downtrend
    assert sma(bars, 10) < sma(bars, 20)


def test_choppy_is_the_residual_flat_series():
    # A flat series: neither SMA rising nor falling — not HOSTILE, not FRIENDLY.
    assert regime_state(_bars([100.0] * 30)) == "CHOPPY"


def test_choppy_when_rising_but_close_dips_below_the_fast_ma():
    # SMAs still rising, but today's close prints below SMA10 → not FRIENDLY,
    # and the fast MA is not falling → not HOSTILE → CHOPPY.
    bars = _bars([100.0 + i for i in range(29)] + [90.0])
    assert sma(bars, 10) > sma(bars[:-5], 10)  # fast MA still rising
    assert regime_state(bars) == "CHOPPY"


def test_the_three_states_partition_the_space_no_precedence_needed():
    # Across a spread of shapes every series lands in exactly one named state or
    # the residual; HOSTILE (fast falling) and FRIENDLY (fast rising) can never
    # both hold, so no ordering of the rules is required.
    shapes = [
        [100.0 + i for i in range(30)],          # up
        [200.0 - i for i in range(30)],          # down
        [100.0] * 30,                            # flat
        [100.0 + (i % 3) for i in range(30)],    # jagged
        [100.0 + i for i in range(29)] + [90.0],  # up then dip
    ]
    for adj in shapes:
        assert regime_state(_bars(adj)) in {"FRIENDLY", "CHOPPY", "HOSTILE"}


# -- slope is sign-only, no magnitude threshold anywhere (§4.9) ----------------


def test_slope_is_sign_only_a_microscopic_uptrend_still_reads_friendly():
    # Increments of 1e-6 — far below any plausible magnitude threshold. If the
    # filter had one, this would read CHOPPY; sign-only, it is FRIENDLY.
    bars = _bars([100.0 + i * 1e-6 for i in range(30)])
    assert regime_state(bars) == "FRIENDLY"


# -- sizing posture, in words (§4.9) ------------------------------------------


def test_posture_is_the_word_not_a_number():
    assert posture("FRIENDLY") == "full size"
    assert posture("CHOPPY") == "reduced"
    assert posture("HOSTILE") == "sit out"
    assert posture(None) is None  # undefined regime advises nothing


# -- breadth: share above its own rising SMA10/20, displayed not gated (§4.9) --


def test_breadth_is_the_share_of_members_individually_friendly():
    members = {
        "UP1": _bars([100.0 + i for i in range(30)]),   # above rising MAs
        "UP2": _bars([50.0 + i for i in range(30)]),    # above rising MAs
        "FLAT": _bars([100.0] * 30),                    # not rising
        "DOWN": _bars([200.0 - i for i in range(30)]),  # below falling MAs
    }
    assert breadth(members) == 0.5  # 2 of 4


def test_breadth_is_none_for_an_empty_universe():
    assert breadth({}) is None


def test_breadth_denominator_counts_a_young_name_but_never_credits_it():
    # A name too young to have a rising SMA20 cannot be "above rising MAs": it is
    # in the denominator, never the numerator.
    members = {
        "UP": _bars([100.0 + i for i in range(30)]),
        "YOUNG": _bars([100.0 + i for i in range(10)]),  # < warm-up
    }
    assert breadth(members) == 0.5


# -- breakout follow-through: captured, never gated (§4.9) ---------------------


def test_index_breakout_is_a_new_high_over_the_trailing_window():
    # Flat then a new high on the last bar → a breakout.
    up = _bars([100.0] * 25 + [101.0])
    assert index_broke_out(up) is True
    # Last bar not above the trailing high → no breakout.
    flat = _bars([100.0] * 26)
    assert index_broke_out(flat) is False


def test_index_breakout_is_undefined_without_a_full_trailing_window():
    assert index_broke_out(_bars([100.0] * 5)) is None
