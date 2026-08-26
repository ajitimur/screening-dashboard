"""The run's shared statistics — the pieces more than one measurement needs.

:mod:`backtest.metric` owns the pre-registered headline and the arithmetic behind
it: what a trade paid after costs, and the clustered bootstrap of a **mean**. That
covers the headline and every cell shaped like it.

It does not cover a statistic that is not a mean. A gap between two score bands, a
gap between a candidate dimension's two sides, a rank correlation — none of these
is the mean of anything, so none can be built by resampling clusters and averaging
them. :mod:`backtest.ranking` grew the machinery for the first of those (#194) and
:mod:`backtest.candidates` needed the same machinery for the second (#195), which
is when it stopped being the ranking's business: a module that is both a
measurement and the run's statistics library changes for two reasons, and the
second caller would have had to import from the first.

So this module holds what the two share, and holds it once:

* :func:`ranks` and :func:`spearman` — one tie rule and one variance refusal, so
  two rank correlations in one run were never computed differently.
* :func:`cluster_by_symbol` — the unit of independence, applied to whatever row
  type a measurement uses.
* :func:`bootstrap_symbol_statistic` — the clustered bootstrap over an arbitrary
  statistic, on :mod:`backtest.metric`'s own seed, resample count, confidence
  level and cluster floor, so two intervals in one report can never have been
  built differently.
* :func:`format_interval` and :func:`intervals_reported` — the two places a
  measurement renders and counts what it has claimed.

Nothing here knows what is being measured. Every function takes the caller's own
row type, which is what lets one bootstrap serve a score band gap and a candidate
dimension's gap without either module knowing about the other.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, TypeVar

from .metric import (
    BOOTSTRAP_CLUSTER,
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_MIN_CLUSTERS,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    quantile,
)


class HasSymbol(Protocol):
    """Any row that knows which name it belongs to.

    The only thing clustering needs to know about a row. Stated as a protocol
    rather than a base class so a measurement's row type stays a plain frozen
    dataclass of exactly the fields its statistics read.
    """

    @property
    def symbol(self) -> str: ...


# The row type a measurement resamples. The bootstrap hands pooled rows to a
# statistic and reads no field of one itself, so the type is the caller's — an
# outcome bucketed by score band, a candidate dimension's outcome, whatever comes
# next.
Row = TypeVar("Row")
SymbolRow = TypeVar("SymbolRow", bound=HasSymbol)


# -- ranks and rank correlation -----------------------------------------------


def ranks(values: Sequence[float]) -> list[float]:
    """Fractional ranks, ties taking the average of the positions they occupy.

    Ties are the common case on both quantities this run ranks — an eight-point
    integral score, and a candidate dimension's value on a field most of which
    sits one side of its cut — so the tie rule is the whole of why a correlation
    is meaningful here. Breaking ties by arrival order would make rho a function
    of the sort.
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


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman's rho between two paired series, ties averaged.

    ``None`` when either side has no variance. There is no correlation to report
    there, and a zero would read as "measured and found nothing" rather than "not
    measurable".

    Unequal lengths are a **join that lost rows on one side**, not a series to
    truncate, so they raise rather than silently correlating the overlap.
    """
    if len(xs) != len(ys):
        raise ValueError(
            f"a correlation needs paired series; {len(xs)} against {len(ys)} "
            "is a join that lost rows on one side"
        )
    if len(xs) < 2:
        return None
    x, y = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(x) / n, sum(y) / n
    dx = [a - mx for a in x]
    dy = [b - my for b in y]
    sx = sum(a * a for a in dx) ** 0.5
    sy = sum(b * b for b in dy) ** 0.5
    if sx == 0.0 or sy == 0.0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


# -- the unit of independence -------------------------------------------------


def cluster_by_symbol(rows: Iterable[SymbolRow]) -> list[tuple[SymbolRow, ...]]:
    """The rows grouped one cluster per symbol, in symbol order.

    The cluster is the symbol because overlapping signals in one name are not
    independent observations — a stock throwing three signals in a fortnight
    contributes three correlated rows — so resampling *rows* would make the
    effective sample larger than it is and flatter every p-value.

    Ordered by symbol so a resample under a fixed seed is reproducible: clusters
    arriving in insertion order would move an interval with the order the trades
    happened to be read in.
    """
    grouped: dict[str, list[SymbolRow]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return [tuple(grouped[symbol]) for symbol in sorted(grouped)]


# -- the bootstrap, over a statistic rather than over a mean -------------------

# How much of a resample distribution may be undefined before the interval built
# on the rest of it is refused.
#
# A resample is undefined exactly when the statistic could not be evaluated on
# what it drew — no symbol from the top band, none from the bottom, no variance on
# one side. Those are the draws carrying the most uncertainty about a statistic
# resting on a thin edge. Dropping them and reading the interval off what is left
# *conditions on the statistic having been computable*, which renormalises the
# distribution towards the cases where it was, and those are the confident ones.
# The correction goes the wrong way: it tightens the interval exactly where the
# data is weakest.
#
# There is no honest value to substitute for an undefined draw — zero is a
# measurement nobody made — so the remedy is to refuse the interval rather than to
# repair it. A tenth is a judgement and is recorded as one: below it the
# renormalisation moves a percentile bound by less than the resampling noise
# around it, and above it the interval is describing a sub-population of the
# resamples. The count always rides on the output, so a cell just under the line
# reads as one.
MAX_UNDEFINED_SHARE = 0.10


def bootstrap_symbol_statistic(
    clusters: Sequence[Sequence[Row]],
    statistic: Callable[[Sequence[Row]], float | None],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
    cluster: str = BOOTSTRAP_CLUSTER,
    min_clusters: int = BOOTSTRAP_MIN_CLUSTERS,
    max_undefined_share: float = MAX_UNDEFINED_SHARE,
    unavailable: str | None = None,
) -> dict[str, Any]:
    """A clustered bootstrap of an arbitrary statistic over the pooled rows.

    :func:`~backtest.metric.bootstrap_expectancy` resamples the same unit and takes
    the pooled **mean**; a gap between two groups and a rank correlation are not
    means of anything, so they need the resampled cohort itself. Hence a second
    entry point rather than a second bootstrap: the seed, the resample count, the
    confidence level, the cluster floor and the reported fields are all the
    metric's.

    Each resample draws ``len(clusters)`` clusters **with replacement** and pools
    every row inside them, so a symbol is in or out as a whole. ``p_value`` is
    one-sided — the share of resampled statistics at or below zero — which is the
    shape of every claim built on this: whether the quantity pays *more*, not
    whether it pays differently.

    A resample the statistic cannot evaluate is counted under ``undefined`` rather
    than defaulted to zero, because a resample that could not answer is not a
    resample that answered no. Past :data:`MAX_UNDEFINED_SHARE` of the draws the
    interval is **refused**; see that constant for the argument.

    Below ``min_clusters`` no interval is reported at all, for the reason the
    metric records: one symbol resampled two thousand times returns its own mean
    two thousand times, which prints as a zero-width interval at p = 0 and is one
    independent observation.

    ``unavailable`` refuses before any resampling, for a statistic that could not
    be computed on this cohort whatever was drawn — :mod:`backtest.candidates`
    passes it for a rank correlation against a candidate that persists no degree.
    The refusal is stated in the caller's words but reported in this function's
    shape, so a cell that never ran a bootstrap and one that ran and refused are
    read the same way by everything downstream.
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
        "max_undefined_share": max_undefined_share,
        "suppressed": None,
    }
    empty = {**body, "ci_low": None, "ci_high": None, "p_value": None}
    if unavailable is not None:
        return {**empty, "suppressed": unavailable}
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
    share_undefined = undefined / resamples if resamples else 1.0
    if not drawn_values or share_undefined > max_undefined_share:
        return {
            **empty,
            "undefined": undefined,
            "suppressed": (
                f"{share_undefined:.1%} of resamples could not be evaluated over "
                f"{n} {cluster}s, past the {max_undefined_share:.0%} the interval "
                "is allowed: reading it off the rest would condition on the draws "
                "where the statistic was computable, which are the confident ones"
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


# -- rendering and counting what was claimed ----------------------------------


def format_interval(boot: Mapping[str, Any]) -> str:
    """One interval as a phrase, or the count and the fact that there is none.

    The *reason* an interval was refused rides on the payload under
    ``suppressed``, and is deliberately not printed: the reasons are sentences,
    and a page of them would bury the figures they qualify. What prints is the
    cluster count, because a cell with no interval is still a measurement and its
    n is what says how thin it was.
    """
    if boot["ci_low"] is None:
        return f"{boot['clusters']} {boot['cluster']}s — no interval"
    return (
        f"[{boot['ci_low']:+.2f}, {boot['ci_high']:+.2f}] p={boot['p_value']:.3f} "
        f"on {boot['clusters']} {boot['cluster']}s"
    )


def intervals_reported(cells: Iterable[Mapping[str, Any]]) -> int:
    """How many of these cells actually state an interval.

    The multiple-testing budget is the count of claims made at nominal alpha, and
    a suppressed interval made no claim to correct for. Counted rather than
    described, because a budget a reader has to infer from the length of a page is
    a budget nobody is keeping.
    """
    return sum(1 for cell in cells if cell["bootstrap"]["ci_low"] is not None)
