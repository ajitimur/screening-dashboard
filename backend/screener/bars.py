"""Bar ingest and hygiene (spec §3.4 rules 1–2, §3.5, §7.4 stages 2–3).

Bars arrive here as raw source rows and leave as a clean series every downstream
stage can trust. Three hygiene rules are applied *at ingest* so no later
computation has to remember them:

- **Phantom bars** (``volume == 0``) are removed entirely — never zero-filled,
  never carried forward. A no-trade bar prints ``high == low == close``, which
  drags ADR toward zero and makes a thin name screen as slow (§3.4 rule 1).
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


def clean_bars(bars: list[Bar], market: str, now: datetime) -> list[Bar]:
    """Apply every ingest hygiene rule: drop phantoms, discard non-final."""
    return keep_final(drop_phantom_bars(bars), market, now)
