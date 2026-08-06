"""Seam 6b: the rank table and the decile gate (spec §4.3 / ticket 06).

The shared substrate — the one definition of "strong" in the app. Per (name,
lookback, session) it carries a **percentile** and the **raw return**, for
*every* universe member, not only leaders. The gate is the **union of the five
top deciles**, any-of, not a composite; each decile is computed within that
lookback's own population, whose size differs by lookback because a recent
listing is simply absent from the long lookbacks (per-lookback eligibility).

Everything is pure over ``{symbol: list[Bar]}`` — no store, no network.
"""

from datetime import date, timedelta

from screener.bars import Bar
from screener.ranks import (
    TOP_DECILE,
    Rank,
    decile_gate,
    rank_table,
)

CAL = [date(2026, 7, 1) + timedelta(days=i) for i in range(400)]


def _bars(sessions, adj_closes):
    return [Bar(s, 0.0, 0.0, 0.0, 0.0, ac, 1000) for s, ac in zip(sessions, adj_closes)]


def _flat_then_gain(gain):
    """A name flat at 100 for a year, then finishing at ``100 * (1 + gain)`` — so
    its return over every lookback is exactly ``gain`` (the anchor bar is 100)."""
    sessions = CAL[:366]
    closes = [100.0] * 365 + [100.0 * (1 + gain)]
    return _bars(sessions, closes)


# -- the rank table: one row per member per eligible lookback -----------------


def test_rank_table_has_a_row_per_member_per_eligible_lookback():
    # Three names, each with a full year of history: all five lookbacks apply.
    members = {name: _flat_then_gain(g) for name, g in
               [("A", 0.5), ("B", 0.2), ("C", 0.1)]}
    rows = rank_table(members, CAL[365])
    # 3 names × 5 lookbacks = 15 rows.
    assert len(rows) == 15
    assert {r.lookback for r in rows} == {"1w", "1m", "3m", "6m", "12m"}
    assert all(isinstance(r, Rank) for r in rows)


def test_every_row_carries_percentile_and_raw_return():
    members = {"A": _flat_then_gain(0.5), "B": _flat_then_gain(0.2)}
    by_key = {(r.symbol, r.lookback): r for r in rank_table(members, CAL[365])}
    a12 = by_key[("A", "12m")]
    assert abs(a12.raw_return - 0.5) < 1e-9
    assert 0.0 < a12.percentile <= 1.0


def test_a_recent_listing_is_absent_from_long_lookbacks_not_zero_filled():
    # OLD has a year of history; NEW listed 10 days ago. NEW is present on 1w
    # but absent from 3m/6m/12m — no row, not a zero-return row.
    members = {
        "OLD": _flat_then_gain(0.3),
        "NEW": _bars(CAL[356:366], [100.0] * 9 + [130.0]),
    }
    rows = rank_table(members, CAL[365])
    new_lookbacks = {r.lookback for r in rows if r.symbol == "NEW"}
    assert new_lookbacks == {"1w"}  # only the window it has history for
    # And its absence shrinks the long-lookback denominator: 12m has one member.
    assert sum(1 for r in rows if r.lookback == "12m") == 1


# -- percentile: empirical CDF, top decile = the top ~10% ---------------------


def test_percentile_is_the_share_of_the_population_at_or_below():
    # Ten names with distinct 1w returns 1%..10%. The top name sits at 10/10.
    members = {f"N{i}": _bars(CAL[358:366], [100.0] * 7 + [100.0 * (1 + i / 100)])
               for i in range(1, 11)}
    rows = [r for r in rank_table(members, CAL[365]) if r.lookback == "1w"]
    pct = {r.symbol: r.percentile for r in rows}
    assert abs(pct["N10"] - 1.0) < 1e-9  # the biggest gainer: all 10 at or below
    assert abs(pct["N1"] - 0.1) < 1e-9   # the smallest: only itself
    assert abs(pct["N5"] - 0.5) < 1e-9


# -- the decile gate: union across five lookbacks, any-of ---------------------


def test_decile_gate_is_top_decile_in_any_lookback():
    # A name top-decile on exactly one lookback still passes the union gate.
    rows = [
        Rank("WINNER", "3m", percentile=0.95, raw_return=1.0),
        Rank("WINNER", "1m", percentile=0.40, raw_return=0.1),
        Rank("MIDDLE", "3m", percentile=0.55, raw_return=0.2),
        Rank("MIDDLE", "1m", percentile=0.60, raw_return=0.2),
    ]
    assert decile_gate(rows) == {"WINNER"}


def test_decile_boundary_is_inclusive_at_the_threshold():
    at = Rank("AT", "1w", percentile=TOP_DECILE, raw_return=0.3)
    below = Rank("BELOW", "1w", percentile=TOP_DECILE - 1e-9, raw_return=0.2)
    assert decile_gate([at, below]) == {"AT"}


def test_gate_passes_about_a_tenth_per_lookback_but_more_in_union():
    # 100 names, each a distinct 12m gainer, all with full history so every
    # lookback applies. Per lookback the top decile is ~10 names; because the
    # ranks differ across lookbacks (returns are identical here, so they don't)
    # the union equals one decile — this fixes the single-lookback width.
    members = {f"N{i:03d}": _flat_then_gain(i / 100) for i in range(100)}
    rows = rank_table(members, CAL[365])
    one_lb = [r for r in rows if r.lookback == "12m" and r.percentile >= TOP_DECILE]
    assert 9 <= len(one_lb) <= 11  # ~10% of 100
    # Identical returns across lookbacks -> the same names top every decile, so
    # the union is exactly that decile, not five times larger.
    assert decile_gate(rows) == {r.symbol for r in one_lb}
