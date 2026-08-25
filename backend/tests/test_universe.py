"""Seam 5: the tradeable universe — liquidity, instrument type, listing age,
density and hysteresis (spec §4.1, §3.4 rules 3/6, ticket 05 D2–D13).

Universe = **liquidity + instrument type + listing age**, and nothing else:

- **Liquidity floor** — the *median* of unadjusted ``close × volume`` over the
  trailing 20 traded bars must clear Rp 1B (IDX) / $20M (US). A median, so one
  block trade cannot lift an illiquid name over the bar (D2).
- **Instrument type** — common stock only, excluded by security-name pattern
  and, for the preferreds the name hides, by the "$" in the symbol (#105);
  **ADRs are kept** (D13). The only non-behavioural rule in the system.
- **Listing age** — ≥ 20 non-phantom bars, the minimum for the median and ADR
  to exist (D5).
- **Density gate** — ≥ 16 of the market's last 20 sessions non-phantom for the
  name *and* its latest bar within 3 sessions of the market's latest. Doubles as
  suspension detection (§3.4 rule 3).
- **Hysteresis** — a name enters at ≥ 1.0× the floor and leaves only below 0.8×,
  so decile denominators do not churn nightly with no price action behind them
  (D11).
- **Sticky membership** — a name whose fetch failed carries yesterday's
  classification; removal needs positive evidence (§3.4 rule 6).

The store is seeded with clean bars (Seam 4 already proved ingest), the source
boundary is faked, and no test touches the network.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.bars import Bar
from screener.labels import Label
from screener.pipeline import run_market_universe
from screener.source import Instrument, Source
from screener.store import Store
from screener.universe import (
    LIQUIDITY_FLOOR,
    Candidate,
    classify,
    is_common_stock,
    median_dollar_volume,
    passes_density_gate,
    rebuild_universe,
)

# A run of consecutive trading days to build a market calendar from.
CAL = [date(2026, 7, 1) + timedelta(days=i) for i in range(40)]


def _bars(sessions, *, close=100.0, volume=1000, adj_close=None):
    """Clean bars (already phantom-dropped) at the given sessions."""
    return [
        Bar(s, close, close + 1, close - 1, close, adj_close or close, volume)
        for s in sessions
    ]


# -- median dollar volume: median, not mean (D2) ------------------------------


def test_median_dollar_volume_ignores_a_single_block_trade():
    # 19 quiet bars at Rp 200M, one Rp 40B block. The 20-day MEAN clears Rp 1B;
    # the median does not — the name has not become tradeable.
    bars = _bars(CAL[:19], close=200.0, volume=1_000_000)  # 200M each
    bars.append(Bar(CAL[19], 40000.0, 40001.0, 39999.0, 40000.0, 40000.0, 1_000_000))
    mean = sum(b.dollar_volume for b in bars) / len(bars)
    assert mean >= 1_000_000_000  # the mean is fooled
    assert median_dollar_volume(bars) < 1_000_000_000  # the median is not


def test_median_dollar_volume_uses_only_the_trailing_twenty():
    # 30 bars; the trailing 20 are all Rp 2B, the oldest 10 are noise.
    old = _bars(CAL[:10], close=1.0, volume=1)
    recent = _bars(CAL[10:30], close=2000.0, volume=1_000_000)  # 2B each
    assert median_dollar_volume(old + recent) == 2_000_000_000


# -- instrument type: common stock only, ADRs kept (D13) ----------------------


def test_common_stock_kept_and_excluded_classes_dropped():
    assert is_common_stock("AAPL", "Apple Inc. - Common Stock")
    assert is_common_stock("BRK.B", "Berkshire Hathaway")
    assert is_common_stock("BBCA.JK", "")  # IDX carries no name; the screener guarantees equity
    for name in [
        "Acme Corp Warrant",
        "Acme Corp Rights",
        "Acme Acquisition Units",
        "Acme 5.5% Notes due 2030",
        "Acme Series A Preferred Stock",
        "Acme Pfd Series B",
        # "Preference" is the same instrument as "Preferred" (#92): the live US
        # enumeration carries TRTN$A under this exact wording and nothing else in
        # the name marks it as anything but common stock.
        "Triton International Limited 8.50% Series A Cumulative Redeemable "
        "Perpetual Preference Shares",
        "Acme Holdings plc 6% Preference Share",
        "Acme Capital Trust",
        "Acme Income Fund",
    ]:
        assert not is_common_stock("ACME", name), name


def test_preferreds_are_excluded_on_the_symbol_when_the_name_hides_them():
    # Issue #105. Nasdaq writes a preferred or depositary series with "$", and
    # the names carry none of the stems the pattern above matches — "7.125%
    # Series H" and "Depositary Shares" both read as common stock. Nine of these
    # sat in the US gate's denominator every night, fetched and silent. The
    # symbol says what the name does not.
    hidden = {
        "DBRG$H": "DigitalBridge Group, Inc. 7.125% Series H",
        "DBRG$I": "DigitalBridge Group, Inc. 7.15% Series I",
        "DBRG$J": "DigitalBridge Group, Inc. 7.125% Series J",
        "EQH$A": "Equitable Holdings, Inc. Depositary Shares",
        "MET$E": "MetLife, Inc. Depositary Shares",
        "MS$F": "Morgan Stanley Dep Shs Rpstg 1/1000th Int Prd Ser F Fxd to Flag",
        "NLY$F": "Annaly Capital Management Inc 6.95% Series F",
        "STT$G": "State Street Corporation Depositary shares",
        "TFC$I": "Truist Financial Corporation Depositary Shares",
    }
    assert len(hidden) == 9
    for symbol, name in hidden.items():
        # The name alone reads as common stock — that is the defect.
        assert is_common_stock("PLAIN", name), f"{symbol}: name-based rule misses this"
        assert not is_common_stock(symbol, name), symbol


def test_a_dotted_share_class_is_still_common_stock():
    # The other half of #105: BRK.B is ordinary common stock and belongs in the
    # universe. Only the "$" form is an instrument-type exclusion — a dot is a
    # share class, and the dot/dash mismatch is a wire-format problem solved at
    # the fetch boundary (``provider_symbol``), never a universe one.
    for symbol in ["BRK.A", "BRK.B", "BF.B", "HEI.A", "MOG.A", "TAP.A", "UHAL.B", "MKC.V",
                   "AGM.A", "CIG.C", "CRD.B", "GEF.B", "LEN.B", "WSO.B"]:
        assert is_common_stock(symbol, "Corp Common Stock"), symbol


def test_a_market_index_is_not_common_stock():
    # Issue #162. The index is a benchmark, never a rankable name, and the "^"
    # prefix is the only mark it carries: it has no "$", and where the symbol is
    # read without a security name — the replay store keeps bars, not listings —
    # an empty name read as common stock let ``^IXIC`` compete in the replayed
    # field. The live path is protected by the role filter upstream; this is the
    # second layer, and the only one the replay can reach.
    for symbol in ["^IXIC", "^JKSE", "^GSPC"]:
        assert not is_common_stock(symbol, ""), symbol
        assert not is_common_stock(symbol, "NASDAQ Composite Index"), symbol


def test_the_twelve_named_adrs_survive_instrument_exclusion():
    # The D13 defect check: an earlier pattern matching "Depositary Sh" would
    # have deleted the most liquid ADRs the method exists to trade.
    adrs = {
        "BABA": "Alibaba Group Holding Limited American Depositary Shares",
        "ARM": "Arm Holdings plc American Depositary Shares",
        "SE": "Sea Limited American Depositary Shares",
        "PDD": "PDD Holdings Inc. American Depositary Shares",
        "NOK": "Nokia Corporation Sponsored American Depositary Shares",
        "SHEL": "Shell PLC American Depositary Shares",
        "JD": "JD.com Inc. American Depositary Shares",
        "VALE": "Vale S.A. American Depositary Shares",
        "UL": "Unilever PLC American Depositary Shares",
        "INFY": "Infosys Limited American Depositary Shares",
        "ARGX": "argenx SE American Depositary Shares",
        "SIMO": "Silicon Motion Technology Corporation American Depositary Shares",
    }
    for symbol, name in adrs.items():
        assert is_common_stock(symbol, name), symbol


# -- density gate (§3.4 rule 3) -----------------------------------------------


def test_density_gate_needs_sixteen_of_the_last_twenty():
    market = CAL[:20]
    # traded 16 of the last 20 (4 gaps), latest bar is the market's latest -> ok
    traded16 = {market[i] for i in range(20) if i not in (0, 5, 10, 15)}
    assert passes_density_gate(traded16, market)
    # 15 of 20 (5 gaps), still traded on the latest session -> fails on count
    traded15 = {market[i] for i in range(20) if i not in (0, 5, 10, 14, 15)}
    assert len(traded15) == 15
    assert not passes_density_gate(traded15, market)


def test_density_gate_flags_a_stale_name_as_suspended():
    market = CAL[:25]
    # traded densely but nothing in the last 4 sessions -> suspension
    stale = set(market[:21])  # last bar is market[20], 4 sessions behind latest
    assert not passes_density_gate(stale, market)
    # one session closer is within 3 of the market's latest -> clears recency
    fresh = set(market[:22])  # last bar market[21], 3 sessions behind latest
    assert passes_density_gate(fresh, market)


# -- classify: the whole stack, with hysteresis and stickiness ----------------


def _candidate(symbol, sessions, *, name="Corp - Common Stock", close=2000.0,
               volume=1_000_000, resolved=True):
    return Candidate(symbol=symbol, name=name, resolved=resolved,
                     bars=_bars(sessions, close=close, volume=volume))


def test_a_liquid_common_stock_with_history_enters():
    market = CAL[:25]
    liquid = _candidate("AAA", market[:25], close=2000.0, volume=1_000_000)  # 2B/day
    members = classify("IDX", [liquid], market, prior_members=set())
    assert members == ["AAA"]


def test_hysteresis_holds_a_member_between_0_8_and_1_0x():
    market = CAL[:25]
    floor = LIQUIDITY_FLOOR["IDX"]
    # median dollar volume = 0.9x the floor: below entry, above the 0.8x exit.
    px = 900.0  # 900 * 1_000_000 = 900M = 0.9 * 1B
    band = _candidate("BND", market[:25], close=px, volume=1_000_000)
    assert 0.8 * floor <= median_dollar_volume(band.bars) < floor
    # not a member yesterday -> stays out (needs >= 1.0x to enter)
    assert classify("IDX", [band], market, prior_members=set()) == []
    # a member yesterday -> stays in (only leaves below 0.8x)
    assert classify("IDX", [band], market, prior_members={"BND"}) == ["BND"]


def test_a_member_falling_below_0_8x_leaves():
    market = CAL[:25]
    floor = LIQUIDITY_FLOOR["IDX"]
    weak = _candidate("WK", market[:25], close=700.0, volume=1_000_000)  # 0.7x
    assert median_dollar_volume(weak.bars) < 0.8 * floor
    assert classify("IDX", [weak], market, prior_members={"WK"}) == []


def test_a_young_listing_under_twenty_bars_is_not_eligible():
    market = CAL[:25]
    young = _candidate("IPO", market[:19], close=5000.0, volume=1_000_000)  # 5B/day
    assert classify("IDX", [young], market, prior_members=set()) == []


def test_a_non_common_stock_never_enters_even_if_liquid():
    market = CAL[:25]
    warrant = _candidate("WT", market[:25], name="Acme Corp Warrant",
                         close=9000.0, volume=1_000_000)
    assert classify("IDX", [warrant], market, prior_members=set()) == []


def test_an_unresolved_name_carries_yesterdays_classification():
    market = CAL[:25]
    # No fresh bars at all; fetch failed. Sticky: prior membership decides.
    gone = Candidate(symbol="OLD", name="Corp - Common Stock", resolved=False, bars=[])
    assert classify("IDX", [gone], market, prior_members={"OLD"}) == ["OLD"]
    assert classify("IDX", [gone], market, prior_members=set()) == []


def test_a_suspended_member_leaves_on_positive_evidence():
    market = CAL[:25]
    # Real bars, liquid, common stock — but not traded in the last 3 sessions.
    suspended = _candidate("SUS", market[:21], close=5000.0, volume=1_000_000)
    # was a member; density failure is positive evidence, so it leaves
    assert classify("IDX", [suspended], market, prior_members={"SUS"}) == []


# -- rebuild_universe: reads the store, writes one row per name per session ----


def test_rebuild_universe_writes_membership_rows(store: Store):
    market_sessions = CAL[:25]
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="LIQ", role="candidate", name="Liquid Tbk"),
        Instrument(market="IDX", symbol="THIN", role="candidate", name="Thin Tbk"),
    ]
    # LIQ clears the floor; THIN does not.
    store.append_bars("IDX", "^JKSE", _bars(market_sessions, close=100.0, volume=1))
    store.append_bars("IDX", "LIQ", _bars(market_sessions, close=2000.0, volume=1_000_000))
    store.append_bars("IDX", "THIN", _bars(market_sessions, close=100.0, volume=1_000))

    members = rebuild_universe(
        store, "IDX", date(2026, 8, 4), instruments=instruments, unresolved=set()
    )

    assert members == ["LIQ"]  # THIN below floor, index is a reference
    assert store.universe("IDX", date(2026, 8, 4)) == ["LIQ"]


def test_rebuild_universe_is_sticky_across_sessions(store: Store):
    m1 = CAL[:25]
    instruments = [
        Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
    ]
    store.append_bars("IDX", "AAA", _bars(m1, close=2000.0, volume=1_000_000))
    rebuild_universe(store, "IDX", date(2026, 8, 4), instruments=instruments, unresolved=set())
    assert store.universe("IDX", date(2026, 8, 4)) == ["AAA"]

    # Next session AAA's fetch fails (unresolved). Sticky: it keeps membership.
    members = rebuild_universe(
        store, "IDX", date(2026, 8, 5), instruments=instruments, unresolved={"AAA"}
    )
    assert members == ["AAA"]
    assert store.universe("IDX", date(2026, 8, 5)) == ["AAA"]


# -- end to end: source -> ingest -> rebuild -> run record --------------------

WIB = ZoneInfo("Asia/Jakarta")


def _row(session, *, close, volume):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


class FakeBarClient:
    """Fakes enumerate + fetch (+ fetch_info), keyed by symbol."""

    def __init__(self, instruments, bars_by_symbol, info_by_symbol=None):
        self._instruments = instruments
        self._bars = bars_by_symbol
        self._info = info_by_symbol or {}

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol, start=None):
        return self._bars.get(symbol, [])

    def fetch_info(self, symbol):
        return self._info.get(symbol, {})


def test_run_market_universe_ingests_and_builds_a_liquid_universe(store: Store, tmp_path):
    # A calendar of 25 final IDX sessions (well past the finality margin).
    sessions = CAL[:25]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)  # long after the last session
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="LIQ", role="candidate", name="Liquid Tbk"),
        Instrument(market="IDX", symbol="THIN", role="candidate", name="Thin Tbk"),
    ]
    bars = {
        "^JKSE": [_row(s, close=100.0, volume=1) for s in sessions],
        "LIQ": [_row(s, close=2000.0, volume=1_000_000) for s in sessions],  # 2B/day
        "THIN": [_row(s, close=100.0, volume=1_000) for s in sessions],  # 100k/day
    }
    info = {"LIQ": {"sector": "Energy", "industry": "Coal"}}
    source = Source(FakeBarClient({"IDX": instruments}, bars, info),
                    rate_per_sec=1000, sleep=lambda s: None)

    record = run_market_universe(store, source, "IDX", date(2026, 8, 20), now=now, digests_dir=tmp_path)

    assert record.status == "published"
    assert record.symbols_enumerated == 2  # two candidates; the index excluded
    assert record.symbols_resolved == 2
    # Only the liquid common stock is a member; the index is a reference.
    assert store.universe("IDX", date(2026, 8, 20)) == ["LIQ"]
    # The new member's labels were fetched and cached as part of the run (§3.3);
    # THIN never entered the universe, so it was never a label fetch.
    assert store.label("IDX", "LIQ") == Label("LIQ", "Energy", "Coal", date(2026, 8, 20))
    assert store.label("IDX", "THIN") is None
    # Bars for all instruments (index included) were ingested on the way.
    assert len(store.bars("IDX", "^JKSE")) == 25


def test_run_market_universe_excludes_instrument_type_listings_from_the_gate(store: Store, tmp_path):
    # Issue #90: a US market takes the whole listing file, so ~a quarter of its
    # candidates are warrants/rights/units/preferreds. The provider serves them
    # no history, so they come back as silence (unresolved), and the universe
    # throws them out on their name anyway — but the instrument-type rule runs
    # *after* resolution. Left in the completeness denominator they hold a
    # complete common-equity pull under the floor forever. They must sit outside
    # the gate, so a full pull of the tradeable names publishes.
    sessions = CAL[:25]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    # 20 common stocks that all resolve.
    instruments += [
        Instrument(market="US", symbol=f"S{i}", role="candidate", name=f"Corp {i} - Common Stock")
        for i in range(20)
    ]
    # 10 warrants the provider serves no history for — pure silence.
    instruments += [
        Instrument(market="US", symbol=f"W{i}", role="candidate", name=f"Corp {i} Warrant")
        for i in range(10)
    ]
    bars = {"^IXIC": [_row(s, close=100.0, volume=1) for s in sessions]}
    bars.update({f"S{i}": [_row(s, close=2000.0, volume=1_000_000) for s in sessions] for i in range(20)})
    source = Source(FakeBarClient({"US": instruments}, bars), rate_per_sec=1000, sleep=lambda s: None)

    record = run_market_universe(store, source, "US", date(2026, 8, 20), now=now, digests_dir=tmp_path)

    assert record is not None
    assert record.status == "published"
    # The ten warrants stayed out of the denominator; every tradeable name resolved.
    assert record.symbols_enumerated == 20
    assert record.symbols_resolved == 20
    assert store.universe("US", date(2026, 8, 20)) == sorted(f"S{i}" for i in range(20))
