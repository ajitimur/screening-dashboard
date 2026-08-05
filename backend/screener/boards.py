"""The five leaderboards — a read-time cut of the rank table (spec §5.2 / §4.3).

Five separate boards per market, **30 rows each, ranked on pure return** with no
volatility adjustment (ticket 06 R3/R9). That bias is deliberate: normalising by
ADR replaces up to 20 of 30 US rows and answers a question the method does not
ask, so the boards *are* dominated by high-volatility names and a quiet mega-cap
making an unusual move may never appear — the correct bias, not a bug to fix.

Boards are **not a stored stream** (they are absent from §7.2's derived-table
list): they are computed on demand from the persisted rank table, which already
carries every universe member's percentile and raw return. The store-driven
wrapper (reading tonight's ranks, last session's ranks for the ``NEW`` marker,
and each board member's ADR) composes this pure function.

Row furniture, none of it smoothed (ticket 06 R10 — including the 1w board, which
turns over ~half its rows nightly; the churn is honest and ``NEW`` is what makes
it readable):

- **``k/5`` breadth badge** — how many lookbacks the name currently leads
  (top-decile in). A persistence count, **not** a quality score (R11).
- **``NEW`` marker** — the name was absent from *that board* last session (R10).
- **``surge`` flag** — 1w board only: up ≥30% over the five-day window (§1's scan
  #1, spec §4.3). It rides the same raw return the board sorts on.
- **ADR** — a column that rides every row for the toggle (§4.4 / ticket 06 R8),
  never the sort key. Carried as ``None`` when it cannot be computed, not zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from .indicators import LOOKBACKS
from .ranks import TOP_DECILE, Rank

# Every board is the top 30, constant in count (ticket 06 R4). Over-determined:
# §1's "top 1–2% of gainers" is 20–39 names on the US universe, and IDX's natural
# decile is 29. Distinct-name load lands near 112 US / 88 IDX (R4 / acceptance B3).
BOARD_SIZE = 30

# The 1w board flags a name up ≥30% over the five-day window — §1's scan #1
# (spec §4.3). Inclusive at the threshold; measured 20 US / 5 IDX names, all
# already on the board (zero missed).
SURGE_THRESHOLD = 0.30


@dataclass(frozen=True)
class BoardRow:
    """One leaderboard row: a ranked name plus its furniture (spec §4.3)."""

    symbol: str
    raw_return: float
    breadth: int  # k/5 — lookbacks currently led (top-decile), a persistence count
    is_new: bool  # absent from this board last session
    surge: bool  # 1w only: up ≥30% over the five-day window
    adr: float | None  # a column for the toggle, never the sort key


@dataclass(frozen=True)
class Board:
    """One market's leaderboard for a single lookback: its top-30 rows."""

    lookback: str
    rows: list[BoardRow]


def _breadth(rows: list[Rank]) -> dict[str, int]:
    """Each name's ``k/5``: the count of lookbacks it is currently top-decile in.

    Free to compute — the same ``percentile >= TOP_DECILE`` test the decile gate
    runs (ticket 06 R11). A name absent from a lookback contributes no row there
    and so is simply not counted, which is the honest reading of ``k/5``.
    """
    counts: dict[str, int] = {}
    for r in rows:
        if r.percentile >= TOP_DECILE:
            counts[r.symbol] = counts.get(r.symbol, 0) + 1
    return counts


def _board_rows(rows: list[Rank], lookback: str) -> list[Rank]:
    """The top-30 rank rows for one lookback, highest raw return first.

    Ties break by symbol so the cut is deterministic across runs (the rank table
    carries no wall clock to break them with)."""
    ranked = sorted(
        (r for r in rows if r.lookback == lookback),
        key=lambda r: (-r.raw_return, r.symbol),
    )
    return ranked[:BOARD_SIZE]


def board_symbols(rows: list[Rank]) -> set[str]:
    """The union of the five boards' members — the names that appear on *some*
    board. The store-driven wrapper reads only these symbols' bars to compute the
    ADR column, rather than the whole universe's."""
    members: set[str] = set()
    for lookback in LOOKBACKS:
        members.update(r.symbol for r in _board_rows(rows, lookback))
    return members


def build_boards(
    rows: list[Rank],
    prev_rows: list[Rank],
    adrs: dict[str, float | None],
) -> list[Board]:
    """The five boards for a session, built from its rank rows (spec §4.3).

    ``prev_rows`` is last session's rank table — the ``NEW`` marker is per-board
    absence from it, so a name can be new on 3m and not on 1w. ``adrs`` maps each
    board member to its ADR for the toggle column; a symbol absent from the map
    carries ``None`` rather than a fabricated zero. On the very first session
    ``prev_rows`` is empty, so every row is correctly ``NEW``.
    """
    breadth = _breadth(rows)
    boards: list[Board] = []
    for lookback in LOOKBACKS:
        prev_members = {r.symbol for r in _board_rows(prev_rows, lookback)}
        boards.append(
            Board(
                lookback=lookback,
                rows=[
                    BoardRow(
                        symbol=r.symbol,
                        raw_return=r.raw_return,
                        breadth=breadth.get(r.symbol, 0),
                        is_new=r.symbol not in prev_members,
                        surge=lookback == "1w" and r.raw_return >= SURGE_THRESHOLD,
                        adr=adrs.get(r.symbol),
                    )
                    for r in _board_rows(rows, lookback)
                ],
            )
        )
    return boards
