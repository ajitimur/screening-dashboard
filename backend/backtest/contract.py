"""The backtest run contract as a single frozen, serialisable value (issue #184).

The contract is the whole of Phase 0: every choice the run makes before any code
runs, fixed and committed so no threshold is chosen after seeing its result (PRD
user story 1). It is modelled as an **ordered list of cells**, each a
:class:`Cell` carrying a stable ``key``, a JSON-native ``value`` and a one-line
``justification`` — so a reader can tell a measured choice from an arbitrary one
(user story 3), and so the whole object round-trips to and from JSON without loss.

Why a value and not module constants
-------------------------------------
The plan requires that a later contract change be a *new run recorded beside the
old one*, never a revision mistaken for the original (user story 2). That is only
enforceable if the contract is data that travels with its results, so the
contract is stamped into everything the package emits (:func:`backtest.stamp_result`).
Two runs under different contracts are therefore distinguishable from their
serialised output alone: any cell that differs changes the bytes.

Why a flat cell list rather than a typed tree
---------------------------------------------
Every cell — scalar, gate, exit arm, decision rule — carries the same two things:
a value and its justification. A flat list keeps serialisation lossless and
trivial (a cell is exactly its JSON object), keeps the file diff-stable (cells
are emitted in a fixed order), and lets a later phase register a new cell without
a schema migration. Typed access is provided by :meth:`RunContract.value` keyed
on the ``*_KEY`` constants below; the contract is data, and callers look values
up by key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The committed serialised contract lives beside the reference study's outputs,
# under ``references/``. Committing it is what "fixed before any code runs" means
# (user story 1); a drift test pins :data:`DEFAULT_CONTRACT` against these bytes.
DEFAULT_CONTRACT_JSON = (
    Path(__file__).resolve().parents[2] / "references" / "backtest_run_contract.json"
)

# A JSON-native value: the leaf types round-trip through ``json`` byte-for-value.
JSONValue = Any


@dataclass(frozen=True)
class Cell:
    """One Phase 0 choice: a stable key, a JSON-native value, and why it was made.

    ``value`` is restricted to JSON-native shapes (``str``/``int``/``float``/
    ``bool``/``None``/``list``/``dict``) so that a cell *is* its serialised form —
    :meth:`to_dict` and :meth:`from_dict` are lossless with no normalisation, and
    two cells differing in any value differ in their bytes. ``justification`` is
    the one-line record required of every cell (PRD user story 3).
    """

    key: str
    value: JSONValue
    justification: str

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("a contract cell needs a key")
        if not self.justification or not self.justification.strip():
            raise ValueError(f"cell {self.key!r} needs a one-line justification")

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "justification": self.justification}

    @staticmethod
    def from_dict(d: dict) -> "Cell":
        return Cell(key=d["key"], value=d["value"], justification=d["justification"])


@dataclass(frozen=True)
class RunContract:
    """The frozen run contract: an ordered, key-unique collection of cells.

    ``contract_version`` and ``label`` name the run so a revision reads as a new
    run beside the old one (user story 2). The cells hold every Phase 0 choice.
    """

    contract_version: str
    label: str
    cells: tuple[Cell, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for cell in self.cells:
            if cell.key in seen:
                raise ValueError(f"duplicate contract cell key: {cell.key!r}")
            seen.add(cell.key)

    # -- typed access ---------------------------------------------------------

    def cell(self, key: str) -> Cell:
        """The cell at ``key`` (raises ``KeyError`` if the run never registered it)."""
        for cell in self.cells:
            if cell.key == key:
                return cell
        raise KeyError(key)

    def value(self, key: str) -> JSONValue:
        """The value of the cell at ``key`` — the typed read every caller uses."""
        return self.cell(key).value

    def keys(self) -> tuple[str, ...]:
        return tuple(c.key for c in self.cells)

    # -- serialisation --------------------------------------------------------

    def to_dict(self) -> dict:
        """A JSON-serialisable dict of the whole contract, cells in registered order."""
        return {
            "contract_version": self.contract_version,
            "label": self.label,
            "cells": [c.to_dict() for c in self.cells],
        }

    @staticmethod
    def from_dict(d: dict) -> "RunContract":
        """Reconstruct a contract from :meth:`to_dict` output, losslessly."""
        return RunContract(
            contract_version=d["contract_version"],
            label=d["label"],
            cells=tuple(Cell.from_dict(c) for c in d["cells"]),
        )

    def to_json(self, *, indent: int = 2) -> str:
        """The committed on-disk form: stable, indented JSON with a trailing newline."""
        return json.dumps(self.to_dict(), indent=indent) + "\n"

    @staticmethod
    def from_json(text: str) -> "RunContract":
        return RunContract.from_dict(json.loads(text))

    def write(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.to_json())

    @staticmethod
    def load(path: str | Path) -> "RunContract":
        return RunContract.from_json(Path(path).read_text())


# -- the committed Phase 0 contract -------------------------------------------
#
# Every cell below is a Phase 0 choice from PRD #182, each with the one-line
# justification the PRD requires (user story 3). The ``*_KEY`` constants are the
# stable handles callers read; the cell order is the serialised order, kept fixed
# so the committed file diffs cleanly.

# Scope.
SCOPE_SETUPS_KEY = "scope.setups"
SCOPE_LEVEL_KEY = "scope.level"
SCOPE_MARKETS_KEY = "scope.markets"
# Window.
WINDOW_MEASURED_START_KEY = "window.measured_start"
WINDOW_MEASURED_END_KEY = "window.measured_end"
WINDOW_STORE_START_KEY = "window.store_start"
# Universe.
UNIVERSE_TREND_GATE_KEY = "universe.trend_gate"
UNIVERSE_LIQUIDITY_FLOOR_KEY = "universe.liquidity_floor"
UNIVERSE_ADTV_KEY = "universe.adtv"
UNIVERSE_ADTV_AGGREGATOR_KEY = "universe.adtv_aggregator"
UNIVERSE_VOLATILITY_GATE_KEY = "universe.volatility_gate"
UNIVERSE_VOLATILITY_GAP_REASON_KEY = "universe.volatility_gap_reason"
UNIVERSE_IDX_PRICE_FLOOR_KEY = "universe.idx_price_floor"
UNIVERSE_IDX_PRICE_FLOOR_ROLE_KEY = "universe.idx_price_floor_role"
UNIVERSE_STATELESSNESS_KEY = "universe.statelessness"
UNIVERSE_REFERENCE_EXCLUSION_KEY = "universe.reference_exclusion"
# Detection.
DETECTION_GATE_KEY = "detection.gate"
# Regime.
REGIME_SOURCE_KEY = "regime.source"
REGIME_ROLE_KEY = "regime.role"
# Entry, stop, exits.
ENTRY_RULE_KEY = "entry.rule"
STOP_RULE_KEY = "stop.rule"
EXIT_ARM_A_KEY = "exit.arm_a"
EXIT_ARM_B_KEY = "exit.arm_b"
EXIT_ARM_C_KEY = "exit.arm_c"
EXIT_TRAIL_MECHANIC_KEY = "exit.trail_mechanic"
# Costs, metric, decision.
COSTS_KEY = "costs.per_market"
METRIC_PRIMARY_KEY = "metric.primary"
DECISION_KILL_KEY = "decision.kill"
DECISION_SHIP_KEY = "decision.ship"
DECISION_ONE_MARKET_FAILURE_KEY = "decision.one_market_failure"
DECISION_INCONCLUSIVE_KEY = "decision.inconclusive"
DECISION_LICENSED_CHANGES_KEY = "decision.licensed_changes"


_CELLS: tuple[Cell, ...] = (
    Cell(
        SCOPE_SETUPS_KEY,
        "long_breakout_eod",
        "Long breakout EOD setups only, so the run measures the same thing the "
        "reference set and the detector do (PRD story 7).",
    ),
    Cell(
        SCOPE_LEVEL_KEY,
        "signal_primary_portfolio_deferred",
        "Signal level is declared primary and portfolio level specified but "
        "deferred, so the open question is answered without the capital model "
        "blocking it (story 8).",
    ),
    Cell(
        SCOPE_MARKETS_KEY,
        ["US", "IDX"],
        "US and IDX reported separately throughout, so findings §8's result that "
        "magnitudes do not transfer is honoured rather than averaged away (story 4).",
    ),
    Cell(
        WINDOW_MEASURED_START_KEY,
        "2012-01-01",
        "The measured window starts 2012-01-01 so the sample spans several "
        "regimes rather than one (story 5).",
    ),
    Cell(
        WINDOW_MEASURED_END_KEY,
        "latest_complete_session",
        "The measured window runs to the latest complete session, so the sample "
        "extends as far as the data legitimately allows (story 5).",
    ),
    Cell(
        WINDOW_STORE_START_KEY,
        "2011-01-01",
        "The store window starts 2011-01-01 so the detector's 80-bar minimum "
        "history, the universe gates and the regime's 25-bar warm-up are all "
        "satisfied before the first measured session (story 6).",
    ),
    Cell(
        UNIVERSE_TREND_GATE_KEY,
        "close > SMA50",
        "The trend gate is close > SMA50 on both markets, so the universe "
        "reflects the method's own precondition (story 10).",
    ),
    Cell(
        UNIVERSE_LIQUIDITY_FLOOR_KEY,
        {"US": 10_000_000.0, "IDX": 10_000_000_000.0},
        "Liquidity floors are $10M for US and Rp 10B for IDX — a deliberate "
        "contract value, not the app's inherited $20M / Rp 1B (story 11).",
    ),
    Cell(
        UNIVERSE_ADTV_KEY,
        "median_20d_unadjusted_close_x_volume",
        "ADTV is the 20-day median of unadjusted close × volume, so one block "
        "trade cannot lift an illiquid name over the floor (story 12).",
    ),
    Cell(
        UNIVERSE_ADTV_AGGREGATOR_KEY,
        "median",
        "The aggregator is the median; a switch to mean is a deliberate act, so "
        "which spiky small caps qualify never changes by accident (story 13).",
    ),
    Cell(
        UNIVERSE_VOLATILITY_GATE_KEY,
        "ADR20 >= 3.5%",
        "The volatility gate is ADR20 ≥ 3.5%, set deliberately below the rubric's "
        "5% floor so the ADR dimension is left with spread to test (story 14).",
    ),
    Cell(
        UNIVERSE_VOLATILITY_GAP_REASON_KEY,
        "gate_below_rubric_floor_is_deliberate",
        "The gap below the rubric's 5% floor is recorded so nobody later 'fixes' "
        "it to match and silently destroys the thing being measured — findings §6 "
        "Finding 2 measured the 5% floor withholding a score point from 31% of "
        "his real entries (story 15).",
    ),
    Cell(
        UNIVERSE_IDX_PRICE_FLOOR_KEY,
        100.0,
        "A nominal price floor of Rp 100 on the split-corrected series excludes "
        "IDX names whose quotes hit the tick grid hard enough to distort ADR and "
        "range geometry (story 16).",
    ),
    Cell(
        UNIVERSE_IDX_PRICE_FLOOR_ROLE_KEY,
        "data_validity",
        "The Rp 100 floor is data validity and never cost control, so no reader "
        "infers a penny-stock filter with an implied cost story (story 17).",
    ),
    Cell(
        UNIVERSE_STATELESSNESS_KEY,
        "stateless_gates_through_t_minus_1",
        "The universe is stateless — three gates measured through t−1 with no "
        "reference to prior membership — a known difference from the app's "
        "hysteresis band whose boundary churn is nearly free at signal level and "
        "real at portfolio level (stories 9, 18, 19).",
    ),
    Cell(
        UNIVERSE_REFERENCE_EXCLUSION_KEY,
        "exclude_index_and_benchmark_etfs",
        "The five benchmark references stay out of the ranked field, pinned "
        "against the enumeration by a test, so this fresh build inherits the #162 "
        "fix rather than reproducing the contamination (stories 73, 74).",
    ),
    Cell(
        DETECTION_GATE_KEY,
        ["1m", "3m", "6m", "12m"],
        "The detection gate is the four-lookback width (detector v3, ADR 0003 "
        "amendment); the denominator is built against that width and it is not "
        "swept in the primary run (PRD Implementation Decisions).",
    ),
    Cell(
        REGIME_SOURCE_KEY,
        "app_regime_off_market_index_at_t_minus_1",
        "Regime is the app's own regime, unmodified, read off each market's own "
        "index at t−1 — so findings are actionable in the product and the "
        "conditioning input obeys the point-in-time rule (stories 21, 23).",
    ),
    Cell(
        REGIME_ROLE_KEY,
        "conditioning_variable_never_filter",
        "Regime is a conditioning variable and never a filter: every state trades "
        "and each one's expectancy is measured instead of assumed (story 22).",
    ),
    Cell(
        ENTRY_RULE_KEY,
        "detection_trigger_filled_next_session",
        "Entry is taken at the detection's own trigger, filled the next session, "
        "so the simulated trade uses the detector's own decision rather than a "
        "second definition (story 31).",
    ),
    Cell(
        STOP_RULE_KEY,
        "detection_stop_unmodified",
        "The stop is the detection's own stop, used unmodified, so R is "
        "denominated the way the app denominates it (story 32).",
    ),
    Cell(
        EXIT_ARM_A_KEY,
        {"scale_fraction": 0.5, "scale_day": 5, "trail_ma": 10, "arbitrary_mechanics": True},
        "Arm A scales 50% off at the close of the fifth session after entry and "
        "trails the remainder on a 10MA — the trader's documented behaviour; its "
        "R is two position-weighted legs summed, and 'day 5' and the trail are "
        "recorded as arbitrary (stories 34, 36, 37, 39).",
    ),
    Cell(
        EXIT_ARM_B_KEY,
        {"trail_ma": 10},
        "Arm B is a pure 10MA trail, directly comparable to the reference set's "
        "simulated exit and the arm the primary metric is computed on (story 35).",
    ),
    Cell(
        EXIT_ARM_C_KEY,
        {"trail_ma": 20},
        "Arm C is a pure 20MA trail, the reference set's second simulated exit "
        "(story 35).",
    ),
    Cell(
        EXIT_TRAIL_MECHANIC_KEY,
        "close_through_ma_signals_fill_next_open",
        "A trail signals on a close through the MA and fills at the next open, so "
        "the exit is point-in-time and reproducible; recorded as arbitrary so a "
        "later run can vary it deliberately (stories 38, 39).",
    ),
    Cell(
        COSTS_KEY,
        {
            "US": {"commission_bps": 0.0, "slippage_bps": 5.0},
            "IDX": {"commission_bps": 15.0, "slippage_bps": 25.0},
        },
        "Commission and slippage are per-market contract values applied before "
        "any sweep, so IDX's real fees and spread are not modelled with US's "
        "near-zero assumptions; this pre-registered baseline is recorded here and "
        "swept variants are reported with the count of variants tried (story 40).",
    ),
    Cell(
        METRIC_PRIMARY_KEY,
        "arm_b_after_cost_expectancy_r_per_market_per_year",
        "The one pre-registered primary metric is arm B's after-cost expectancy "
        "in R, per market per year, so the headline cannot be chosen after the "
        "fact (story 41).",
    ),
    Cell(
        DECISION_KILL_KEY,
        {
            "metric": "arm_b_after_cost_expectancy_r",
            "comparator": "<=",
            "threshold": 0.0,
            "requires": ["both_markets", "full_window", "and_excluding_2020_2021"],
            "basis": "survivor_biased_number",
        },
        "Kill fires only when arm B's after-cost expectancy is ≤ 0 in both "
        "markets on the full window and with 2020–21 excluded, and the line is "
        "drawn on the survivor-biased number so a failure is decisive — the "
        "honest figure can only be worse (stories 42, 43).",
    ),
    Cell(
        DECISION_SHIP_KEY,
        {
            "requires": ["positive_result", "clears_phase2_pessimistic_bound"],
            "scope": "per_market",
        },
        "Ship requires a positive result that also clears the Phase 2 pessimistic "
        "bound, scoped per market so a US pass licenses nothing in Jakarta "
        "(stories 44, 45).",
    ),
    Cell(
        DECISION_ONE_MARKET_FAILURE_KEY,
        "method_stands_that_market_off_until_explained",
        "A one-market failure is its own pre-named verdict: the method stands and "
        "that market is off until a run explains the difference, so it is not "
        "improvised in the moment (story 46).",
    ),
    Cell(
        DECISION_INCONCLUSIVE_KEY,
        "report_inconclusive_no_swept_tiebreak",
        "An inconclusive run is reported as inconclusive; reaching for a swept "
        "variant to break the tie is ruled out by the contract that exists to "
        "prevent it (story 47).",
    ),
    Cell(
        DECISION_LICENSED_CHANGES_KEY,
        "write_licensed_change_before_any_constant_moves",
        "Each verdict's licensed change is written down before any constant moves, "
        "so a result cannot be converted into an unguarded edit (story 48).",
    ),
)


DEFAULT_CONTRACT = RunContract(
    contract_version="1",
    label="out-of-sample backtest — US+IDX, 2012 onward (PRD #182)",
    cells=_CELLS,
)
