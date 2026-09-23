"""Bar ingest and hygiene (spec §3.4 rules 1–2, §3.5, §7.4 stages 2–3).

Bars arrive here as raw source rows and leave as a clean series every downstream
stage can trust. Three hygiene rules are applied *at ingest* so no later
computation has to remember them:

- **Phantom bars** (``volume == 0``) are removed entirely — never zero-filled,
  never carried forward. A no-trade bar prints ``high == low == close``, which
  drags ADR toward zero and makes a thin name screen as slow (§3.4 rule 1). The
  one carve-out is per symbol and narrow: an instrument with no volume to
  report at all (``^VIX``, ``IDR=X`` — §4.10) keeps its bars, because there
  zero volume is not evidence that nothing traded.
- **Finality**: a bar dated ``D`` is final iff ``now`` is past ``D``'s *normal*
  session close + 30 min, in the exchange's local time. Non-final bars are
  discarded, not stored flagged — 14 minutes of trading was once served as a
  full day (§3.4 rule 2). Keying to the *normal* close means US early closes
  (13:00 ET) need no special handling: the rule waits longer than necessary,
  never shorter.
- **Both series preserved**: the unadjusted OHLC (dollar volume is
  ``close × volume`` on the unadjusted close, because the source rescales prices
  for corporate actions but leaves volume alone) and the adjusted close (for
  everything geometric) — §3.5.

There is deliberately **no trading-calendar table**: the exchange calendar is
the union of observed bar dates (§3.4 rule 4), read off the store, never a
hardcoded holiday list. Finality never consults a calendar either — it keys to
each bar's own date and the exchange's normal close.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Each market's exchange: local timezone and *normal* session close. Finality
# keys to the normal close, so a US early close errs on the safe side (§3.4
# rule 2). IDX: the 2026-08-04 bar was measured final at 19:49 WIB against a
# 16:00 close (spec §7.3).
EXCHANGE = {
    "US": {"tz": "America/New_York", "close": time(16, 0)},
    "IDX": {"tz": "Asia/Jakarta", "close": time(16, 0)},
}

# A bar dated D is final only once this margin past D's normal close has passed.
FINALITY_MARGIN = timedelta(minutes=30)


@dataclass(frozen=True)
class Bar:
    """One EOD bar, both series carried (spec §3.5).

    ``close`` is the unadjusted close (dollar volume rides on it); ``adj_close``
    is the split/dividend-adjusted close that everything geometric uses.
    """

    session: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int

    @property
    def dollar_volume(self) -> float:
        """Dollar volume on the *unadjusted* close (§3.5)."""
        return self.close * self.volume


# -- parsing (pure, so it is unit-tested without the network) -----------------


def parse_bars(rows: list[dict]) -> list[Bar]:
    """Normalise raw source rows (yfinance, ``auto_adjust=False``) into bars.

    Columns arrive capitalised: ``Date, Open, High, Low, Close, Adj Close,
    Volume``. ``Date`` may be a ``date``, ``datetime``/Timestamp or ISO string.
    """
    return [
        Bar(
            session=_as_date(row["Date"]),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            adj_close=float(row["Adj Close"]),
            volume=int(row["Volume"]),
        )
        for row in rows
    ]


def newest_bar_has_close(rows: list[dict]) -> bool:
    """Did the newest raw row actually print a close — in **both** series (§3.5)?

    The provider can answer a session with the *scaffolding* of a bar — open,
    high, low and volume all populated — and no close at all, which arrives as
    NaN rather than as a missing row. That is not a bar: every geometric figure
    downstream is computed off a close, and NaN propagates through all of them
    without ever raising, so a shell bar poisons a run quietly instead of failing
    it. On 2026-09-22 it did exactly that to 5,320 of 5,338 US bars — 2,065 of
    2,070 names carried a NaN return, every percentile collapsed to 1.0 (NaN
    sorts as greatest, so the whole universe tied at the top) and the night
    published anyway.

    So the source treats such a payload as silence (:meth:`Source.resolve`).

    **Both** series are asked because §3.5 splits them: the unadjusted close
    carries dollar volume, the adjusted close carries returns, MAs, gaps, ADR and
    tightness — everything geometric. A row with a finite ``Close`` and a NaN
    ``Adj Close`` reproduces the whole of 2026-09-22, so guarding one alone would
    leave the defect reachable.

    Only the **newest** row is asked. A genuine history carries the odd NaN close
    deep in the past (a healthy 2026-09-21 pull had four), and refusing those
    would quarantine every night; it is the session about to be ingested that has
    to have printed. Rows arrive date-ascending from the provider — the same
    order :func:`parse_bars` is handed them in — so the newest is the last.
    """
    if not rows:
        return False
    newest = rows[-1]
    return _printed(newest.get("Close")) and _printed(newest.get("Adj Close"))


def _printed(value: object) -> bool:
    """Did this field arrive as a real number — not absent, not NaN, not an inf?

    A close that never printed arrives as NaN, and NaN is a perfectly good float:
    every comparison against it is False and every arithmetic result is NaN
    again, which is how it reached the rank table without anything raising.
    ``bool`` is excluded deliberately — ``True`` is finite and would pass, but a
    boolean in a price field is a parse accident, never a price.
    """
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _as_date(value: object) -> date:
    if isinstance(value, datetime):  # datetime is a date subclass — test first
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    if hasattr(value, "date"):  # pandas Timestamp and the like
        return value.date()
    raise TypeError(f"cannot read a session date from {value!r}")


# -- hygiene ------------------------------------------------------------------


def drop_phantom_bars(bars: list[Bar]) -> list[Bar]:
    """Remove zero-volume (no-trade) bars from the series entirely (rule 1)."""
    return [b for b in bars if b.volume > 0]


def is_final(session: date, market: str, now: datetime) -> bool:
    """Is the bar dated ``session`` final as of ``now`` (rule 2)?

    ``now`` must be timezone-aware; the comparison happens against the bar's
    normal exchange close + 30 min in the exchange's local time.
    """
    exchange = EXCHANGE[market]
    final_after = datetime.combine(
        session, exchange["close"], tzinfo=ZoneInfo(exchange["tz"])
    ) + FINALITY_MARGIN
    return now > final_after


def keep_final(bars: list[Bar], market: str, now: datetime) -> list[Bar]:
    """Discard bars whose session is not yet final (rule 2)."""
    return [b for b in bars if is_final(b.session, market, now)]


def clean_bars(
    bars: list[Bar], market: str, now: datetime, *, keep_volumeless: bool = False
) -> list[Bar]:
    """Apply every ingest hygiene rule: drop phantoms, discard non-final.

    ``keep_volumeless`` lifts the phantom rule for an instrument that carries no
    volume to report at all — a volatility index is a computed level, a spot FX
    pair trades off-exchange, and every one of their bars prints ``volume == 0``
    (spec §4.10). The rule reads that as "no trade occurred", so for those two
    series it would drop the whole history. Which symbols qualify is the source's
    business (:data:`screener.source.VOLUMELESS`), not this module's: the
    hygiene rule stays a rule, with one flag for the case where zero volume is
    not evidence of anything.

    Finality is applied either way. For the FX pair that rides the market's
    exchange close as a **documented approximation** — the currency trades around
    the clock, so there is no session close of its own to key to, and the
    market's own close is the conservative reading of when its bar stopped
    moving for the purposes of a market whose session that is.
    """
    kept = bars if keep_volumeless else drop_phantom_bars(bars)
    return keep_final(kept, market, now)
