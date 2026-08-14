"""Parse and classify Kullamägi's executed-trade reference set (PRD #114).

The reference set is the committed JSON of his executed trades
(``references/trades_bo_gain10smaPct_desc.json``): 828 real long breakout
entries, all US, each an *observed* entry paired with two *simulated* exits
(rules applied after the fact). The entry is real; the exits are counterfactual,
and the study must not blur them (PRD "Further Notes").

This module reads the JSON into typed :class:`ExecutedTrade` rows, classifies
each as **replayable** (its ticker has bars in the replay store) or a
**blind-spot ticker** (it does not — a delisted, acquired or renamed name the
provider returns nothing for), and reports the counts. The blind-spot ticker
list is written to ``references/`` so the size of the store's survivorship hole
is a fixed, citable fact rather than a vague worry (user story 23).

The counts are computed, never hard-coded. :data:`REFERENCE_FIGURES` records the
figures measured in #114 so a later change to the reference set or the store is
caught as drift (:func:`assert_matches_reference`), not silently absorbed.

**Schema note.** The reference tool emits one exit block per simulated exit,
named in the row keys — ``gain10smaPct`` / ``mfe10smaPct`` / ``r10sma`` for the
10-day-SMA trailing exit, and the parallel ``…20sma…`` keys for the 20-day one.
The parser auto-detects exits from any ``gain<exit>Pct`` key rather than pinning
one hard-coded pair, so a reference set carrying a different or extra exit still
parses; :data:`PRIMARY_EXIT` (the one named in the file, ``10sma``) is the exit
the R totals are taken over.
"""

from __future__ import annotations

import json
import re
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

# The figures measured over the committed reference set in #114. Recomputed by
# the report every run; these exist only to detect drift and are never the source
# of a reported number.
REFERENCE_FIGURES: dict[str, float] = {
    "total_rows": 828,
    "rows_with_outcomes": 827,
    "distinct_tickers": 312,
    "blind_spot_tickers": 81,
    "blind_spot_trades": 141,
    "blind_spot_r_share": 0.117,
}

# The blind-spot R share is a float; a change below this tolerance is rounding,
# not drift (the #114 figure is quoted to 0.1%).
_R_SHARE_TOL = 0.001


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


def _parse_outcomes(record: Mapping[str, object]) -> dict[str, Outcome]:
    outcomes: dict[str, Outcome] = {}
    for key in record:
        match = _GAIN_KEY.match(key)
        if match is None:
            continue
        exit_label = match.group("exit")
        outcomes[exit_label] = Outcome(
            gain_pct=_as_float(record.get(f"gain{exit_label}Pct")),
            mfe_pct=_as_float(record.get(f"mfe{exit_label}Pct")),
            r=_as_float(record.get(f"r{exit_label}")),
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
        trades.append(
            ExecutedTrade(
                ticker=str(record["ticker"]),
                entry_date=date.fromisoformat(str(record["entryDate"])),
                entry_price=float(record["entryPrice"]),
                stop_price=float(record["stopPrice"]),
                stop_pct=float(record["stopPct"]),
                outcomes=_parse_outcomes(record),
            )
        )
    return trades


def load_trades(json_path: str | Path) -> list[ExecutedTrade]:
    """Read and parse the committed reference JSON at ``json_path``."""
    records = json.loads(Path(json_path).read_text())
    return parse_trades(records)


@dataclass(frozen=True)
class ClassifiedTrade:
    """An executed trade with its replayable/blind-spot verdict."""

    trade: ExecutedTrade
    replayable: bool


def classify(
    trades: list[ExecutedTrade], store: Store, *, market: str = "US"
) -> list[ClassifiedTrade]:
    """Tag each trade replayable iff its ticker has bars in the replay store.

    A ticker is looked up once and cached, so a name traded several times costs
    one store read rather than one per entry.
    """
    has_bars: dict[str, bool] = {}
    classified: list[ClassifiedTrade] = []
    for trade in trades:
        if trade.ticker not in has_bars:
            has_bars[trade.ticker] = bool(store.bars(market, trade.ticker))
        classified.append(ClassifiedTrade(trade=trade, replayable=has_bars[trade.ticker]))
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
    :data:`_R_SHARE_TOL`. A mismatch means the reference set or the store moved,
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
    if abs(report.blind_spot_r_share - share_expected) > _R_SHARE_TOL:
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
    import argparse

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
