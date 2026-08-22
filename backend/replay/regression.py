"""A3, the outcome regression: which score dimensions relate to a run (PRD #114
"A3 analyses", issue #121).

The first of A3's two analyses — kept apart from the selection contrast in code
and in the write-up. For every *replayable* executed trade a **feature vector** is
reconstructed at the evaluation session (the last session strictly before entry,
PRD user story 3), and each replayable score dimension is regressed against the
trade's **maximum favourable excursion** under the 10-day-SMA simulated exit
(:data:`mfe`), across executed trades only.

**MFE, not realised R.** The study is calibrating a *detector*, and realised R
bundles the trader's stop discipline into the label: most of his trades exited at
the stop, so regressing tightness against R would mostly teach us about stop
widths, not about whether the setup ran (PRD user story 15). MFE measures how far
the setup ran regardless of where he got out. The realised R distribution is
reported alongside as a descriptive statistic so the actual returns stay in view
(user story 16), never as the regression target.

**Range restriction is the trap.** Every trade in the sample already passed the
trader's eye, so the dimensions he applies most consistently show the least
variance and correlate with nothing. A null on such a dimension is evidence of his
discipline, not of the dimension's uselessness. So each dimension reports its
**spread** within the sample next to its correlation (user story 18), and a null
on a dimension with no spread is labelled **untestable** rather than absent (user
story 19) — deleting a filter that generated the sample in the first place is
exactly the mistake the label guards against. The "Prior move" dimension is
untestable by construction: every detection cleared the decile gate, so it never
varies within the field.

**The sector dimension is absent throughout** (PRD "Star score in replay"): the
seven regressed dimensions are the app's eight less Sector, whose 2020 history is
unrecoverable.

**Two preliminary #114 findings, confirmed or refuted.** The trade's own stop
width in ADR (:data:`stop_width_adr`, his stop as a multiple of the night's ADR)
and the ADR at entry are reported as distributions, so the fourfold stop-width gap
and the ADR-floor finding can be checked against the reconstructed set (user
stories 20/21).

This ticket produces *evidence only*. No constant in :mod:`screener` is changed;
a gate is loosened elsewhere only when this analysis shows a dimension has no
signal **and** real spread (PRD "Calibration rule").
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from math import ceil, floor
from typing import Iterable, Sequence

from screener.bars import Bar
from screener.detection import Detection
from screener.indicators import adr as _adr
from screener.score import DIMENSIONS as _SCORE_DIMENSIONS, Dimension
from screener.store import Store

from .chain import BURN_IN_SESSIONS, REPLAY_MARKET
from .field import (
    FieldSession,
    SECTOR_DIMENSION,
    replay_field,
    seven_dimension_score,
)
from .reference import (
    PRIMARY_EXIT,
    ExecutedTrade,
    classify,
    evaluation_session,
    load_trades,
)

# The dimensions regressed here: the app's eight less the dropped sector
# dimension, in the score's published order. Named off the app's own table so a
# change to the rubric's dimensions flows through unmodified (PRD user story 31).
REGRESSED_DIMENSIONS: tuple[tuple[str, int], ...] = tuple(
    (name, weight) for name, weight in _SCORE_DIMENSIONS if name != SECTOR_DIMENSION
)


@dataclass(frozen=True)
class FeatureVector:
    """One executed trade's reconstructed features at the evaluation session.

    ``detected`` is whether the app's detector fired on the name that night; only a
    detected trade carries score ``dimensions`` (seven, sector absent). ``mfe`` and
    ``r`` are the primary exit's maximum favourable excursion and realised R.
    ``stop_width_adr`` is the trade's *own* stop as a multiple of the night's ADR
    (his risk convention, PRD user story 20); ``adr_at_entry`` is that ADR (user
    story 21). Either is ``None`` when the ADR could not be computed (< 20 bars).
    """

    ticker: str
    entry_date: date
    eval_session: date | None
    detected: bool
    dimensions: list[Dimension]
    adr_at_entry: float | None
    stop_width_adr: float | None
    mfe: float | None
    r: float | None

    def hit(self, dimension: str) -> bool | None:
        """Whether ``dimension`` was hit on this trade, or ``None`` if undetected."""
        for d in self.dimensions:
            if d.dimension == dimension:
                return d.hit
        return None


@dataclass(frozen=True)
class DimensionStat:
    """One dimension's outcome regression against MFE, with its spread.

    ``correlation`` is the point-biserial correlation of the dimension's boolean
    against MFE across the detected trades; ``spread`` is the standard deviation of
    that boolean within the sample. ``untestable`` is set when the dimension shows
    no spread (or too few points) — its ``correlation`` is then ``None`` and the
    null is *untestable*, not absent (PRD user story 19).
    """

    dimension: str
    weight: int
    n: int
    hit_rate: float
    spread: float
    correlation: float | None
    untestable: bool


@dataclass(frozen=True)
class Distribution:
    """A five-number summary plus the mean, for a descriptive statistic.

    ``values`` is the sorted sample, so a caller can read a share at or below a
    threshold (:meth:`share_le`) — used to confirm or refute the #114 findings that
    quote a share (e.g. the fraction of stops at or under 1.0 ADR)."""

    n: int
    minimum: float
    p25: float
    median: float
    p75: float
    maximum: float
    mean: float
    values: tuple[float, ...]

    def share_le(self, threshold: float) -> float:
        """Share of the sample at or below ``threshold`` (0.0 on an empty sample)."""
        if not self.values:
            return 0.0
        return sum(1 for v in self.values if v <= threshold) / len(self.values)


# -- pure statistics (numpy-free, so it unit-tests without the network) --------


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    """The ``q``-quantile (``q`` in ``[0, 1]``) by linear interpolation.

    Type-7 / numpy-default interpolation between order statistics, so a hand-worked
    fixture value lands exactly. ``sorted_vals`` must be non-empty and ascending.
    """
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo, hi = floor(pos), ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def distribution(values: Iterable[float]) -> Distribution | None:
    """Summarise ``values`` as a :class:`Distribution`, or ``None`` if empty."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    return Distribution(
        n=n,
        minimum=ordered[0],
        p25=_percentile(ordered, 0.25),
        median=_percentile(ordered, 0.50),
        p75=_percentile(ordered, 0.75),
        maximum=ordered[-1],
        mean=sum(ordered) / n,
        values=tuple(ordered),
    )


def _pstdev(xs: Sequence[float]) -> float:
    """Population standard deviation (0.0 on fewer than two points)."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    return (sum((x - mean) ** 2 for x in xs) / n) ** 0.5


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson correlation, or ``None`` when either series has no variance."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx**0.5 * syy**0.5)


# -- the feature vector and the regression -------------------------------------


def build_feature_vector(
    *,
    ticker: str,
    entry_date: date,
    eval_session: date | None,
    det: Detection | None,
    prior_move: bool,
    adr_at_entry: float | None,
    stop_pct: float,
    mfe: float | None,
    r: float | None,
) -> FeatureVector:
    """Assemble one trade's feature vector at the evaluation session.

    A detected trade carries the seven surviving score dimensions
    (:func:`replay.field.seven_dimension_score`, sector struck); an undetected one
    carries no dimensions and is excluded from the regression. ``stop_width_adr``
    is his own stop as a multiple of the night's ADR — ``None`` when the ADR is
    unavailable or non-positive.
    """
    dimensions = (
        seven_dimension_score(det, prior_move=prior_move).breakdown
        if det is not None
        else []
    )
    stop_width_adr = None
    if adr_at_entry is not None and adr_at_entry > 0:
        stop_width_adr = (stop_pct / 100.0) / adr_at_entry
    return FeatureVector(
        ticker=ticker,
        entry_date=entry_date,
        eval_session=eval_session,
        detected=det is not None,
        dimensions=dimensions,
        adr_at_entry=adr_at_entry,
        stop_width_adr=stop_width_adr,
        mfe=mfe,
        r=r,
    )


def regress_dimensions(
    vectors: Iterable[FeatureVector],
    *,
    dimensions: tuple[tuple[str, int], ...] = REGRESSED_DIMENSIONS,
) -> list[DimensionStat]:
    """Regress each dimension against MFE across the *detected* trades.

    Only detected trades with an MFE contribute (an undetected trade has no
    dimensions to read). A dimension with no spread — every trade the same value —
    is labelled :attr:`DimensionStat.untestable`, its correlation ``None`` (PRD
    user story 19). Returns one stat per dimension, in the score's published order,
    the sector dimension absent (user story 6 of the sector drop).
    """
    usable = [v for v in vectors if v.detected and v.mfe is not None]
    ys = [v.mfe for v in usable]
    stats: list[DimensionStat] = []
    for name, weight in dimensions:
        xs = [1.0 if v.hit(name) else 0.0 for v in usable]
        n = len(xs)
        spread = _pstdev(xs)
        untestable = n < 2 or spread == 0.0
        correlation = None if untestable else _pearson(xs, ys)
        stats.append(
            DimensionStat(
                dimension=name,
                weight=weight,
                n=n,
                hit_rate=sum(xs) / n if n else 0.0,
                spread=spread,
                correlation=correlation,
                untestable=untestable,
            )
        )
    return stats


@dataclass(frozen=True)
class OutcomeRegression:
    """The A3 outcome-regression result: feature vectors, per-dimension stats and
    the descriptive distributions, with coverage against the blind-spot tickers.

    ``r_distribution`` is realised R reported alongside the regression, never its
    target (PRD user story 16). ``stop_width_adr_distribution`` and
    ``adr_distribution`` carry the two #114 preliminary findings for confirmation.
    ``blind_spot_count`` is the coverage figure every field-derived output must
    carry (user story 22).
    """

    exit_label: str
    feature_vectors: list[FeatureVector]
    dimension_stats: list[DimensionStat]
    mfe_distribution: Distribution | None
    r_distribution: Distribution | None
    stop_width_adr_distribution: Distribution | None
    adr_distribution: Distribution | None
    n_replayable: int
    n_detected: int
    blind_spot_count: int


def _adr_at(bars: list[Bar], as_of: date) -> float | None:
    """The app's ADR over the bars on or before ``as_of`` (``None`` if < 20 bars)."""
    up_to = [b for b in bars if b.session <= as_of]
    return _adr(up_to)


def _dim_hit(breakdown: list[Dimension], name: str) -> bool:
    for d in breakdown:
        if d.dimension == name:
            return d.hit
    return False


def build_regression(
    replayable: list[ExecutedTrade],
    calendar: list[date],
    fields: Iterable[FieldSession],
    store: Store,
    market: str,
    blind_spot_count: int,
    *,
    exit_label: str = PRIMARY_EXIT,
) -> OutcomeRegression:
    """Reconstruct a feature vector per trade over an already-built replayed field.

    The field-free core of :func:`run_regression`: given the fields the caller
    already computed, it reads each trade's detection off the field at its
    evaluation session and regresses the dimensions against MFE, so the one-process
    runner (:mod:`replay.study`) can share one field across all four analyses
    instead of replaying it per analysis.
    """
    by_session = {f.session: f for f in fields}

    bars_cache: dict[str, list[Bar]] = {}
    vectors: list[FeatureVector] = []
    for trade in replayable:
        if trade.ticker not in bars_cache:
            bars_cache[trade.ticker] = store.bars(market, trade.ticker)
        bars = bars_cache[trade.ticker]

        eval_session = evaluation_session(calendar, trade.entry_date)
        adr_at_entry = _adr_at(bars, eval_session) if eval_session is not None else None

        det: Detection | None = None
        prior_move = False
        field = by_session.get(eval_session) if eval_session is not None else None
        if field is not None:
            for sd in field.detections:
                if sd.symbol == trade.ticker:
                    det = sd.detection
                    prior_move = _dim_hit(sd.score.breakdown, "Prior move")
                    break

        outcome = trade.outcomes.get(exit_label)
        vectors.append(
            build_feature_vector(
                ticker=trade.ticker,
                entry_date=trade.entry_date,
                eval_session=eval_session,
                det=det,
                prior_move=prior_move,
                adr_at_entry=adr_at_entry,
                stop_pct=trade.stop_pct,
                mfe=outcome.mfe_pct if outcome else None,
                r=outcome.r if outcome else None,
            )
        )

    return OutcomeRegression(
        exit_label=exit_label,
        feature_vectors=vectors,
        dimension_stats=regress_dimensions(vectors),
        mfe_distribution=distribution(v.mfe for v in vectors if v.mfe is not None),
        r_distribution=distribution(v.r for v in vectors if v.r is not None),
        stop_width_adr_distribution=distribution(
            v.stop_width_adr for v in vectors if v.stop_width_adr is not None
        ),
        adr_distribution=distribution(
            v.adr_at_entry for v in vectors if v.adr_at_entry is not None
        ),
        n_replayable=len(replayable),
        n_detected=sum(1 for v in vectors if v.detected),
        blind_spot_count=blind_spot_count,
    )


def run_regression(
    trades: list[ExecutedTrade],
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
    exit_label: str = PRIMARY_EXIT,
) -> OutcomeRegression:
    """Reconstruct a feature vector per replayable trade and run the regression.

    Runs the forward chain and replayed field (:func:`replay.field.replay_field`)
    once, then for each replayable trade looks up its detection in the field at its
    evaluation session — the last session strictly before entry — and reads the
    seven score dimensions off it. The ADR at entry and the trade's own stop width
    in ADR are computed for *every* replayable trade, detected or not, so the two
    #114 distributions cover his whole entry set. Blind-spot trades get no vector
    (they are a blind spot, not a stage failure).
    """
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]
    calendar = store.sessions(market)

    fields = replay_field(
        store,
        market,
        trades=replayable,
        blind_spot_tickers=blind_spot_tickers,
        burn_in=burn_in,
        sessions=sessions,
    )
    blind_spot_count = (
        fields[0].blind_spot_count if fields else len(set(blind_spot_tickers))
    )
    return build_regression(
        replayable, calendar, fields, store, market, blind_spot_count,
        exit_label=exit_label,
    )


def _fmt_corr(stat: DimensionStat) -> str:
    if stat.untestable:
        return "untestable (no spread)"
    if stat.correlation is None:
        return "n/a"
    return f"{stat.correlation:+.3f}"


def _fmt_dist(label: str, dist: Distribution | None) -> str:
    if dist is None:
        return f"{label}: (no data)"
    return (
        f"{label}: n={dist.n} min={dist.minimum:.3f} p25={dist.p25:.3f} "
        f"median={dist.median:.3f} p75={dist.p75:.3f} max={dist.maximum:.3f} "
        f"mean={dist.mean:.3f}"
    )


def format_report(report: OutcomeRegression) -> str:
    """Human-readable summary: the per-dimension regression and the distributions."""
    lines = [
        f"outcome regression against MFE ({report.exit_label} exit)",
        f"replayable trades: {report.n_replayable}  detected: {report.n_detected}  "
        f"blind-spot coverage: {report.blind_spot_count} tickers missing",
        "",
        "dimension        weight  n   hit-rate  spread  corr(MFE)",
    ]
    for s in report.dimension_stats:
        lines.append(
            f"  {s.dimension:<14} x{s.weight}  {s.n:<3} {s.hit_rate:>7.1%}  "
            f"{s.spread:>5.3f}  {_fmt_corr(s)}"
        )
    lines += [
        "",
        _fmt_dist("realised R (descriptive)", report.r_distribution),
        _fmt_dist("stop width in ADR       ", report.stop_width_adr_distribution),
        _fmt_dist("ADR at entry            ", report.adr_distribution),
    ]
    if report.stop_width_adr_distribution is not None:
        lines.append(
            f"  stops at or under 1.0 ADR: "
            f"{report.stop_width_adr_distribution.share_le(1.0):.1%}"
        )
    return "\n".join(lines)


# -- command-line entry point -------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the outcome regression over the replay store and print the report.

    Thin CLI over the pure functions above (one entry point per study, PRD user
    story 30). Run as ``python -m replay.regression --store data/replay.duckdb``.
    """
    from .reference import DEFAULT_REFERENCE_JSON

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=REPLAY_MARKET)
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        report = run_regression(trades, store, args.market)
    finally:
        store.close()

    print(format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
