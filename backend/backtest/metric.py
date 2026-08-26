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
from typing import Any, Sequence

from screener.store import Store

from .contract import (
    COSTS_KEY,
    DEFAULT_CONTRACT,
    METRIC_PRIMARY_KEY,
    SCOPE_MARKETS_KEY,
    RunContract,
)
from .denominator import DenominatorStore, denominator_path
from .result import stamp_result
from .run import ContractDrift
from .simulate import ARM_B, SimulatedTrade, simulate_market

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

# The count of swept variants standing behind the headline. Zero, and structurally
# so: this module computes the pre-registered metric and no sweep exists yet. A
# later phase updates this rather than leaving a reader to assume it.
SWEPT_VARIANTS = 0
SWEEP_NOTE = (
    "the pre-registered metric is computed and recorded before any swept variant "
    "exists; a swept result is reported with the count of variants tried"
)


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
    for side in ("commission_bps", "slippage_bps"):
        if side not in costs[market]:
            raise ContractDrift(
                f"the contract's costs for {market!r} carry no {side!r}"
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
    return float(costs["commission_bps"]) + float(costs["slippage_bps"])


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


def _quantile(values: Sequence[float], q: float) -> float:
    """The ``q``-quantile of already-sorted ``values``, linearly interpolated."""
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
    """
    n = len(clusters)
    body: dict[str, Any] = {
        "cluster": cluster,
        "clusters": n,
        "observations": sum(len(c) for c in clusters),
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
    }
    if n == 0:
        return {**body, "ci_low": None, "ci_high": None, "p_value": None}

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
        "ci_low": _quantile(means, tail),
        "ci_high": _quantile(means, 1.0 - tail),
        "p_value": sum(1 for m in means if m <= 0.0) / len(means),
    }


def _distribution(rs: Sequence[float]) -> dict[str, Any]:
    """The shape behind an expectancy: the quantiles and the two conditional means.

    Reported whole rather than as a standard deviation, because the question a low
    win rate raises is about the *right tail* specifically, and a spread statistic
    answers it only if the distribution is symmetric — which this one is
    emphatically not.
    """
    if not rs:
        return {
            "min": None, "p10": None, "q1": None, "median": None,
            "q3": None, "p90": None, "max": None,
            "mean_win": None, "mean_loss": None,
        }
    ordered = sorted(rs)
    wins = [r for r in ordered if r > 0]
    losses = [r for r in ordered if r <= 0]
    return {
        "min": ordered[0],
        "p10": _quantile(ordered, 0.10),
        "q1": _quantile(ordered, 0.25),
        "median": _quantile(ordered, 0.50),
        "q3": _quantile(ordered, 0.75),
        "p90": _quantile(ordered, 0.90),
        "max": ordered[-1],
        "mean_win": sum(wins) / len(wins) if wins else None,
        "mean_loss": sum(losses) / len(losses) if losses else None,
    }


def expectancy_cell(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    market: str,
    label: str,
    arm: str = PRIMARY_ARM,
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
    foreign = {t.market for t in trades} - {market}
    if foreign:
        raise ValueError(
            f"an expectancy cell is one market's: {market!r} was asked for and "
            f"{sorted(foreign)} arrived too; US and IDX never pool"
        )
    other_arms = {t.arm for t in trades} - {arm}
    if other_arms:
        raise ValueError(
            f"the pre-registered metric is arm {arm}'s: {sorted(other_arms)} "
            "arrived too, and no arm produced the average of them"
        )

    closed = [t for t in trades if t.r_multiple is not None]
    rs = [after_cost_r(t, contract) for t in closed]
    before = [t.r_multiple for t in closed]
    wins = [r for r in rs if r > 0]
    return {
        "label": label,
        "trades": len(trades),
        "closed": len(closed),
        "open_at_end": len(trades) - len(closed),
        "symbols": len({t.symbol for t in trades}),
        "price_scale_dropped": sum(1 for t in trades if not t.price_scale_ok),
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


def _years(trades: Sequence[SimulatedTrade]) -> list[int]:
    """Every year from the first entry to the last, gaps included.

    The span rather than the years present: a year inside the window with no trade
    is a measurement — possibly a data hole — and an absent row would read as a
    quiet market until somebody looked.
    """
    if not trades:
        return []
    entries = [t.entry.session.year for t in trades]
    return list(range(min(entries), max(entries) + 1))


def market_report(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    market: str,
    arm: str = PRIMARY_ARM,
) -> dict[str, Any]:
    """One market's headline: the per-year cells, then the two windows beside them.

    ``trades`` may span markets and arms; only this market's, on this arm, are
    counted — so a caller hands over the whole run and the separation happens here
    rather than at every call site.

    The years come first because they are the metric: the two window figures are a
    summary of them and a pooled fourteen-year number over a crash and a mania
    describes neither. The 2020–21-excluded window sits beside the full one rather
    than replacing it, because which of the two a reader should believe is exactly
    the question the pair exists to pose.
    """
    check_costs(contract, market)
    costs = contract.value(COSTS_KEY)[market]
    mine = [t for t in trades if t.market == market and t.arm == arm]
    kept = [t for t in mine if t.entry.session.year not in EXCLUDED_YEARS]
    return {
        "market": market,
        "arm": arm,
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
                arm=arm,
            )
            for year in _years(mine)
        ],
        "windows": [
            expectancy_cell(contract, mine, market=market, label=FULL_WINDOW, arm=arm),
            {
                **expectancy_cell(
                    contract, kept, market=market, label=EXCLUDED_YEARS_WINDOW, arm=arm
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
    arm: str = PRIMARY_ARM,
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
    named = tuple(markets) if markets is not None else tuple(
        contract.value(SCOPE_MARKETS_KEY)
    )
    return stamp_result(
        contract,
        {
            "metric": contract.value(METRIC_PRIMARY_KEY),
            "arm": arm,
            "pre_registered": True,
            "sweep": {"variants_tried": SWEPT_VARIANTS, "note": SWEEP_NOTE},
            "bootstrap": {
                "cluster": BOOTSTRAP_CLUSTER,
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "confidence": BOOTSTRAP_CONFIDENCE,
            },
            "year_attributed_to": "entry_session",
            "markets": [
                market_report(contract, trades, market=market, arm=arm)
                for market in named
            ],
        },
    )


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
        else "no interval"
    )
    return (
        f"  {cell['label']:<{width}} {cell['expectancy_r']:+.3f}R  "
        f"win {cell['win_rate']:.1%}  n={cell['closed']}  "
        f"med {dist['median']:+.2f} p90 {dist['p90']:+.2f} max {dist['max']:+.2f}  {ci}"
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
    markets = tuple(args.market) if args.market else tuple(
        contract.value(SCOPE_MARKETS_KEY)
    )
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
