"""The market regime — a three-state filter, advisory only (spec §4.9).

One index per market (``^IXIC`` US, ``^JKSE`` IDX) drives a three-state regime
carrying a sizing posture in words. It is the map's clearest instance of *he does
not stop looking, he stops sizing*: the regime **never filters, never reorders
and never touches the star score** — the candidate list is identical in all three
states. Everything here is read and displayed, and nothing here gates.

The load-bearing choice is that the two named states are **not complements**:

- ``HOSTILE`` — ``SMA10`` falling **and** ``SMA20`` falling **and** ``SMA10 <
  SMA20`` (§10 verbatim).
- ``FRIENDLY`` — ``close`` above **both** SMAs **and** both rising.
- ``CHOPPY`` — **everything else**, the residual. The gap between the two named
  states *is* chop; defining it as the residual adds zero parameters and fails
  safe, and because HOSTILE needs the fast MA falling while FRIENDLY needs it
  rising, the three partition the space exactly — no precedence rule is needed.

Slope is **sign-only** — this session's SMA against five sessions ago, no
magnitude threshold anywhere. The whole filter has **zero tunable parameters**,
deliberately: survivorship bias (delisted names return zero rows on Yahoo, so any
series rebuilt from today's universe is biased upward) makes any threshold here
uncalibratable. Below :data:`REGIME_WARMUP` index bars the state is **undefined**
(``None``), not defaulted.

Pure over a clean, oldest-first ``list[Bar]`` — the store-driven wrapper that
reads index and member bars lives in the API layer / pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from .bars import Bar
from .indicators import sma

# The two moving averages the regime reads, and the sign-only slope lookback: a
# SMA is "rising" iff ``SMA[t] > SMA[t−5]`` (spec §4.9 / §4.2 "Rising"). No
# magnitude threshold — the whole point is zero tunable parameters.
SMA_FAST = 10
SMA_SLOW = 20
SLOPE_LOOKBACK = 5

# Warm-up: the slow SMA five sessions ago needs 20 bars ending at ``t−5``, so 25
# index bars in total. Below this the state is undefined, not defaulted (§4.9).
REGIME_WARMUP = SMA_SLOW + SLOPE_LOOKBACK

# The three states, defined here where they are computed; the API layer
# (``models.RegimeResponse``) re-exports this so there is one source of truth.
RegimeState = Literal["FRIENDLY", "CHOPPY", "HOSTILE"]

# The sizing posture each state carries — **words, never a computed position
# size** (spec §4.9). An undefined regime advises nothing.
_POSTURE: dict[RegimeState, str] = {
    "FRIENDLY": "full size",
    "CHOPPY": "reduced",
    "HOSTILE": "sit out",
}

# The trailing window an index breakout is measured against — a new high over the
# prior 20 sessions. Used only by the follow-through capture (§4.9), never a gate.
FOLLOWTHROUGH_WINDOW = 20


def posture(state: RegimeState | None) -> str | None:
    """The sizing posture for ``state``, in words (spec §4.9).

    ``FRIENDLY`` → full size, ``CHOPPY`` → reduced, ``HOSTILE`` → sit out. An
    undefined regime (``None``) advises nothing.
    """
    return _POSTURE.get(state) if state is not None else None


def _snapshot(bars: list[Bar]) -> tuple[float, float, float, float, float] | None:
    """``(close, fast, slow, fast_prev, slow_prev)`` for a regime-length series.

    ``None`` below :data:`REGIME_WARMUP` bars. At or above it all four SMAs exist
    together — the slow SMA five sessions ago is exactly what 25 bars affords — so
    every caller past the ``None`` check compares plain floats. ``*_prev`` are the
    SMAs as of five sessions ago, read by dropping the last five bars.
    """
    if len(bars) < REGIME_WARMUP:
        return None
    fast = sma(bars, SMA_FAST)
    slow = sma(bars, SMA_SLOW)
    fast_prev = sma(bars[:-SLOPE_LOOKBACK], SMA_FAST)
    slow_prev = sma(bars[:-SLOPE_LOOKBACK], SMA_SLOW)
    if None in (fast, slow, fast_prev, slow_prev):  # unreachable past the warm-up
        return None
    return bars[-1].adj_close, fast, slow, fast_prev, slow_prev  # type: ignore[return-value]


def regime_state(bars: list[Bar]) -> RegimeState | None:
    """The three-state regime for one index's oldest-first bars (spec §4.9).

    ``None`` when there are fewer than :data:`REGIME_WARMUP` bars — the state is
    undefined, not defaulted. Otherwise exactly one of ``HOSTILE`` / ``FRIENDLY``
    / ``CHOPPY``: the two named states cannot both hold (one needs the fast MA
    falling, the other rising), so ``CHOPPY`` is simply the residual.
    """
    snap = _snapshot(bars)
    if snap is None:
        return None
    close, fast, slow, fast_prev, slow_prev = snap
    if fast < fast_prev and slow < slow_prev and fast < slow:
        return "HOSTILE"
    if close > fast and close > slow and fast > fast_prev and slow > slow_prev:
        return "FRIENDLY"
    return "CHOPPY"


def _above_rising_mas(bars: list[Bar]) -> bool:
    """Is this name above **both** its SMAs with both rising (spec §4.9)?

    The per-name form of the FRIENDLY condition — what breadth counts. A name too
    young for a rising SMA20 is simply not above rising MAs (``False``), never an
    error.
    """
    snap = _snapshot(bars)
    if snap is None:
        return False
    close, fast, slow, fast_prev, slow_prev = snap
    return close > fast and close > slow and fast > fast_prev and slow > slow_prev


def breadth(members_bars: dict[str, list[Bar]]) -> float | None:
    """Share of the market's universe above its own rising SMA10/SMA20 (§4.9).

    **Displayed and gates nothing** — it is the measure survivorship bias
    corrupts most directly, so any threshold picked today would be fitted to a
    series wrong in a known direction. The denominator is every member; a name
    too young to be evaluated counts against it but is never credited. ``None``
    for an empty universe.
    """
    if not members_bars:
        return None
    up = sum(1 for bars in members_bars.values() if _above_rising_mas(bars))
    return up / len(members_bars)


@dataclass(frozen=True)
class FollowThrough:
    """One nightly breakout-follow-through observation for a market's index.

    Append-only, keyed ``(market, session)``. ``broke_out`` is whether the index
    closed to a new trailing-window high; ``index_close`` is its adjusted close.
    The rows accumulate a **forward** record: whether a break on session ``D``
    followed through is read later from subsequent ``index_close`` values, never
    reconstructed from a survivorship-biased past. Never displayed, never gated
    (spec §4.9).
    """

    session: date
    broke_out: bool
    index_close: float


def index_broke_out(bars: list[Bar]) -> bool | None:
    """Did the index close to a new high over its trailing window (§4.9)?

    The forward-recorded unit of breakout follow-through: today's adjusted close
    above the max of the prior :data:`FOLLOWTHROUGH_WINDOW` sessions. ``None``
    until a full trailing window exists. This is **captured nightly and never
    displayed or gated** — it is the only unbiased regime signal available
    (recorded forward, not reconstructed) and is irrecoverable if not started at
    launch.
    """
    if len(bars) < FOLLOWTHROUGH_WINDOW + 1:
        return None
    prior_high = max(b.adj_close for b in bars[-FOLLOWTHROUGH_WINDOW - 1 : -1])
    return bars[-1].adj_close > prior_high
