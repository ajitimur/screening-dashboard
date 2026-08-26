"""Does the rubric rank, out of sample? (issue #194, PRD #182 Phase 5).

Outcomes bucketed by star-score decile, per market and per year, with n on every
bucket and significance bootstrapped clustered by symbol. The question is the one
findings §4a raised and could not answer: **does a higher score actually predict a
better result?**

Why this is not §4a again
-------------------------
§4a measured whether the star score separates the trader's *picks* from the field
— his 104 in-field trades against 14,239 detections — and found his picks at
≥3.5★ at 1.63× the field's rate — a gap of **+5.59pp**, at an exact-binomial
**p = 0.055**.
It refused to read that as "the rubric ranks", for a reason that is structural
rather than a caveat: the v2 weights were derived from the selection contrast on
*that* field, and A2 then asked whether they reproduced the separation they had
been fitted to. A rubric fitted to a separation will reproduce it. That is a fit
statistic, and it was marginal even so.

Here the outcome variable is **R** — what the trade actually paid, mechanically,
under the contract's own entry, stop and exit. No weight was fitted to it, no
detection's score could see it, and the trades are ones the trader never took over
a window his record does not cover. That independence is the whole point of the
measurement, so §4a's figures ride on the payload (:data:`IN_SAMPLE_GAP`) with the
reason they are not comparable rather than being left for a reader to line up. The
two are also different *shapes*: §4a compares a rate of scores between two
populations, this compares a mean outcome between score bands of one.

Deciles of a coarse score, and why a tie never splits
-----------------------------------------------------
The replayed score is **seven dimensions of eight integral points** — the app's
nine minus the struck ``Sector`` row (findings §1) — so its distribution takes at
most nine values and true deciles do not exist. Cutting them anyway would put two
trades scoring identically into different buckets and then report the difference
between those buckets, which would be a difference in sort order and nothing else.

So a score value is **atomic**: :func:`bands` walks the scores upward, closes a
bucket when the cumulative share crosses a decile boundary, and never splits a
value across two. The buckets therefore collapse to fewer than ten, and each one
names the decile positions it covers — a band spanning deciles 1–8 says so, which
is the honest reading of a distribution 80% of which sits on one score.

The cut is made **once per market on the whole measured window** and every year is
reported against it. Cutting per year would make "the top bucket" a different score
band in every row, so a year-on-year comparison would be a comparison of two
different questions.

What is reported, and what the verdict rule is
----------------------------------------------
Three things, because one of them alone would mislead:

* **Every bucket's after-cost expectancy**, with its n, its symbol count and its
  clustered interval — a monotone ladder is visible here and nowhere else.
* **The gap**, top band minus bottom band. The sharpest statement of the claim.
* **The rank correlation** (Spearman's rho, ties averaged) over the whole cohort,
  which the gap cannot give: a rubric whose extremes separate while its middle is
  noise is a different finding from one that ranks throughout.

:data:`VERDICT_RULE` reads the verdict off both, and requires both to agree.
Neither alone is enough: a gap can be carried by one hot name at the top, and a rho
can be positive and tiny. A cohort whose top or bottom band is too thin to
bootstrap gets :data:`VERDICT_TOO_THIN` rather than a number, because the gap is
computed *between* those two bands and an interval on a single-symbol band prints
certainty it has not earned.

Costs, arms and clustering are the metric's
-------------------------------------------
Nothing here re-implements arithmetic :mod:`backtest.metric` already owns. The
after-cost R of a trade, the per-market costs, the cell shape behind every bucket
(win rate, R-distribution, clustered interval) and the year span are all called
from that module, so the ranking and the headline cannot disagree about what a
trade paid. The arm is :data:`~backtest.metric.PRIMARY_ARM` for the same reason:
the pre-registered metric is arm B's, and bucketing arm A's trades under the same
banner would report a ranking of a result no headline names.

The one piece of arithmetic that is new is the bootstrap over an arbitrary
*statistic* (:func:`bootstrap_symbol_statistic`). The metric's bootstrap resamples
clusters and takes their pooled **mean**, which cannot express a gap between two
bands or a rank correlation — those need the whole resampled cohort, not a list of
numbers. It resamples the same unit, by symbol, for the same reason: a stock
throwing three signals in a fortnight contributes three correlated rows, and
resampling rows would count them as three independent observations and flatter
every p-value.

What this measurement does not do
---------------------------------
It does not fire or clear the kill criterion — that is the pre-registered metric's
(:mod:`backtest.metric`), and the contract's ``decision.kill`` cell draws the line.
This is the measurement that says what a *fired* kill criterion leaves standing:
whether the app's claim reduces to **ranking what a human selects** rather than
selecting on its own. And it is one more view of a dataset that already had nine
before any threshold was swept (:data:`MULTIPLE_TESTING_NOTE`), pre-specified by
#194 rather than chosen after the fact.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from replay.field import SEVEN_DIM_LABEL, SEVEN_DIM_MAX_POINTS, SevenDimScore
from screener.score import DIMENSIONS
from screener.store import Store

from .contract import DEFAULT_CONTRACT, SCOPE_MARKETS_KEY, RunContract
from .denominator import DenominatorStore, denominator_path
from .metric import (
    BOOTSTRAP_CLUSTER,
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_MIN_CLUSTERS,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    PRIMARY_ARM,
    after_cost_r,
    check_costs,
    expectancy_cell,
    measured_years,
    quantile,
)
from .result import stamp_result
from .run import ContractDrift
from .simulate import SimulatedTrade, simulate_market

# -- the score these buckets are cut on ---------------------------------------

# The replayed score, named on every output. Seven dimensions of eight points: the
# app's nine minus the struck ``Sector`` row, which the store cannot recover
# because the labels table carries no history (findings §1, PRD "Out of Scope").
SCORE_LABEL = SEVEN_DIM_LABEL
SCORE_DIMENSIONS = 7
SCORE_MAX_POINTS = SEVEN_DIM_MAX_POINTS
SCORE_MAX_STARS = SCORE_MAX_POINTS / 2

# The app's own ceiling, derived from the live weight table rather than typed, so a
# weight change moves it here too. Carried beside the replayed one because ≥3.5★
# is 7 of 8 on this scale and 7 of 9 on the app's, and a band read off the wrong
# ceiling mislabels every bucket in the report.
APP_MAX_POINTS = sum(weight for _, weight in DIMENSIONS)

SCORE_NOTE = (
    f"the {SCORE_LABEL} — {SCORE_DIMENSIONS} dimensions of {SCORE_MAX_POINTS} "
    f"points, ceiling {SCORE_MAX_STARS:.1f}★ — and not the app's "
    f"{APP_MAX_POINTS}-point score: the replay strikes Sector, so a band here is "
    "one dimension short of the one the product prints"
)


def check_seven_dimension_score(score: SevenDimScore) -> None:
    """Refuse a score that is not the seven-dimension replayed one.

    A nine-point row arriving here means the field was scored by something other
    than :func:`replay.field.seven_dimension_score`, and reading it as a
    seven-dimension one would silently re-base every band — 6 points is 3.0★ on
    one scale and 3.0★ on the other while meaning a different sixth of the rubric.
    A mislabelled band is invisible in the output, so it is refused at the door.
    """
    if score.max_points != SCORE_MAX_POINTS or score.label != SCORE_LABEL:
        raise ContractDrift(
            f"a bucket is cut on the {SCORE_LABEL} out of {SCORE_MAX_POINTS} "
            f"points; {score.label!r} out of {score.max_points} arrived, and "
            "reading one as the other re-bases every band"
        )


# -- §4a, carried so the two measurements are never conflated ------------------

# The in-sample figure this measurement exists to replace, quoted from
# `references/qullamaggie-replay-findings.md` §4a rather than recomputed. It rides
# on the payload because the danger is not that a reader disbelieves §4a — it is
# that a reader lines the two gaps up as though they answered the same question.
IN_SAMPLE_GAP: dict[str, Any] = {
    "source": "findings §4a — the paired A2 re-run (#136), under rubric v2",
    "measure": "share of scores at >= 3.5 stars, his picks against the field",
    "picks_rate": 0.1442,
    "picks_n": 104,
    "field_rate": 0.0883,
    "field_n": 14239,
    "gap_pp": 5.59,
    "p_value": 0.055,
    "test": "exact binomial",
    "why_it_is_not_this_measurement": (
        "in-sample by construction: v2's weights were fitted to the selection "
        "contrast on that same field, so A2 asked whether they reproduced a "
        "separation they had been built from — a fit statistic, and marginal at "
        "p = 0.055 even so. It also measures a different thing: a rate of scores "
        "between his picks and the field, where this measures the outcome R paid "
        "by score band, on trades nobody selected"
    ),
}

OUT_OF_SAMPLE_NOTE = (
    "the outcome variable here is R after costs, which no weight was fitted to "
    "and no detection's score could see; the field is taken mechanically over a "
    "window his record does not cover"
)

# Story 100: three exit arms and three regime states are nine views of one dataset
# before any threshold is swept, and this is another. Stated on the output rather
# than in this docstring, because a multiple-testing budget a reader cannot see is
# a budget nobody is keeping.
MULTIPLE_TESTING_NOTE = (
    "one more view of a dataset that already carried nine before any sweep; "
    "pre-specified by #194 and computed once, not chosen after the fact"
)

# What a fired kill criterion leaves standing. The criterion itself is the
# pre-registered metric's (``decision.kill``), and nothing here fires it.
KILL_CRITERION_NOTE = (
    "this measurement does not fire or clear the kill criterion — that is the "
    "pre-registered metric's. It is what decides, if the criterion fires, whether "
    "the app's claim reduces to ranking what a human selects rather than "
    "selecting on its own"
)


# -- the cut ------------------------------------------------------------------

DECILES = 10


@dataclass(frozen=True)
class Band:
    """One bucket of the cut: a contiguous run of scores, and the deciles it covers.

    ``deciles`` is what makes the tie rule readable rather than merely correct. A
    band holding 80% of the cohort covers deciles 1–8 and says so, so a reader sees
    a collapsed distribution instead of a report that quietly has three buckets
    where it promised ten.

    ``low_points`` and ``high_points`` are inclusive and equal whenever the band is
    a single score, which is the common case at the edges.
    """

    index: int
    deciles: tuple[int, ...]
    low_points: int
    high_points: int

    @property
    def low_stars(self) -> float:
        return self.low_points / 2

    @property
    def high_stars(self) -> float:
        return self.high_points / 2

    @property
    def label(self) -> str:
        """The band as a reader reads it — in stars, which is what the app prints."""
        if self.low_points == self.high_points:
            return f"{self.low_stars:.1f}★"
        return f"{self.low_stars:.1f}–{self.high_stars:.1f}★"

    def holds(self, points: int) -> bool:
        return self.low_points <= points <= self.high_points


@dataclass(frozen=True)
class ScoredTrade:
    """One simulated trade beside the score of the detection that produced it.

    The two are joined rather than stored together because the simulator has no
    business carrying a score — it takes an entry and an exit and knows nothing
    about the rubric — and the denominator's detection row is where the score
    already lives. :func:`scored_trades` performs the join and refuses a trade
    whose score is missing.
    """

    trade: SimulatedTrade
    score: SevenDimScore

    @property
    def symbol(self) -> str:
        return self.trade.symbol

    @property
    def market(self) -> str:
        return self.trade.market

    @property
    def points(self) -> int:
        return self.score.points

    @property
    def year(self) -> int:
        """The year of the **entry** session — the year the decision was taken.

        The same attribution :mod:`backtest.metric` uses, and for the same reason:
        attributing by exit would move a trade's year with the exit rule, which is
        the one thing the arms vary.
        """
        return self.trade.entry.session.year


def bands(cohort: Sequence[ScoredTrade], *, deciles: int = DECILES) -> tuple[Band, ...]:
    """The cut: score bands in ascending order, no score split across two of them.

    Walks the distinct scores upward, accumulating until the cumulative share
    crosses the next decile boundary, then closes a band covering every decile
    position it reached. A score that carries more than a tenth of the cohort
    therefore swallows several deciles at once and the result has fewer than
    ``deciles`` bands — which is a fact about an eight-point score, not a defect in
    the cut.

    A function of the score distribution alone, so shuffling the cohort moves
    nothing: a cut that read arrival order would produce different buckets on a
    re-run of the same data with nothing in the output to show it.
    """
    if not cohort:
        return ()
    counts = Counter(s.points for s in cohort)
    total = sum(counts.values())
    out: list[Band] = []
    cumulative = 0
    low: int | None = None
    next_decile = 1
    for points in sorted(counts):
        low = points if low is None else low
        cumulative += counts[points]
        reached = min(deciles, cumulative * deciles // total)
        if reached >= next_decile:
            out.append(
                Band(
                    index=len(out) + 1,
                    deciles=tuple(range(next_decile, reached + 1)),
                    low_points=low,
                    high_points=points,
                )
            )
            next_decile = reached + 1
            low = None
    return tuple(out)


# -- the rows the statistics run on -------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """One closed trade reduced to what a statistic needs: its symbol, score and R.

    A flat row rather than a :class:`ScoredTrade`, because the bootstrap resamples
    tens of thousands of times and every statistic below reads exactly these three
    fields. Costs are already applied — there is one place a trade becomes a
    number, :func:`~backtest.metric.after_cost_r`, and this is where it is called.
    """

    symbol: str
    points: int
    r: float


def outcomes(
    cohort: Sequence[ScoredTrade], contract: RunContract
) -> list[Outcome]:
    """The cohort's **closed** trades as rows, after costs, in cohort order.

    A trade still running has no R, and marking one to the last close would invent
    an exit the rules never gave — systematically, for every name still open — so
    it contributes to a bucket's ``trades`` count and to nothing else.
    """
    rows: list[Outcome] = []
    for scored in cohort:
        r = after_cost_r(scored.trade, contract)
        if r is None:
            continue
        rows.append(Outcome(symbol=scored.symbol, points=scored.points, r=r))
    return rows


def symbol_clusters(
    cohort: Sequence[ScoredTrade], contract: RunContract
) -> list[tuple[Outcome, ...]]:
    """The closed outcomes grouped one cluster per symbol, symbol order.

    The unit of independence. Ordered by symbol so a resample under a fixed seed is
    reproducible — clusters arriving in insertion order would move the interval
    with the order the trades happened to be read in.
    """
    grouped: dict[str, list[Outcome]] = {}
    for row in outcomes(cohort, contract):
        grouped.setdefault(row.symbol, []).append(row)
    return [tuple(grouped[symbol]) for symbol in sorted(grouped)]


# -- the two statistics -------------------------------------------------------


def top_minus_bottom(
    rows: Sequence[Outcome], cut: Sequence[Band]
) -> float | None:
    """The gap: the top band's mean R minus the bottom band's, or ``None``.

    ``None`` when either edge band is empty — which a resample can easily produce
    — because a gap against a band nobody drew is not zero, it is undefined, and
    the difference matters to every interval built on it.
    """
    if len(cut) < 2:
        return None
    top = [row.r for row in rows if cut[-1].holds(row.points)]
    bottom = [row.r for row in rows if cut[0].holds(row.points)]
    if not top or not bottom:
        return None
    return sum(top) / len(top) - sum(bottom) / len(bottom)


def _ranks(values: Sequence[float]) -> list[float]:
    """Fractional ranks, ties taking the average of the positions they occupy.

    Ties are the common case on an eight-point score, so this is the whole of why
    the correlation is meaningful here: breaking them by arrival order would make
    rho a function of the sort.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = average
        i = j + 1
    return out


def rank_correlation(rows: Sequence[Outcome]) -> float | None:
    """Spearman's rho between score and outcome — the whole-cohort ranking claim.

    Reported beside the gap because the two can disagree, and the disagreement is
    informative: a rubric whose extremes separate while its middle is noise is a
    different finding from one that ranks throughout, and the gap alone cannot
    tell them apart.

    ``None`` when either side has no variance — one score, or every trade paying
    the same. There is no correlation to report there, and a zero would read as
    "measured and found nothing" rather than "not measurable".
    """
    if len(rows) < 2:
        return None
    x = _ranks([float(row.points) for row in rows])
    y = _ranks([row.r for row in rows])
    n = len(rows)
    mx, my = sum(x) / n, sum(y) / n
    dx = [a - mx for a in x]
    dy = [b - my for b in y]
    sx = sum(a * a for a in dx) ** 0.5
    sy = sum(b * b for b in dy) ** 0.5
    if sx == 0.0 or sy == 0.0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


# -- the bootstrap, over a statistic rather than over a mean -------------------


def bootstrap_symbol_statistic(
    clusters: Sequence[Sequence[Outcome]],
    statistic: Callable[[Sequence[Outcome]], float | None],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
    cluster: str = BOOTSTRAP_CLUSTER,
    min_clusters: int = BOOTSTRAP_MIN_CLUSTERS,
) -> dict[str, Any]:
    """A clustered bootstrap of an arbitrary statistic over the pooled rows.

    :func:`~backtest.metric.bootstrap_expectancy` resamples the same unit and takes
    the pooled **mean**; a gap between two bands and a rank correlation are not
    means of anything, so they need the resampled cohort itself. Hence a second
    entry point rather than a second bootstrap: the seed, the resample count, the
    confidence level, the cluster floor and the reported fields are all the
    metric's, so two intervals in one report can never have been built differently.

    Each resample draws ``len(clusters)`` clusters **with replacement** and pools
    every row inside them, so a symbol is in or out as a whole. ``p_value`` is
    one-sided — the share of resampled statistics at or below zero — which is the
    shape of the claim: the question is whether a higher score pays *more*, not
    whether it pays differently.

    A resample the statistic cannot evaluate (an empty edge band, no variance) is
    counted under ``undefined`` and left out of the interval rather than defaulted
    to zero, because a resample that could not answer is not a resample that
    answered no. If every resample is undefined the interval is refused outright.

    Below ``min_clusters`` no interval is reported at all, for the reason the
    metric records: one symbol resampled two thousand times returns its own mean
    two thousand times, which prints as a zero-width interval at p = 0 and is one
    independent observation.
    """

    n = len(clusters)
    pooled = [row for cluster_rows in clusters for row in cluster_rows]
    body: dict[str, Any] = {
        "cluster": cluster,
        "clusters": n,
        "observations": len(pooled),
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
        "min_clusters": min_clusters,
        "undefined": 0,
        "suppressed": None,
    }
    empty = {**body, "ci_low": None, "ci_high": None, "p_value": None}
    if n < min_clusters:
        return {
            **empty,
            "suppressed": (
                f"{n} {cluster}s is fewer than {min_clusters}: too thin for an "
                "interval, and a degenerate one would read as significance"
            ),
        }

    rng = random.Random(seed)
    indices = range(n)
    drawn_values: list[float] = []
    undefined = 0
    for _ in range(resamples):
        drawn = [row for i in indices for row in clusters[rng.choice(indices)]]
        value = statistic(drawn)
        if value is None:
            undefined += 1
            continue
        drawn_values.append(value)
    if not drawn_values:
        return {
            **empty,
            "undefined": undefined,
            "suppressed": (
                f"every resample was undefined over {n} {cluster}s: no interval "
                "exists to report"
            ),
        }

    drawn_values.sort()
    tail = (1.0 - confidence) / 2.0
    return {
        **body,
        "undefined": undefined,
        "ci_low": quantile(drawn_values, tail),
        "ci_high": quantile(drawn_values, 1.0 - tail),
        "p_value": sum(1 for v in drawn_values if v <= 0.0) / len(drawn_values),
    }


# -- the verdict --------------------------------------------------------------

VERDICT_RANKS = "ranks"
VERDICT_NO_EVIDENCE = "no evidence it ranks"
VERDICT_TOO_THIN = "too thin to say"

VERDICT_RULE = (
    "'ranks' requires the top-minus-bottom gap and Spearman's rho to have "
    "symbol-clustered intervals both entirely above zero; either one alone is "
    "'no evidence it ranks', because a gap can rest on one hot name at the top "
    "and a rho can be positive and negligible. A cohort whose top or bottom band "
    "is below the cluster floor is 'too thin to say' — the gap is computed "
    "between those two bands. 'no evidence it ranks' is never 'the score does not "
    "rank': one sample cannot license that"
)


def verdict(
    *,
    gap: dict[str, Any],
    rho: dict[str, Any],
    edges: Sequence[dict[str, Any]],
) -> str:
    """The verdict :data:`VERDICT_RULE` spells out, read off both statistics.

    ``edges`` are the two bands the gap is taken between; a suppressed interval on
    either makes the gap unreadable however wide the cohort as a whole is.
    """
    thin = any(cell["bootstrap"]["suppressed"] is not None for cell in edges)
    if thin or gap["value"] is None or rho["rho"] is None:
        return VERDICT_TOO_THIN
    if gap["bootstrap"]["ci_low"] is None or rho["bootstrap"]["ci_low"] is None:
        return VERDICT_TOO_THIN
    if gap["bootstrap"]["ci_low"] > 0 and rho["bootstrap"]["ci_low"] > 0:
        return VERDICT_RANKS
    return VERDICT_NO_EVIDENCE


# -- joining a trade to the score that produced it ----------------------------

ScoreIndex = Mapping[tuple[date, str], SevenDimScore]


def score_index(
    denominator: DenominatorStore, market: str, *, include_burn_in: bool = False
) -> dict[tuple[date, str], SevenDimScore]:
    """Every persisted detection's score for one market, keyed by session and symbol.

    The key is the pair the denominator's own primary key uses, so the join below
    is exact: a symbol is detected at most once on a session.

    Burn-in sessions are excluded by default for the reason they are flagged at
    all — a warm-up session is persisted and never measured (story 76) — and the
    default matches :func:`~backtest.simulate.walk_detections`, so the index and
    the trades cover the same sessions rather than nearly the same ones.
    """
    index: dict[tuple[date, str], SevenDimScore] = {}
    for header in denominator.sessions(
        market, burn_in=None if include_burn_in else False
    ):
        for scored in denominator.detections(market, header.session):
            check_seven_dimension_score(scored.score)
            index[(header.session, scored.symbol)] = scored.score
    return index


def scored_trades(
    trades: Sequence[SimulatedTrade], scores: ScoreIndex
) -> list[ScoredTrade]:
    """Join each trade to its detection's score, refusing a trade that has none.

    The join is **total** or it is a bug: every simulated trade came from a
    persisted detection, and that detection carries a score. Dropping an unmatched
    trade quietly would shrink the cohort the ranking is measured on with nothing
    in the output to say which trades left — and the trades most likely to go
    missing are not a random sample of them.
    """
    out: list[ScoredTrade] = []
    for trade in trades:
        key = (trade.detection_session, trade.symbol)
        if key not in scores:
            raise ValueError(
                f"no persisted score for {trade.symbol} detected "
                f"{trade.detection_session}: the join from trade to detection is "
                "total, and a missing row is a broken denominator rather than a "
                "trade to drop"
            )
        score = scores[key]
        check_seven_dimension_score(score)
        out.append(ScoredTrade(trade=trade, score=score))
    return out


# -- the report ---------------------------------------------------------------


def check_cohort(cohort: Sequence[ScoredTrade], *, market: str) -> None:
    """Refuse a cohort spanning two markets or two arms, before anything is cut.

    Checked over the whole cohort rather than per bucket, because a foreign trade
    that happened to land in a band nobody read would pass a per-bucket check and
    still move the cut every other band was made against. findings §8 measured that
    magnitudes do not transfer between the markets, and the pre-registered arm is
    arm B's — a ranking averaged over two arms would rank a result no arm produced.
    """
    foreign = {s.market for s in cohort} - {market}
    if foreign:
        raise ValueError(
            f"a ranking is one market's: {market!r} was asked for and "
            f"{sorted(foreign)} arrived too; US and IDX never pool"
        )
    other_arms = {s.trade.arm for s in cohort} - {PRIMARY_ARM}
    if other_arms:
        raise ValueError(
            f"the ranking is measured on arm {PRIMARY_ARM}, the pre-registered "
            f"arm: {sorted(other_arms)} arrived too"
        )


def bucket_cell(
    contract: RunContract,
    band: Band,
    cohort: Sequence[ScoredTrade],
    *,
    market: str,
) -> dict[str, Any]:
    """One band's cell: the metric's own expectancy cell, plus the band it is.

    The body is :func:`~backtest.metric.expectancy_cell` unmodified, so a bucket
    reports the same fields the headline does — the win rate, the R-distribution
    and the symbol-clustered interval — and a reader comparing a bucket against the
    headline is comparing two figures built the same way.
    """
    in_band = [s for s in cohort if band.holds(s.points)]
    return {
        "bucket": band.index,
        "deciles": list(band.deciles),
        "band": band.label,
        "low_points": band.low_points,
        "high_points": band.high_points,
        "low_stars": band.low_stars,
        "high_stars": band.high_stars,
        "share_of_cohort": (len(in_band) / len(cohort)) if cohort else 0.0,
        **expectancy_cell(
            contract, [s.trade for s in in_band], market=market, label=band.label
        ),
    }


def _gap_cell(
    contract: RunContract, cohort: Sequence[ScoredTrade], cut: Sequence[Band]
) -> dict[str, Any]:
    """The top-minus-bottom gap with its clustered interval, and the bands it spans."""
    rows = outcomes(cohort, contract)
    clusters = symbol_clusters(cohort, contract)
    return {
        "top": cut[-1].label if cut else None,
        "bottom": cut[0].label if cut else None,
        "value": top_minus_bottom(rows, cut),
        "bootstrap": bootstrap_symbol_statistic(
            clusters, lambda drawn: top_minus_bottom(drawn, cut)
        ),
    }


def _rho_cell(
    contract: RunContract, cohort: Sequence[ScoredTrade]
) -> dict[str, Any]:
    """Spearman's rho over the whole cohort, with its clustered interval."""
    rows = outcomes(cohort, contract)
    return {
        "statistic": "spearman_rho",
        "ties": "averaged",
        "rho": rank_correlation(rows),
        "pairs": len(rows),
        "bootstrap": bootstrap_symbol_statistic(
            symbol_clusters(cohort, contract), rank_correlation
        ),
    }


def _slice(
    contract: RunContract,
    cohort: Sequence[ScoredTrade],
    cut: Sequence[Band],
    *,
    market: str,
) -> dict[str, Any]:
    """One slice — a window or a year — bucketed on ``cut``, with its verdict."""
    buckets = [bucket_cell(contract, band, cohort, market=market) for band in cut]
    gap = _gap_cell(contract, cohort, cut)
    rho = _rho_cell(contract, cohort)
    return {
        "trades": len(cohort),
        "symbols": len({s.symbol for s in cohort}),
        "buckets": buckets,
        "gap": gap,
        "spearman": rho,
        "verdict": verdict(
            gap=gap, rho=rho, edges=[buckets[0], buckets[-1]] if buckets else []
        ),
    }


def market_ranking(
    contract: RunContract,
    cohort: Sequence[ScoredTrade],
    *,
    market: str,
) -> dict[str, Any]:
    """One market's ranking: the window's buckets, then every year against them.

    The cut is made **once**, on the whole measured window, and every year is
    reported against it — so "the top bucket" names one score band throughout and a
    year-on-year comparison is a comparison of one question. A year with no trade
    in a band reports a zero rather than a missing row, for the reason the metric
    reports a silent year: an absent row and a quiet year are indistinguishable
    after the fact.
    """
    check_costs(contract, market)
    check_cohort(cohort, market=market)
    for scored in cohort:
        check_seven_dimension_score(scored.score)

    cut = bands(cohort)
    by_year: dict[int, list[ScoredTrade]] = {}
    for scored in cohort:
        by_year.setdefault(scored.year, []).append(scored)

    return {
        "market": market,
        "arm": PRIMARY_ARM,
        "deciles": DECILES,
        "bands": len(cut),
        "tie_rule": (
            "a score value is atomic: it never splits across two buckets, so the "
            f"buckets collapse to fewer than {DECILES} on a "
            f"{SCORE_MAX_POINTS}-point score and each names the deciles it covers"
        ),
        "cut_on": "the market's whole measured window, so a band means the same "
                  "score in every year",
        **_slice(contract, cohort, cut, market=market),
        "years": [
            {
                "year": year,
                **_slice(
                    contract, by_year.get(year, []), cut, market=market
                ),
            }
            for year in measured_years(contract, [s.trade for s in cohort])
        ],
    }


def ranking_report(
    contract: RunContract,
    cohort: Sequence[ScoredTrade],
    *,
    markets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The whole ranking measurement as one stamped payload, market by market.

    ``markets`` defaults to the contract's own scope, so a market that produced no
    trade reports its zeros rather than vanishing. There is deliberately no pooled
    figure: findings §8 measured that magnitudes do not transfer, and the way to
    stop a pooled number being quoted is for it never to have been computed.
    """
    named = tuple(markets) if markets else tuple(contract.value(SCOPE_MARKETS_KEY))
    return stamp_result(
        contract,
        {
            "question": (
                "does a higher star score predict a better result, out of sample?"
            ),
            "arm": PRIMARY_ARM,
            "score": {
                "label": SCORE_LABEL,
                "dimensions": SCORE_DIMENSIONS,
                "max_points": SCORE_MAX_POINTS,
                "max_stars": SCORE_MAX_STARS,
                "app_max_points": APP_MAX_POINTS,
                "note": SCORE_NOTE,
            },
            "out_of_sample": OUT_OF_SAMPLE_NOTE,
            "in_sample_reference": IN_SAMPLE_GAP,
            "verdict_rule": VERDICT_RULE,
            "multiple_testing": MULTIPLE_TESTING_NOTE,
            "kill_criterion": KILL_CRITERION_NOTE,
            "bootstrap": {
                "cluster": BOOTSTRAP_CLUSTER,
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "confidence": BOOTSTRAP_CONFIDENCE,
            },
            "year_attributed_to": "entry_session",
            "markets": [
                market_ranking(
                    contract,
                    [s for s in cohort if s.market == market],
                    market=market,
                )
                for market in named
            ],
        },
    )


# -- printing it, and the command that produces it ----------------------------


def _interval(boot: dict[str, Any]) -> str:
    """One interval as a phrase, or the reason there is none."""
    if boot["ci_low"] is None:
        return f"{boot['clusters']} {boot['cluster']}s — too thin for an interval"
    return (
        f"[{boot['ci_low']:+.2f}, {boot['ci_high']:+.2f}] p={boot['p_value']:.3f} "
        f"on {boot['clusters']} {boot['cluster']}s"
    )


def _bucket_line(cell: dict[str, Any]) -> str:
    """One bucket as a line: the band, its n, what it paid and how sure that is.

    n sits immediately beside the expectancy and never on a line of its own,
    because a band's expectancy without its count is unreadable — six trades and
    six hundred print the same number.
    """
    deciles = cell["deciles"]
    span = (
        f"D{deciles[0]}" if len(deciles) == 1 else f"D{deciles[0]}–D{deciles[-1]}"
    )
    head = f"  {span:<8} {cell['band']:<12} n={cell['closed']:<5}"
    if cell["closed"] == 0:
        return f"{head} no closed trades ({cell['trades']} taken)"
    return (
        f"{head} {cell['expectancy_r']:+.3f}R  win {cell['win_rate']:.1%}  "
        f"{cell['symbols']} symbols  {_interval(cell['bootstrap'])}"
    )


def _slice_lines(body: dict[str, Any], *, indent: str = "") -> list[str]:
    """One slice's buckets, then the two statistics the verdict is read off."""
    lines = [indent + line for line in map(_bucket_line, body["buckets"])]
    gap, rho = body["gap"], body["spearman"]
    value = "undefined" if gap["value"] is None else f"{gap['value']:+.3f}R"
    rho_value = "undefined" if rho["rho"] is None else f"{rho['rho']:+.3f}"
    lines += [
        f"{indent}  gap {gap['bottom']} → {gap['top']}: {value}  "
        f"{_interval(gap['bootstrap'])}",
        f"{indent}  rho {rho_value} over {rho['pairs']} trades  "
        f"{_interval(rho['bootstrap'])}",
        f"{indent}  verdict: {body['verdict']}",
    ]
    return lines


def format_ranking(report: dict[str, Any]) -> str:
    """The measurement as a page a terminal can print.

    §4a's figure is printed **before** the buckets rather than as a footnote, so a
    reader meets the in-sample gap and the reason it is not this measurement before
    reading a number that could be mistaken for it.
    """
    score, prior = report["score"], report["in_sample_reference"]
    lines: list[str] = [
        f"{report['question']} — arm {report['arm']}",
        f"  scored on the {score['label']}: {score['dimensions']} dimensions, "
        f"{score['max_points']} points, ceiling {score['max_stars']:.1f}★",
        f"  — not the app's {score['app_max_points']}-point score, which carries "
        "the struck Sector row",
        "  out of sample: R after costs, which no weight was fitted to and no "
        "detection's score could see",
        f"  against §4a, which was in-sample: picks {prior['picks_rate']:.1%} vs "
        f"field {prior['field_rate']:.1%} at ≥3.5★, gap +{prior['gap_pp']:.2f}pp,",
        f"  p={prior['p_value']:.3f} ({prior['test']}) — a rubric measured against "
        "the separation its own weights were fitted to",
        f"  bootstrap {report['bootstrap']['resamples']}× clustered by "
        f"{report['bootstrap']['cluster']}, seed {report['bootstrap']['seed']}",
    ]
    for body in report["markets"]:
        lines += [
            "",
            f"{body['market']} — {body['bands']} bands over {body['trades']} "
            f"trades in {body['symbols']} symbols",
        ]
        lines += _slice_lines(body)
        lines.append("  per year")
        for year in body["years"]:
            # A year that traded nothing is one line rather than a band per
            # bucket. It stays on the page — a silent year is a measurement, and
            # possibly a data hole — but fourteen of them spelled out in full
            # would bury the years that did trade.
            if year["trades"] == 0:
                lines.append(f"    {year['year']}  no trades")
                continue
            lines.append(f"    {year['year']}  ({year['trades']} trades)")
            lines += _slice_lines(year, indent="    ")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Bucket the persisted denominator's outcomes by star-score decile and record it::

        python -m backtest.ranking --store data/backtest.duckdb \\
            --out-json references/backtest_score_ranking.json

    Both markets by default, arm B only — the pre-registered arm. Reads the bar
    store and the denominator beside it, and writes neither.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument(
        "--market", action="append", default=None,
        help="narrow to one market (repeatable); defaults to the contract's scope",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped result",
    )
    args = parser.parse_args(argv)

    contract = DEFAULT_CONTRACT
    markets = tuple(args.market) if args.market else tuple(
        contract.value(SCOPE_MARKETS_KEY)
    )
    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        cohort: list[ScoredTrade] = []
        for market in markets:
            trades = simulate_market(
                store, denominator, market, contract, arms=(PRIMARY_ARM,)
            )
            cohort += scored_trades(trades, score_index(denominator, market))
    finally:
        denominator.close()
        store.close()

    report = ranking_report(contract, cohort, markets=markets)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_ranking(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
