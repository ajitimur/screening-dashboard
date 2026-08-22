"""The B-criteria acceptance metrics computed off a published run (spec §8.2).

Ticket 45: the ten wayfinding figures are free to compute the day the pipeline
exists. :mod:`screener.acceptance` reads what a run published — the universe, the
rank table, the detections, the labels and the reported breaks — and returns each
B-criterion as a measured value against its spec expectation, flagging any
deviation beyond ~10% so a rule implemented differently from the spec surfaces as
a regression rather than being silently accepted.
"""

from datetime import date, datetime

from screener.acceptance import (
    ADR_SPOT_CHECK,
    adr_names_present,
    compute_b_criteria,
)
from screener.candidates import build_candidates
from screener.detection import DETECTOR_VERSION, Detection
from screener.ranks import Rank
from screener.store import Store

SESSION = date(2026, 8, 5)


def _det(symbol, *, stopw_adr=1.28, cluster_k=5, adr=0.06, base_len=10):
    """A stored detection with the columns the B-criteria read dialable. The
    trigger is the cluster high by identity and ``line_end`` sits below it, so B7
    is 0 by construction."""
    return Detection(
        symbol=symbol, session=SESSION, detector_version=DETECTOR_VERSION,
        trigger=100.0, stop=stopw_adr * adr * 98.0, stopw_adr=stopw_adr,
        base_len=base_len, move_gain=103.0, adr=adr, close=98.0,
        cluster_k=cluster_k, cluster_high=100.0, cluster_low=97.0,
        cluster_range_adr=0.99, range_3bar_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=99.9, base_low=97.0,
        churn_l=0.45, sma20_rising=True, dryup=0.90,
    )


def _seed(store: Store) -> tuple[list[Detection], list[Rank], dict, dict]:
    """A US session with 10 members, 4 detections, labels on 9 of 10, 2 breaks."""
    members = [f"U{i}" for i in range(10)]
    store.append_run(
        "US", SESSION, status="published",
        symbols_enumerated=10, symbols_resolved=10,
        created_at=datetime(2026, 8, 5, 22, 10),
    )
    store.append_universe("US", SESSION, members)

    # U0,U1,U2 top-decile in 1m → decile gate is 3 of 10 (B2 share 0.30).
    ranks = [Rank(f"U{i}", "1m", 0.95 if i < 3 else 0.5, 2.0 - i * 0.1) for i in range(10)]
    store.append_ranks("US", SESSION, ranks)

    dets = [
        _det("U0", stopw_adr=1.28, cluster_k=3),
        _det("U1", stopw_adr=1.28, cluster_k=3),
        _det("U2", stopw_adr=1.28, cluster_k=5),
        _det("U3", stopw_adr=0.80, cluster_k=5),
    ]
    store.append_detections("US", SESSION, dets)

    for i in range(9):  # 9 of 10 carry both labels → B10 coverage 0.9
        store.upsert_label("US", f"U{i}", "Technology", "Semiconductors", SESSION)

    store.append_digest_breaks("US", SESSION, ["U0", "U1"])
    industry_of = {f"U{i}": "Semiconductors" for i in range(9)}
    sector_of = {f"U{i}": "Technology" for i in range(9)}
    return dets, ranks, industry_of, sector_of


def test_b_criteria_measured_off_the_published_run():
    store = Store.memory()
    dets, ranks, industry_of, sector_of = _seed(store)
    metrics = {m.key: m for m in compute_b_criteria(store, "US")}

    assert metrics["B1"].measured == 10          # universe size
    assert abs(metrics["B2"].measured - 0.30) < 1e-9   # decile-gate share
    assert metrics["B3"].measured == 10          # distinct board names (<30/lookback)
    assert metrics["B4"].measured == 4           # detections
    assert metrics["B5"].measured == 2           # digest rows
    assert abs(metrics["B6"].measured - 0.75) < 1e-9   # 3 of 4 stops > 1×ADR
    assert metrics["B7"].measured == 0.0         # line never sets the trigger
    assert abs(metrics["B8"].measured - 0.50) < 1e-9   # 2 of 4 clusters k=3
    assert abs(metrics["B10"].measured - 0.90) < 1e-9  # 9 of 10 labelled

    # B9 is the ≥4★ share of the very list the app renders — computed by the same
    # path, so acceptance never invents a second scoring definition.
    cands = build_candidates(dets, ranks, industry_of, sector_of)
    expected_b9 = sum(c.score >= 4.0 for c in cands) / len(cands)
    assert abs(metrics["B9"].measured - expected_b9) < 1e-9
    store.close()


def test_deviation_flag_fires_beyond_ten_percent():
    store = Store.memory()
    _seed(store)
    metrics = {m.key: m for m in compute_b_criteria(store, "US")}
    # Measured universe is 10 against an expected ~1966 — a gross deviation.
    assert metrics["B1"].expected == 1966
    assert metrics["B1"].deviates is True
    # B7 expects exactly 0 and measured 0 — an identity that holds, no deviation.
    assert metrics["B7"].deviates is False
    store.close()


def test_adr_spot_check_reports_present_and_missing():
    store = Store.memory()
    members = list(ADR_SPOT_CHECK[:6]) + ["FOO", "BAR"]
    store.append_run(
        "US", SESSION, status="published", symbols_enumerated=8,
        symbols_resolved=8, created_at=datetime(2026, 8, 5, 22, 10),
    )
    store.append_universe("US", SESSION, members)
    present, missing = adr_names_present(store, "US")
    assert present == list(ADR_SPOT_CHECK[:6])
    assert missing == list(ADR_SPOT_CHECK[6:])
    store.close()
