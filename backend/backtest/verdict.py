"""The verdict: the criteria fixed in the contract, evaluated and recorded (issue #199).

Four outcomes, all four named before the run produced a number, each licensing
something written down in advance (``decision.*`` in the contract):

* **Kill** — the detector as encoded has no edge. The app's claim reduces to
  *ranking* what a human selects, never selecting on its own, and the write-up says
  so in those words.
* **Ship** — the licensed change is named before any constant moves, and goes
  through the calibration rule.
* **One market failing** — its own verdict: the method stands and that market is
  off until a run explains why it differs.
* **Neither** — the run is inconclusive and is reported as inconclusive.

The two criteria have different scopes, deliberately. The **kill is global**: it
needs *both* markets to fail, because findings §8 says magnitudes do not transfer,
so one market failing is evidence about that market rather than about the method.
The **ship is per market**: a US pass licenses nothing in Jakarta.

Which number each is drawn on
-----------------------------
The kill is measured on the **survivor-biased** figure, deliberately. Survivorship
inflates results in a known direction — the missing names are disproportionately the
ones that died — so a failure there is decisive: the honest figure can only be
worse. A *pass* proves much less, which is why only the ship criterion has to clear
Phase 2's pessimistic bound, and why a market with no bound attached cannot ship at
all. An absent bound is not a bound of zero.

Both windows, both criteria. The full window contains a mania that rewarded
momentum nearly everywhere; the 2020–21-excluded window is the same run without it.
A verdict resting on one of them is a verdict about the tape.

No swept figure enters
----------------------
:func:`verdict_report` refuses a metric report that carries swept variants
(:class:`SweptVerdictRefused`). "Reaching for a swept variant to break the tie is
the failure mode the whole contract exists to prevent" is the contract's own
sentence, and this is it made executable: a sweep's count rides on the payload for
the record, and none of its figures is reachable from the decision.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contract import (
    DECISION_INCONCLUSIVE_KEY,
    DECISION_KILL_KEY,
    DECISION_LICENSED_CHANGES_KEY,
    DECISION_ONE_MARKET_FAILURE_KEY,
    DECISION_SHIP_KEY,
    DEFAULT_CONTRACT,
    SCOPE_MARKETS_KEY,
    RunContract,
)
from .metric import (
    BIAS_BOUND_KEY,
    EXCLUDED_YEARS_WINDOW,
    FULL_WINDOW,
    PRE_REGISTERED_KEY,
    PRIMARY_ARM,
    PRIMARY_METRIC,
    SWEEP_KEY,
    VARIANTS_TRIED_KEY,
    window_cell,
)
from .result import stamp_result
from .run import ContractDrift
from .survivorship import bias_bound

# -- the four verdicts, and what each licenses ---------------------------------

KILL = "kill"
SHIP = "ship"
ONE_MARKET_FAILURE = "one_market_failure"
INCONCLUSIVE = "inconclusive"

# Precedence, in order. It is a tuple rather than a chain of ``if``s because the
# order *is* the rule and a reader should be able to see it in one line: a global
# kill outranks a single market's failure, which outranks any market's ship,
# because "the method has no edge" and "this market is off" are statements about
# more than the market that licensed a change.
PRECEDENCE = (KILL, ONE_MARKET_FAILURE, SHIP, INCONCLUSIVE)

# What each verdict licenses, written down before any number moved a constant
# (``decision.licensed_changes``). Quoted here rather than left to the write-up so
# the licensed change and the verdict are produced by the same command.
LICENSED: dict[str, str] = {
    KILL: (
        "the detector as encoded has no edge; the app's claim reduces to ranking "
        "what a human selects, never selecting on its own, and the write-up says "
        "so in those words"
    ),
    SHIP: (
        "the change this licenses is named in the write-up before any constant "
        "moves, and goes through the calibration rule (findings §7) like any "
        "other; it is licensed only in the market that passed"
    ),
    ONE_MARKET_FAILURE: (
        "the method stands and the failing market is off until a run explains why "
        "it differs; every other market keeps its own verdict and whatever that "
        "verdict licenses, because the ship is per market and one market's failure "
        "is evidence about that market"
    ),
    INCONCLUSIVE: (
        "nothing. The run is reported as inconclusive, and reaching for a swept "
        "variant to break the tie is the failure mode the contract exists to "
        "prevent"
    ),
}

# The two windows every criterion reads, in the order they are reported. Both, or
# the verdict is a verdict about the tape.
WINDOWS = (FULL_WINDOW, EXCLUDED_YEARS_WINDOW)

# The basis the kill is drawn on, as the contract spells it. Checked rather than
# assumed: a kill quietly redrawn on the pessimistic figure would fire on runs the
# contract does not kill.
KILL_BASIS = "survivor_biased_number"

# The sub-keys of the two decision cells, and the values this code implements.
# Named for the same reason the cells are: a bare ``cell["basis"]`` at five sites
# is five places a rename has to be found by grep, and the drift checks below are
# the one place the contract and the code are compared at all.
BASIS = "basis"
COMPARATOR = "comparator"
THRESHOLD = "threshold"
REQUIRES = "requires"
SCOPE = "scope"
KILL_COMPARATOR = "<="
KILL_THRESHOLD = 0.0
KILL_REQUIRES = ("both_markets", "full_window", "and_excluding_2020_2021")
SHIP_SCOPE = "per_market"
SHIP_REQUIRES = ("positive_result", "clears_phase2_pessimistic_bound")

# Why a market with no attached bound cannot ship, carried on that market's own
# block rather than left as a silent ``False``.
NO_BOUND_REASON = (
    "no survivorship bound is attached, and an absent bound is not a bound of "
    "zero: the ship criterion requires the pessimistic figure to stay above zero, "
    "so a market whose bias was never measured cannot clear it"
)

# How the hole under a market's bound was measured, carried onto that market's
# block. A bound is only as strong as the count it was built from, and Phase 2
# measured the two markets differently: US against a dated listing spine with
# recycled tickers separated out, IDX against the enumeration alone, where a
# recycled ticker cannot be told from an IPO at all. A ship licensed off the
# weaker basis is still a ship — the contract says so — but a reader who cannot
# see which basis it rests on cannot weigh it, so the fact rides on the verdict
# rather than on a paragraph somebody may not read.
BOUND_BASIS_KEY = "bound_basis"
WEAK_BASIS_CAVEAT = (
    "this market's hole is counted on the enumeration side and is neither "
    "exposure-weighted nor separated from recycled tickers, so its pessimistic "
    "bound is optimistic in a known direction: the true bound can only be lower"
)

# Phase 2 attaches a bound to the **full** window only, and the ship criterion reads
# both. The 2020–21-excluded twin is therefore derived here by re-running #196's own
# arithmetic at the same hole share — which assumes the hole is the same size inside
# the shorter window as across the whole one. That is an assumption rather than a
# measurement, and it makes the criterion *stricter* rather than looser, so it is
# recorded on the payload instead of left for a reader to infer from a figure #196
# never published.
DERIVED_BOUND_NOTE = (
    "the full window's bound is Phase 2's own; the 2020-21-excluded window's "
    "pessimistic figure is derived here at the same hole share, which assumes the "
    "hole is the same size inside the shorter window"
)

QUIET_WINDOW_REASON = (
    "a window with no closed trade has no expectancy to compare, so neither "
    "criterion can be evaluated on it and the market is inconclusive rather than "
    "passed or failed"
)


class SweptVerdictRefused(TypeError):
    """A verdict was asked for over a report carrying swept variants.

    The contract rules out breaking a tie with a swept figure, and a rule that only
    lives in prose is a rule somebody follows until the tie is close. So the type
    refuses: the decision reads the pre-registered report or it does not run.
    """


# -- refusing a contract that has moved out from under the code ----------------


def check_kill_cell(contract: RunContract) -> None:
    """Refuse a contract whose kill criterion is not the one evaluated here.

    Three things are pinned: the metric it is drawn on, the comparator, and the
    basis. A cell whose ``basis`` moved to the pessimistic figure would describe a
    stricter kill than this code fires, and the disagreement would be invisible —
    both would print a verdict.
    """
    cell = contract.value(DECISION_KILL_KEY)
    if cell.get(BASIS) != KILL_BASIS:
        raise ContractDrift(
            f"the kill criterion is drawn on {cell.get(BASIS)!r}; this evaluates "
            f"it on the {KILL_BASIS!r}, which is what makes a failure decisive"
        )
    if cell.get(COMPARATOR) != KILL_COMPARATOR:
        raise ContractDrift(
            f"the kill comparator is {cell.get(COMPARATOR)!r}, not "
            f"{KILL_COMPARATOR!r}; a strict comparator kills a different set of runs"
        )
    if cell.get(THRESHOLD) != KILL_THRESHOLD:
        raise ContractDrift(
            f"the kill threshold is {cell.get(THRESHOLD)!r}; this evaluates it at "
            f"{KILL_THRESHOLD}, and a moved line kills a different set of runs"
        )
    missing = [r for r in KILL_REQUIRES if r not in cell.get(REQUIRES, ())]
    if missing:
        raise ContractDrift(
            f"the kill criterion no longer requires {', '.join(missing)}; a kill "
            "over fewer markets or one window is a different verdict and has its "
            "own name"
        )


def check_ship_cell(contract: RunContract) -> None:
    """Refuse a contract whose ship criterion is not the one evaluated here.

    The kill has had this check since it was written and the ship needs it for the
    same reason, which is the stronger one: if ``clears_phase2_pessimistic_bound``
    dropped out of the cell, this code would go on demanding the bound while the
    contract no longer did — and the disagreement would print as a verdict either
    way, with a licence attached.
    """
    cell = contract.value(DECISION_SHIP_KEY)
    if cell.get(SCOPE) != SHIP_SCOPE:
        raise ContractDrift(
            f"the ship criterion is scoped {cell.get(SCOPE)!r}; this evaluates it "
            f"{SHIP_SCOPE!r}, because a pass in one market licenses nothing in the "
            "other"
        )
    missing = [r for r in SHIP_REQUIRES if r not in cell.get(REQUIRES, ())]
    if missing:
        raise ContractDrift(
            f"the ship criterion no longer requires {', '.join(missing)}; a ship "
            "that need not clear the Phase 2 bound is a different criterion"
        )


def check_pre_registered(report: Mapping[str, Any]) -> None:
    """Refuse anything but the recorded pre-registered metric as the decision input."""
    if report.get(PRE_REGISTERED_KEY) is not True:
        raise SweptVerdictRefused(
            "the verdict is evaluated on the pre-registered metric; this report "
            f"does not carry {PRE_REGISTERED_KEY}=true"
        )
    tried = report.get(SWEEP_KEY, {}).get(VARIANTS_TRIED_KEY)
    if tried:
        raise SweptVerdictRefused(
            f"this report carries {tried} swept variants; a swept figure may not "
            "enter the decision, and may not break a tie"
        )
    if report.get("metric") != PRIMARY_METRIC:
        raise ContractDrift(
            f"the verdict reads {PRIMARY_METRIC!r}; this report records "
            f"{report.get('metric')!r}"
        )


# -- one market's finding ------------------------------------------------------


@dataclass(frozen=True)
class WindowFigure:
    """One window's two numbers: the survivor-biased figure and its pessimistic twin.

    Both, always. The kill reads the first and the ship reads both, so a type that
    carried one of them would make one criterion reach somewhere else for the other.
    """

    label: str
    expectancy_r: float | None
    pessimistic_r: float | None
    closed: int

    @property
    def measured(self) -> bool:
        return self.expectancy_r is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "expectancy_r": self.expectancy_r,
            "pessimistic_r": self.pessimistic_r,
            "closed": self.closed,
        }


@dataclass(frozen=True)
class MarketFinding:
    """One market against both criteria, with the reason it landed where it did.

    ``fails`` and ``ships`` are not opposites and the type keeps them apart: a
    market can do neither, which is the inconclusive case the contract names, and a
    single boolean would have to pick one of the two to be its ``False``.
    """

    market: str
    windows: tuple[WindowFigure, ...]
    bound_attached: bool
    hole_share: float | None
    bound_basis: Mapping[str, Any] | None = None

    @property
    def measured(self) -> bool:
        """Both windows have an expectancy to read. Neither criterion runs without it."""
        return len(self.windows) == len(WINDOWS) and all(
            w.measured for w in self.windows
        )

    @property
    def fails(self) -> bool:
        """This market's half of the kill: at or below zero on **both** windows.

        Read off the survivor-biased figure, which is what makes a failure
        decisive — the honest number can only be worse.
        """
        return self.measured and all(
            (w.expectancy_r or 0.0) <= 0.0 for w in self.windows
        )

    @property
    def ships(self) -> bool:
        """Above zero on both windows, and the pessimistic bound above zero too."""
        if not self.measured or not self.bound_attached:
            return False
        return all(
            w.expectancy_r is not None
            and w.expectancy_r > 0.0
            and w.pessimistic_r is not None
            and w.pessimistic_r > 0.0
            for w in self.windows
        )

    @property
    def verdict(self) -> str:
        if self.ships:
            return SHIP
        if self.fails:
            return ONE_MARKET_FAILURE
        return INCONCLUSIVE

    @property
    def reason(self) -> str:
        """Why this market landed where it did, in one line, on every market.

        Printed on a pass as well as on a failure: a market that shipped and a
        market that could not be evaluated both print a verdict, and the difference
        between them is exactly this sentence.
        """
        if not self.measured:
            return QUIET_WINDOW_REASON
        if self.fails:
            return (
                "at or below zero on both windows on the survivor-biased figure, "
                "which is the decisive direction"
            )
        if self.ships:
            return (
                "above zero on both windows and the pessimistic bound holds above "
                "zero on both"
            )
        if not self.bound_attached:
            return NO_BOUND_REASON
        positive = [w for w in self.windows if (w.expectancy_r or 0.0) > 0.0]
        if not positive:
            return (
                "mixed across the two windows: neither above zero on both nor at "
                "or below zero on both"
            )
        if len(positive) < len(self.windows):
            return (
                "positive on one window and not the other, so it neither ships nor "
                "fails"
            )
        return (
            "positive on both windows, but the pessimistic bound does not stay "
            "above zero, so survivorship alone could account for it"
        )

    @property
    def bound_caveat(self) -> str | None:
        """Why this market's bound is weaker than it looks, or ``None`` if it is not.

        Reported on any market whose hole was counted on the weaker basis, whether
        or not it shipped: a caveat that appeared only under a pass would be a
        caveat a reader learns to read as a verdict.
        """
        if not self.bound_basis:
            return None
        weak = not self.bound_basis.get("exposure_weighted") or not self.bound_basis.get(
            "recycled_measured"
        )
        return WEAK_BASIS_CAVEAT if weak else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "verdict": self.verdict,
            "ships": self.ships,
            "fails": self.fails,
            "bound_attached": self.bound_attached,
            "hole_share": self.hole_share,
            BOUND_BASIS_KEY: dict(self.bound_basis) if self.bound_basis else None,
            "bound_caveat": self.bound_caveat,
            "windows": [w.to_dict() for w in self.windows],
            "reason": self.reason,
            "licenses": LICENSED[self.verdict],
        }


def bound_bases(survivorship: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """How each market's hole was counted, read off Phase 2's own report.

    Three fields and no numbers: the size of the hole already rides on the bound,
    and re-reading it here would be a second path to a figure the verdict is
    supposed to take from one place.
    """
    return {
        body["market"]: {
            "basis": body["hole"]["basis"],
            "recycled_measured": body["hole"]["recycled_measured"],
            "exposure_weighted": body["hole"]["exposure_weighted"],
        }
        for body in survivorship["markets"]
        if body.get("hole")
    }


def market_finding(
    body: Mapping[str, Any], *, basis: Mapping[str, Any] | None = None
) -> MarketFinding:
    """One market's block of the metric report, read as a finding.

    The pessimistic twin for each window is computed with
    :func:`~backtest.survivorship.bias_bound` — Phase 2's own arithmetic, off the
    hole share the attached bound already carries. Recomputing it here with a second
    formula would be a second place for the twin to be charged differently from the
    headline it is compared against, and #196's bound attaches only the full
    window's; the ship criterion reads both, so the second is derived from the same
    function rather than from a new one.
    """
    attached = body.get(BIAS_BOUND_KEY)
    share = attached.get("hole_share") if attached else None
    windows: list[WindowFigure] = []
    for label in WINDOWS:
        cell = window_cell(body, label)
        if cell is None:
            continue
        pessimistic = (
            bias_bound(cell, market=body["market"], hole_share=share).pessimistic_r
            if share is not None
            else None
        )
        windows.append(
            WindowFigure(
                label=label,
                expectancy_r=cell["expectancy_r"],
                pessimistic_r=pessimistic,
                closed=int(cell["closed"]),
            )
        )
    return MarketFinding(
        market=body["market"],
        windows=tuple(windows),
        bound_attached=attached is not None,
        hole_share=share,
        bound_basis=basis,
    )


# -- the run's verdict ---------------------------------------------------------


def kill_fires(findings: Sequence[MarketFinding], *, scope: Sequence[str]) -> bool:
    """The global kill: every market in the contract's scope fails.

    Scope rather than "the markets present", because a kill computed over one
    market's block would fire the run's most consequential verdict on half the
    evidence — and a market missing from the report is exactly how that would
    happen without anybody choosing it.
    """
    by_market = {f.market: f for f in findings}
    if any(market not in by_market for market in scope):
        return False
    return bool(scope) and all(by_market[market].fails for market in scope)


def run_verdict(findings: Sequence[MarketFinding], *, scope: Sequence[str]) -> str:
    """The run's one verdict, by the precedence in :data:`PRECEDENCE`.

    Driven off that tuple rather than off a chain of ``if``s, so the order a reader
    sees declared is the order the code takes: reordering the rule is reordering
    :data:`PRECEDENCE`, and a verdict with no test below is a ``KeyError`` here
    rather than a silent fall-through to "inconclusive".

    The per-market findings are the operative ones and they all ride on the payload;
    this is the global reading. A market that ships under a run-level
    ``one_market_failure`` still ships — its own block says so, and that verdict's
    licence says so too — while the run-level word names the more consequential
    fact, which is that a market is off.
    """
    fires = {
        KILL: lambda: kill_fires(findings, scope=scope),
        ONE_MARKET_FAILURE: lambda: any(f.fails for f in findings),
        SHIP: lambda: any(f.ships for f in findings),
        INCONCLUSIVE: lambda: True,
    }
    return next(verdict for verdict in PRECEDENCE if fires[verdict]())


def check_scope(report: Mapping[str, Any], contract: RunContract) -> None:
    """Refuse a metric report missing a market the contract's scope names."""
    present = {body["market"] for body in report["markets"]}
    missing = [m for m in contract.value(SCOPE_MARKETS_KEY) if m not in present]
    if missing:
        raise ContractDrift(
            f"the metric report is missing {', '.join(missing)}; the kill is global "
            "and cannot be evaluated over a subset of the contract's markets"
        )


def verdict_report(
    contract: RunContract,
    metric: Mapping[str, Any],
    *,
    sweep: Mapping[str, Any] | None = None,
    bases: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """The verdict as one stamped payload: the criteria, the findings, the licence.

    ``sweep`` is recorded and never read into the decision. Its count rides on the
    payload so a reader can see how many variants were tried beside a verdict that
    none of them informed — which is the honest form of "the pre-registered number
    stands as the headline even when a swept one looks better".
    """
    check_kill_cell(contract)
    check_ship_cell(contract)
    check_pre_registered(metric)
    check_scope(metric, contract)

    scope = tuple(contract.value(SCOPE_MARKETS_KEY))
    findings = [
        market_finding(body, basis=(bases or {}).get(body["market"]))
        for body in metric["markets"]
    ]
    verdict = run_verdict(findings, scope=scope)
    return stamp_result(
        contract,
        {
            "verdict": verdict,
            "licenses": LICENSED[verdict],
            "arm": PRIMARY_ARM,
            "metric": metric["metric"],
            "basis": KILL_BASIS,
            "windows": list(WINDOWS),
            "bound_note": DERIVED_BOUND_NOTE,
            "criteria": {
                "kill": contract.value(DECISION_KILL_KEY),
                "ship": contract.value(DECISION_SHIP_KEY),
                "one_market_failure": contract.value(
                    DECISION_ONE_MARKET_FAILURE_KEY
                ),
                "inconclusive": contract.value(DECISION_INCONCLUSIVE_KEY),
                "licensed_changes": contract.value(DECISION_LICENSED_CHANGES_KEY),
            },
            "kill": {
                "fired": verdict == KILL,
                "scope": "global",
                "markets_required": list(scope),
                "basis": KILL_BASIS,
                "failing": [f.market for f in findings if f.fails],
            },
            "ship": {
                "scope": "per_market",
                "shipping": [f.market for f in findings if f.ships],
                "requires_bound": True,
            },
            "markets": [f.to_dict() for f in findings],
            SWEEP_KEY: {
                VARIANTS_TRIED_KEY: (
                    sweep[VARIANTS_TRIED_KEY] if sweep else 0
                ),
                "used_in_verdict": False,
                "note": (
                    "swept variants are recorded beside this verdict and none of "
                    "them entered it; a swept variant may not break a tie"
                ),
            },
        },
    )


# -- printing it, and the command that produces it -----------------------------


def format_verdict(report: Mapping[str, Any]) -> str:
    """The verdict as a page a terminal can print — the licence beside the word.

    The licensed change is printed immediately under the verdict and never in a
    footnote, because a verdict read without it is a verdict somebody converts into
    an edit.
    """
    lines = [
        f"verdict: {report['verdict'].upper()} — arm {report['arm']}, "
        f"on the {report['basis'].replace('_', ' ')}",
        f"  licenses: {report['licenses']}",
        "",
        f"kill (global, both markets, both windows): "
        f"{'FIRED' if report['kill']['fired'] else 'did not fire'}"
        + (
            f" — failing: {', '.join(report['kill']['failing'])}"
            if report["kill"]["failing"]
            else ""
        ),
        "ship (per market): "
        + (
            ", ".join(report["ship"]["shipping"])
            if report["ship"]["shipping"]
            else "no market cleared it"
        ),
        "",
    ]
    for body in report["markets"]:
        lines.append(f"{body['market']} — {body['verdict']}")
        for window in body["windows"]:
            headline = (
                "no closed trades"
                if window["expectancy_r"] is None
                else f"{window['expectancy_r']:+.3f}R on n={window['closed']}"
            )
            bound = (
                "no bound"
                if window["pessimistic_r"] is None
                else f"pessimistic {window['pessimistic_r']:+.3f}R"
            )
            lines.append(f"  {window['label']:<22} {headline:<28} {bound}")
        lines.append(f"  {body['reason']}")
        if body.get("bound_caveat"):
            lines.append(f"  caveat: {body['bound_caveat']}")
        lines.append(f"  licenses: {body['licenses']}")
        lines.append("")
    lines.append(
        f"swept variants tried: {report[SWEEP_KEY][VARIANTS_TRIED_KEY]} — "
        f"{report[SWEEP_KEY]['note']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Evaluate the contract's criteria over the recorded headline, and record it.

    The command::

        python -m backtest.verdict \\
            --metric-json references/backtest_primary_metric.json \\
            --sweep-json references/backtest_sweep.json \\
            --out-json references/backtest_verdict.json

    The metric report must be the **bounded** one — the pre-registered headline with
    Phase 2's bound attached by ``python -m backtest.survivorship
    --metric-json ... --out-metric-json ...`` — because a market with no bound
    cannot clear the ship criterion and will report exactly that.

    ``--sweep-json`` is optional and is read for its **count only**. Nothing in the
    decision reads a swept figure.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--metric-json", required=True,
        help="the recorded pre-registered metric, bounded by backtest.survivorship",
    )
    parser.add_argument(
        "--sweep-json", default=None,
        help="a sweep from `python -m backtest.sweep`; its count is recorded beside "
             "the verdict and none of its figures enters it",
    )
    parser.add_argument(
        "--survivorship-json", default=None,
        help="Phase 2's report, from `python -m backtest.survivorship --out-json`; "
             "read for how each market's hole was counted, so a bound built on the "
             "weaker basis carries its caveat",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped verdict",
    )
    args = parser.parse_args(argv)

    metric = json.loads(Path(args.metric_json).read_text())
    sweep = (
        json.loads(Path(args.sweep_json).read_text()) if args.sweep_json else None
    )
    bases = (
        bound_bases(json.loads(Path(args.survivorship_json).read_text()))
        if args.survivorship_json
        else None
    )
    report = verdict_report(DEFAULT_CONTRACT, metric, sweep=sweep, bases=bases)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_verdict(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
