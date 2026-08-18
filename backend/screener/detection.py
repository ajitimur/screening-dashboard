"""Setup detection: the base, cluster, envelope, trigger and stop (spec §4.5).

The heart of the app. Detection emits **a base, not a state** — every name
currently sitting in a valid base, nightly, with its trigger and stop, regardless
of whether anything happened today. It runs against **every universe member every
night**, not only recent movers.

The structure is two levels, ported from the wayfinding prototype
(``prototypes/16-trendline-fit/split.py``):

- **The base** runs from the prior move's peak to today (capped at 45 bars). No
  slope test decides its extent — it is a span, not a shape, so a bar that pierces
  the envelope does not invalidate it (the boundaries are fits, not monotonic
  tests).
- **The cluster** is the largest 3–7 bar trailing window tight enough to sit
  under ``TIGHT_MULT × ADR``. Its max high *is* the trigger, by identity.

The envelope is anchored at the cluster's max-high bar and searched over
**non-positive slopes only**, so the fitted line can never exceed the anchor —
measured at 100.0% of 29,242 detections during design. It therefore **never
reaches the trigger**: it gates ``line_ok`` and it draws the chart, nothing else.

Gates (a name is a detection iff all hold):

- **Cluster** — a tight 3–7 bar cluster exists (step 3).
- **Catch-up** — price is back at the 10/20 MA (step 2).
- **Decile** — top decile in **any of 1m/3m/6m**, off the rank table
  (:func:`detection_gate`). 1w is a momentum burst, not §3.1's big prior move;
  12m is stale enough that a name that topped out months ago still carries it.

``line_ok`` is **not** a gate — it becomes a sort tiebreak downstream. A name
failing it is still emitted as a detection (spec §4.5).

Three parameters from the reference are **deleted and must not be reintroduced**
(spec §4.5): ``MA_PROX_ADR`` (defined and never read), ``MAX_OVERSHOOT_FRAC``
(redundant — it catches only 4.4% of what the ADR overshoot test already does),
and the prior-move ≥25% floor (redundant against the decile gate).

Everything here is pure over a clean, oldest-first ``list[Bar]`` — the detector
operates on the **unadjusted** OHLC series, because the trigger and stop are real
order levels a trader places, not adjusted prices. ``adr``/``adr_abs`` (both
unadjusted-consistent) are reused from :mod:`.indicators`; the catch-up MA is on
the same unadjusted close, distinct from ``indicators.sma``'s adjusted definition.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from statistics import median

from .bars import Bar
from .indicators import adr as _adr
from .ranks import TOP_DECILE, Rank

# The prior-move windows, largest gain wins; the base starts at the winning
# window's peak (spec §4.5 step 1). Frozen borrowed defaults from q-scanner-v2.
MOVE_WINDOWS = (21, 42, 63, 126)
MAX_BASE_LEN = 45  # re-anchor to the highest high within 45 bars past this
MIN_BASE_LEN = 3   # §3.1's minimum; the base always ends today

# The cluster: the largest trailing k in [K_MIN, K_MAX] spanning ≤ TIGHT_MULT×ADR.
K_MIN, K_MAX = 3, 7
TIGHT_MULT = 1.5

# Catch-up: price back at the 10/20 MA, in ADR units (spec §4.5 step 2).
CATCHUP_10, CATCHUP_20 = 1.0, 2.0

# The envelope: an asymmetric loss over the base's highs, overshoot weighted 3×
# undershoot (only the ratio binds), searched over 200 non-positive slopes down
# to −0.5×ADR per bar (spec §4.5 step 4).
OVER_W, UNDER_W = 3.0, 1.0
SLOPE_STEPS = 200
MAX_SLOPE_ADR = 0.5

# line_ok: touches within 0.35×ADR of the line, grouped with a ≥3-bar gap into
# zones; ok iff ≥2 zones (or ≥1 reaching back into the first 60% of the base) and
# the max overshoot stays within 1.0×ADR (spec §4.5 step 5).
TOUCH_TOL_ADR = 0.35
MIN_TOUCHES = 2
MIN_TOUCH_GAP = 3
REACHES_BACK_FRAC = 0.6
MAX_OVERSHOOT_ADR = 1.0

# Detection requires ≥ 80 bars of history and a positive ADR (spec §4.5).
MIN_HISTORY = 80

# The proposed stop is placed at the trader's own convention, not at the cluster
# low. The replay (findings §6 finding 1; PRD #114, issue #127) measured his 649
# executed stops at a **median of 0.345 ADR** (p25 0.238, p75 0.490, 98.15% at or
# under 1.0 ADR); the cluster-low stop the detector used to propose ran a median
# of 1.28 ADR — roughly four times wider than the stop he actually places. The
# card's risk and affordability read this proposed stop, so the number a user
# reads is now derived from a stop the trader would plausibly place. The cluster
# geometry (``cluster_low``) is unchanged and still carried on the row; it is just
# no longer what the detector proposes as the stop.
STOP_CONVENTION_ADR = 0.345

# The star score's derived signals (spec §4.7). Dry-up compares the base's median
# volume to the 50 bars before it; "SMA20 rising" is §4.2's sign-only rising test
# (X[t] > X[t−5]) on the 20-bar MA. Read here, scored in :mod:`.score`.
DRYUP_LOOKBACK = 50
SMA_SUPPORT = 20
RISING_LAG = 5

# The decile gate reads only 3 of the 5 ranking windows (spec §4.5 gates).
DETECTION_LOOKBACKS = ("1m", "3m", "6m")

# Stamped on every detection row; bump when the detector's output changes so
# rows from different logic are never silently compared (spec §7.2 / A1).
DETECTOR_VERSION = 1


@dataclass(frozen=True)
class Detection:
    """One dated detection row: a base with its trigger, stop and signal vector.

    Emitted for a name that clears the cluster and catch-up gates (the decile gate
    is applied by the pipeline against the rank table). ``trigger`` is the cluster
    high **by identity**; ``line_end`` is the fitted line at today and is always
    ≤ ``trigger`` — the line never sets the trigger (spec §4.5 step 6).
    """

    symbol: str
    session: date
    detector_version: int
    trigger: float          # cluster high, by identity — never the fitted line
    stop: float             # the convention stop budget: STOP_CONVENTION_ADR·adr·trigger (issue #127)
    stopw_adr: float        # stop width normalised — equals STOP_CONVENTION_ADR by construction
    base_len: int
    move_gain: float        # the winning prior-move run-up, percent
    adr: float
    close: float
    cluster_k: int
    cluster_high: float
    cluster_low: float
    cluster_range_adr: float
    line_ok: bool           # a verdict on the fit's quality, NOT a gate
    touch_zones: int
    overshoot_adr: float
    slope: float            # the fitted envelope's slope, price per bar (≤ 0)
    line_end: float         # the fitted line at today; always ≤ trigger
    base_low: float
    # -- the star score's derived signals (spec §4.7) — persisted so a corrected
    # rubric replays backwards; scored in :mod:`.score`, never here.
    churn_l: float          # (Σ base daily ranges ÷ base range) ÷ base_len; orderliness
    sma20_rising: bool      # SMA20 rising, sign-only (X[t] > X[t−5]); MA support
    dryup: float            # median base volume ÷ median volume of the 50 bars before it

    @property
    def stop_price(self) -> float:
        """The proposed stop line in price terms: the trigger less the convention
        stop budget (``trigger − stop``). This is the stop the Board and Setups
        cards draw and derive risk from (issue #127) — no longer the cluster low.
        On a fixture whose ``stop`` was built as ``trigger − cluster_low`` this
        still evaluates to the cluster low, so the identity degrades gracefully."""
        return self.trigger - self.stop

    @property
    def dist_adr(self) -> float:
        """Distance from today's close up to the trigger, in ADR — "how soon"
        (§5.1). ``adr_abs = adr × close`` is ADR in price units; the distance is
        that many average daily ranges below the trigger. ``nan`` if ADR is
        non-positive (it never is on a stored detection, which required a positive
        ADR to exist). The candidate row and the chart facts read the same figure."""
        adr_abs = self.adr * self.close
        if adr_abs <= 0:
            return float("nan")
        return (self.trigger - self.close) / adr_abs


# -- pure geometry (numpy-free, so it is unit-tested without the network) ------


def _argmax(seq: list[float], lo: int, hi: int) -> int:
    """Index in ``[lo, hi]`` of the maximum, first on a tie (as ``np.argmax``)."""
    return max(range(lo, hi + 1), key=lambda i: seq[i])


def _prior_move(high: list[float], low: list[float], as_of: int):
    """Best low→high run-up over the configured windows ending at ``as_of``.

    Over each window the lowest low is the origin and the highest high after it
    the peak; the largest gain wins. Returns ``(gain_pct, peak_index)`` or
    ``None`` when no window has the minimum 5 bars or every origin has a
    non-positive low (a handful of IDX bars carry a zero low even after the
    phantom drop, which would divide by zero).
    """
    best = None
    for w in MOVE_WINDOWS:
        start = max(0, as_of - w)
        if as_of - start < 5:
            continue
        origin = min(range(start, as_of + 1), key=lambda i: low[i])
        if low[origin] <= 0:
            continue
        peak = _argmax(high, origin, as_of)
        gain = (high[peak] / low[origin] - 1.0) * 100.0
        if best is None or gain > best[0]:
            best = (gain, peak)
    return best


def _find_cluster(high: list[float], low: list[float], as_of: int, adr_abs: float):
    """Largest trailing 3–7 bar window spanning ≤ ``TIGHT_MULT × ADR``.

    Returns ``(k, cluster_high, cluster_low, range_adr)`` for the first (largest)
    k that is tight enough, or ``None`` (``no_cluster``, a rejection).
    """
    if adr_abs <= 0:
        return None
    for k in range(K_MAX, K_MIN - 1, -1):
        lo = as_of - k + 1
        if lo < 0:
            continue
        ch = max(high[lo:as_of + 1])
        cl = min(low[lo:as_of + 1])
        range_adr = (ch - cl) / adr_abs
        if range_adr <= TIGHT_MULT:
            return k, ch, cl, range_adr
    return None


def _fit_envelope(
    high: list[float], adr_abs: float, anchor: int, base_start: int,
    as_of: int, cluster_k: int,
):
    """The anchored, backwards-extrapolated upper envelope, plus its ``line_ok``.

    The line is pinned at ``high[anchor]`` (the cluster's max high) and the slope
    minimising the asymmetric loss over the base's highs is chosen from 200
    non-positive candidates. Returns ``(slope, line_ok, zones, overshoot_adr,
    line_end)``; ``line_end`` is the line evaluated at today and is ≤ the anchor
    by construction (non-positive slope, positive lever), so it never reaches the
    trigger.
    """
    y_a = high[anchor]
    span = -MAX_SLOPE_ADR * adr_abs  # the steepest (most negative) slope
    best_slope = 0.0
    best_loss = None
    for s in range(SLOPE_STEPS):
        m = span * (1.0 - s / (SLOPE_STEPS - 1))  # linspace(span, 0, SLOPE_STEPS)
        loss = 0.0
        for t in range(base_start, as_of + 1):
            resid = high[t] - (y_a + m * (t - anchor))
            loss += OVER_W * resid if resid > 0 else UNDER_W * -resid
        if best_loss is None or loss < best_loss:
            best_loss, best_slope = loss, m
    m = best_slope

    tol = TOUCH_TOL_ADR * adr_abs
    cluster_start = as_of - cluster_k + 1
    resid = [high[t] - (y_a + m * (t - anchor)) for t in range(base_start, as_of + 1)]
    touch_idx = [
        base_start + i
        for i, r in enumerate(resid)
        if abs(r) <= tol and base_start + i < cluster_start
    ]
    if touch_idx:
        zones = 1 + sum(
            1 for a, b in zip(touch_idx[:-1], touch_idx[1:]) if b - a >= MIN_TOUCH_GAP
        )
    else:
        zones = 0
    overs = [r for r in resid if r > tol]
    over_max = max(overs) / adr_abs if overs else 0.0
    base_len = as_of - base_start + 1
    reaches_back = bool(touch_idx) and touch_idx[0] <= base_start + REACHES_BACK_FRAC * base_len
    line_ok = (
        (zones >= MIN_TOUCHES or (zones >= 1 and reaches_back))
        and over_max <= MAX_OVERSHOOT_ADR
    )
    line_end = y_a + m * (as_of + 1 - anchor)
    return m, line_ok, zones, over_max, line_end


def _churn_l(
    high: list[float], low: list[float], base_start: int, as_of: int
) -> float:
    """Orderliness signal: ``(Σ daily ranges over the base ÷ base range) ÷ L``.

    The sum of per-bar ranges relative to the base's net span, divided by base
    length — a smooth drift runs low (~0.19), a barcode high (~0.62). Zero when
    the base has no vertical span (every bar identical), which fails the band."""
    span = max(high[base_start:as_of + 1]) - min(low[base_start:as_of + 1])
    if span <= 0:
        return 0.0
    total = sum(high[t] - low[t] for t in range(base_start, as_of + 1))
    base_len = as_of - base_start + 1
    return total / span / base_len


def _dryup(vol: list[int], base_start: int, as_of: int) -> float:
    """Volume signal: median base volume ÷ median volume of the 50 bars before it.

    Below 1.0 the base is quieter than the run-up that preceded it — the dry-up
    §3.5 wants. ``1.0`` (neutral, no dry-up) when no bars precede the base, which
    only happens for a base that starts at the very first bar."""
    pre = vol[max(0, base_start - DRYUP_LOOKBACK):base_start]
    if not pre:
        return 1.0
    pre_med = median(pre)
    if pre_med <= 0:
        return 1.0
    return median(vol[base_start:as_of + 1]) / pre_med


def _sma_close(close: list[float], as_of: int, window: int) -> float | None:
    """SMA of the **unadjusted** close over ``window`` traded bars ending at
    ``as_of``. Distinct from ``indicators.sma`` (adjusted close, for returns):
    the catch-up MA is a support level in the same price the trigger lives in."""
    if as_of + 1 < window:
        return None
    return sum(close[as_of - window + 1:as_of + 1]) / window


def _as_of_index(bars: list[Bar], as_of: date) -> int | None:
    """Index of the last bar on or before ``as_of``; ``None`` if none exists."""
    sessions = [b.session for b in bars]
    idx = bisect_right(sessions, as_of) - 1
    return idx if idx >= 0 else None


def detect(symbol: str, bars: list[Bar], as_of: date) -> Detection | None:
    """The base for ``(symbol, as_of)``, or ``None`` if the name is not a setup.

    Returns ``None`` when the per-name gates fail: too little history (< 80 bars)
    or non-positive ADR, no prior move, a base shorter than 3 bars, price not yet
    caught up to the 10/20, or no tight cluster. The **decile** gate is not
    applied here — it is cross-sectional and lives in the pipeline; a caller
    detecting a single name in isolation has already decided it is eligible.
    """
    idx = _as_of_index(bars, as_of)
    if idx is None or idx < MIN_HISTORY:
        return None
    high = [b.high for b in bars]
    low = [b.low for b in bars]
    close = [b.close for b in bars]
    vol = [b.volume for b in bars]

    a = _adr(bars[:idx + 1])
    if a is None or a <= 0:
        return None
    adr_abs = a * close[idx]

    mv = _prior_move(high, low, idx)
    if mv is None:
        return None
    move_gain, peak = mv
    base_start = peak
    if idx - base_start + 1 > MAX_BASE_LEN:
        recent = idx - MAX_BASE_LEN + 1
        base_start = _argmax(high, recent, idx)
    base_len = idx - base_start + 1
    if base_len < MIN_BASE_LEN:
        return None

    s10 = _sma_close(close, idx, 10)
    s20 = _sma_close(close, idx, 20)
    caught_up = (
        s10 is not None and s20 is not None
        and close[idx] - s10 <= CATCHUP_10 * adr_abs
        and close[idx] - s20 <= CATCHUP_20 * adr_abs
    )
    if not caught_up:
        return None

    cluster = _find_cluster(high, low, idx, adr_abs)
    if cluster is None:
        return None
    k, cluster_high, cluster_low, range_adr = cluster

    anchor = _argmax(high, idx - k + 1, idx)
    slope, line_ok, zones, over_max, line_end = _fit_envelope(
        high, adr_abs, anchor, base_start, idx, k
    )

    trigger = cluster_high  # by identity — never max(line, high); the clamp is dead
    # The proposed stop is the trader's convention (issue #127): a fixed
    # STOP_CONVENTION_ADR multiple of the night's ADR below the trigger, in price
    # units. By construction ``stopw_adr`` equals the convention — the a·trigger
    # in ``stop`` cancels — so every proposed stop sits at 0.345 ADR, not the
    # ~1.28 ADR the cluster-low distance used to yield.
    stop = STOP_CONVENTION_ADR * a * trigger if trigger > 0 else float("nan")
    stopw_adr = stop / trigger / a if trigger > 0 else float("nan")

    # The star score's three derived signals (spec §4.7), persisted on the row so
    # a corrected rubric replays over history. SMA20 rising is sign-only: the MA
    # today above the MA five bars back (§4.2's "rising").
    s20 = _sma_close(close, idx, SMA_SUPPORT)
    s20_prev = _sma_close(close, idx - RISING_LAG, SMA_SUPPORT)
    sma20_rising = s20 is not None and s20_prev is not None and s20 > s20_prev
    return Detection(
        symbol=symbol,
        session=as_of,
        detector_version=DETECTOR_VERSION,
        trigger=trigger,
        stop=stop,
        stopw_adr=stopw_adr,
        base_len=base_len,
        move_gain=move_gain,
        adr=a,
        close=close[idx],
        cluster_k=k,
        cluster_high=cluster_high,
        cluster_low=cluster_low,
        cluster_range_adr=range_adr,
        line_ok=line_ok,
        touch_zones=zones,
        overshoot_adr=over_max,
        slope=slope,
        line_end=line_end,
        base_low=min(low[base_start:idx + 1]),
        churn_l=_churn_l(high, low, base_start, idx),
        sma20_rising=sma20_rising,
        dryup=_dryup(vol, base_start, idx),
    )


def detection_gate(rows: list[Rank]) -> set[str]:
    """Names top-decile in **any of 1m/3m/6m** — the detection precondition.

    A subset of the general union gate: 1w (a momentum burst) and 12m (stale) are
    excluded, so a name that topped out months ago no longer qualifies on staleness
    alone (spec §4.5 gates)."""
    return {
        r.symbol
        for r in rows
        if r.lookback in DETECTION_LOOKBACKS and r.percentile >= TOP_DECILE
    }
