"""Adjustment-drift detection and repair from the incremental overlap (issue #102).

#100's 20-bar overlap hands this the comparison for free: the overlapping adjusted
closes between the freshly-fetched overlap and stored history. A corporate action
rescales *all* of a symbol's history to a new adjustment basis, so the overlap's
adjusted closes disagree with the stored ones. Appending the new-basis bars on top
of the old-basis stored history would write a *seam* — a discontinuity the detector
reads as real price action (spec §3.6).

So on disagreement the pull immediately full-refetches that symbol
(``period="max"``) and *replaces* its bars, rather than appending the overlap and
waiting for the symbol's turn in #101's rolling full-depth slice. ``append_bars`` is
write-once (``ON CONFLICT DO NOTHING``, spec §7.2), so the repair needs a new,
narrowly-scoped ``replace_bars(market, symbol, bars)`` — one symbol's bars only,
never sessions and never a derived row. §7.2 exists so a *throttled* run cannot
silently rewrite good data; a rebasis means the stored bars are *wrong*, not stale.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.pipeline import OVERLAP_SESSIONS, _full_depth_today, run_market_universe
from screener.ranks import Rank
from screener.source import Instrument, Source
from screener.store import Bar, Store

NY = ZoneInfo("America/New_York")


def _weekdays_ending(last: date, n: int) -> list[date]:
    out: list[date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return list(reversed(out))


SESSIONS = _weekdays_ending(date(2026, 8, 6), 40)


def _row(session, adj, close=200.0, volume=1_000_000):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": adj, "Volume": volume,
    }


def _now_after(session: date) -> datetime:
    return datetime(session.year, session.month, session.day, 22, 10, tzinfo=NY)


def _pick(in_slice: bool, session: date, taken: set) -> str:
    i = 0
    while True:
        sym = f"S{i}"
        if sym not in taken and _full_depth_today(sym, session) is in_slice:
            return sym
        i += 1


class _BasisClient:
    """A fake client that serves one adjustment basis per fetch depth.

    ``full`` maps a symbol to the bars a full-depth (``start=None``) fetch returns;
    ``overlap`` maps it to the bars an incremental (``start=``) fetch returns
    (defaulting to ``full``). This lets a night hand the incremental overlap a
    *different* adjustment basis than the one the cold refetch would rebuild — the
    rebasis the detector exists to catch.
    """

    def __init__(self, instruments, full, *, overlap=None):
        self._instruments = instruments
        self._full = full
        self._overlap = overlap or {}
        self.calls: list[tuple[str, object]] = []

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        self.calls.append((symbol, start))
        if start is None:
            return self._full.get(symbol, [])
        return self._overlap.get(symbol, self._full.get(symbol, []))

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}

    def starts_for(self, symbol):
        return [start for sym, start in self.calls if sym == symbol]


def _source(client) -> Source:
    return Source(client, rate_per_sec=1000, max_attempts=1, sleep=lambda s: None)


def _market(symbols, adj):
    """An enumeration of common stocks plus the index, all on adjustment ``adj``."""
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    full = {"^IXIC": [_row(s, adj=100.0, close=100.0, volume=1) for s in SESSIONS]}
    for sym in symbols:
        instruments.append(
            Instrument(market="US", symbol=sym, role="candidate",
                       name=f"{sym} Inc - Common Stock")
        )
        full[sym] = [_row(s, adj=adj) for s in SESSIONS]
    return instruments, full


# -- replace_bars: the narrow write-once exception ----------------------------


def test_replace_bars_rewrites_one_symbols_bars_only(store: Store):
    store.append_bars("US", "A", [Bar(SESSIONS[0], 1, 1, 1, 1, 10.0, 100)])
    store.append_bars("US", "B", [Bar(SESSIONS[0], 1, 1, 1, 1, 20.0, 100)])

    store.replace_bars("US", "A", [Bar(SESSIONS[0], 1, 1, 1, 1, 99.0, 100)])

    assert [b.adj_close for b in store.bars("US", "A")] == [99.0]
    assert [b.adj_close for b in store.bars("US", "B")] == [20.0], "B was touched"


def test_replace_bars_touches_no_derived_rows(store: Store):
    # A repair is bars-only: ranks/detections/digests computed on the old basis
    # are left as-is (§3.5's ratio invariance makes recomputing them immaterial).
    store.append_bars("US", "A", [Bar(SESSIONS[0], 1, 1, 1, 1, 10.0, 100)])
    store.append_universe("US", SESSIONS[0], ["A"])
    store.append_ranks("US", SESSIONS[0], [Rank("A", "1M", 0.9, 0.5)])
    store.append_digest_breaks("US", SESSIONS[0], ["A"])

    store.replace_bars("US", "A", [Bar(SESSIONS[0], 1, 1, 1, 1, 99.0, 100)])

    assert store.universe("US", SESSIONS[0]) == ["A"]
    assert [r.percentile for r in store.ranks("US", SESSIONS[0])] == [0.9]
    assert store.digest_breaks("US", SESSIONS[0]) == ["A"]


# -- detection and repair end to end ------------------------------------------


def test_an_overlap_mismatch_is_detected_and_repaired_end_to_end(
    store: Store, tmp_path
):
    drift = _pick(False, SESSIONS[-1], set())  # out of tonight's full-depth slice
    others = [s for s in (_pick(False, SESSIONS[-1], {drift}),)]
    symbols = [drift, *others]

    # Night one seeds every symbol on basis A (adj == 200).
    instruments_a, full_a = _market(symbols, adj=200.0)
    run_market_universe(
        store, _source(_BasisClient(instruments_a, full_a)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )
    assert store.bars("US", drift)[0].adj_close == 200.0

    # Night two: a corporate action rebased ``drift`` to basis B (adj == 100). Its
    # incremental overlap now disagrees with stored history; the cold refetch
    # rebuilds the whole series on basis B.
    instruments_b, full_b = _market(symbols, adj=100.0)
    overlap_b = {drift: [_row(s, adj=100.0) for s in SESSIONS[-OVERLAP_SESSIONS:]]}
    client = _BasisClient(instruments_b, full_b, overlap=overlap_b)
    record = run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert record.status == "published"
    # The overlap mismatch triggered a full-depth refetch of ``drift`` only, on
    # top of its incremental fetch — its whole history is now on basis B, no seam.
    assert None in client.starts_for(drift), "no full-depth repair refetch happened"
    assert all(b.adj_close == 100.0 for b in store.bars("US", drift)), "seam remains"


def test_a_matching_overlap_does_not_refetch(store: Store, tmp_path):
    # No rebasis, no seam: the overlap matches stored history, so the symbol is
    # fetched incrementally once and never full-refetched.
    keep = _pick(False, SESSIONS[-1], set())
    instruments, full = _market([keep], adj=200.0)
    run_market_universe(
        store, _source(_BasisClient(instruments, full)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    overlap = {keep: [_row(s, adj=200.0) for s in SESSIONS[-OVERLAP_SESSIONS:]]}
    client = _BasisClient(instruments, full, overlap=overlap)
    run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert None not in client.starts_for(keep), "a matching overlap was refetched"


def test_a_repair_does_not_recompute_a_prior_sessions_derived_rows(
    store: Store, tmp_path
):
    # A repair changes bars going forward; the ranks/detections/digests of already
    # -computed sessions stay exactly as they were (asserted, not left to omission).
    drift = _pick(False, SESSIONS[-1], set())
    instruments_a, full_a = _market([drift], adj=200.0)
    run_market_universe(
        store, _source(_BasisClient(instruments_a, full_a)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )
    before = store.ranks("US", SESSIONS[-2])
    assert before, "night one computed no ranks to compare against"

    instruments_b, full_b = _market([drift], adj=100.0)
    overlap_b = {drift: [_row(s, adj=100.0) for s in SESSIONS[-OVERLAP_SESSIONS:]]}
    run_market_universe(
        store, _source(_BasisClient(instruments_b, full_b, overlap=overlap_b)),
        "US", SESSIONS[-1], now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    after = store.ranks("US", SESSIONS[-2])
    assert after == before, "the repair recomputed a prior session's ranks"
