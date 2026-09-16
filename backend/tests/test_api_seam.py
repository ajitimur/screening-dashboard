"""Seam 2: hit an endpoint via TestClient against a fixture store.

This is the API-contract seam every read-endpoint ticket writes its tests
against (spec §7.5). The app is constructed against an in-memory fixture store,
so the payload is asserted without touching the on-disk file.
"""

import pytest
from fastapi.testclient import TestClient

from screener.app import create_app
from screener.score import RUBRIC_VERSION
from screener.store import Store


def client_for(store: Store) -> TestClient:
    return TestClient(create_app(store=store))


def test_runs_endpoint_returns_as_of_session(seeded_store: Store):
    client = client_for(seeded_store)

    resp = client.get("/api/runs/IDX")
    assert resp.status_code == 200
    body = resp.json()

    assert body["market"] == "IDX"
    assert body["latest"]["session"] == "2026-08-04"
    assert body["latest"]["status"] == "published"
    assert [r["session"] for r in body["runs"]] == ["2026-08-04", "2026-08-03"]


def test_runs_endpoint_empty_state_when_no_run(store: Store):
    # No run has published yet — the tab shows an explicit empty state.
    body = client_for(store).get("/api/runs/US").json()
    assert body["latest"] is None
    assert body["runs"] == []
    assert body["universe_size"] is None


def test_runs_endpoint_surfaces_tonights_universe_size(store: Store):
    # The market tab shows tonight's universe size (ticket 31 acceptance).
    from datetime import date, datetime

    from screener.pipeline import run_market

    run_market(
        store, "IDX", date(2026, 8, 4),
        enumerated=["AAA", "BBB", "CCC"], resolved=["AAA", "BBB", "CCC"],
        now=datetime(2026, 8, 4, 19, 30),
    )
    body = client_for(store).get("/api/runs/IDX").json()
    assert body["universe_size"] == 3


def test_market_is_case_insensitive(seeded_store: Store):
    assert client_for(seeded_store).get("/api/runs/idx").json()["latest"]["session"] == "2026-08-04"


def test_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/runs/LSE").status_code == 404


# -- /api/regime/{market} (ticket 36, spec §4.9) ------------------------------


def _regime_store() -> Store:
    """A store with a friendly IDX index and a universe of two members — one
    riding above rising MAs, one flat — plus a published run."""
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.pipeline import run_market

    store = Store.memory()
    cal = [date(2026, 6, 1) + timedelta(days=i) for i in range(30)]
    session = cal[-1]

    def bars(adj):
        return [Bar(s, c, c + 1, c - 1, c, c, 1000) for s, c in zip(cal, adj)]

    store.append_bars("IDX", "^JKSE", bars([100.0 + i for i in range(30)]))  # rising
    store.append_bars("IDX", "UP", bars([100.0 + i for i in range(30)]))     # friendly
    store.append_bars("IDX", "FLAT", bars([100.0] * 30))                     # not
    # run_market writes the universe (= the resolved members) as it publishes.
    run_market(
        store, "IDX", session,
        enumerated=["UP", "FLAT"], resolved=["UP", "FLAT"],
        now=datetime(2026, 6, 30, 19, 30),
    )
    return store


def test_regime_endpoint_reports_state_posture_breadth_and_session():
    store = _regime_store()
    try:
        body = client_for(store).get("/api/regime/IDX").json()
        assert body["market"] == "IDX"
        assert body["session"] == "2026-06-30"
        assert body["state"] == "FRIENDLY"          # the index is in a clean uptrend
        assert body["posture"] == "full size"       # words, not a number
        assert body["breadth"] == 0.5               # 1 of 2 members above rising MAs
    finally:
        store.close()


def test_regime_endpoint_is_empty_when_no_run_published(store: Store):
    body = client_for(store).get("/api/regime/US").json()
    assert body == {
        "market": "US", "session": None, "state": None,
        "posture": None, "breadth": None,
    }


def test_regime_state_undefined_below_the_warmup(store: Store):
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.pipeline import run_market

    cal = [date(2026, 6, 1) + timedelta(days=i) for i in range(10)]  # < 25 bars
    session = cal[-1]
    store.append_bars("IDX", "^JKSE", [Bar(s, 100.0, 101.0, 99.0, 100.0, 100.0, 1000) for s in cal])
    run_market(
        store, "IDX", session, enumerated=["AAA"], resolved=["AAA"],
        now=datetime(2026, 6, 10, 19, 30),
    )
    body = client_for(store).get("/api/regime/IDX").json()
    assert body["session"] == "2026-06-10"
    assert body["state"] is None        # undefined, not defaulted
    assert body["posture"] is None      # an undefined regime advises nothing


def test_regime_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/regime/LSE").status_code == 404


# -- /api/volatility/{market} (issue #224, spec §4.10) ------------------------
#
# The primary seam for the volatility state: everything the reading is — the
# realized-vol math, the era-bounded percentile, the warm-up, the nine-cell
# posture — is asserted here, through the endpoint, over a seeded store. The
# state is the regime's sibling, so it gets the regime's own kind of tests
# rather than a second set below the API.

# A market index is generated from two schedules, one per coordinate the banner
# shows: ``drifts`` sets the *trend* (what the regime reads) and ``amps`` the
# swing size (what the volatility reading measures). They are independent knobs
# on the same series, which is what makes a trend×volatility cell constructible.
#
# The percentile is a rank against the series' own past, so the vol coordinate is
# set by where the recent swing sits relative to the older one: a tail quieter
# than its history ranks low (CALM), a tail that is strictly the most violent
# stretch ranks at the top (STRESSED).
_BARS = 111  # 21 for the first vol reading + 90 ranked readings

_TREND = {
    "FRIENDLY": [0.006] * _BARS,
    # Up, then a gentle roll-over: neither strictly falling MAs nor a close above
    # both rising ones, which is what the residual state is.
    "CHOPPY": [0.006] * (_BARS - 20) + [0.006 - 0.0005 * i for i in range(1, 21)],
    "HOSTILE": [-0.006] * _BARS,
}
_SWING = {
    "CALM": [0.02] * 80 + [0.004] * (_BARS - 80),       # quieter than its history
    "ELEVATED": [0.002] * 76 + [0.02] * 20 + [0.008] * 15,  # mid-pack
    "STRESSED": [0.002] * 86 + [0.002 + 0.002 * i for i in range(1, 26)],  # a fresh high
}

# §4.10's posture matrix, spelled out here as the contract rather than imported:
# a test that reads the sentences out of the module it is checking would pass
# through any rewording of them.
_POSTURE_CELLS = {
    ("FRIENDLY", "CALM"): "full size — quiet tape",
    ("FRIENDLY", "ELEVATED"): "full size — vol building, honor stops",
    ("FRIENDLY", "STRESSED"): (
        "full size, but vol is stressed — expect wide swings, size stops accordingly"
    ),
    ("CHOPPY", "CALM"): "reduced — directionless but quiet",
    ("CHOPPY", "ELEVATED"): "reduced — directionless and vol building",
    ("CHOPPY", "STRESSED"): "reduced — chop with stressed vol is whipsaw territory",
    ("HOSTILE", "CALM"): "sit out — downtrend, even quiet",
    ("HOSTILE", "ELEVATED"): "sit out — downtrend with vol building",
    ("HOSTILE", "STRESSED"): (
        "sit out — downtrend in stressed vol, worst cell on the board"
    ),
}


def _index_bars(calendar, drifts, amps):
    """Bars whose returns carry ``drifts`` as trend and ``amps`` as swing size."""
    from screener.bars import Bar

    out, close = [], 100.0
    for i, (session, drift, amp) in enumerate(zip(calendar, drifts, amps)):
        close *= 1 + drift + (amp if i % 2 == 0 else -amp)
        out.append(Bar(session, close, close * 1.01, close * 0.99, close, close, 1000))
    return out


def _volatility_store(
    market="US", *, trend="FRIENDLY", swing="STRESSED", bars=_BARS, second_leg=None,
) -> Store:
    """A store with a published run and an index shaped to one trend×vol cell."""
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.source import MARKET_INDEX, SECOND_LEG

    store = Store.memory()
    calendar = [date(2026, 3, 1) + timedelta(days=i) for i in range(bars)]
    session = calendar[-1]
    store.append_bars(
        market,
        MARKET_INDEX[market],
        _index_bars(calendar, _TREND[trend], _SWING[swing]),
    )
    if second_leg is not None:
        store.append_bars(
            market,
            SECOND_LEG[market],
            [Bar(s, v, v, v, v, v, 0) for s, v in zip(calendar, second_leg)],
        )
    store.append_run(
        market, session, status="published", symbols_enumerated=1, symbols_resolved=1,
        created_at=datetime(2026, 6, 19, 22, 10),
    )
    return store


def test_volatility_endpoint_reports_state_percentile_sample_and_second_leg():
    # The index's most violent stretch is right now, so it ranks at the top of
    # its own three-year history: STRESSED, with the denominator on show.
    store = _volatility_store(second_leg=[18.4] * _BARS)
    try:
        body = client_for(store).get("/api/volatility/US").json()
        assert body["market"] == "US"
        assert body["session"] == "2026-06-19"
        assert body["state"] == "STRESSED"
        assert body["sample_size"] == 90          # displayed, never hidden
        assert body["percentile"] > 80            # the STRESSED edge
        assert body["index_vol"] > 0
        assert body["era_start"] is None          # US ranks on the rolling window
        assert body["second_leg"] == 18.4         # VIX, raw and unbucketed
        assert body["second_leg_symbol"] == "^VIX"
    finally:
        store.close()


@pytest.mark.parametrize(("trend", "vol"), sorted(_POSTURE_CELLS))
def test_every_trend_by_volatility_cell_carries_its_own_posture(trend, vol):
    """Nine cells, nine sentences (spec §4.10).

    The point of the matrix: "full size" in stressed volatility must never read
    as an unqualified go-ahead, which a three-word posture beside a state word
    cannot say.
    """
    store = _volatility_store(trend=trend, swing=vol)
    try:
        body = client_for(store).get("/api/volatility/US").json()
        assert body["state"] == vol
        assert body["posture"] == _POSTURE_CELLS[(trend, vol)]
        # The regime's own three-word posture is untouched on its own endpoint.
        assert client_for(store).get("/api/regime/US").json()["state"] == trend
    finally:
        store.close()


def test_volatility_state_is_undefined_below_the_warmup_but_the_reading_shows():
    # 80 bars leave 59 readings — one short of the 60-reading warm-up.
    store = _volatility_store(bars=80)
    try:
        body = client_for(store).get("/api/volatility/US").json()
        assert body["session"] == "2026-05-19"
        assert body["state"] is None        # undefined, not defaulted
        assert body["posture"] is None      # an undefined state advises nothing
        # The reading itself is still reported: the sample size is exactly what
        # makes "warming up" legible rather than a blank.
        assert body["sample_size"] == 59
        assert body["index_vol"] > 0
    finally:
        store.close()


def test_volatility_endpoint_is_empty_when_no_run_published(store: Store):
    body = client_for(store).get("/api/volatility/US").json()
    assert body == {
        "market": "US", "session": None, "state": None, "posture": None,
        "index_vol": None, "percentile": None, "sample_size": None,
        "era_start": None, "second_leg": None, "second_leg_symbol": "^VIX",
    }


def test_idx_percentile_ranks_within_the_current_arb_era_only():
    """IDX ranks within-era, because the bands censor the eras differently.

    The history here straddles the 2025-04-08 decree (Kep-00003/BEI/04-2025), and
    only the sessions on or after it count toward the rank — a percentile across
    the boundary would compare observations censored by different amounts
    (ADR 0006).
    """
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.volatility import VOL_WINDOW

    era = date(2025, 4, 8)
    calendar = [date(2024, 10, 1) + timedelta(days=i) for i in range(320)]
    session = calendar[-1]
    store = Store.memory()
    store.append_bars(
        "IDX", "^JKSE",
        _index_bars(calendar, _TREND["FRIENDLY"] * 3, _SWING["STRESSED"] * 3),
    )
    store.append_bars(
        "IDX", "IDR=X",
        [Bar(s, 16000.0, 16000.0, 16000.0, 16000.0, 16000.0 + i, 0)
         for i, s in enumerate(calendar)],
    )
    store.append_run(
        "IDX", session, status="published", symbols_enumerated=1, symbols_resolved=1,
        created_at=datetime(2025, 8, 16, 19, 30),
    )
    try:
        body = client_for(store).get("/api/volatility/IDX").json()
        assert body["era_start"] == era.isoformat()
        assert body["sample_size"] == sum(1 for s in calendar if s >= era)
        # Far short of every reading the stored history could have supplied —
        # which is the whole point, and why the sample size is on screen.
        assert body["sample_size"] < len(calendar) - VOL_WINDOW
        # The IDX second leg is a *volatility*, not the 16,000-rupiah level it
        # was computed from: there is no implied-vol index to read instead.
        assert 0 < body["second_leg"] < 1
        assert body["second_leg_symbol"] == "IDR=X"
    finally:
        store.close()


def test_volatility_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/volatility/LSE").status_code == 404


def test_the_candidate_list_is_identical_whatever_the_volatility_state():
    """Advisory only: he stops sizing, not looking (spec §4.9/§4.10).

    The same session, read once under a calm index and once under a stressed
    one — same candidates, same order, same scores. The volatility state never
    filters, never reorders and never reaches the star score.
    """
    import json

    def candidates_under(swing):
        # The index is shaped per cell below; its history starts too late for
        # a 6m relative move, so that row reads absent under both cells and the
        # two bodies are comparable byte for byte.
        store = _candidates_store(index=False)
        try:
            from datetime import date, timedelta

            from screener.source import MARKET_INDEX

            calendar = [date(2026, 4, 16) + timedelta(days=i) for i in range(_BARS)]
            store.append_bars(
                "US", MARKET_INDEX["US"],
                _index_bars(calendar, _TREND["FRIENDLY"], _SWING[swing]),
            )
            client = client_for(store)
            state = client.get("/api/volatility/US").json()["state"]
            return state, json.dumps(client.get("/api/candidates/US").json())
        finally:
            store.close()

    calm_state, calm_body = candidates_under("CALM")
    stressed_state, stressed_body = candidates_under("STRESSED")
    assert (calm_state, stressed_state) == ("CALM", "STRESSED")
    assert calm_body == stressed_body


# -- /api/candidates/{market} (ticket 38, spec §4.5 / §5.1) -------------------


def _candidates_store(*, index: bool = True) -> Store:
    """A store with a published US run and two detections — one tight (affordable)
    stop, one wide — plus ranks, one industry label, and the bars the rubric's
    Relative move row reads: AAA doubled over the year against a flat index,
    ZZZ merely matched it. ``index=False`` leaves the market index out, for a
    test that shapes its own."""
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.detection import DETECTOR_VERSION, Detection
    from screener.ranks import Rank

    store = Store.memory()
    session = date(2026, 8, 5)
    cal = [session - timedelta(days=239 - i) for i in range(240)]

    def series(closes):
        return [
            Bar(s, c, c * 1.01, c * 0.99, c, c, 1000) for s, c in zip(cal, closes)
        ]

    store.append_bars("US", "AAA", series([50.0 + 50.0 * i / 239 for i in range(240)]))
    store.append_bars("US", "ZZZ", series([98.0] * 240))
    if index:
        store.append_bars("US", "^IXIC", series([1000.0] * 240))
    store.append_run(
        "US", session, status="published",
        symbols_enumerated=2, symbols_resolved=2,
        created_at=datetime(2026, 8, 5, 22, 10),
    )
    store.append_universe("US", session, ["AAA", "ZZZ"])

    def det(symbol, cluster_low, adr=0.02):
        adr_abs = adr * 98.0
        stop = 100.0 - cluster_low
        return Detection(
            symbol=symbol, session=session, detector_version=DETECTOR_VERSION,
            trigger=100.0, stop=stop, stopw_adr=stop / adr_abs,
            base_len=30, move_gain=103.0, adr=adr, close=98.0,
            cluster_k=5, cluster_high=100.0, cluster_low=cluster_low,
            cluster_range_adr=0.99, range_3bar_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
            slope=-0.001, line_end=99.9, base_low=cluster_low,
            churn_l=0.45, sma20_rising=True, dryup=0.90,
        )

    # ZZZ: cluster_low 99.0 → stop 1.0 / adr_abs 1.96 ≈ 0.51 (affordable).
    # AAA: cluster_low 95.0 → stop 5.0 / adr_abs 1.96 ≈ 2.55 (the majority).
    store.append_detections("US", session, [det("AAA", 95.0), det("ZZZ", 99.0)])
    # AAA is top-decile in 1m/3m (a 2/5 breadth badge and a binding lookback);
    # ZZZ is in no decile. Both score tight+orderly+MA+volume; both miss base
    # length (30), sector (lone member) and ADR (0.02) — AAA's relative-move
    # point (it outran the flat index; ZZZ only matched it, and the cut is
    # strict) puts it a half-star ahead, so score, not ticker, decides the order.
    store.append_ranks("US", session, [
        Rank("AAA", "1m", 0.95, 1.2), Rank("AAA", "3m", 0.95, 1.1),
    ])
    store.upsert_label("US", "AAA", "Technology", "Semiconductors", session)
    return store


def test_candidates_endpoint_returns_score_ordered_five_column_rows():
    store = _candidates_store()
    try:
        body = client_for(store).get("/api/candidates/US").json()
        assert body["market"] == "US"
        assert body["session"] == "2026-08-05"
        # Sorted by star score descending, now that the rubric lands (ticket 39).
        assert body["ordered_by"] == "score"
        assert [c["symbol"] for c in body["candidates"]] == ["AAA", "ZZZ"]

        # Recalibrated rubric (PRD #138, v4 by #222): tight ×2 + orderly ×1 + MA
        # ×1 + volume ×1 = 5 points, plus AAA's relative-move point = 6 → 3.0;
        # ZZZ matched the index exactly and the cut is strict, so it misses.
        aaa, zzz = body["candidates"]
        assert aaa["score"] == 3.0
        assert zzz["score"] == 2.5
        # The payload carries the eight-row breakdown that reconstructs the score,
        # and the rubric version stamp that says which weights produced it.
        assert body["rubric_version"] == RUBRIC_VERSION == 4
        assert len(aaa["breakdown"]) == 8
        assert sum(r["weight"] for r in aaa["breakdown"] if r["hit"]) == 6
        # The relative move row carries its value in ADR units off the store's
        # own bars; ZZZ's is a real zero, not an absence.
        rel = {c["symbol"]: next(r for r in c["breakdown"] if r["dimension"] == "Relative move")
               for c in (aaa, zzz)}
        assert rel["AAA"]["hit"] is True and rel["AAA"]["value"] > 0
        assert rel["ZZZ"]["hit"] is False and rel["ZZZ"]["value"] == 0.0
        assert "Prior move" not in {r["dimension"] for r in aaa["breakdown"]}
        # The decile gate rides the row as its binding lookback's name — 1m and
        # 3m tie at 0.95, the shorter window binds — and no percentile field.
        assert aaa["gate_lookback"] == "1m"
        assert zzz["gate_lookback"] is None
        assert "gate_percentile" not in aaa
        # Nothing marks the line_ok tiebreak — no such field on the row.
        assert "line_ok" not in aaa
        assert aaa["industry"] == "Semiconductors"  # the theme layer
        assert aaa["breadth"] == 2                   # top-decile in 2 of 5 lookbacks
        assert abs(aaa["dist_adr"] - (100.0 - 98.0) / (0.02 * 98.0)) < 1e-9
    finally:
        store.close()


def test_candidates_stop_column_flags_the_affordable_minority_and_filters_nothing():
    store = _candidates_store()
    try:
        rows = client_for(store).get("/api/candidates/US").json()["candidates"]
        assert len(rows) == 2  # the stop column never filters
        by_sym = {c["symbol"]: c for c in rows}
        assert by_sym["ZZZ"]["affordable"] is True   # sub-1×ADR, highlighted
        assert by_sym["AAA"]["affordable"] is False  # the wide majority
    finally:
        store.close()


def test_candidates_endpoint_folds_the_chart_facts_onto_the_row():
    # A Setups card shows trigger/stop/distance without a per-symbol chart fetch:
    # the facts ride the row, projected from the same detection (spec §4.3). Bars
    # supply dollar_volume; a prior session supplies new_tonight.
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.detection import DETECTOR_VERSION, Detection
    from screener.ranks import Rank

    store = Store.memory()
    prev, session = date(2026, 8, 4), date(2026, 8, 5)
    cal = [date(2026, 1, 1) + timedelta(days=i) for i in range(160)]
    store.append_bars(
        "US", "AAA", [Bar(s, 98.0, 99.0, 97.0, 98.0, 98.0, 1000) for s in cal]
    )

    def det(symbol, sess):
        adr_abs = 0.02 * 98.0
        return Detection(
            symbol=symbol, session=sess, detector_version=DETECTOR_VERSION,
            trigger=100.0, stop=3.0, stopw_adr=3.0 / adr_abs,
            base_len=30, move_gain=103.0, adr=0.02, close=98.0,
            cluster_k=5, cluster_high=100.0, cluster_low=97.0, cluster_range_adr=0.99, range_3bar_adr=0.99,
            line_ok=True, touch_zones=2, overshoot_adr=0.0, slope=-0.001,
            line_end=99.9, base_low=97.0, churn_l=0.45, sma20_rising=True, dryup=0.90,
        )

    # Last session AAA was detected; tonight AAA and FRESH are — so AAA is held
    # over (new_tonight false) and FRESH is new (absent from prev's detected rows).
    store.append_run(
        "US", prev, status="published", symbols_enumerated=1, symbols_resolved=1,
        created_at=datetime(2026, 8, 4, 22, 10),
    )
    store.append_detections("US", prev, [det("AAA", prev)])
    store.append_run(
        "US", session, status="published", symbols_enumerated=2, symbols_resolved=2,
        created_at=datetime(2026, 8, 5, 22, 10),
    )
    store.append_universe("US", session, ["AAA", "FRESH"])
    store.append_detections("US", session, [det("AAA", session), det("FRESH", session)])
    store.append_ranks("US", session, [Rank("AAA", "1m", 0.95, 1.2)])
    store.upsert_label("US", "AAA", "Technology", "Semiconductors", session)
    try:
        rows = client_for(store).get("/api/candidates/US").json()["candidates"]
        by_sym = {c["symbol"]: c for c in rows}
        aaa = by_sym["AAA"]
        # The folded facts, projected from the detection row.
        assert aaa["trigger_price"] == 100.0   # overlay.trigger = cluster high
        assert aaa["stop_price"] == 97.0       # overlay.stop = cluster low
        assert aaa["close"] == 98.0
        assert aaa["adr"] == 0.02
        assert aaa["sector"] == "Technology"   # new on the row; industry stays too
        assert aaa["industry"] == "Semiconductors"
        assert aaa["dollar_volume"] == 98.0 * 1000  # median close×volume from bars
        assert aaa["decile_ranks"] == {"1m": 0.95}
        assert "risk_adr" not in aaa           # refused vocabulary — stopw_adr stays
        # Phase-2 fields: typed nullable, returned null.
        assert aaa["verdict"] is None
        assert len(aaa["breakdown"]) == 8
        # new_tonight: absence from the previous session's detected rows.
        assert aaa["new_tonight"] is False     # detected last session
        assert by_sym["FRESH"]["new_tonight"] is True  # not detected last session
        # No bars for FRESH → dollar_volume degrades to null, not a fabricated zero.
        assert by_sym["FRESH"]["dollar_volume"] is None
    finally:
        store.close()


def test_candidates_endpoint_is_empty_when_no_run_published(store: Store):
    body = client_for(store).get("/api/candidates/US").json()
    assert body == {
        "market": "US", "session": None, "ordered_by": "score", "candidates": [],
        "rubric_version": RUBRIC_VERSION,
    }


def test_candidates_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/candidates/LSE").status_code == 404


# -- /api/chart/{market}/{symbol} (ticket 40, spec §5.1) ----------------------


def _chart_store() -> Store:
    """A published US run with one detected name (AAA) carrying bars, a detection,
    ranks and a sector label, plus a bare name (BBB) with bars but no detection."""
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.detection import DETECTOR_VERSION, Detection
    from screener.ranks import Rank

    store = Store.memory()
    session = date(2026, 8, 5)
    cal = [date(2026, 1, 1) + timedelta(days=i) for i in range(120)]
    store.append_bars("US", "AAA", [Bar(s, 98.0, 99.0, 97.0, 98.0, 98.0, 1000) for s in cal])
    store.append_bars("US", "BBB", [Bar(s, 50.0, 51.0, 49.0, 50.0, 50.0, 2000) for s in cal])
    # The market index, flat like AAA: the rubric's Relative move row reads a
    # real zero off it (a miss on the strict cut), not an absence.
    store.append_bars("US", "^IXIC", [Bar(s, 1e3, 1.01e3, 0.99e3, 1e3, 1e3, 1) for s in cal])
    store.append_run(
        "US", session, status="published",
        symbols_enumerated=2, symbols_resolved=2,
        created_at=datetime(2026, 8, 5, 22, 10),
    )
    store.append_universe("US", session, ["AAA", "BBB"])
    adr_val = 0.02
    stop = 100.0 - 97.0
    store.append_detections("US", session, [Detection(
        symbol="AAA", session=session, detector_version=DETECTOR_VERSION,
        trigger=100.0, stop=stop, stopw_adr=stop / (adr_val * 98.0),
        base_len=30, move_gain=103.0, adr=adr_val, close=98.0,
        cluster_k=5, cluster_high=100.0, cluster_low=97.0, cluster_range_adr=0.99, range_3bar_adr=0.99,
        line_ok=True, touch_zones=2, overshoot_adr=0.0, slope=-0.001,
        line_end=99.9, base_low=97.0,
        churn_l=0.45, sma20_rising=True, dryup=0.90,
    )])
    store.append_ranks("US", session, [
        Rank("AAA", "1m", 0.95, 1.2), Rank("AAA", "3m", 0.90, 1.1),
    ])
    store.upsert_label("US", "AAA", "Technology", "Semiconductors", session)
    return store


def test_chart_endpoint_returns_candles_ma_set_and_facts_in_one_call():
    store = _chart_store()
    try:
        body = client_for(store).get("/api/chart/US/AAA").json()
        assert body["market"] == "US"
        assert body["symbol"] == "AAA"
        assert body["session"] == "2026-08-05"
        # Candles and the four MA lines — the daily set (spec §2).
        assert len(body["candles"]) == 120
        assert body["candles"][-1]["close"] == 98.0
        for line in ("sma10", "sma20", "sma50", "ema65"):
            assert len(body[line]) > 0
        # The facts block reconstructed from the detection row.
        f = body["facts"]
        assert f["base_len"] == 30
        assert f["trigger"] == 100.0
        assert abs(f["dist_adr"] - (100.0 - 98.0) / (0.02 * 98.0)) < 1e-9
        assert abs(f["stopw_adr"] - (100.0 - 97.0) / (0.02 * 98.0)) < 1e-9
        assert f["adr"] == 0.02
        assert f["dollar_volume"] == 98.0 * 1000  # median close×volume
        assert f["decile_ranks"] == {"1m": 0.95, "3m": 0.90}
        assert f["sector"] == "Technology"
        # The setup overlay (ticket 41): base/cluster shading bounds, the two
        # horizontal rules, the envelope line and the eight-row score breakdown.
        s = body["setup"]
        assert s["trigger"] == 100.0
        assert s["stop"] == 97.0            # the cluster-low stop rule
        assert s["cluster_start"] > s["base_start"]  # cluster sits inside the base
        assert len(s["envelope"]) == 30     # one line point per base bar
        assert [d["dimension"] for d in s["breakdown"]] == [
            "Tightness", "Orderliness", "Relative move", "Base length",
            "MA support", "Volume", "Sector", "ADR",
        ]
        points = sum(d["weight"] for d in s["breakdown"] if d["hit"])
        assert s["score"] == points / 2
        # Relative move scored off the store's own index bars, exactly as the
        # list scores it (rubric v4): AAA matched a flat index, a real zero.
        rel = next(d for d in s["breakdown"] if d["dimension"] == "Relative move")
        assert rel["value"] == 0.0 and rel["hit"] is False
    finally:
        store.close()


def test_chart_of_a_name_without_a_detection_still_draws_without_facts():
    store = _chart_store()
    try:
        body = client_for(store).get("/api/chart/US/BBB").json()
        assert len(body["candles"]) == 120
        assert body["facts"] is None  # no base tonight → nothing to describe
        assert body["setup"] is None  # no base → nothing to shade or break down
    finally:
        store.close()


def test_chart_bars_window_returns_the_trailing_n_candles():
    # ?bars=N draws only the last N bars — a thumbnail costs N bars, not the full
    # stored history (spec §4.6). The response shape is otherwise unchanged.
    store = _chart_store()
    try:
        body = client_for(store).get("/api/chart/US/AAA?bars=60").json()
        assert len(body["candles"]) == 60
        assert body["candles"][-1]["close"] == 98.0  # still the last stored bar
        # The response shape is unchanged — the four MA lines are still present,
        # computed over full history and sliced to the drawn window.
        for line in ("sma10", "sma20", "sma50", "ema65"):
            assert len(body[line]) > 0
        # Same bundle, just fewer bars: the facts/setup blocks are untouched.
        assert body["facts"]["base_len"] == 30
        assert body["setup"]["trigger"] == 100.0
    finally:
        store.close()


def test_chart_without_bars_param_returns_full_history():
    # Omitting ?bars keeps the default: the full stored series (120 bars).
    store = _chart_store()
    try:
        body = client_for(store).get("/api/chart/US/AAA").json()
        assert len(body["candles"]) == 120
    finally:
        store.close()


def test_chart_window_never_admits_a_quarantined_pulls_bars():
    # The ordering is the correctness requirement (spec §4.6): the session filter
    # runs *before* the tail truncation. A newer pull sits in the store past the
    # published session (quarantined, not published); a small window must still
    # draw published bars, never the quarantined tail.
    from datetime import date, datetime, timedelta

    from screener.bars import Bar

    store = Store.memory()
    session = date(2026, 4, 30)  # the published as-of session
    cal = [date(2026, 1, 1) + timedelta(days=i) for i in range(120)]
    # 120 published bars up to and including the session, then 5 quarantined bars
    # beyond it — a newer pull whose run is not published.
    published = [Bar(s, 98.0, 99.0, 97.0, 98.0, 98.0, 1000) for s in cal]
    quarantined = [
        Bar(session + timedelta(days=i), 5.0, 5.0, 5.0, 5.0, 5.0, 9)
        for i in range(1, 6)
    ]
    store.append_bars("US", "AAA", published + quarantined)
    store.append_run(
        "US", session, status="published",
        symbols_enumerated=1, symbols_resolved=1,
        created_at=datetime(2026, 4, 30, 22, 10),
    )
    store.append_universe("US", session, ["AAA"])
    try:
        body = client_for(store).get("/api/chart/US/AAA?bars=3").json()
        assert len(body["candles"]) == 3
        # Every drawn bar is on or before the published session; the quarantined
        # tail (had truncation run first) would have filled the whole window.
        assert all(c["session"] <= session.isoformat() for c in body["candles"])
        assert body["candles"][-1]["session"] == session.isoformat()
        assert all(c["close"] == 98.0 for c in body["candles"])  # none of the 5.0 tail
    finally:
        store.close()


def test_chart_unknown_symbol_is_404(store: Store):
    assert client_for(store).get("/api/chart/US/NOPE").status_code == 404


def test_chart_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/chart/LSE/AAA").status_code == 404
