"""The B-criteria acceptance pass: the ten wayfinding numbers, measured (spec §8.2).

The first full run is a **regression test against the entire wayfinding effort**
(ticket 45). Section 8.2 lists ten figures every one of which was measured during
design; a deviation beyond ~10% on any of them means a rule was implemented
differently from the spec. This module computes all ten off what a run *published*
— the universe, the rank table, the detections, the label cache and the reported
breaks — and pairs each with its spec expectation and a deviation flag, so the
operator records B1–B10 on night one and any drift surfaces as a spec question
rather than being read as a mediocre list (which the rubric's known cold running,
§4.7, would otherwise be blamed for).

Every figure is **derived from persisted rows through the same code paths the app
uses** — :func:`ranks.decile_gate`, :func:`boards.board_symbols`,
:func:`candidates.build_candidates`. There is deliberately no second definition of
"strong", "on a board" or "≥4★" here; acceptance measures the app, not a parallel
reimplementation of it.

Pure reads over the store, so it runs after any published session and is unit
tested without the network. The provisional list-length levels in §4.8 are the one
thing this pass exists to replace: they were rescaled from a 628-name US sample
against the real universe, and are free to compute the day the pipeline exists.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from statistics import median

from .boards import board_symbols
from .candidates import AFFORDABLE_ADR, build_candidates
from .ranks import decile_gate
from .store import Store

# A B-criterion is a spec deviation when the measured value lands more than this
# far from its expectation — §8.2's "~10%". Below it the universe simply moved.
TOLERANCE = 0.10

# The ≥4★ line: a candidate at or above this many stars counts toward B9's share.
FOUR_STAR = 4.0

# D2's instrument-filter spot check (spec §8.4): twelve US-listed ADRs that a
# too-eager instrument-type filter would wrongly eat. **All twelve must survive**
# in the US universe; a missing one means the filter cut something real.
ADR_SPOT_CHECK: tuple[str, ...] = (
    "BABA", "ARM", "SE", "PDD", "NOK", "SHEL",
    "JD", "VALE", "UL", "INFY", "ARGX", "SIMO",
)

# The spec's §8.2 expectations, per market. ``None`` where the spec gives no figure
# for that market (B4/B9 were measured on the US sample only; IDX has no published
# detections-per-night level). Shares are fractions of the universe/list; counts are
# absolute. These are the numbers ticket 45 replaces once measured on a real run.
_EXPECTED: dict[str, dict[str, float | None]] = {
    "US": {
        "B1": 1966, "B2": 0.285, "B3": 112, "B4": 30, "B5": 9.6,
        "B6": 0.92, "B7": 0.0, "B8": 0.37, "B9": 0.18, "B10": 0.99,
    },
    "IDX": {
        "B1": 288, "B2": 0.285, "B3": 88, "B4": None, "B5": 1.2,
        "B6": 0.92, "B7": 0.0, "B8": 0.37, "B9": 0.18, "B10": 0.99,
    },
}

_LABELS: dict[str, tuple[str, str]] = {
    "B1": ("Universe size", "count"),
    "B2": ("Union-of-five-deciles gate width", "share"),
    "B3": ("Distinct names across the five boards", "count"),
    "B4": ("Detections per night", "count"),
    "B5": ("Digest rows per night", "count"),
    "B6": ("Share of list whose cluster-low stop > 1×ADR", "share"),
    "B7": ("Share where the fitted line sets the trigger", "share"),
    "B8": ("Share of clusters at k=3", "share"),
    "B9": ("≥4★ share of the nightly list", "share"),
    "B10": ("Sector/industry coverage", "share"),
}


@dataclass(frozen=True)
class BMetric:
    """One B-criterion measured against its spec expectation (spec §8.2).

    ``measured`` is the figure off the published run; ``expected`` is §8.2's value
    for this market (``None`` where the spec gives none); ``deviates`` is True when
    the two are more than :data:`TOLERANCE` apart — the signal to investigate a
    spec deviation before accepting the list. ``detail`` carries the secondary
    figure the spec pairs with some criteria (a median), informational only.
    """

    key: str
    label: str
    unit: str
    measured: float
    expected: float | None
    deviates: bool
    detail: str = ""


def _deviates(measured: float, expected: float | None) -> bool:
    """True when ``measured`` is a spec deviation against ``expected`` (§8.2).

    An expectation of exactly 0 (B7's identity) deviates on any non-zero measure;
    a ``None`` expectation — the spec gives no figure for this market — never
    deviates. Otherwise the ~10% band applies."""
    if expected is None:
        return False
    if expected == 0:
        return measured != 0
    return abs(measured - expected) > TOLERANCE * abs(expected)


def _resolve_session(store: Store, market: str, session: date | None) -> date:
    if session is not None:
        return session
    latest = store.latest_run(market)
    if latest is None:
        raise ValueError(f"{market} has no published run to measure")
    return latest.session


def compute_b_criteria(
    store: Store, market: str, session: date | None = None
) -> list[BMetric]:
    """The ten B-criteria for ``market``'s ``session`` (default: last published).

    Reads the session's universe, ranks, detections, label cache and reported
    breaks and derives each figure through the app's own code paths. Returns the
    ten metrics in B1–B10 order, each paired with its spec expectation and a
    deviation flag (spec §8.2).
    """
    session = _resolve_session(store, market, session)
    universe = store.universe(market, session)
    n = len(universe)
    ranks = store.ranks(market, session)
    detections = store.detections(market, session)
    labels = store.labels(market)
    breaks = store.digest_breaks(market, session)

    industry_of = {sym: lab.industry for sym, lab in labels.items()}
    sector_of = {sym: lab.sector for sym, lab in labels.items()}
    candidates = build_candidates(detections, ranks, industry_of, sector_of)

    stops = [det.stopw_adr for det in detections]
    ks = [det.cluster_k for det in detections]
    n_det = len(detections)

    b6_detail = f"median {median(stops):.2f}×" if stops else "no detections"
    b8_detail = f"median k={median(ks):g}" if ks else "no detections"

    measured: dict[str, float] = {
        "B1": n,
        "B2": len(decile_gate(ranks)) / n if n else 0.0,
        "B3": len(board_symbols(ranks)),
        "B4": n_det,
        "B5": len(breaks),
        "B6": sum(s > AFFORDABLE_ADR for s in stops) / n_det if n_det else 0.0,
        # The line is anchored at the cluster high and searched over non-positive
        # slopes, so line_end ≤ cluster_high always: this share is 0 by identity,
        # and any non-zero value is a bug (spec §8.2 B7 / §4.5).
        "B7": sum(det.line_end > det.cluster_high for det in detections) / n_det if n_det else 0.0,
        "B8": sum(k == 3 for k in ks) / n_det if n_det else 0.0,
        "B9": sum(c.score >= FOUR_STAR for c in candidates) / len(candidates)
        if candidates else 0.0,
        "B10": sum(1 for m in universe if m in labels) / n if n else 0.0,
    }
    detail = {"B6": b6_detail, "B8": b8_detail}

    expected = _EXPECTED.get(market, {})
    out: list[BMetric] = []
    for key in _LABELS:
        label, unit = _LABELS[key]
        exp = expected.get(key)
        out.append(
            BMetric(
                key=key,
                label=label,
                unit=unit,
                measured=measured[key],
                expected=exp,
                deviates=_deviates(measured[key], exp),
                detail=detail.get(key, ""),
            )
        )
    return out


def adr_names_present(
    store: Store, market: str, session: date | None = None
) -> tuple[list[str], list[str]]:
    """D2's spot check: which of the twelve ADRs survive in the universe (§8.4).

    Returns ``(present, missing)`` in :data:`ADR_SPOT_CHECK` order. A non-empty
    ``missing`` on US means the instrument-type filter ate something real — the one
    judgement check no earlier ticket owns."""
    session = _resolve_session(store, market, session)
    members = set(store.universe(market, session))
    present = [s for s in ADR_SPOT_CHECK if s in members]
    missing = [s for s in ADR_SPOT_CHECK if s not in members]
    return present, missing


def _fmt(metric: BMetric) -> str:
    """One report line: measured, expectation and a deviation marker."""
    def show(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:.3f}" if metric.unit == "share" else f"{v:g}"

    flag = "⚠ DEVIATES" if metric.deviates else "ok"
    detail = f"  ({metric.detail})" if metric.detail else ""
    return (
        f"  {metric.key:>3}  {metric.label:<44}  "
        f"measured {show(metric.measured):>8}  "
        f"expected {show(metric.expected):>8}  {flag}{detail}"
    )


def render_report(store: Store, market: str, session: date | None = None) -> str:
    """The human acceptance report for one market: the ten B-criteria and, on US,
    the D2 ADR spot check (spec §8.2/§8.4)."""
    session = _resolve_session(store, market, session)
    metrics = compute_b_criteria(store, market, session)
    lines = [f"{market} acceptance — session {session.isoformat()} (spec §8.2)"]
    lines += [_fmt(m) for m in metrics]

    present, missing = adr_names_present(store, market, session)
    lines.append("")
    lines.append(f"  D2 ADR spot check — {len(present)}/{len(ADR_SPOT_CHECK)} present")
    if missing:
        lines.append(f"      MISSING: {', '.join(missing)}  (instrument filter ate a real name)")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m screener.acceptance <IDX|US>``. Prints the B-criteria
    report for a market's last published session against the live store."""
    from .app import DEFAULT_DB_PATH

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0].upper() not in _EXPECTED:
        print("usage: python -m screener.acceptance <IDX|US>", file=sys.stderr)
        return 2
    market = args[0].upper()
    store = Store.open(DEFAULT_DB_PATH)
    try:
        print(render_report(store, market), end="")
    except ValueError as exc:
        print(f"{market}: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
