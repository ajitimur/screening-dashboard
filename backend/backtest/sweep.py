"""Sweeping cost and threshold variants — after the headline, never before (issue #199).

Phase 5 ends with a sweep, and the order is the whole point: the pre-registered
metric is computed and **recorded** first, and only then may a variant be tried.
Every threshold tried is a test, and enough of them will produce a winner from
noise. Three exit arms and three regime states are already nine views of one
dataset before a single variant is swept.

So the ordering is not a convention this module documents and hopes for — it is the
type it takes. :func:`sweep_report` cannot be reached without a
:class:`RecordedMetric`, and the only way to make one is :func:`read_recorded`,
which reads the headline **back off disk**. A sweep run before the headline was
recorded has no file to read, and a sweep run over a swept report is refused for the
same reason a sweep of a sweep is not a second opinion.

What is swept, and what is not
------------------------------
Two axes, both computable from trades the simulator already produced:

* **Costs** — the contract's per-market commission and slippage, scaled. The plan
  names costs as swept (``costs.per_market``'s own justification says so), and the
  pre-registered baseline is what the headline was charged.
* **The score floor** — trade only detections scoring at or above *k* of the
  replayed rubric's eight points. This is the threshold a reader reaches for first
  and #194 already measured the rubric's ranking as a null, so a floor that looks
  good here is exactly the winner-from-noise this ticket exists to bound.

The detection gate is **not** swept: the contract says so in as many words
(``detection.gate``), because the denominator was built against that width and a
swept gate would need a new crawl rather than new arithmetic.

Nothing here moves a constant. A variant carries its own :class:`RunContract`, built
by copying the committed one and replacing a single cell, and that variant contract
is never written to disk and never becomes :data:`~backtest.contract.DEFAULT_CONTRACT`.
The rubric, the detector and the gates are read and never touched.

Why a swept figure can never be quoted alone
--------------------------------------------
:func:`best_variant` returns a :class:`SweptResult`, and the count of variants tried
is a field on it rather than a number a caller looks up separately. A swept figure
and the number of chances it had are the same fact, so they travel together — a
result quoted without the count is a result quoted without its p-value's
denominator.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from screener.store import Store

from .contract import (
    COSTS_KEY,
    DEFAULT_CONTRACT,
    DETECTION_GATE_KEY,
    SCOPE_MARKETS_KEY,
    Cell,
    RunContract,
)
from .cohort import detection_index
from .denominator import DenominatorStore, denominator_path
from .metric import (
    COMMISSION_BPS,
    EXCLUDED_YEARS,
    EXCLUDED_YEARS_WINDOW,
    FULL_WINDOW,
    PRE_REGISTERED_KEY,
    PRIMARY_ARM,
    PRIMARY_METRIC,
    SLIPPAGE_BPS,
    SWEEP_KEY,
    VARIANTS_TRIED_KEY,
    expectancy_cell,
    market_block,
    window_cell,
)
from .ranking import SCORE_MAX_POINTS, ScoredTrade, scored_trades
from .result import stamp_result
from .run import ContractDrift
from .simulate import simulate_market

# -- the rule the order encodes ------------------------------------------------
#
# The three keys that say what kind of payload this is — ``pre_registered``,
# ``sweep`` and ``variants_tried`` — are :mod:`backtest.metric`'s, imported rather
# than respelled: that module writes them and this one refuses on them, and a
# rename reaching only the reader would leave the refusal passing everything.

MULTIPLE_COMPARISONS_NOTE = (
    "every threshold tried is a test, and enough of them will produce a winner "
    "from noise; three exit arms and three regime states are already nine views of "
    "one dataset before any sweep begins, so every swept figure is reported with "
    "the count of variants behind it"
)

HEADLINE_RULE = (
    "the pre-registered figure stands as the headline even where a swept variant "
    "looks better; a swept variant may not break a tie and licenses nothing"
)


class SweptBeforeRecorded(RuntimeError):
    """A sweep was asked for before the pre-registered metric was recorded.

    The ordering is the ticket. A sweep computed first and a headline computed
    second are indistinguishable in the output from the honest order, so the
    distinction is enforced at the door: the headline has to exist **on disk**
    before a variant can be built.
    """


# -- the axes ------------------------------------------------------------------

# The cost axis: the contract's per-market bps, scaled. Both directions, because a
# sweep that only ever raised costs would be a stress test rather than a sweep —
# the flattering variant is precisely the one a reader must see counted.
COST_AXIS = "costs"
COST_MULTIPLIERS = (0.5, 2.0, 3.0)

# The threshold axis: a minimum on the replayed seven-dimension score, out of eight
# points. Floors below three would cut almost nothing (the distribution sits high)
# and a floor of eight is a handful of trades in the whole run, so the swept range
# is the interior where a cut both bites and leaves a cohort.
SCORE_FLOOR_AXIS = "score_floor"
SCORE_FLOORS = (3, 4, 5, 6, 7)

# What each axis varied, in one place: the payload's ``axes`` block is built from
# this rather than restated beside it, so an axis added below cannot go unreported.
AXIS_VALUES: dict[str, list[Any]] = {
    COST_AXIS: [f"×{m:g}" for m in COST_MULTIPLIERS],
    SCORE_FLOOR_AXIS: list(SCORE_FLOORS),
}
AXES = tuple(AXIS_VALUES)

# What is deliberately *not* swept, recorded here rather than left as an absence a
# reader has to notice: the denominator was built against the contract's gate width
# and varying it needs a new crawl, not new arithmetic.
NOT_SWEPT = (DETECTION_GATE_KEY,)
NOT_SWEPT_NOTE = (
    "the detection gate is not swept in this run: the denominator was built "
    "against the contract's four-lookback width, so a swept gate is a new crawl "
    "rather than a variant of this one"
)


# -- reading the recorded headline ---------------------------------------------


@dataclass(frozen=True)
class RecordedMetric:
    """The pre-registered headline, read back off disk before any sweep runs.

    Carrying the ``path`` rather than only the payload is what makes the claim
    checkable afterwards: the sweep's own output names the file its headline came
    from, so "was the headline recorded first?" is answerable from the committed
    bytes rather than from a promise in a commit message.
    """

    path: Path
    report: dict[str, Any]

    def market(self, market: str) -> dict[str, Any]:
        body = market_block(self.report, market)
        if body is None:
            raise KeyError(
                f"the recorded headline has no {market!r} block; a sweep cannot be "
                "reported against a market the pre-registered metric never measured"
            )
        return body

    def expectancy(self, market: str, label: str = FULL_WINDOW) -> float | None:
        """The pre-registered after-cost expectancy for one market and window."""
        cell = window_cell(self.market(market), label)
        if cell is None:
            raise KeyError(f"no {label!r} window on the recorded headline for {market}")
        return cell["expectancy_r"]


def read_recorded(path: str | Path) -> RecordedMetric:
    """The one way to obtain a :class:`RecordedMetric` — and the ordering check.

    Four refusals, and each is a way the ticket's first acceptance criterion could
    be broken while the output still looked right:

    * **No file.** The headline was never recorded, so there is nothing for a
      swept figure to stand beside.
    * **Not pre-registered.** A payload without the flag is not the headline.
    * **Already swept.** ``variants_tried`` above zero means this *is* a sweep, and
      a sweep of a sweep hides the count that matters behind a smaller one.
    * **A different metric.** A headline computed on another metric would let a
      swept arm-B figure be reported against an arm-A promise.
    """
    file = Path(path)
    if not file.exists():
        raise SweptBeforeRecorded(
            f"no recorded pre-registered metric at {file}: the headline is "
            "computed and recorded before any variant is swept, so there is "
            "nothing here for a swept figure to be reported beside"
        )
    report = json.loads(file.read_text())
    if report.get(PRE_REGISTERED_KEY) is not True:
        raise SweptBeforeRecorded(
            f"{file} does not carry {PRE_REGISTERED_KEY}=true; only the "
            "pre-registered metric may be swept against"
        )
    tried = report.get(SWEEP_KEY, {}).get(VARIANTS_TRIED_KEY)
    if tried != 0:
        raise SweptBeforeRecorded(
            f"{file} already reports {tried} swept variants; a sweep of a sweep "
            "reports the second count and hides the first"
        )
    if report.get("metric") != PRIMARY_METRIC:
        raise ContractDrift(
            f"{file} records {report.get('metric')!r}, not the pre-registered "
            f"{PRIMARY_METRIC!r}; a swept variant of one metric cannot be reported "
            "against another's promise"
        )
    return RecordedMetric(path=file, report=report)


# -- the variants --------------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    """One swept variant: an axis, a label, its contract and its cut.

    The contract is the variant's own — the committed one with a single cell
    replaced — so a variant's figures are computed under a contract that says what
    they were computed under. ``min_points`` is ``None`` on every cost variant,
    because a variant varies one thing or it measures two at once.
    """

    axis: str
    label: str
    contract: RunContract
    min_points: int | None = None

    def keep(self, scored: ScoredTrade) -> bool:
        """Whether this variant's cut admits one trade. Costs admit every trade."""
        return self.min_points is None or scored.points >= self.min_points

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "label": self.label,
            "costs": self.contract.value(COSTS_KEY),
            "min_points": self.min_points,
        }


# The suffix every variant contract's label carries. Two runs under different
# contracts are distinguishable from their serialised output alone (#184), and a
# variant is a different contract — so its label says so rather than leaving a
# reader to compare cost cells.
VARIANT_LABEL_SUFFIX = " — swept variant, not the pre-registered run"


def variant_contract(
    contract: RunContract, *, key: str, value: Any, why: str
) -> RunContract:
    """The committed contract with one cell replaced — a variant, never a revision.

    The result is a new value that is returned, printed and thrown away. It is
    never written over the committed contract file and never rebinds
    :data:`~backtest.contract.DEFAULT_CONTRACT`, which is what keeps this module
    inside the ticket's last acceptance criterion: no detector, rubric or gate
    constant moves because a sweep ran.
    """
    return RunContract(
        contract_version=contract.contract_version,
        label=contract.label + VARIANT_LABEL_SUFFIX,
        cells=tuple(
            Cell(key=c.key, value=value, justification=why) if c.key == key else c
            for c in contract.cells
        ),
    )


def scaled_costs(contract: RunContract, multiplier: float) -> dict[str, Any]:
    """The contract's per-market costs, both components scaled by ``multiplier``."""
    return {
        market: {
            COMMISSION_BPS: float(costs[COMMISSION_BPS]) * multiplier,
            SLIPPAGE_BPS: float(costs[SLIPPAGE_BPS]) * multiplier,
        }
        for market, costs in contract.value(COSTS_KEY).items()
    }


def cost_variants(contract: RunContract = DEFAULT_CONTRACT) -> tuple[Variant, ...]:
    """The cost axis: every market's commission and slippage scaled together.

    Scaled together rather than per market, because a variant that raised Jakarta's
    costs and left New York's alone would be two variants reported as one and would
    make the per-market comparison the run is built on incomparable.
    """
    return tuple(
        Variant(
            axis=COST_AXIS,
            label=f"costs×{multiplier:g}",
            contract=variant_contract(
                contract,
                key=COSTS_KEY,
                value=scaled_costs(contract, multiplier),
                why=(
                    f"a swept cost variant at {multiplier:g}× the pre-registered "
                    "per-market commission and slippage; the pre-registered "
                    "baseline is the headline and this is not"
                ),
            ),
        )
        for multiplier in COST_MULTIPLIERS
    )


def score_floor_variants(
    contract: RunContract = DEFAULT_CONTRACT,
) -> tuple[Variant, ...]:
    """The threshold axis: trade only detections at or above *k* of eight points.

    The contract is the committed one, unchanged: a score floor is a cut applied to
    the cohort rather than a cell the run pre-registered, and inventing a cell for
    it would put a swept threshold in the same object as the promised ones.
    """
    return tuple(
        Variant(
            axis=SCORE_FLOOR_AXIS,
            label=f"score>={floor}",
            contract=contract,
            min_points=floor,
        )
        for floor in SCORE_FLOORS
    )


def variants(contract: RunContract = DEFAULT_CONTRACT) -> tuple[Variant, ...]:
    """Every variant this sweep tries, in axis order — the count is ``len`` of it.

    One list, so the count reported beside a swept figure and the variants actually
    computed cannot diverge: both are this tuple.
    """
    return cost_variants(contract) + score_floor_variants(contract)


# -- running them --------------------------------------------------------------


def variant_market(
    variant: Variant, cohort: Sequence[ScoredTrade], *, market: str, tried: int
) -> dict[str, Any]:
    """One variant's two windows for one market, with the count of variants on it.

    The arithmetic is :mod:`backtest.metric`'s own
    (:func:`~backtest.metric.expectancy_cell`), so a swept cell and a headline cell
    cannot report the same trades differently — the difference between them is the
    contract and the cut, and nothing else.
    """
    kept = [s.trade for s in cohort if s.trade.market == market and variant.keep(s)]
    excluded = [t for t in kept if t.entry.session.year not in EXCLUDED_YEARS]
    return {
        "market": market,
        VARIANTS_TRIED_KEY: tried,
        "is_headline": False,
        "windows": [
            expectancy_cell(
                variant.contract, kept, market=market, label=FULL_WINDOW
            ),
            {
                **expectancy_cell(
                    variant.contract,
                    excluded,
                    market=market,
                    label=EXCLUDED_YEARS_WINDOW,
                ),
                "excluded_years": list(EXCLUDED_YEARS),
            },
        ],
    }


def pre_registered_block(recorded: RecordedMetric) -> dict[str, Any]:
    """The recorded headline, copied onto the sweep's own payload.

    Copied rather than referenced by path alone: the sweep's output is read on its
    own, and a reader who has to open a second file to find the figure that stands
    is a reader who will quote the swept one.
    """
    return {
        "source": str(recorded.path),
        "metric": recorded.report["metric"],
        "arm": recorded.report["arm"],
        "is_headline": True,
        VARIANTS_TRIED_KEY: 0,
        "markets": [
            {
                "market": body["market"],
                "windows": [
                    {"label": cell["label"], "expectancy_r": cell["expectancy_r"]}
                    for cell in body["windows"]
                ],
            }
            for body in recorded.report["markets"]
        ],
    }


def sweep_report(
    recorded: RecordedMetric,
    cohorts: Mapping[str, Sequence[ScoredTrade]],
    *,
    contract: RunContract = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    """Every variant, per market, under the headline that was recorded first.

    ``cohorts`` is each market's scored trades — the simulator's arm-B trades joined
    to the score of the detection that produced them, which is what the threshold
    axis cuts on.

    The pre-registered block comes first in the payload for the same reason
    :func:`~backtest.metric.format_metric` prints the years before the windows: the
    serialised order is where "the headline stands" is either honoured or quietly
    broken.
    """
    tried = len(variants(contract))
    named = tuple(contract.value(SCOPE_MARKETS_KEY))
    return stamp_result(
        contract,
        {
            "swept": True,
            "arm": PRIMARY_ARM,
            PRE_REGISTERED_KEY: pre_registered_block(recorded),
            VARIANTS_TRIED_KEY: tried,
            "axes": [
                {"axis": axis, "values": AXIS_VALUES[axis]}
                | ({"of_points": SCORE_MAX_POINTS} if axis == SCORE_FLOOR_AXIS else {})
                for axis in AXES
            ],
            "not_swept": {"cells": list(NOT_SWEPT), "note": NOT_SWEPT_NOTE},
            "variants": [
                {
                    **variant.to_dict(),
                    VARIANTS_TRIED_KEY: tried,
                    "is_headline": False,
                    "markets": [
                        variant_market(
                            variant,
                            cohorts.get(market, ()),
                            market=market,
                            tried=tried,
                        )
                        for market in named
                    ],
                }
                for variant in variants(contract)
            ],
            "note": MULTIPLE_COMPARISONS_NOTE,
            "headline_rule": HEADLINE_RULE,
        },
    )


# -- reading a swept figure without dropping its count -------------------------


@dataclass(frozen=True)
class SweptResult:
    """One swept figure and the number of chances it had, as a single value.

    The count is a field rather than something a caller fetches separately, because
    the two are one fact: the best of eight variants is a different claim from a
    figure measured once, and a type that let them be separated would let the
    difference be dropped in the retelling.
    """

    axis: str
    label: str
    market: str
    window: str
    expectancy_r: float | None
    variants_tried: int
    headline_r: float | None
    is_headline: bool = False

    @property
    def beats_headline(self) -> bool:
        if self.expectancy_r is None or self.headline_r is None:
            return False
        return self.expectancy_r > self.headline_r

    def line(self) -> str:
        """The swept figure as the one line it travels on, count included."""
        if self.expectancy_r is None:
            return (
                f"  {self.market} {self.window}: no swept variant produced a "
                f"closed cohort ({self.variants_tried} variants tried)"
            )
        headline = (
            "no headline recorded"
            if self.headline_r is None
            else f"headline {self.headline_r:+.3f}R stands"
        )
        return (
            f"  {self.market} {self.window}: best swept {self.expectancy_r:+.3f}R "
            f"({self.axis} {self.label}) out of {self.variants_tried} variants "
            f"tried — {headline}"
        )


def best_variant(
    report: Mapping[str, Any], *, market: str, window: str = FULL_WINDOW
) -> SweptResult:
    """The most flattering swept figure for one market and window, with its count.

    "Most flattering" rather than "best", deliberately: this is the number a reader
    would reach for, so it is the one the report puts under the count and beside the
    headline that stands regardless.
    """
    # Through :func:`headline` rather than around it: the figure a swept result is
    # compared against and the figure that stands have to be the same read, or the
    # comparison printed beside the count is against a number nobody promised.
    stands = headline(report, market=market, window=window)
    tried = report[VARIANTS_TRIED_KEY]
    best: SweptResult | None = None
    for variant in report["variants"]:
        for body in variant["markets"]:
            if body["market"] != market:
                continue
            cell = window_cell(body, window)
            if cell is not None and cell["expectancy_r"] is not None:
                if best is None or cell["expectancy_r"] > (best.expectancy_r or 0.0):
                    best = SweptResult(
                        axis=variant["axis"],
                        label=variant["label"],
                        market=market,
                        window=window,
                        expectancy_r=cell["expectancy_r"],
                        variants_tried=tried,
                        headline_r=stands,
                    )
    return best or SweptResult(
        axis="", label="", market=market, window=window, expectancy_r=None,
        variants_tried=tried, headline_r=stands,
    )


def headline(
    report: Mapping[str, Any], *, market: str, window: str = FULL_WINDOW
) -> float | None:
    """The figure that stands — the pre-registered one, whatever the sweep found.

    A function rather than a dictionary lookup at four call sites, so "which number
    is the headline?" has one answer in the code as well as in the prose.
    """
    body = market_block(report[PRE_REGISTERED_KEY], market)
    cell = window_cell(body, window) if body else None
    if cell is None:
        raise KeyError(f"no recorded headline for {market} on the {window!r} window")
    return cell["expectancy_r"]


# -- printing it, and the command that produces it -----------------------------


def _variant_figure(cell: Mapping[str, Any] | None) -> str:
    """One swept cell as a figure and the cohort behind it, or the absence of one.

    The n is printed beside every swept figure and never dropped: a floor that
    cuts the cohort to a handful is how a sweep produces its most flattering
    number, and the figure alone does not show it.
    """
    if cell is None or cell["expectancy_r"] is None:
        return "no closed trades"
    return f"{cell['expectancy_r']:+.3f}R n={cell['closed']}"


def format_sweep(report: Mapping[str, Any]) -> str:
    """The sweep as a page a terminal can print — the headline first, always."""
    pre = report[PRE_REGISTERED_KEY]
    lines = [
        f"swept variants — {report[VARIANTS_TRIED_KEY]} tried, "
        f"arm {report['arm']}",
        f"  {HEADLINE_RULE}",
        "",
        f"the pre-registered headline ({pre['source']})",
    ]
    for body in pre["markets"]:
        figures = "  ".join(
            f"{cell['label']} "
            + ("n/a" if cell["expectancy_r"] is None else f"{cell['expectancy_r']:+.3f}R")
            for cell in body["windows"]
        )
        lines.append(f"  {body['market']:<5} {figures}")

    lines += ["", "the most flattering swept figure, with its count"]
    for body in pre["markets"]:
        for window in (FULL_WINDOW, EXCLUDED_YEARS_WINDOW):
            lines.append(best_variant(report, market=body["market"], window=window).line())

    # Both windows on every variant, for the reason the headline reports both: a
    # swept figure that only holds on the full window is a figure about the mania,
    # and a table printing one column would hide exactly that.
    lines += ["", f"every variant — {FULL_WINDOW} | {EXCLUDED_YEARS_WINDOW}"]
    for variant in report["variants"]:
        for body in variant["markets"]:
            figures = " | ".join(
                _variant_figure(window_cell(body, label))
                for label in (FULL_WINDOW, EXCLUDED_YEARS_WINDOW)
            )
            lines.append(
                f"  {variant['axis']:<12} {variant['label']:<12} "
                f"{body['market']:<5} {figures}"
            )
    lines += ["", f"  {report['not_swept']['note']}", f"  {report['note']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Sweep the variants, against a headline that was recorded first.

    The command::

        python -m backtest.sweep --store data/backtest.duckdb \\
            --recorded references/backtest_primary_metric.json \\
            --out-json references/backtest_sweep.json

    ``--recorded`` is required and is not a convenience: it is the ordering rule.
    Without a recorded pre-registered metric on disk the command refuses to run,
    which is the acceptance criterion made executable rather than documented.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument(
        "--recorded", required=True,
        help="the recorded pre-registered metric, from "
             "`python -m backtest.metric --out-json`; no sweep runs without it",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped sweep",
    )
    args = parser.parse_args(argv)

    contract = DEFAULT_CONTRACT
    # Read first, and let it raise before a single bar is opened: a sweep that
    # computed its variants and *then* discovered no headline had been recorded
    # would have done the forbidden thing already.
    recorded = read_recorded(args.recorded)

    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        cohorts: dict[str, list[ScoredTrade]] = {}
        for market in contract.value(SCOPE_MARKETS_KEY):
            trades = simulate_market(
                store, denominator, market, contract, arms=(PRIMARY_ARM,)
            )
            cohorts[market] = scored_trades(
                trades, detection_index(denominator, market)
            )
    finally:
        denominator.close()
        store.close()

    report = sweep_report(recorded, cohorts, contract=contract)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_sweep(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
