"""The one-process runner that reproduces the whole study (PRD #114, issue #131).

Every earlier ticket landed one analysis with its own ``python -m`` entry point,
and each of those rebuilds the entire 947-session forward chain from scratch — so
reproducing the study meant four independent rebuilds of the most expensive thing
in it. This runner builds the field **once** and computes all four analyses
against it:

- the A1 funnel/recall walk (:mod:`replay.funnel`),
- the A2 placement in the star-ranked field (:mod:`replay.placement`),
- the A3 outcome regression against MFE (:mod:`replay.regression`), and
- the A3 selection contrast (:mod:`replay.contrast`).

**One chain, one detection pass, four analyses.** The forward chain (universe +
ranks per session) is replayed once (:func:`replay.chain.replay_chain`) and the
per-session detection pass runs once over it (:func:`replay.field.build_field_sessions`);
the funnel reads the chain's ranks and the other three read the built field, none
rebuilding. The taken/not-taken flags differ between callers but never change
which detections exist or their order, so a single shared field is correct for all
four (issue #131).

**Progress and an ETA, never a silent hour.** The first attempt at this study was
killed at 60 minutes precisely because it had printed nothing — a silent long run
is indistinguishable from a hung one. So the chain and the detection pass both call
back per session, and the CLI prints a throttled line with a running count and an
ETA (:func:`progress_printer`). A failure surfaces as an exception rather than a
hang.

**Two outputs.** The human-readable reports (:func:`format_study`) are the four
analyses' own ``format_report`` blocks, one after another. The machine-readable
results file (:func:`write_results`) carries every result row — in particular the
funnel rows with their per-lookback decile detail (#133) — so the decile
decomposition can be recomputed without another rebuild.

Nothing here touches the live store or the app: the runner reads and writes only
the purpose-built replay store, and imports :mod:`screener` read-only (user stories
27–29).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Sequence, TextIO

from screener.store import Store

from .caching_store import CachingStore
from .chain import BURN_IN_SESSIONS, REPLAY_MARKET, replay_chain
from .contrast import SelectionContrast, build_contrast
from .contrast import format_report as format_contrast
from .field import build_field_sessions
from .funnel import FunnelReport, build_funnel_report
from .funnel import format_report as format_funnel
from .placement import PlacementReport, StarDistribution, build_placement_report
from .placement import format_report as format_placement
from .reference import (
    DEFAULT_REFERENCE_JSON,
    ExecutedTrade,
    ReferenceReport,
    assert_matches_reference,
    build_report,
    classify,
    load_trades,
)
from .regression import Distribution, OutcomeRegression, build_regression
from .regression import format_report as format_regression

# ``progress(phase, i, total, session)`` — ``phase`` is "chain" or "field", ``i``
# is the 1-based session index, ``total`` the session count for that phase.
Progress = Callable[[str, int, int, date], None]


@dataclass(frozen=True)
class StudyResult:
    """The whole study's result: coverage plus all four analyses over one field.

    ``coverage`` is the reference-set count report (the survivorship hole);
    ``funnel``/``placement``/``regression``/``contrast`` are the four analyses'
    result objects, each computed against the same built field. ``chain_sessions``
    and ``measured_sessions`` record the size of the forward pass (burn-in included,
    and excluded) so the run's shape is a fact on the result, not an assumption.
    """

    market: str
    coverage: ReferenceReport
    funnel: FunnelReport
    placement: PlacementReport
    regression: OutcomeRegression
    contrast: SelectionContrast
    chain_sessions: int
    measured_sessions: int


def run_study(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    trades: list[ExecutedTrade],
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
    progress: Progress | None = None,
) -> StudyResult:
    """Reproduce the whole study against one built field.

    Replays the forward chain and the per-session detection pass exactly once, then
    computes the A1 funnel, A2 placement and both A3 analyses against them. The
    ``progress`` callback (if given) is invoked per session for the chain and the
    detection pass, so a long run reports rather than hanging silently. Returns a
    :class:`StudyResult` carrying coverage and all four analyses.
    """
    store = CachingStore.wrap(store)
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]
    calendar = store.sessions(market)
    coverage = build_report(trades, store, market=market)
    blind_spots = list(blind_spot_tickers) or coverage.blind_spot_ticker_list

    def phase_progress(phase: str) -> Callable[[int, int, date], None] | None:
        if progress is None:
            return None
        return lambda i, total, session: progress(phase, i, total, session)

    # One forward pass: universe + ranks per session, computed once…
    chain = replay_chain(
        store,
        market,
        blind_spot_tickers=blind_spots,
        burn_in=burn_in,
        sessions=sessions,
        progress=phase_progress("chain"),
    )
    # …and one detection pass over it, building the field the three field-analyses
    # share. The funnel reads the chain's ranks directly and needs no field.
    fields = build_field_sessions(
        store, market, chain, trades=replayable, progress=phase_progress("field")
    )
    blind_spot_count = chain[0].blind_spot_count if chain else len(set(blind_spots))

    funnel = build_funnel_report(
        classified, calendar, chain, store, market, blind_spot_tickers=blind_spots
    )
    placement = build_placement_report(replayable, calendar, fields, blind_spot_count)
    regression = build_regression(
        replayable, calendar, fields, store, market, blind_spot_count
    )
    contrast = build_contrast(fields, blind_spot_count=blind_spot_count)

    return StudyResult(
        market=market,
        coverage=coverage,
        funnel=funnel,
        placement=placement,
        regression=regression,
        contrast=contrast,
        chain_sessions=len(chain) + burn_in,
        measured_sessions=len(chain),
    )


# -- human-readable reports ---------------------------------------------------


def format_study(result: StudyResult) -> str:
    """The four analyses' own report blocks, one after another, with a header."""
    blocks = [
        f"Qullamägi replay study — one-process reproduction ({result.market})",
        f"chain: {result.chain_sessions} sessions "
        f"({result.chain_sessions - result.measured_sessions} burn-in, "
        f"{result.measured_sessions} measured)",
        "",
        "== coverage ==",
        _format_coverage(result.coverage),
        "",
        "== A1 funnel ==",
        format_funnel(result.funnel),
        "",
        "== A2 placement ==",
        format_placement(result.placement),
        "",
        "== A3 outcome regression ==",
        format_regression(result.regression),
        "",
        "== A3 selection contrast ==",
        format_contrast(result.contrast),
    ]
    return "\n".join(blocks)


def _format_coverage(report: ReferenceReport) -> str:
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


def write_reports(result: StudyResult, path: str | Path) -> None:
    """Write the human-readable reports for all four analyses to ``path``."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_study(result) + "\n")


# -- machine-readable results -------------------------------------------------


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _star_dist(dist: StarDistribution) -> dict:
    # Star values are multiples of 0.5; JSON object keys must be strings. Emitted
    # high-to-low rather than in the order the scores happened to arrive: this file
    # is committed beside the findings, so two runs of the same field must produce
    # the same bytes or the diff reports churn where nothing moved.
    return {
        "total": dist.total,
        "counts": {str(k): dist.counts[k] for k in sorted(dist.counts, reverse=True)},
    }


def _distribution(dist: Distribution | None) -> dict | None:
    if dist is None:
        return None
    return {
        "n": dist.n,
        "min": dist.minimum,
        "p25": dist.p25,
        "median": dist.median,
        "p75": dist.p75,
        "max": dist.maximum,
        "mean": dist.mean,
    }


def study_to_dict(result: StudyResult) -> dict:
    """A JSON-serialisable dict of every result row (#131 machine-readable output).

    The funnel rows carry their full per-lookback decile detail (#133), so the
    decile decomposition — and any later re-slice of it — is recomputable from this
    file alone, without another rebuild.
    """
    cov = result.coverage
    f = result.funnel
    p = result.placement
    reg = result.regression
    con = result.contrast

    return {
        "market": result.market,
        "chain_sessions": result.chain_sessions,
        "measured_sessions": result.measured_sessions,
        "coverage": {
            "total_rows": cov.total_rows,
            "rows_with_outcomes": cov.rows_with_outcomes,
            "distinct_tickers": cov.distinct_tickers,
            "blind_spot_tickers": cov.blind_spot_tickers,
            "blind_spot_trades": cov.blind_spot_trades,
            "blind_spot_r_share": cov.blind_spot_r_share,
            "blind_spot_ticker_list": list(cov.blind_spot_ticker_list),
        },
        "funnel": {
            "stages": list(f.stages),
            "blind_spot_count": f.blind_spot_count,
            "continuation_count": f.continuation_count,
            "condition_counts": dict(f.condition_counts),
            "recall": {
                stage.stage: {
                    "passed": stage.passed,
                    "total": stage.total,
                    "passed_ex_continuation": stage.passed_ex_continuation,
                    "total_ex_continuation": stage.total_ex_continuation,
                }
                for stage in (f.liquidity, f.decile, f.detection)
            },
            "decile_decomposition": {
                "total_misses": f.decile_decomposition.total_misses,
                "coverage_gap": f.decile_decomposition.coverage_gap,
                "recovered_by_five": f.decile_decomposition.recovered_by_five,
                "outside_any_union": f.decile_decomposition.outside_any_union,
            },
            "cluster_characterisation": {
                "total_misses": f.cluster_characterisation.total_misses,
                "continuation": f.cluster_characterisation.continuation,
                "fresh": f.cluster_characterisation.fresh,
                "marginal": f.cluster_characterisation.marginal,
                "far": f.cluster_characterisation.far,
                "range_distribution": _distribution(
                    f.cluster_characterisation.range_distribution
                ),
                "prior_distance_distribution": _distribution(
                    f.cluster_characterisation.prior_distance_distribution
                ),
            },
            "rows": [
                {
                    "ticker": r.ticker,
                    "entry_date": _iso(r.entry_date),
                    "eval_session": _iso(r.eval_session),
                    "liquidity_pass": r.liquidity_pass,
                    "decile_present": r.decile_present,
                    "decile_pass": r.decile_pass,
                    "decile_pass_five": r.decile_pass_five,
                    "eval_percentiles": dict(r.eval_percentiles),
                    "decile_verdicts": dict(r.decile_verdicts),
                    "detection_pass": r.detection_pass,
                    "failed_condition": r.failed_condition,
                    "first_failing_stage": r.first_failing_stage,
                    "entry_session_break": r.entry_session_break,
                    "continuation": r.continuation,
                    "median_dollar_volume": r.median_dollar_volume,
                    "range_3bar_adr": r.range_3bar_adr,
                    "sessions_since_prior_entry": r.sessions_since_prior_entry,
                }
                for r in f.rows
            ],
        },
        "placement": {
            "board_size": p.board_size,
            "blind_spot_count": p.blind_spot_count,
            "scope": p.scope,
            "in_field_count": p.in_field_count,
            "top_thirty_count": p.top_thirty_count,
            "picks": _star_dist(p.picks),
            "field": _star_dist(p.field),
            # The same field re-scored under every rubric version (#136), each
            # stamped, so a rubric change is separable from a field change.
            "by_rubric": [
                {
                    "rubric_version": r.rubric_version,
                    "picks": _star_dist(r.picks),
                    "field": _star_dist(r.field),
                    "top_thirty": r.top_thirty,
                }
                for r in p.by_rubric
            ],
            "placements": [
                {
                    "ticker": pl.ticker,
                    "entry_date": _iso(pl.entry_date),
                    "eval_session": _iso(pl.eval_session),
                    "in_field": pl.in_field,
                    "top_thirty": pl.top_thirty,
                    "stars": pl.stars,
                }
                for pl in p.placements
            ],
        },
        "regression": {
            "exit_label": reg.exit_label,
            "n_replayable": reg.n_replayable,
            "n_detected": reg.n_detected,
            "blind_spot_count": reg.blind_spot_count,
            "dimension_stats": [
                {
                    "dimension": s.dimension,
                    "weight": s.weight,
                    "n": s.n,
                    "hit_rate": s.hit_rate,
                    "spread": s.spread,
                    "correlation": s.correlation,
                    "untestable": s.untestable,
                }
                for s in reg.dimension_stats
            ],
            "mfe_distribution": _distribution(reg.mfe_distribution),
            "r_distribution": _distribution(reg.r_distribution),
            "stop_width_adr_distribution": _distribution(
                reg.stop_width_adr_distribution
            ),
            "adr_distribution": _distribution(reg.adr_distribution),
            "feature_vectors": [
                {
                    "ticker": v.ticker,
                    "entry_date": _iso(v.entry_date),
                    "eval_session": _iso(v.eval_session),
                    "detected": v.detected,
                    "dimension_hits": {d.dimension: d.hit for d in v.dimensions},
                    "adr_at_entry": v.adr_at_entry,
                    "stop_width_adr": v.stop_width_adr,
                    "mfe": v.mfe,
                    "r": v.r,
                }
                for v in reg.feature_vectors
            ],
        },
        "contrast": {
            "n_executed": con.n_executed,
            "n_not_taken": con.n_not_taken,
            "blind_spot_count": con.blind_spot_count,
            "comparison_group_note": con.comparison_group_note,
            "precision_note": con.precision_note,
            "dimension_contrasts": [
                {
                    "dimension": c.dimension,
                    "weight": c.weight,
                    "taken_n": c.taken_n,
                    "taken_hit_rate": c.taken_hit_rate,
                    "taken_spread": c.taken_spread,
                    "not_taken_n": c.not_taken_n,
                    "not_taken_hit_rate": c.not_taken_hit_rate,
                    "not_taken_spread": c.not_taken_spread,
                    "combined_spread": c.combined_spread,
                    "untestable_within_executed": c.untestable_within_executed,
                    "testable_in_contrast": c.testable_in_contrast,
                    "testability_restored": c.testability_restored,
                }
                for c in con.dimension_contrasts
            ],
        },
    }


def write_results(result: StudyResult, path: str | Path) -> None:
    """Write the machine-readable results file to ``path`` (stable, 2-space JSON)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(study_to_dict(result), indent=2) + "\n")


def load_results(path: str | Path) -> dict:
    """Read a machine-readable results file back (the inverse of :func:`write_results`)."""
    return json.loads(Path(path).read_text())


# -- progress printing --------------------------------------------------------


def _fmt_eta(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def progress_printer(stream: TextIO, *, every_seconds: float = 5.0) -> Progress:
    """A throttled progress callback that prints a count and an ETA to ``stream``.

    Prints at most once every ``every_seconds`` per phase (and always the final
    session of a phase), so a 30-minute run prints steadily without flooding the
    log. The ETA is a straight-line projection from the elapsed time and the share
    of sessions done — enough to tell a slow run from a hung one.
    """
    started: dict[str, float] = {}
    last: dict[str, float] = {}

    def report(phase: str, i: int, total: int, session: date) -> None:
        now = time.monotonic()
        started.setdefault(phase, now)
        elapsed = now - started[phase]
        is_last = i >= total
        if not is_last and now - last.get(phase, 0.0) < every_seconds:
            return
        last[phase] = now
        rate = i / elapsed if elapsed > 0 else 0.0
        eta = (total - i) / rate if rate > 0 else 0.0
        pct = i / total if total else 1.0
        stream.write(
            f"[{phase}] {i}/{total} ({pct:.0%})  {session}  "
            f"elapsed {_fmt_eta(elapsed)}  ETA {_fmt_eta(eta)}\n"
        )
        stream.flush()

    return report


# -- command-line entry point -------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run coverage plus all four analyses against one built store, and write both
    outputs.

    The single documented command that reproduces the whole study (issue #131):

        python -m replay.study --store data/replay.duckdb \\
            --out-report references/replay_study_report.txt \\
            --out-json references/replay_study_results.json

    Coverage and the blind-spot list are recomputed from the reference set, and by
    default asserted against the #114 figures (``--no-drift-check`` to skip, needed
    for a synthetic reference). Progress and an ETA print to stderr while the chain
    runs, so a silent hour is distinguishable from a hang.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=REPLAY_MARKET)
    parser.add_argument("--burn-in", type=int, default=BURN_IN_SESSIONS,
                        help="burn-in sessions before the first measured session")
    parser.add_argument("--out-report", default="references/replay_study_report.txt",
                        help="where to write the human-readable reports")
    parser.add_argument("--out-json", default="references/replay_study_results.json",
                        help="where to write the machine-readable results file")
    parser.add_argument("--no-drift-check", action="store_true",
                        help="skip the assertion of coverage against the #114 figures")
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        result = run_study(
            store,
            args.market,
            trades=trades,
            burn_in=args.burn_in,
            progress=progress_printer(sys.stderr),
        )
    finally:
        store.close()

    if not args.no_drift_check:
        assert_matches_reference(result.coverage)

    write_reports(result, args.out_report)
    write_results(result, args.out_json)

    print(format_study(result))
    print(f"\nwrote {args.out_report}")
    print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
