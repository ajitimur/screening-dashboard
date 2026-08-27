"""The pre-registered headline metric (issue #191, PRD #182 Phase 5).

One metric, promised in advance: **arm B's after-cost expectancy in R, per market
per year**. Arm B because it is the reference set's primary simulated exit, which
is what keeps the headline comparable to figures already committed to this repo.

The contract names it (``metric.primary``) and this module computes it. Nothing
here reads a bar: :mod:`backtest.simulate` already turned each persisted detection
into a trade denominated in R, and everything below is arithmetic over those
trades. That separation is why the fixtures in the seam tests author trades
directly — a metric that needed a chain to test would be a metric nobody could
check by hand.

Costs, and why they are per market
----------------------------------
Commission and slippage are contract cells, per market (``costs.per_market``), and
they are **paid on both sides**: bps of the traded price on the entry and on every
leg that comes off. IDX carries real fees and spread; US is near-zero. Modelling
Jakarta with New York's assumptions would flatter the one market where costs can
plausibly eat the edge, so a market the cell does not name is
:class:`~backtest.run.ContractDrift` rather than a free trade.

The cost is converted to R by the trade's own stop width, which keeps it in the
unit the result is denominated in — and keeps it rescale-immune for the same
reason :attr:`~backtest.simulate.SimulatedTrade.r_multiple` is: numerator and
denominator are both prices from the same series.

Why the win rate never travels alone
------------------------------------
A low win rate is judged against its right tail, not on its own. 22.7% of the
reference trader's trades made money and his mean R was positive anyway (findings
§3c). A method with a 20% win rate is not broken; a method with a 20% win rate and
a *small* right tail is. So every expectancy in this module carries the win rate
and the R-distribution behind it, and
``test_the_same_win_rate_with_a_thin_tail_is_a_different_result`` pins that the two
cases are distinguishable from the output alone.

Never pooled only
-----------------
The measured window contains a crash and a mania, so a pooled fourteen-year number
describes neither. Every market therefore reports **per year**, and the
2020–21-excluded figure sits beside the full-window one because that tape rewarded
momentum nearly everywhere. A year inside the span with no trades reports zeros
rather than vanishing, for the same reason an arm that ran and traded nothing does:
a missing row and a quiet year are indistinguishable after the fact.

A trade is attributed to the year of its **entry session** — the year the decision
was taken — so a trade entered in December and exited in February counts where it
was decided. The alternative (attributing by exit) would move a trade's year with
the exit rule under test, which is the one thing the arms are varying.

US and IDX never pool, and it is enforced rather than remembered:
:func:`expectancy_cell` refuses a cohort spanning two markets, because findings §8
measured that magnitudes do not transfer and a mean across the two is a number
about neither. It refuses a cohort spanning two arms for the same reason — the
pre-registered metric is arm B's, and an arm A trade averaged into it would report
a figure no arm produced under arm B's name.

Significance is clustered by symbol, never by row
-------------------------------------------------
A stock throwing three signals in a fortnight contributes three correlated rows.
Bootstrapping those rows treats them as three independent observations, and every
p-value that comes out is flattered — the effective sample is smaller than the row
count. So :func:`bootstrap_expectancy` resamples **clusters**, and
:func:`clusters_by_symbol` makes the cluster a symbol. The seam test runs the same
data both ways and asserts the interval widens and the p-value rises; that widening
*is* the correction.

The bootstrap is seeded (:data:`BOOTSTRAP_SEED`) and its seed and resample count
ride on every cell, because a significance figure that moved between two runs of
the same data would make every result unreproducible with nothing in the output to
show it.

A cell with fewer than :data:`BOOTSTRAP_MIN_CLUSTERS` symbols gets no interval at
all, and says so. A resample can only draw the clusters it has, so one symbol
resampled 2,000 times returns a zero-width interval at p = 0 — which prints as
overwhelming significance and is one independent observation. Per-year cells are
exactly where the cluster count goes thin, so this is a floor the metric needs
where it is reported rather than an edge case.

Never pooled only, at both edges
--------------------------------
The per-year span is anchored at the contract's ``window.measured_start``, not at
the first trade: a market that traded nothing until 2016 in a run measuring from
2012 has four silent years, and an empty crawl is precisely what hides in them.
The far end stays observed, because the contract's ``measured_end`` is the token
``latest_complete_session`` rather than a date — so a market silent in its final
years is still under-reported at that end, and that limit is stated rather than
papered over.

What this module does not do
----------------------------
No sweep. Every threshold tried is a test, and enough of them produce a winner from
noise, so the pre-registered metric is computed and recorded **before** any swept
variant exists. The report says so with a variant count of zero, which is a claim a
later phase must update rather than a blank it can quietly fill.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from screener.store import Store

from .contract import (
    COSTS_KEY,
    DEFAULT_CONTRACT,
    METRIC_PRIMARY_KEY,
    SCOPE_MARKETS_KEY,
    WINDOW_MEASURED_START_KEY,
    RunContract,
)
from .denominator import DenominatorStore, denominator_path
from .result import stamp_result
from .run import ContractDrift
from .simulate import ARM_B, SimulatedTrade, price_scale_drops, simulate_market

# -- what the contract says, and what this module adds to it ------------------

# The arm the headline is computed on. Arm B is the reference set's primary
# simulated exit, so the figure stays comparable to what this repo has already
# committed; A and C are measured beside it and are not the headline.
PRIMARY_ARM = ARM_B

# The pre-registered metric's own name, as the contract spells it.
# :func:`check_primary_metric` refuses a contract that has moved out from under it.
PRIMARY_METRIC = "arm_b_after_cost_expectancy_r_per_market_per_year"

# Costs are bps of the traded price, charged on **each side** — the entry and every
# leg that comes off. Named rather than left implicit at the one call site, because
# "is that a round-trip figure or a per-side one?" is the question a reader asks of
# every cost model and the answer must not be inferred from arithmetic.
COST_CHARGED = "both_sides"
BPS = 10_000.0

# The two sub-keys inside the contract's per-market costs cell. Named for the same
# reason the cells themselves are: a bare ``costs["commission_bps"]`` at four sites
# is four places a rename has to be found by grep.
COMMISSION_BPS = "commission_bps"
SLIPPAGE_BPS = "slippage_bps"

# The two windows every market reports, side by side. 2020–21 is excluded in the
# second because that tape rewarded momentum nearly everywhere, and a result that
# rests on it alone is a result about the tape.
FULL_WINDOW = "full"
EXCLUDED_YEARS_WINDOW = "excluding_2020_2021"
EXCLUDED_YEARS = (2020, 2021)

# The bootstrap. The cluster is the **symbol**: overlapping signals in one name are
# correlated, so resampling rows would count a stock's three-signal fortnight as
# three independent observations.
BOOTSTRAP_CLUSTER = "symbol"
BOOTSTRAP_RESAMPLES = 2_000
BOOTSTRAP_SEED = 191
BOOTSTRAP_CONFIDENCE = 0.95

# Below this many clusters no interval is reported at all. A resample can only ever
# draw from the clusters it has, so one symbol resampled 2,000 times returns that
# symbol's own mean 2,000 times: a zero-width interval and a p-value of exactly 0 or
# 1. That prints as overwhelming significance and is the opposite — it is a cell
# with one independent observation. Per-year cells are precisely where the cluster
# count goes thin, so the floor matters most exactly where the metric is reported.
#
# Five is a judgement, not a derivation, and is recorded as one: below five symbols
# a 95% percentile interval is pinned by fewer than five distinct values and
# describes the sample's own range rather than the uncertainty around it. The
# suppressed cells still report ``clusters``, so a thin cell reads as thin.
BOOTSTRAP_MIN_CLUSTERS = 5

# The count of swept variants standing behind the headline. Zero, and structurally
# so: this module computes the pre-registered metric and no sweep exists yet. A
# later phase updates this rather than leaving a reader to assume it.
SWEPT_VARIANTS = 0
SWEEP_NOTE = (
    "the pre-registered metric is computed and recorded before any swept variant "
    "exists; a swept result is reported with the count of variants tried"
)

# Where the survivorship bound rides (PRD Phase 2, issue #196). The key a market's
# block carries it under, and what gets printed when nothing carries it.
#
# The bound is *attached* by :func:`backtest.survivorship.attach_bias_bound` rather
# than computed here, because the size of the hole is measured against the bar store
# and a reconstructed listing spine and this module reads neither — a metric that
# reached for them would need a crawl to report a mean. But the printed page is
# where the pair is either honoured or quietly broken, so the absence of a bound is
# printed *as* the absence rather than left blank: a blank would read as "no bias",
# which is the one reading Phase 2 exists to make impossible.
BIAS_BOUND_KEY = "bias_bound"
NO_BOUND_LINE = (
    "  bias bound: not attached — this figure is survivor-biased by an unmeasured "
    "amount (backtest.survivorship)"
)

# The three keys that say *what kind of number this payload is*: the flag claiming
# pre-registration, and the sweep block carrying the count of variants behind it.
# Named here rather than where they are read, because this module is the one that
# writes them: :mod:`backtest.sweep` refuses a payload that is not pre-registered
# and :mod:`backtest.verdict` refuses one that has been swept, and a rename that
# only reached the readers would leave both refusals silently passing everything.
PRE_REGISTERED_KEY = "pre_registered"
SWEEP_KEY = "sweep"
VARIANTS_TRIED_KEY = "variants_tried"


# -- refusing a contract that has moved out from under the code ---------------


def check_primary_metric(contract: RunContract) -> None:
    """Refuse a run whose contract's primary metric is not the one computed here.

    Moving the cell without moving the code leaves a run whose contract and
    behaviour disagree while both look right — and the headline is exactly the
    figure pre-registration exists to keep fixed. The remedy is a new contract
    recorded beside the old one, never a silent reinterpretation.
    """
    named = contract.value(METRIC_PRIMARY_KEY)
    if named != PRIMARY_METRIC:
        raise ContractDrift(
            f"contract's primary metric is {named!r}, but this module computes "
            f"{PRIMARY_METRIC!r}; a moved headline is a new run, not a rerun"
        )


def check_costs(contract: RunContract, market: str) -> None:
    """Refuse a market the contract's costs cell does not price.

    An unnamed market defaulting to zero would report the most flattering
    expectancy in the whole run and would look like a clean result, which is the
    one failure mode a cost model has that reading the output cannot catch.
    """
    costs = contract.value(COSTS_KEY)
    if market not in costs:
        raise ContractDrift(
            f"the contract's {COSTS_KEY!r} cell prices {sorted(costs)} and not "
            f"{market!r}; an unpriced market is drift, not a free trade"
        )
    for side in (COMMISSION_BPS, SLIPPAGE_BPS):
        if side not in costs[market]:
            raise ContractDrift(
                f"the contract's costs for {market!r} carry no {side!r}"
            )


def check_one_market_one_arm(
    trades: Sequence[SimulatedTrade], *, market: str, what: str
) -> None:
    """Refuse a cohort spanning two markets or two arms, whatever is measuring it.

    Both refusals exist because neither failure has a shape a reader could catch
    afterwards. A mean across the two markets is the figure findings §8 forbids —
    magnitudes do not transfer — and it would print as an ordinary number. A mean
    across two arms would report a figure no arm produced, under the name of the
    one the run pre-registered.

    ``what`` names the caller in the message, because the same refusal now guards
    two different measurements (:func:`expectancy_cell` and the ranking's cohort)
    and "one market's" is unhelpful when a reader cannot tell which one refused.
    """
    foreign = {t.market for t in trades} - {market}
    if foreign:
        raise ValueError(
            f"{what} is one market's: {market!r} was asked for and "
            f"{sorted(foreign)} arrived too; US and IDX never pool"
        )
    other_arms = {t.arm for t in trades} - {PRIMARY_ARM}
    if other_arms:
        raise ValueError(
            f"{what} is measured on arm {PRIMARY_ARM}, the pre-registered arm: "
            f"{sorted(other_arms)} arrived too, and no arm produced the average "
            "of them"
        )


def per_side_cost_bps(contract: RunContract, market: str) -> float:
    """Commission plus slippage for one side of a trade in ``market``, in bps.

    The two are summed because they are charged the same way — bps of the price
    actually traded — and separating them in the arithmetic would suggest a
    distinction the model does not make. Both are still reported separately on
    every cell, because only one of them is a fee somebody could negotiate.
    """
    check_costs(contract, market)
    costs = contract.value(COSTS_KEY)[market]
    return float(costs[COMMISSION_BPS]) + float(costs[SLIPPAGE_BPS])


# -- the arithmetic: costs, the distribution behind an expectancy, the bootstrap


def cost_r(trade: SimulatedTrade, contract: RunContract) -> float:
    """The round trip's cost, in R, for one trade under the contract's costs.

    Charged on the entry (the whole position, once) and on every leg that comes
    off, weighted by the share of the position it was — so arm A's two legs pay
    twice on halves rather than once on a whole, which is what actually happens.
    A scale pays too: it is a planned partial, but it is still a fill.

    Divided by the trade's own stop width, which puts the cost in the same unit as
    the result and keeps it immune to a retroactive rescale of the bar series: both
    terms are prices from that series, so a constant factor cancels.
    """
    rate = per_side_cost_bps(contract, trade.market) / BPS
    if trade.stop_width <= 0:
        return 0.0
    priced = trade.entry.price + sum(
        leg.weight * leg.exit.price for leg in trade.legs
    )
    return rate * priced / trade.stop_width


def after_cost_r(trade: SimulatedTrade, contract: RunContract) -> float | None:
    """A trade's R after costs, or ``None`` while any of the position is still on.

    ``None`` rather than a number, and never a mark to the last close: closing a
    running trade at whatever price the window ended on would invent an exit the
    rules never gave, systematically, for every name still running.
    """
    if trade.r_multiple is None:
        return None
    return trade.r_multiple - cost_r(trade, contract)


def clusters_by_symbol(
    trades: Sequence[SimulatedTrade], contract: RunContract
) -> list[tuple[float, ...]]:
    """The closed trades' after-cost R, grouped into one cluster per symbol.

    The unit of independence for the bootstrap. Overlapping signals in one name are
    not independent observations — a stock throwing three signals in a fortnight
    contributes three correlated rows — so the symbol is what gets resampled and the
    rows inside it travel together.

    Ordered by symbol so a resample under a fixed seed is reproducible: a bootstrap
    whose clusters arrived in dictionary insertion order would move with the order
    the trades happened to be read in.
    """
    grouped: dict[str, list[float]] = {}
    for trade in trades:
        r = after_cost_r(trade, contract)
        if r is None:
            continue
        grouped.setdefault(trade.symbol, []).append(r)
    return [tuple(grouped[symbol]) for symbol in sorted(grouped)]


def quantile(values: Sequence[float], q: float) -> float:
    """The ``q``-quantile of already-sorted ``values``, linearly interpolated.

    Public because :mod:`backtest.ranking`'s bootstrap builds its interval the
    same way: two percentile conventions in one report would make two intervals
    incomparable while both printed as 95%.
    """
    if len(values) == 1:
        return values[0]
    pos = q * (len(values) - 1)
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (pos - low)


def bootstrap_expectancy(
    clusters: Sequence[Sequence[float]],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
    cluster: str = BOOTSTRAP_CLUSTER,
    min_clusters: int = BOOTSTRAP_MIN_CLUSTERS,
) -> dict[str, Any]:
    """A clustered bootstrap of the mean of ``clusters``' pooled values.

    Each resample draws ``len(clusters)`` clusters **with replacement** and pools
    everything inside them, so a cluster is either in or out as a whole. That is
    the correction the whole exercise turns on: resampling rows instead would let
    one name's twenty signals arrive twenty independent times, tighten the interval
    and flatter the p-value.

    ``p_value`` is one-sided — the share of resample means at or below zero — and
    one-sided is the right shape because the decision rule it feeds is one-sided
    too: the kill criterion asks whether expectancy is ≤ 0, not whether it differs
    from 0. It is a percentile-bootstrap approximation and is named as such rather
    than dressed up as a test statistic.

    ``cluster`` names the unit for the reader, and taking it as an argument is what
    lets the seam test run the same data clustered by row and show the difference.

    A cell with fewer than :data:`BOOTSTRAP_MIN_CLUSTERS` clusters gets **no
    interval and no p-value**, and a ``suppressed`` line saying why. Reporting one
    would be worse than reporting nothing: a single cluster resampled 2,000 times
    returns its own mean 2,000 times, which prints as a zero-width interval at
    p = 0 and reads as overwhelming significance from one independent observation.
    """
    n = len(clusters)
    body: dict[str, Any] = {
        "cluster": cluster,
        "clusters": n,
        "observations": sum(len(c) for c in clusters),
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
        "min_clusters": min_clusters,
        "suppressed": None,
    }
    if n < min_clusters:
        return {
            **body,
            "ci_low": None,
            "ci_high": None,
            "p_value": None,
            "suppressed": (
                f"{n} {cluster}s is fewer than {min_clusters}: too thin for an "
                "interval, and a degenerate one would read as significance"
            ),
        }

    rng = random.Random(seed)
    indices = range(n)
    means: list[float] = []
    for _ in range(resamples):
        drawn = [clusters[rng.choice(indices)] for _ in indices]
        total = sum(sum(c) for c in drawn)
        count = sum(len(c) for c in drawn)
        if count:
            means.append(total / count)
    if not means:
        return {**body, "ci_low": None, "ci_high": None, "p_value": None}

    means.sort()
    tail = (1.0 - confidence) / 2.0
    return {
        **body,
        "ci_low": quantile(means, tail),
        "ci_high": quantile(means, 1.0 - tail),
        "p_value": sum(1 for m in means if m <= 0.0) / len(means),
    }


# The quantiles every distribution reports, and the fractions they read at. One
# table rather than a list of keys and a parallel list of calls, so an empty
# distribution and a populated one cannot drift into carrying different fields —
# which would make a quiet cell and a computed one differently shaped.
_QUANTILES = (
    ("p10", 0.10),
    ("q1", 0.25),
    ("median", 0.50),
    ("q3", 0.75),
    ("p90", 0.90),
)
_DISTRIBUTION_KEYS = ("min", *(name for name, _ in _QUANTILES), "max",
                      "mean_win", "mean_loss")


def _distribution(rs: Sequence[float]) -> dict[str, Any]:
    """The shape behind an expectancy: the quantiles and the two conditional means.

    Reported whole rather than as a standard deviation, because the question a low
    win rate raises is about the *right tail* specifically, and a spread statistic
    answers it only if the distribution is symmetric — which this one is
    emphatically not.
    """
    if not rs:
        return {key: None for key in _DISTRIBUTION_KEYS}
    ordered = sorted(rs)
    wins = [r for r in ordered if r > 0]
    losses = [r for r in ordered if r <= 0]
    return {
        "min": ordered[0],
        **{name: quantile(ordered, q) for name, q in _QUANTILES},
        "max": ordered[-1],
        "mean_win": sum(wins) / len(wins) if wins else None,
        "mean_loss": sum(losses) / len(losses) if losses else None,
    }


# -- the report: one cell, one market, the whole headline ---------------------


def expectancy_cell(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    market: str,
    label: str,
) -> dict[str, Any]:
    """One market's after-cost expectancy over one slice, with its shape and its CI.

    ``label`` names the slice — a year, or one of the two windows — and is the only
    thing that distinguishes two cells from each other, so it is carried rather than
    inferred from the trades inside.

    Every cohort is **one market and one arm**, and both are refused rather than
    checked at the call site. A mean across two markets is the figure story 4
    forbids and would be invisible in the output; a mean across two arms would
    report a number no arm produced under arm B's name. Neither has a shape a reader
    could catch afterwards, so neither is reachable.

    A cell with no closed trades reports ``None`` for every figure that needs one
    and zeros for the counts. That is a quiet slice, and it is deliberately not the
    same output as a slice nobody computed.
    """
    check_costs(contract, market)
    check_one_market_one_arm(trades, market=market, what="an expectancy cell")

    closed = [t for t in trades if t.r_multiple is not None]
    rs = [after_cost_r(t, contract) for t in closed]
    before = [t.r_multiple for t in closed]
    wins = [r for r in rs if r > 0]
    return {
        "label": label,
        "trades": len(trades),
        "closed": len(closed),
        # Off the trade's **own** property rather than off "has no R", because the
        # two are not the same set: a trade whose stop width is non-positive has
        # come fully off and still cannot be denominated. Counting it as open would
        # report a finished trade as running, so it gets its own count and the two
        # numbers add up to the total with nothing hidden between them.
        "open_at_end": sum(1 for t in trades if t.open_at_end),
        "undenominated": sum(
            1 for t in trades if t.closed and t.r_multiple is None
        ),
        "symbols": len({t.symbol for t in trades}),
        # The simulator's own count, not a second one: it is the function whose
        # docstring argues why the flag is reported and never filtered, and two
        # implementations of that would be two places for it to become a filter.
        "price_scale_dropped": price_scale_drops(trades),
        "expectancy_r": (sum(rs) / len(rs)) if rs else None,
        "expectancy_r_before_cost": (sum(before) / len(before)) if before else None,
        "cost_r": (
            sum(cost_r(t, contract) for t in closed) / len(closed) if closed else None
        ),
        "win_rate": (len(wins) / len(rs)) if rs else None,
        "wins": len(wins),
        "losses": len(rs) - len(wins),
        "total_r": sum(rs),
        "distribution": _distribution(rs),
        "bootstrap": bootstrap_expectancy(clusters_by_symbol(trades, contract)),
    }


def market_block(
    report: Mapping[str, Any], market: str
) -> dict[str, Any] | None:
    """One market's block of a metric report, or ``None`` where it has none.

    Public, and read by every module that consumes this payload rather than
    produces it — the sweep quoting the headline it must stand beside, the verdict
    reading the two windows a criterion is drawn on. One spelling of "find the
    market, then find the window", because four spellings is four places for a
    label to be looked up under a name the writer no longer uses.
    """
    for body in report["markets"]:
        if body["market"] == market:
            return body
    return None


def window_cell(
    body: Mapping[str, Any], label: str
) -> dict[str, Any] | None:
    """The window cell at ``label`` on one market's block, or ``None``.

    ``None`` rather than a raise: a caller asking for the 2020–21-excluded window
    of a report that carries only the full one is asking a question the report
    cannot answer, and the answer to that is "no figure", which every caller here
    already has to handle for a market that traded nothing.
    """
    for cell in body["windows"]:
        if cell["label"] == label:
            return cell
    return None


def _reported_markets(
    contract: RunContract, asked: Sequence[str] | None
) -> tuple[str, ...]:
    """The markets to report: those asked for, or the contract's own scope.

    One fallback, in one place. Defaulting at the command *and* in the report would
    be two places for "which markets is this run about" to diverge, and the
    divergence would show up as a market silently missing from a headline that
    promised both.
    """
    return tuple(asked) if asked else tuple(contract.value(SCOPE_MARKETS_KEY))


def measured_years(
    contract: RunContract, trades: Sequence[SimulatedTrade]
) -> list[int]:
    """Every year of the measured window that this market could have traded in.

    Public rather than private because :mod:`backtest.ranking` reports per year
    too, and two implementations of "which years does this market get a row for"
    would be two places for a silent year to go missing from one report and not
    the other.

    The span rather than the years present: a year with no trade is a measurement —
    possibly a data hole — and an absent row reads as a quiet market until somebody
    looks.

    Anchored at the **contract's** ``window.measured_start`` rather than at the
    first trade, because a market that traded nothing until 2016 in a run that
    started measuring in 2012 has four silent years, and those are exactly the years
    a crawl that came back empty would hide. Spanning the observed trades alone
    protects interior gaps and quietly drops the ones at the edge, which is the
    failure mode this function exists to prevent arriving through the function
    itself.

    The far end stays observed: the contract's ``measured_end`` is the token
    ``latest_complete_session`` rather than a date, so no year is derivable from it.
    A market silent for its final years is therefore still under-reported at that
    end, and that is a known limit rather than a covered case.
    """
    if not trades:
        return []
    entries = [t.entry.session.year for t in trades]
    start = int(str(contract.value(WINDOW_MEASURED_START_KEY))[:4])
    return list(range(min(start, *entries), max(entries) + 1))


def market_report(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    market: str,
) -> dict[str, Any]:
    """One market's headline: the per-year cells, then the two windows beside them.

    ``trades`` may span markets and arms; only this market's, on
    :data:`PRIMARY_ARM`, are counted — so a caller hands over the whole run and the
    separation happens here rather than at every call site.

    The arm is **not** a parameter, and that is the point: the metric's name and the
    trades under it have to be the same arm or the report is a mislabel. A caller
    able to choose the arm could stamp arm A's result with arm B's pre-registered
    name, which is the very confusion the two-arm refusal in :func:`expectancy_cell`
    exists to prevent, arriving one level up.

    The years come first because they are the metric: the two window figures are a
    summary of them and a pooled fourteen-year number over a crash and a mania
    describes neither. The 2020–21-excluded window sits beside the full one rather
    than replacing it, because which of the two a reader should believe is exactly
    the question the pair exists to pose.
    """
    check_costs(contract, market)
    costs = contract.value(COSTS_KEY)[market]
    mine = [t for t in trades if t.market == market and t.arm == PRIMARY_ARM]
    kept = [t for t in mine if t.entry.session.year not in EXCLUDED_YEARS]
    return {
        "market": market,
        "arm": PRIMARY_ARM,
        "costs": {
            "commission_bps": float(costs["commission_bps"]),
            "slippage_bps": float(costs["slippage_bps"]),
            "per_side_bps": per_side_cost_bps(contract, market),
            "charged": COST_CHARGED,
        },
        "years": [
            expectancy_cell(
                contract,
                [t for t in mine if t.entry.session.year == year],
                market=market,
                label=str(year),
            )
            for year in measured_years(contract, mine)
        ],
        "windows": [
            expectancy_cell(contract, mine, market=market, label=FULL_WINDOW),
            {
                **expectancy_cell(
                    contract, kept, market=market, label=EXCLUDED_YEARS_WINDOW
                ),
                "excluded_years": list(EXCLUDED_YEARS),
            },
        ],
    }


def metric_report(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    markets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The whole pre-registered metric as one stamped payload, market by market.

    ``markets`` defaults to the contract's own ``scope.markets``, so a market that
    produced no trade still reports its zeros rather than vanishing from the
    headline — the same distinction the arms' report keeps between an arm that ran
    quietly and one that never ran.

    There is deliberately **no top-level expectancy**. findings §8 measured that
    magnitudes do not transfer between the two markets, so a pooled figure would be
    a number about neither, and the way to stop one being quoted is for it never to
    have been computed.
    """
    check_primary_metric(contract)
    named = _reported_markets(contract, markets)
    return stamp_result(
        contract,
        {
            "metric": contract.value(METRIC_PRIMARY_KEY),
            "arm": PRIMARY_ARM,
            PRE_REGISTERED_KEY: True,
            SWEEP_KEY: {VARIANTS_TRIED_KEY: SWEPT_VARIANTS, "note": SWEEP_NOTE},
            "bootstrap": {
                "cluster": BOOTSTRAP_CLUSTER,
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "confidence": BOOTSTRAP_CONFIDENCE,
            },
            "year_attributed_to": "entry_session",
            "markets": [
                market_report(contract, trades, market=market)
                for market in named
            ],
        },
    )


# -- printing it, and the command that produces it ----------------------------


def _cell_line(cell: dict[str, Any], *, width: int = 22) -> str:
    """One cell as a line: the expectancy, then the shape and the interval behind it.

    The win rate is printed immediately beside the expectancy and never on its own
    line, because the two are read together or the low one gets read as a verdict.
    """
    if cell["closed"] == 0:
        return f"  {cell['label']:<{width}} no closed trades (n={cell['trades']})"
    dist = cell["distribution"]
    boot = cell["bootstrap"]
    ci = (
        f"[{boot['ci_low']:+.2f}, {boot['ci_high']:+.2f}] p={boot['p_value']:.3f} "
        f"on {boot['clusters']} {boot['cluster']}s"
        if boot["ci_low"] is not None
        # The thin cell says it is thin, in the place a reader looks for the
        # interval — a blank there would read as "no result" rather than "too few
        # symbols to say", and those are different findings.
        else f"{boot['clusters']} {boot['cluster']}s — too thin for an interval"
    )
    # The cell's own bound, where one was attached — every result carries it, not
    # only the window figure a reader skims to. Compact and on the same line, for
    # the reason the win rate is: a pair split from its figure is a pair somebody
    # quotes half of.
    bound = cell.get(BIAS_BOUND_KEY)
    bounded = (
        f"  bound {bound['pessimistic_r']:+.3f}R"
        if bound and bound["pessimistic_r"] is not None
        else ""
    )
    return (
        f"  {cell['label']:<{width}} {cell['expectancy_r']:+.3f}R  "
        f"win {cell['win_rate']:.1%}  n={cell['closed']}  "
        f"med {dist['median']:+.2f} p90 {dist['p90']:+.2f} max {dist['max']:+.2f}  {ci}"
        f"{bounded}"
    )


def format_metric(report: dict[str, Any]) -> str:
    """The headline as a page a terminal can print — per market, per year, never pooled.

    The years are printed before the windows, in that order, because the printed
    page is where "never pooled only" is either honoured or quietly broken: a reader
    who skims to a bold summary figure must have passed the years to get there.
    """
    lines: list[str] = [
        f"{report['metric']} — arm {report['arm']}",
        f"  costs charged {COST_CHARGED}; bootstrap {report['bootstrap']['resamples']}× "
        f"clustered by {report['bootstrap']['cluster']}, seed {report['bootstrap']['seed']}",
        f"  swept variants behind this figure: {report['sweep']['variants_tried']}",
    ]
    for body in report["markets"]:
        costs = body["costs"]
        lines += [
            "",
            f"{body['market']} — {costs['commission_bps']:.0f}bps commission + "
            f"{costs['slippage_bps']:.0f}bps slippage per side",
            "  per year",
        ]
        lines += [_cell_line(cell) for cell in body["years"]] or [
            "    no trades in this market"
        ]
        lines.append("  windows")
        lines += [_cell_line(cell) for cell in body["windows"]]
        # One line, and it is printed whether or not a bound was attached — the
        # market's figures are never reachable without passing it.
        bound = body.get(BIAS_BOUND_KEY)
        lines.append(bound["line"] if bound else NO_BOUND_LINE)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Compute the pre-registered metric over a persisted denominator and record it.

    The command that produces the headline::

        python -m backtest.metric --store data/backtest.duckdb \\
            --out-json references/backtest_primary_metric.json

    Both markets by default, because the contract's scope names both and a headline
    missing one is not the pre-registered metric. Arm B only: the other two arms are
    measured by ``python -m backtest.simulate`` and are not the headline.

    Reads the bar store and the denominator beside it, and writes neither.
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
    # ``None`` is passed straight through rather than defaulted here:
    # :func:`metric_report` already falls back to the contract's own scope, and
    # defaulting in two places is two places for the fallback to diverge.
    markets = _reported_markets(contract, args.market)
    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        trades: list[SimulatedTrade] = []
        for market in markets:
            trades += simulate_market(
                store, denominator, market, contract, arms=(PRIMARY_ARM,)
            )
    finally:
        denominator.close()
        store.close()

    report = metric_report(contract, trades, markets=markets)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_metric(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
