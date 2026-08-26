"""Parse and classify Kullamägi's executed-trade reference set (PRD #114).

The reference set is the committed JSON of his executed trades
(``references/trades_bo_gain10smaPct_desc.json``): 828 real long breakout
entries, all US, each an *observed* entry paired with two *simulated* exits
(rules applied after the fact). The entry is real; the exits are counterfactual,
and the study must not blur them (PRD "Further Notes").

This module reads the JSON into typed :class:`ExecutedTrade` rows, classifies
each as **replayable** (the store's bars for its ticker cover the session the
trade is evaluated at) or a **blind spot** (they do not — a delisted, acquired or
renamed name the provider returns nothing for, or a symbol recycled onto a
listing that did not exist at the entry), and reports the counts. The blind-spot
ticker list is written to ``references/`` so the size of the store's survivorship
hole is a fixed, citable fact rather than a vague worry (user story 23).

The counts are computed, never hard-coded. :data:`REFERENCE_FIGURES` records the
figures measured in #114 so a later change to the reference set or the store is
caught as drift (:func:`assert_matches_reference`), not silently absorbed.

**Blind spot is measured in the replay window, not over all history.** The
classification asks whether the ticker has bars *in the replay store* covering the
trade's evaluation session, and the store holds only ``2019-04..2022-12``
(:mod:`replay.store`). That is the operationally true test — it is exactly the
condition under which the funnel and the field can say anything about a trade —
and it is stricter than asking whether the provider returns the symbol at all
today. The two differ by 11 tickers / 31
trades, every one of them a **symbol-reuse** case: the ticker resolves today, but
its bar history begins years after the entry it is paired with, because the
symbol was recycled onto an unrelated listing (APXT, BNKU, EYES, FNGU, FUSE, LAC,
LAZR, NRGU, SI, SPWR, USLV). Counting those replayable would not merely understate the
hole; at any window overlap it would replay one company's trade against another
company's bars — which is exactly what a has-any-bars test did to ``FUSE`` until
#139 (its entry is 2021-01-04; its bars run 2022-03-07..2022-12-22, so the ten
above escaped only because their replacement listings happen to begin after the
window ends). The #114 figures were first measured over all history
(81 / 141 / 11.7%), then in the window under a has-any-bars test
(91 / 170 / 18.15%, 658 replayable); the pins below are the window-measured
figures under the covers-the-entry test the study actually runs on.

**Schema note.** The reference tool emits one exit block per simulated exit,
named in the row keys — ``gain10smaPct`` / ``mfe10smaPct`` / ``r10sma`` for the
10-day-SMA trailing exit, and the parallel ``…20sma…`` keys for the 20-day one.
The parser auto-detects exits from any ``gain<exit>Pct`` key rather than pinning
one hard-coded pair, so a reference set carrying a different or extra exit still
parses; :data:`PRIMARY_EXIT` (the one named in the file, ``10sma``) is the exit
the R totals are taken over.
"""

from __future__ import annotations

import argparse
import json
import re
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from screener.store import Store

# The exit named in the reference file (``…gain10smaPct…``); its realised R is
# the R the coverage share is taken over.
PRIMARY_EXIT = "10sma"

# ``gain<exit>Pct`` marks one simulated exit's realised-gain field; the exit
# label is whatever sits between ``gain`` and ``Pct``. The parallel ``mfe<exit>Pct``
# and ``r<exit>`` carry that exit's max-favourable-excursion and realised R.
_GAIN_KEY = re.compile(r"^gain(?P<exit>.+)Pct$")

# The figures measured over the committed reference set in #114, re-pinned in
# #139. Recomputed by the report every run; these exist only to detect drift and
# are never the source of a reported number. The blind-spot figures are measured
# in the replay window, against bars covering each trade's evaluation session (see
# the module docstring). The superseded measurements: 81 / 141 / 11.7% over all
# history (#114), and 91 / 170 / 18.15% in the window under the has-any-bars test
# #139 replaced.
REFERENCE_FIGURES: dict[str, float] = {
    "total_rows": 828,
    "rows_with_outcomes": 827,
    "distinct_tickers": 312,
    "blind_spot_tickers": 92,
    "blind_spot_trades": 172,
    "blind_spot_r_share": 0.180,
}

# The blind-spot R share is a float; a change below this tolerance is rounding,
# not drift (the #114 figure is quoted to 0.1%).
R_SHARE_TOL = 0.001


class DriftError(RuntimeError):
    """The recomputed counts diverge from the #114 reference figures.

    Raised loudly rather than logged: a mismatch means the reference set or the
    store changed under the study, and every downstream ticket's numbers rest on
    these counts, so it must stop the command rather than quietly shift them.
    """


@dataclass(frozen=True)
class Outcome:
    """One simulated exit's outcome fields. Any field may be ``None`` for a row
    the reference tool left without that exit's outcome (one row of 828)."""

    gain_pct: float | None
    mfe_pct: float | None
    r: float | None


@dataclass(frozen=True)
class ExecutedTrade:
    """One executed trade: a real entry, its stop, and its simulated exits.

    ``outcomes`` is keyed by exit label (``"10sma"``, ``"20sma"``); an
    outcome-less row carries an empty mapping.
    """

    ticker: str
    entry_date: date
    entry_price: float
    stop_price: float
    stop_pct: float
    outcomes: Mapping[str, Outcome]

    @property
    def primary(self) -> Outcome | None:
        """The primary exit's outcome, or ``None`` if the row carries no outcomes."""
        return self.outcomes.get(PRIMARY_EXIT)

    @property
    def has_outcomes(self) -> bool:
        """True when the primary exit reports a realised gain — the sense of the
        report's "rows carrying outcomes" count."""
        return self.primary is not None and self.primary.gain_pct is not None

    @property
    def r(self) -> float | None:
        """The realised R under the primary exit, or ``None`` if absent."""
        return self.primary.r if self.primary is not None else None


def _as_float(value: object) -> float | None:
    return None if value is None else float(value)


def _stop_pct_in_percent(record: Mapping[str, object]) -> float:
    """The trade's stop width in **percent**, whatever the row calls it.

    The unit matters more than the key: a fraction read as a percent understates
    every stop width by 100x, which would silently gut the study's stop-width
    finding rather than fail loudly.
    """
    fraction = record.get("stopPercentage")
    if fraction is not None:
        return float(fraction) * 100.0
    for key in ("stopPct", "riskPct"):
        value = record.get(key)
        if value is not None:
            return float(value)
    raise KeyError("row carries no stop width (stopPercentage / stopPct / riskPct)")


def _parse_outcomes(record: Mapping[str, object]) -> dict[str, Outcome]:
    outcomes: dict[str, Outcome] = {}
    for key in record:
        match = _GAIN_KEY.match(key)
        if match is None:
            continue
        exit_label = match.group("exit")
        # The realised-R key is ``rr<exit>`` in the committed reference set; the
        # singular ``r<exit>`` is accepted too so an older export still parses.
        r = record.get(f"rr{exit_label}", record.get(f"r{exit_label}"))
        outcomes[exit_label] = Outcome(
            gain_pct=_as_float(record.get(f"gain{exit_label}Pct")),
            mfe_pct=_as_float(record.get(f"mfe{exit_label}Pct")),
            r=_as_float(r),
        )
    return outcomes


def parse_trades(records: list[Mapping[str, object]]) -> list[ExecutedTrade]:
    """Parse the reference JSON rows into typed :class:`ExecutedTrade` objects.

    Every row becomes a trade — an outcome-less row is still a row, kept in every
    denominator (user story 34), so a blind spot and an outcome gap are quantified
    rather than one silently absorbing the other.
    """
    trades: list[ExecutedTrade] = []
    for record in records:
        # ``entryDate`` is a full ISO timestamp (``2021-02-24T00:00:00.000Z``);
        # the study is end-of-day, so only the date part is meaningful.
        #
        # ``stop_pct`` is carried in **percent** (3.38 for a 3.38% stop) because
        # that is what consumers divide by 100 — see
        # :func:`replay.regression.build_feature_vector`. The reference file's
        # ``stopPercentage`` is a *fraction* (0.0338), so it is scaled here; the
        # file's own ``riskPct`` is the same number already in percent, but at
        # two decimals, so the fraction is preferred for precision. A legacy
        # ``stopPct`` is taken as percent as written.
        stop_pct = _stop_pct_in_percent(record)
        trades.append(
            ExecutedTrade(
                ticker=str(record["ticker"]),
                entry_date=date.fromisoformat(str(record["entryDate"])[:10]),
                entry_price=float(record["entryPrice"]),
                stop_price=float(record["stopPrice"]),
                stop_pct=stop_pct,
                outcomes=_parse_outcomes(record),
            )
        )
    return trades


def load_trades(json_path: str | Path) -> list[ExecutedTrade]:
    """Read and parse the committed reference JSON at ``json_path``.

    The reference tool wraps the rows in a ``{"count": N, "trades": [...]}``
    envelope; a bare list is accepted too so a hand-trimmed extract still parses.
    """
    payload = json.loads(Path(json_path).read_text())
    records = payload["trades"] if isinstance(payload, Mapping) else payload
    return parse_trades(records)


@dataclass(frozen=True)
class ClassifiedTrade:
    """An executed trade with its replayable/blind-spot verdict."""

    trade: ExecutedTrade
    replayable: bool


@dataclass(frozen=True)
class BarSpan:
    """The sessions a ticker's bars run between, oldest to newest, inclusive.

    The store answers "what bars are under this symbol?"; replayability asks the
    narrower "was this symbol quoted on that night?" — so the span, not the bar
    list, is what :func:`classify` keeps, one per ticker rather than one per trade.
    A gap inside the span (a halt, a missing session) still counts as covered: the
    listing existed, which is the question being asked.
    """

    first: date
    last: date

    @classmethod
    def of(cls, bars: list) -> "BarSpan | None":
        """The span of ``bars``, or ``None`` when the store holds none."""
        return cls(first=bars[0].session, last=bars[-1].session) if bars else None

    def covers(self, session: date) -> bool:
        """True when ``session`` falls inside the span."""
        return self.first <= session <= self.last


def evaluation_session(calendar: list[date], entry_date: date) -> date | None:
    """The last session in ``calendar`` strictly before ``entry_date``.

    ``calendar`` is the market's observed session dates, oldest first (the union of
    bar dates — :meth:`screener.store.Store.sessions`), so the "session before"
    lands correctly across weekends and market holidays with no holiday table: a
    gap simply has no session in it. ``None`` when nothing precedes the entry.

    This is the session every replay study evaluates a trade at — the night the
    app would have had to name the stock while the entry was still ahead of the
    trader — so it also defines what :func:`classify` asks the store to cover.
    Re-exported by :mod:`replay.funnel`, which is where it was first defined.
    """
    idx = bisect_left(calendar, entry_date) - 1
    return calendar[idx] if idx >= 0 else None


def classify(
    trades: list[ExecutedTrade], store: Store, *, market: str = "US"
) -> list[ClassifiedTrade]:
    """Tag each trade replayable iff the store's bars for its ticker **cover the
    session the trade is evaluated at** (#139).

    Not "does this symbol exist in the store?" but "can this trade be evaluated?".
    The two answers diverge on a **recycled symbol**: a ticker reassigned to an
    unrelated listing carries bars that begin years after the entry it is paired
    with. A has-any-bars test calls that replayable, and the trade then enters the
    funnel denominator and fails the detector's ``history`` gate — charged to the
    detector as a stage failure when it is a coverage hole (``FUSE``, entry
    2021-01-04, bars from 2022-03). Bars that *end* before the evaluation session
    fail the same test for the same reason.

    The verdict is therefore per *trade*, not per ticker: the same name can be
    replayable at one entry and a blind spot at another. Each ticker's bar span is
    read once and cached, so a name traded several times still costs one store
    read.
    """
    spans: dict[str, BarSpan | None] = {}
    calendar = store.sessions(market)
    classified: list[ClassifiedTrade] = []
    for trade in trades:
        if trade.ticker not in spans:
            spans[trade.ticker] = BarSpan.of(store.bars(market, trade.ticker))
        span = spans[trade.ticker]
        session = evaluation_session(calendar, trade.entry_date)
        replayable = span is not None and session is not None and span.covers(session)
        classified.append(ClassifiedTrade(trade=trade, replayable=replayable))
    return classified


@dataclass(frozen=True)
class ReferenceReport:
    """The count report: the size of the reference set and its survivorship hole.

    ``blind_spot_r_share`` is the blind-spot trades' realised R (primary exit) as
    a share of total realised R, so a ranking result is never read without knowing
    how much of the field's return was missing (user story 22).
    """

    total_rows: int
    rows_with_outcomes: int
    distinct_tickers: int
    blind_spot_tickers: int
    blind_spot_trades: int
    blind_spot_r_share: float
    blind_spot_ticker_list: list[str]


def build_report(
    trades: list[ExecutedTrade], store: Store, *, market: str = "US"
) -> ReferenceReport:
    """Compute the count report over the parsed, classified reference set."""
    classified = classify(trades, store, market=market)

    blind_spot_tickers = sorted(
        {c.trade.ticker for c in classified if not c.replayable}
    )
    blind_spot_trades = [c.trade for c in classified if not c.replayable]

    total_r = sum(t.r for t in trades if t.r is not None)
    blind_spot_r = sum(t.r for t in blind_spot_trades if t.r is not None)
    r_share = blind_spot_r / total_r if total_r else 0.0

    return ReferenceReport(
        total_rows=len(trades),
        rows_with_outcomes=sum(1 for t in trades if t.has_outcomes),
        distinct_tickers=len({t.ticker for t in trades}),
        blind_spot_tickers=len(blind_spot_tickers),
        blind_spot_trades=len(blind_spot_trades),
        blind_spot_r_share=r_share,
        blind_spot_ticker_list=blind_spot_tickers,
    )


def assert_matches_reference(report: ReferenceReport) -> None:
    """Fail loudly if the recomputed counts diverge from the #114 figures.

    The integer counts must match exactly; the R share must match to within
    :data:`R_SHARE_TOL`. A mismatch means the reference set or the store moved,
    which every later analysis rests on, so it raises rather than logs.
    """
    mismatches: list[str] = []
    for key in ("total_rows", "rows_with_outcomes", "distinct_tickers",
                "blind_spot_tickers", "blind_spot_trades"):
        actual = getattr(report, key)
        expected = REFERENCE_FIGURES[key]
        if actual != expected:
            mismatches.append(f"{key}: got {actual}, #114 recorded {expected}")

    share_expected = REFERENCE_FIGURES["blind_spot_r_share"]
    if abs(report.blind_spot_r_share - share_expected) > R_SHARE_TOL:
        mismatches.append(
            f"blind_spot_r_share: got {report.blind_spot_r_share:.4f}, "
            f"#114 recorded {share_expected}"
        )

    if mismatches:
        raise DriftError(
            "replay reference set drifted from the #114 figures:\n  "
            + "\n  ".join(mismatches)
        )


def write_blind_spot_list(report: ReferenceReport, path: str | Path) -> None:
    """Write the sorted blind-spot ticker list to ``path`` as JSON.

    Committed to ``references/`` so the survivorship hole is a fixed, citable fact
    (user story 23). Sorted so the file is stable across runs and reviewable.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.blind_spot_ticker_list, indent=2) + "\n")


def format_report(report: ReferenceReport) -> str:
    """Human-readable one-block summary of the count report."""
    return "\n".join(
        [
            f"total rows:          {report.total_rows}",
            f"rows with outcomes:  {report.rows_with_outcomes}",
            f"distinct tickers:    {report.distinct_tickers}",
            f"blind-spot tickers:  {report.blind_spot_tickers}",
            f"blind-spot trades:   {report.blind_spot_trades}",
            f"blind-spot R share:  {report.blind_spot_r_share:.1%}",
        ]
    )


# -- command-line entry point ---------------------------------------------

# Repo-root-relative default locations for the committed artefacts.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_JSON = _REPO_ROOT / "references" / "trades_bo_gain10smaPct_desc.json"
DEFAULT_BLIND_SPOT_OUT = _REPO_ROOT / "references" / "blind_spot_tickers.json"


def main(argv: list[str] | None = None) -> int:
    """Report the reference-set counts and write the blind-spot ticker list.

    Thin CLI over the pure functions above (one entry point per study, user story
    30): parse the reference JSON, classify against the replay store, print the
    counts, assert them against the #114 figures, and write the blind-spot list.

    Run as ``python -m replay.reference --store data/replay.duckdb``.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--blind-spot-out", default=str(DEFAULT_BLIND_SPOT_OUT),
                        help="where to write the blind-spot ticker list")
    parser.add_argument("--market", default="US")
    parser.add_argument("--no-drift-check", action="store_true",
                        help="skip the assertion against the #114 figures")
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        report = build_report(trades, store, market=args.market)
    finally:
        store.close()

    print(format_report(report))
    write_blind_spot_list(report, args.blind_spot_out)
    print(f"wrote {args.blind_spot_out}")

    if not args.no_drift_check:
        assert_matches_reference(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
