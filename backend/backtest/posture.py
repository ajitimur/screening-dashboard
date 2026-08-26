"""Pricing the regime posture (issue #192, PRD #182 Phase 5).

The app prints **"sit out"** for ``HOSTILE`` and **"reduced"** for ``CHOPPY``
today, on no measured basis at all — two words shipped in the product with
nothing behind them. This module is the measurement: what expectancy did signals
taken in each regime state actually deliver, per market, with ``n`` shown for
every cell.

It reads no bar. :mod:`backtest.simulate` already denominated each trade in R and
:mod:`backtest.run` already persisted each session's regime reading, so everything
here is a join between the two and arithmetic over the result — which is why the
seam tests author trades and readings directly rather than running a chain to
reach them.

Conditioning, never filtering
-----------------------------
The contract's ``regime.role`` cell says ``conditioning_variable_never_filter``.
Every state trades, and the three states plus the undefined bucket **partition**
the trades: :func:`market_posture` reports that arithmetic, alongside the count of
what each of the two *declared* non-regime exclusions removed — the other market,
and the other arms.

That block is honest about its own reach, and the distinction matters. The counts
show that nothing falls between the cells **here**; they cannot show that nothing
was filtered before the trades arrived, because an upstream filter removes rows
first and every sum below would still balance. What actually holds the promise is
structural and sits in two other places: :mod:`backtest.simulate` reads no regime
column at all when it produces trades — pinned by a test that flips a persisted
state and gets the same trades back — and :func:`check_regime_role` refuses a
contract whose role cell has stopped saying "never filter".

The undefined bucket is not a rounding error. Below
:data:`~screener.regime.REGIME_WARMUP` index bars the state is undefined rather
than defaulted, and a trade taken there is still a trade: bucketing it into
``CHOPPY`` would invent a reading and dropping it would be the one thing this
module promises never to do.

Where the state is read, and why that is t−1
--------------------------------------------
Off the **detection session**, which is what t−1 *means* here. The detection
session is the night the candidate was listed with its posture printed beside it;
:func:`~backtest.simulate.entry` takes the break on the session after it and the
fill on the session after that. So the state this module conditions on is exactly
the one a trader could see when the signal appeared — reading the entry session's
state instead would be look-ahead arriving through the conditioning variable
rather than through the price.

Pricing the two words
---------------------
- :func:`hostile_counterfactual` computes what sitting out ``HOSTILE`` would have
  cost or saved: the state's own after-cost total R, the book with and without it,
  and the sign of the difference. "Sit out" is **earned** only where the state's
  expectancy is measurably below zero — the comparison is against not trading at
  all, which is what the word instructs.
- :func:`choppy_reduced` answers ``CHOPPY`` against ``FRIENDLY`` rather than
  against zero, because "reduced" is a *relative* posture: it claims the state is
  worse to trade, not that it is unprofitable. The verdict comes from a clustered
  bootstrap of the **difference** (:func:`bootstrap_difference`), so a gap smaller
  than the noise around it reads as undecided instead of as a finding.

Both verdicts are the interval's, never the mean's, and ``undecided`` is a real
answer rather than a failure: it says the run gives the app's word no measured
basis, which is precisely the question the product asked.

The two companions: reported, never conditioned on
--------------------------------------------------
:func:`breadth_summary` reports breadth with its survivorship warning, and no
cohort in this module can be keyed by it — :func:`posture_cell` takes a
:data:`REPORTED_STATES` member and refuses anything else, so "condition on the
state, not on breadth" is a refusal at the seam rather than a convention. Breadth
is the measure survivorship bias corrupts most directly, and in a backtest the
corruption is *worse* rather than better, because the names missing from the store
are disproportionately the ones that later died.

:func:`follow_through_summary` reports the other companion, and the asymmetry
between them is the point of reporting it here at all: follow-through is
**unbiased** where breadth is not. The live app captures it forward nightly
because a survivorship-biased past cannot rebuild it — but the index series
carries no survivorship hole, so this run reconstructs it legitimately across the
whole window. It is the one regime signal for which the backtest is the better
instrument, and it is still never conditioned on, because it is not what the app's
posture reads.

Everything below is arm B's, the contract's pre-registered arm, and the per-cell
arithmetic is :mod:`backtest.metric`'s own — the costs, the win rate, the
R-distribution and the symbol-clustered bootstrap are reused rather than
respelled, so a posture cell and a headline cell cannot report the same trades
differently.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence, get_args

from screener.regime import REGIME_WARMUP, RegimeState, posture
from screener.source import MARKET_INDEX
from screener.store import Store

from .contract import (
    DEFAULT_CONTRACT,
    REGIME_ROLE_KEY,
    REGIME_SOURCE_KEY,
    SCOPE_MARKETS_KEY,
    RunContract,
)
from .denominator import (
    BREADTH_BASIS,
    FOLLOW_THROUGH_BASIS,
    DenominatorStore,
    RegimeReading,
    SessionRow,
    denominator_path,
)
from .metric import (
    BOOTSTRAP_CLUSTER,
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_MIN_CLUSTERS,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    EXCLUDED_YEARS,
    EXCLUDED_YEARS_WINDOW,
    FULL_WINDOW,
    PRIMARY_ARM,
    _distribution,
    _quantile,
    _reported_markets,
    after_cost_r,
    clusters_by_symbol,
    expectancy_cell,
)
from .result import stamp_result
from .run import ContractDrift
from .simulate import SimulatedTrade, simulate_market

# -- what the contract says, and what this module adds to it ------------------

# The two contract cells this module stands on, restated here only so
# :func:`check_regime_source` and :func:`check_regime_role` can refuse a contract
# that moved out from under the code.
REGIME_SOURCE = "app_regime_off_market_index_at_t_minus_1"
REGIME_ROLE = "conditioning_variable_never_filter"

# Where the state is read: the detection's own session. See the module docstring
# — this *is* t−1, because the break comes on the session after the detection and
# the fill on the one after that.
STATE_READ_AT = "detection_session"

# What that offset actually is, spelled out rather than left inside "t−1". The
# detection session is one session before the break and **two** before the fill, so
# a reader checking for look-ahead can see the gap instead of taking the label's
# word for it.
STATE_READ_AT_NOTE = (
    "the detection session — the night the candidate was listed with the app's "
    "posture beside it, one session before the break that signals entry and two "
    "before the fill; no bar after it is read to date the trade"
)

# The bucket a trade lands in when no state was showing. Two different causes —
# a session below the regime's warm-up, and a session the spine has no row for —
# and :func:`state_basis` tells them apart, because "undefined" and "never
# persisted" are different facts about the run even though both are unreadable as
# a regime.
STATE_UNDEFINED = "UNDEFINED"
BASIS_MEASURED = "measured"
BASIS_BELOW_WARMUP = "below_warmup"
BASIS_SESSION_ABSENT = "session_absent"

# The app's own states, read off the app's own type rather than respelled here.
# The module's whole claim is that it conditions on the state the product actually
# shows, and a hardcoded list would break that claim quietly: a fourth state added
# to :data:`~screener.regime.RegimeState` would land in the undefined bucket and
# read as a warm-up hole rather than as a state nobody had reported yet.
APP_STATES: tuple[str, ...] = get_args(RegimeState)

# Every cell the report carries, in the order it prints them. The undefined bucket
# is one of them and not an appendix: it is what makes the cells a partition of the
# trades rather than a filtered selection of them.
REPORTED_STATES: tuple[str, ...] = (*APP_STATES, STATE_UNDEFINED)

# The two named states whose posture the app prints, and which this module prices.
HOSTILE = "HOSTILE"
CHOPPY = "CHOPPY"
FRIENDLY = "FRIENDLY"

# What a counterfactual did to the book, in words. The sign of the delta says it
# too, but a reader who takes one number off this report should not have to
# remember which direction a negative delta points.
EFFECT_COST = "cost"
EFFECT_SAVED = "saved"
EFFECT_NEUTRAL = "neutral"

# The four things a measurement can say about a word the app prints. ``undecided``
# is a real answer and not a failure to reach one: it says the interval straddles
# the comparison, so the run leaves the posture exactly as unfounded as it found
# it. ``too_thin`` is different again — there were not enough independent names to
# form an interval at all, which is a fact about coverage rather than about regime.
VERDICT_EARNED = "earned"
VERDICT_REFUTED = "refuted"
VERDICT_UNDECIDED = "undecided"
VERDICT_TOO_THIN = "too_thin"

# The limit that rides on every counterfactual here, written into the payload
# rather than left to a reader's charity. This run has no shared position budget,
# so sitting a state out frees no capital to redeploy elsewhere: the figure prices
# what the posture *costs*, and is silent on what it might buy.
SIGNAL_LEVEL_NOTE = (
    "priced at signal level: sitting a state out removes its trades and frees no "
    "capital, because this run has no shared position budget to redeploy — the "
    "figure is what the posture costs or saves directly, never what it might buy"
)

# What actually holds "nothing is excluded by regime", written into the payload
# because the arithmetic beside it cannot hold it alone: a filter applied upstream
# removes trades before this module sees them, and no sum computed here would
# notice. The guarantee is structural and lives in two places — the simulator reads
# no regime column, pinned by a test, and the contract's role cell is refused by
# :func:`check_regime_role` if it moves.
UPSTREAM_GUARANTEE = (
    "the trades reaching this module are produced without reading any regime "
    "column at all (backtest.simulate), and the contract's regime.role cell is "
    "refused if it ever names a filter; the counts below show only that the "
    "states partition what did arrive"
)

# Why the states are not also cut per year. The metric reports per year because
# that is its axis; crossing it with the state would put three-quarters of the run
# in cells too thin to read, and the pair of windows below carries the one
# time-slice that actually threatens this cell.
PER_YEAR_NOTE = (
    "states are reported over the full window and with 2020–21 excluded, not per "
    "year: three states crossed with fourteen years is mostly cells below the "
    "bootstrap's cluster floor, and 2020–21 is the stretch that would inflate "
    "FRIENDLY specifically — which is the time-slice this cell needs"
)

# How many views of one dataset stand behind these figures, so a reader can price
# the multiple-testing risk rather than assume it away. Three exit arms and three
# states is nine, before any threshold is swept — and the pre-registered metric
# stands as the headline regardless of what any view here shows.
VIEWS_NOTE = (
    "three exit arms and three regime states is nine views of one dataset before "
    "any threshold is swept; the pre-registered metric stands as the headline even "
    "where a view here looks better"
)

# The warning that travels with every breadth figure, in the payload and on the
# printed page. Prose in a docstring would not survive a reader querying the JSON.
FOLLOW_THROUGH_NOTE = (
    "follow-through is unbiased where breadth is not: the live app captures it "
    "forward nightly because a survivorship-biased past cannot rebuild it, but the "
    "index series carries no survivorship hole, so this run reconstructs it "
    "legitimately across the whole window — reported, and still never conditioned on"
)

BREADTH_WARNING = (
    "breadth is descriptive only and is never conditioned on: survivorship bias "
    "corrupts it more directly than anything else reported here, and in a backtest "
    "worse rather than better, because the names missing from the store are "
    "disproportionately the ones that later died"
)


def check_regime_source(contract: RunContract) -> None:
    """Refuse a run whose contract reads the regime somewhere other than here.

    The state conditioned on and the state the contract pre-registered have to be
    the same one, or the run reports a posture priced against a definition it never
    promised. The remedy is a new contract recorded beside the old one.
    """
    named = contract.value(REGIME_SOURCE_KEY)
    if named != REGIME_SOURCE:
        raise ContractDrift(
            f"contract's regime source is {named!r}, but this module conditions on "
            f"{REGIME_SOURCE!r}; a moved conditioning variable is a new run"
        )


def check_regime_role(contract: RunContract) -> None:
    """Refuse a contract that has made the regime a filter.

    Everything in this module assumes every state got to trade — the partition, the
    per-state expectancies, and both counterfactuals, which are only counterfactual
    because the trades they remove were actually taken. A contract that filtered
    would leave those figures describing a selection while still being labelled
    measurements of a state.
    """
    named = contract.value(REGIME_ROLE_KEY)
    if named != REGIME_ROLE:
        raise ContractDrift(
            f"contract's regime role is {named!r}, but this module measures every "
            f"state under {REGIME_ROLE!r}; a filtered regime is a different run"
        )


# -- the spine: one market's sessions, and the state showing on each ----------


@dataclass(frozen=True)
class RegimeSpine:
    """One market's measured sessions and the regime reading on each.

    The join key between the persisted denominator and the simulated trades, held
    as a value so the seam tests can author one without a store. It carries whole
    :class:`~backtest.denominator.RegimeReading` values rather than a bare
    ``session → state`` map, because breadth and follow-through are *recorded
    beside* the state and separating them here would leave two places that have to
    agree about which session a reading belongs to.

    A session absent from :attr:`readings` is one the run never measured, which is
    not the same as one whose state was undefined — see :func:`state_basis`.
    """

    market: str
    readings: Mapping[date, RegimeReading]

    @staticmethod
    def of(market: str, rows: Sequence[SessionRow]) -> "RegimeSpine":
        """Build a spine from persisted :class:`~backtest.denominator.SessionRow`s.

        Takes the rows rather than the store so a caller that already read them —
        for the session count, say — does not read them twice.
        """
        return RegimeSpine(
            market=market,
            readings={
                row.session: RegimeReading(
                    state=row.regime_state,
                    breadth=row.breadth,
                    broke_out=row.broke_out,
                    index_close=row.index_close,
                )
                for row in rows
            },
        )


def spine_for_market(
    denominator: DenominatorStore, market: str, *, include_burn_in: bool = False
) -> RegimeSpine:
    """One market's spine, off the rows :mod:`backtest.run` already persisted.

    The regime is computed once, during the run, and read from the store here —
    never recomputed off the index a second time. Two computations of one state
    would be two chances for the reported state to disagree with the persisted one,
    and the disagreement would be invisible in the output.

    Burn-in sessions are excluded by default, matching
    :func:`~backtest.simulate.simulate_market`'s own default: a warm-up session is
    persisted and never measured (story 76), so a trade taken off one is not in the
    trades either.
    """
    return RegimeSpine.of(
        market,
        denominator.sessions(market, burn_in=None if include_burn_in else False),
    )


def state_basis(spine: RegimeSpine, trade: SimulatedTrade) -> str:
    """Why a trade's state reads as it does: measured, below warm-up, or absent.

    The two unreadable cases share a cell but not a cause. ``below_warmup`` is the
    regime's own :data:`~screener.regime.REGIME_WARMUP` refusing to guess from too
    few index bars; ``session_absent`` is a trade whose detection session the spine
    has no row for at all, which is a fact about the run's coverage and worth
    seeing separately from the regime's own silence.
    """
    reading = spine.readings.get(trade.detection_session)
    if reading is None:
        return BASIS_SESSION_ABSENT
    return BASIS_MEASURED if reading.state is not None else BASIS_BELOW_WARMUP


def state_of(spine: RegimeSpine, trade: SimulatedTrade) -> str:
    """The cell a trade belongs to: its state, or :data:`STATE_UNDEFINED`.

    Read off :data:`STATE_READ_AT` — the detection session, the night the candidate
    was listed with the app's posture printed beside it. Never off the entry
    session, which is two sessions later and carries a reading nobody had when the
    signal appeared.

    Returns a string always, so every trade lands in exactly one of
    :data:`REPORTED_STATES` and no caller has to decide what ``None`` means.
    """
    reading = spine.readings.get(trade.detection_session)
    if reading is None or reading.state is None:
        return STATE_UNDEFINED
    return reading.state


def for_market(
    trades: Sequence[SimulatedTrade], market: str
) -> list[SimulatedTrade]:
    """One market's trades on :data:`PRIMARY_ARM`, out of a run-wide list.

    The **only** two exclusions anything in this module performs, and they are
    named here in one place so ``excluded_by_regime`` can be reported against a
    number that already accounts for them. Neither is a regime exclusion: US and
    IDX never pool (findings §8), and the posture qualifies the pre-registered
    headline, so it is priced on the arm that headline is.

    Every entry point applies it rather than trusting its caller — a direct call to
    a counterfactual must not be able to average two arms into one verdict when the
    report a level up could not.
    """
    return [t for t in trades if t.market == market and t.arm == PRIMARY_ARM]


def by_state(
    spine: RegimeSpine, trades: Sequence[SimulatedTrade]
) -> dict[str, list[SimulatedTrade]]:
    """Every trade in exactly one state's bucket, with all four buckets present.

    The partition itself, built here rather than at each call site so the "nothing
    is excluded" arithmetic in :func:`market_posture` reduces over the same
    structure the cells are computed from. A state nobody traded in gets an empty
    list rather than no key: an absent row would read as a market that never saw
    that tape, which is a much stronger claim than one that threw no signal there.
    """
    buckets: dict[str, list[SimulatedTrade]] = {s: [] for s in REPORTED_STATES}
    for trade in trades:
        buckets[state_of(spine, trade)].append(trade)
    return buckets


# -- the difference of two expectancies, bootstrapped by cluster --------------


def bootstrap_difference(
    clusters_a: Sequence[Sequence[float]],
    clusters_b: Sequence[Sequence[float]],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
    cluster: str = BOOTSTRAP_CLUSTER,
    min_clusters: int = BOOTSTRAP_MIN_CLUSTERS,
) -> dict[str, Any]:
    """A clustered bootstrap of ``mean(a) − mean(b)``, each side drawn whole.

    What :func:`~backtest.metric.bootstrap_expectancy` is to one cell, this is to
    the comparison between two — and the comparison is what a *relative* posture
    like "reduced" turns on. Each resample draws ``len(clusters_a)`` clusters from
    the first side and ``len(clusters_b)`` from the second, with replacement,
    pooling everything inside each drawn cluster: a symbol is in or out as a whole
    on whichever side it sat, so one name's fortnight of overlapping signals cannot
    arrive as several independent observations and tighten the interval.

    The two sides are resampled **independently**, which is right here because they
    are disjoint sets of trades taken in different states — there is no pairing to
    preserve.

    ``p_value`` is one-sided: the share of resampled differences at or above zero,
    which is the shape the question has. "Does CHOPPY pay less than FRIENDLY" is a
    directional claim, and a two-sided test would answer a question nobody asked.

    Either side below ``min_clusters`` gets **no interval and no p-value** and a
    ``suppressed`` line saying which, for the same reason a single-cluster cell
    does: a degenerate interval prints as certainty and is the opposite of it.
    """
    n_a, n_b = len(clusters_a), len(clusters_b)
    flat_a = [v for c in clusters_a for v in c]
    flat_b = [v for c in clusters_b for v in c]
    mean_a = sum(flat_a) / len(flat_a) if flat_a else None
    mean_b = sum(flat_b) / len(flat_b) if flat_b else None
    body: dict[str, Any] = {
        "cluster": cluster,
        "clusters_a": n_a,
        "clusters_b": n_b,
        "observations_a": len(flat_a),
        "observations_b": len(flat_b),
        "mean_a": mean_a,
        "mean_b": mean_b,
        "difference": (
            mean_a - mean_b if mean_a is not None and mean_b is not None else None
        ),
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
        "min_clusters": min_clusters,
        "ci_low": None,
        "ci_high": None,
        "p_value": None,
        "suppressed": None,
    }
    if n_a < min_clusters or n_b < min_clusters:
        return {
            **body,
            "suppressed": (
                f"{n_a} and {n_b} {cluster}s against a floor of {min_clusters}: too "
                "thin for an interval, and a degenerate one would read as a finding"
            ),
        }

    # Seeded per side so the two draws cannot correlate through one stream — and
    # so adding a trade to one side does not silently reshuffle the other's draw,
    # which would make two runs of the same data differ for no measured reason.
    rng_a = random.Random(seed)
    rng_b = random.Random(seed + 1)
    diffs: list[float] = []
    for _ in range(resamples):
        drawn_a = [clusters_a[rng_a.randrange(n_a)] for _ in range(n_a)]
        drawn_b = [clusters_b[rng_b.randrange(n_b)] for _ in range(n_b)]
        count_a = sum(len(c) for c in drawn_a)
        count_b = sum(len(c) for c in drawn_b)
        if not count_a or not count_b:
            continue
        diffs.append(
            sum(sum(c) for c in drawn_a) / count_a
            - sum(sum(c) for c in drawn_b) / count_b
        )
    if not diffs:
        return body

    diffs.sort()
    tail = (1.0 - confidence) / 2.0
    return {
        **body,
        "ci_low": _quantile(diffs, tail),
        "ci_high": _quantile(diffs, 1.0 - tail),
        "p_value": sum(1 for d in diffs if d >= 0.0) / len(diffs),
    }


def _verdict(ci_low: float | None, ci_high: float | None) -> str:
    """The verdict an interval supports about a posture that claims "less than".

    One place, because both postures are judged the same way and two spellings of
    "does this interval clear zero" would eventually disagree. Earned when the
    whole interval sits below zero, refuted when it sits above, undecided when it
    straddles.

    A **suppressed** interval arrives here as ``None`` and comes back
    :data:`VERDICT_TOO_THIN`, which is deliberately not folded into ``undecided``:
    "the names disagree" and "there were never enough names to ask" are different
    findings, and only the first is about the regime. The bootstrap decides which
    of the two it is — this function only reads the answer.
    """
    if ci_low is None or ci_high is None:
        return VERDICT_TOO_THIN
    if ci_high < 0.0:
        return VERDICT_EARNED
    if ci_low > 0.0:
        return VERDICT_REFUTED
    return VERDICT_UNDECIDED


# -- the cells, and the two postures they price -------------------------------


def posture_cell(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    market: str,
    state: Any,
    label: str,
) -> dict[str, Any]:
    """One state's expectancy in one market over one window, with n and its shape.

    The arithmetic is :func:`~backtest.metric.expectancy_cell`'s own — the costs,
    the win rate, the R-distribution and the symbol-clustered interval — so a
    posture cell and a headline cell cannot report the same trades differently. The
    single-market and single-arm refusals come with it.

    ``state`` must be a member of :data:`REPORTED_STATES`, and that is the seam
    where "condition on the state, never on breadth" is enforced: a breadth number,
    or a bucket derived from one, is refused here rather than caught in review. The
    conditioning variable of this run reads only the index, and the index carries
    no survivorship hole.
    """
    if state not in REPORTED_STATES:
        raise ValueError(
            f"a posture cell is conditioned on the regime state: {state!r} is not "
            f"one of {REPORTED_STATES}. Breadth is descriptive and is never a "
            "cohort key — it is the column survivorship corrupts most"
        )
    return {
        **expectancy_cell(
            contract, trades, market=market, label=f"{state} {label}"
        ),
        "state": state,
    }


def _windows(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    market: str,
    state: str,
) -> list[dict[str, Any]]:
    """One state's two windows: the full one, and 2020–21 excluded beside it.

    Per state rather than only per market, because 2020–21 is exactly the stretch
    that would inflate ``FRIENDLY`` — a friendly-tape expectancy resting on the
    mania is a figure about the tape, and the pair is what lets a reader see that
    without recomputing anything.
    """
    kept = [t for t in trades if t.entry.session.year not in EXCLUDED_YEARS]
    return [
        posture_cell(contract, trades, market=market, state=state, label=FULL_WINDOW),
        {
            **posture_cell(
                contract, kept, market=market, state=state,
                label=EXCLUDED_YEARS_WINDOW,
            ),
            "excluded_years": list(EXCLUDED_YEARS),
        },
    ]


def _book(
    contract: RunContract, trades: Sequence[SimulatedTrade]
) -> dict[str, Any]:
    """A set of trades as a book: how many closed, what they made, what each made.

    Deliberately not an :func:`~backtest.metric.expectancy_cell` — a book spanning
    every state is not a cell, it is the thing the cells partition, and giving it a
    cell's shape would let it be quoted as one.
    """
    rs = [
        r for r in (after_cost_r(t, contract) for t in trades) if r is not None
    ]
    return {
        "trades": len(trades),
        "closed": len(rs),
        "total_r": sum(rs),
        "expectancy_r": (sum(rs) / len(rs)) if rs else None,
    }


def hostile_counterfactual(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    spine: RegimeSpine,
) -> dict[str, Any]:
    """What sitting out ``HOSTILE`` would have cost or saved this market.

    The counterfactual the product actually needs, and it is only computable
    because the run refused to filter: these trades were taken, so removing them is
    arithmetic rather than a model.

    The market is the **spine's**, not a parameter beside it: the spine is one
    market's sessions read off that market's own index, so a ``market`` argument
    could only ever agree with it or be a bug, and a parameter whose sole use is to
    be checked against another argument is a parameter worth deleting.

    ``delta_total_r`` is the book's change — the negative of what the hostile
    trades made — and :data:`EFFECT_COST` / :data:`EFFECT_SAVED` names its
    direction so a reader taking one number away cannot invert it.

    The ``verdict`` is on the word "sit out" itself, and it is judged against
    **zero**: the posture instructs no trade at all, so the comparison is with not
    trading, not with another state. It comes from the state cell's own
    symbol-clustered interval, so a hostile stretch that merely happened to lose
    across three names reads as :data:`VERDICT_TOO_THIN` rather than as a finding.

    See :data:`SIGNAL_LEVEL_NOTE` for what this figure cannot say.
    """
    mine = for_market(trades, spine.market)
    buckets = by_state(spine, mine)
    hostile = buckets[HOSTILE]
    # The complement off the **partition**, not a second pass over the trades with
    # the test inverted. Two spellings of "everything but HOSTILE" is two places
    # for the book and the cells to stop agreeing, and the disagreement would be
    # invisible: both halves would still look like plausible numbers.
    rest = [t for state, bucket in buckets.items() if state != HOSTILE
            for t in bucket]
    cell = posture_cell(
        contract, hostile, market=spine.market, state=HOSTILE, label=FULL_WINDOW
    )
    total_r = cell["total_r"]
    delta = -total_r
    if cell["closed"] == 0 or total_r == 0.0:
        effect = EFFECT_NEUTRAL
    else:
        effect = EFFECT_COST if total_r > 0 else EFFECT_SAVED
    boot = cell["bootstrap"]
    whole = _book(contract, mine)
    without = _book(contract, rest)
    return {
        "state": HOSTILE,
        "posture": posture(HOSTILE),
        "judged_against": "zero",
        "judged_against_note": (
            "the word instructs no trade at all, so the comparison is with not "
            "trading rather than with another state"
        ),
        "trades": cell["trades"],
        "closed": cell["closed"],
        "expectancy_r": cell["expectancy_r"],
        "total_r": total_r,
        "delta_total_r": delta,
        "delta_expectancy_r": (
            without["expectancy_r"] - whole["expectancy_r"]
            if None not in (without["expectancy_r"], whole["expectancy_r"])
            else None
        ),
        "effect": effect,
        "verdict": _verdict(boot["ci_low"], boot["ci_high"]),
        "bootstrap": boot,
        "book": {"all": whole, "without_hostile": without},
        "basis": SIGNAL_LEVEL_NOTE,
    }


def _shape(contract: RunContract, trades: Sequence[SimulatedTrade]) -> dict[str, Any]:
    """The win rate and R-distribution behind one side of a comparison.

    Reported because an expectancy never travels alone here (CONTEXT.md,
    *After-cost expectancy*): 22.7% of the reference trader's trades made money and
    his mean R was positive anyway, so a low win rate is judged against its right
    tail rather than on its own. A "reduced" verdict resting on two bare means
    would hide the case that actually matters — two states with the same mean and
    different tails are not the same state to trade.

    :func:`~backtest.metric._distribution` computes the shape, so the quantiles a
    posture reports and the ones the headline reports are the same quantiles.
    """
    rs = [r for r in (after_cost_r(t, contract) for t in trades) if r is not None]
    wins = [r for r in rs if r > 0]
    return {
        "closed": len(rs),
        "win_rate": (len(wins) / len(rs)) if rs else None,
        "wins": len(wins),
        "losses": len(rs) - len(wins),
        "distribution": _distribution(rs),
    }


def choppy_reduced(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    spine: RegimeSpine,
) -> dict[str, Any]:
    """Does ``CHOPPY`` earn its "reduced", measured against ``FRIENDLY``?

    Against ``FRIENDLY`` and not against zero, because "reduced" is a **relative**
    posture: it claims the state is worse to trade, not that it is unprofitable. A
    ``CHOPPY`` expectancy of +0.2R would refute the word while still being a
    perfectly good reason to trade — judging it against zero would call that a pass.

    The verdict is the difference bootstrap's, so a gap smaller than the noise
    around it comes out :data:`VERDICT_UNDECIDED` rather than as a finding — and
    undecided is the honest answer to a word the app prints on no basis: this run
    gives it none either.

    Both sides carry their **win rate and R-distribution**, for the reason every
    expectancy in this repo does: a gap between two means says nothing about which
    tail produced it, and the tail is what a sizing posture is actually about.

    The market is the spine's own and the arm is :data:`PRIMARY_ARM`; both are
    applied here rather than assumed of the caller, so a direct call cannot average
    two markets or two arms into one comparison.
    """
    mine = for_market(trades, spine.market)
    buckets = by_state(spine, mine)
    choppy, friendly = buckets[CHOPPY], buckets[FRIENDLY]
    boot = bootstrap_difference(
        clusters_by_symbol(choppy, contract), clusters_by_symbol(friendly, contract)
    )
    return {
        "state": CHOPPY,
        "posture": posture(CHOPPY),
        "judged_against": FRIENDLY,
        "trades": len(choppy),
        "trades_friendly": len(friendly),
        "expectancy_r": boot["mean_a"],
        "expectancy_r_friendly": boot["mean_b"],
        "delta_expectancy_r": boot["difference"],
        "shape": _shape(contract, choppy),
        "shape_friendly": _shape(contract, friendly),
        "verdict": _verdict(boot["ci_low"], boot["ci_high"]),
        "bootstrap": boot,
    }


def breadth_summary(spine: RegimeSpine) -> dict[str, Any]:
    """One market's breadth over the window — descriptive, and warned as such.

    Reported because the plan asks for it, and shaped so it cannot be mistaken for
    a conditioning variable: ``conditioned_on`` is a literal ``False`` in the
    payload, the basis the run persisted travels with it, and
    :data:`BREADTH_WARNING` says in the output itself why. A warning that lived only
    in a docstring would not survive a reader querying the JSON.

    A spread rather than a mean alone, because the question breadth answers is
    "how narrow did this market get", and a fourteen-year average of a share that
    swings between 0.05 and 0.7 answers nothing.
    """
    values = sorted(
        r.breadth for r in spine.readings.values() if r.breadth is not None
    )
    return {
        "sessions": len(values),
        "sessions_without_breadth": len(spine.readings) - len(values),
        "min": values[0] if values else None,
        "median": _quantile(values, 0.5) if values else None,
        "max": values[-1] if values else None,
        "mean": (sum(values) / len(values)) if values else None,
        "basis": BREADTH_BASIS,
        "conditioned_on": False,
        "warning": BREADTH_WARNING,
    }


# -- the report ---------------------------------------------------------------


def follow_through_summary(spine: RegimeSpine) -> dict[str, Any]:
    """The index's breakout follow-through over the window — and it is *unbiased*.

    Breadth's companion, and the one place the asymmetry between them has to be
    said out loud: breadth is survivorship-corrupted and this is not. The app
    captures follow-through forward nightly precisely because a survivorship-biased
    past cannot rebuild it — but the **index series carries no survivorship hole**,
    so a backtest reconstructs it legitimately across the whole window. This is the
    only regime signal for which the backtest is a *better* instrument than the
    live app.

    Reported and never conditioned on, like breadth — not because it is corrupt,
    but because it is not what the app's posture reads, and a cell keyed by it
    would be a cell about a different regime than the one shipped.
    """
    seen = [
        r.broke_out for r in spine.readings.values() if r.broke_out is not None
    ]
    return {
        "sessions": len(seen),
        "sessions_without_reading": len(spine.readings) - len(seen),
        "breakouts": sum(1 for b in seen if b),
        "breakout_rate": (sum(1 for b in seen if b) / len(seen)) if seen else None,
        "basis": FOLLOW_THROUGH_BASIS,
        "conditioned_on": False,
        "note": FOLLOW_THROUGH_NOTE,
    }


def market_posture(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    spine: RegimeSpine,
) -> dict[str, Any]:
    """One market's whole posture: every state's cells, both counterfactuals,
    breadth and follow-through beside them, and the exclusion accounting.

    ``trades`` may span markets and arms; :func:`for_market` narrows them, and the
    market is the **spine's own** — one market's sessions read off one market's
    index — so a caller hands over the whole run and the separation happens here.

    ``conditioning`` accounts for every trade that did *not* reach a cell, and
    names which of the two declared, non-regime reasons dropped it. It is
    deliberately not a proof that the run never filtered by regime: an upstream
    filter would remove trades before this function ever saw them, and no
    arithmetic here could notice. What holds that promise is upstream and
    structural — :mod:`backtest.simulate` reads no regime column at all, which is
    pinned by a test, and the contract's ``regime.role`` cell is refused by
    :func:`check_regime_role` if it ever changes. This block's job is the narrower
    and checkable one: showing that *within* this module the states partition the
    trades and nothing quietly falls between the cells.
    """
    check_regime_source(contract)
    check_regime_role(contract)
    market = spine.market
    mine = for_market(trades, market)
    buckets = by_state(spine, mine)
    in_cells = sum(len(b) for b in buckets.values())
    return {
        "market": market,
        "index": MARKET_INDEX[market],
        "arm": PRIMARY_ARM,
        "states": [
            {
                "state": state,
                "basis_counts": {
                    basis: sum(
                        1 for t in buckets[state] if state_basis(spine, t) == basis
                    )
                    for basis in (
                        BASIS_MEASURED, BASIS_BELOW_WARMUP, BASIS_SESSION_ABSENT
                    )
                },
                "windows": _windows(
                    contract, buckets[state], market=market, state=state
                ),
                "trades": len(buckets[state]),
            }
            for state in REPORTED_STATES
        ],
        "counterfactual": hostile_counterfactual(contract, mine, spine),
        "reduced": choppy_reduced(contract, mine, spine),
        "breadth": breadth_summary(spine),
        "follow_through": follow_through_summary(spine),
        "conditioning": {
            "role": contract.value(REGIME_ROLE_KEY),
            # Every trade handed in, then the two declared exclusions, then what
            # reached a cell. Spelled out rather than reduced to one zero, because
            # "nothing was excluded by regime" is only worth reading beside the
            # count of what *was* excluded and why.
            "handed_in": len(trades),
            "excluded_other_markets": sum(1 for t in trades if t.market != market),
            "excluded_other_arms": sum(
                1 for t in trades if t.market == market and t.arm != PRIMARY_ARM
            ),
            "trades": len(mine),
            "in_cells": in_cells,
            "excluded_by_regime": len(mine) - in_cells,
            "partition_holds": len(mine) == in_cells,
            "sessions": len(spine.readings),
            "warmup_bars": REGIME_WARMUP,
            "upstream_guarantee": UPSTREAM_GUARANTEE,
        },
    }


def posture_report(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    spines: Mapping[str, RegimeSpine],
    *,
    markets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The whole priced posture as one stamped payload, market by market.

    ``markets`` defaults to the contract's own ``scope.markets``, so a market that
    produced no trade still reports its zeros rather than vanishing.

    There is deliberately **no top-level expectancy and no pooled state cell**.
    findings §8 measured that magnitudes do not transfer between the two markets,
    so a pooled HOSTILE figure would be a number about neither — and the way to
    stop one being quoted is for it never to have been computed.
    """
    check_regime_source(contract)
    check_regime_role(contract)
    named = _reported_markets(contract, markets)
    missing = [m for m in named if m not in spines]
    if missing:
        raise ValueError(
            f"no regime spine for {missing}: a market reported with no sessions "
            "would show every trade as undefined and read as a warm-up hole"
        )
    # A mapping whose key disagrees with the spine it points at is the one way left
    # to date a market's trades off another market's index, now that the market is
    # the spine's own rather than a second argument beside it.
    mislabelled = [m for m in named if spines[m].market != m]
    if mislabelled:
        raise ValueError(
            f"the spine filed under {mislabelled} names a different market: the "
            "regime is read off each market's own index, and the two indices differ"
        )
    return stamp_result(
        contract,
        {
            "regime_source": REGIME_SOURCE,
            "regime_role": REGIME_ROLE,
            "state_read_at": STATE_READ_AT,
            "state_read_at_note": STATE_READ_AT_NOTE,
            "arm": PRIMARY_ARM,
            "states": list(REPORTED_STATES),
            "per_year": PER_YEAR_NOTE,
            "views": VIEWS_NOTE,
            "bootstrap": {
                "cluster": BOOTSTRAP_CLUSTER,
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "confidence": BOOTSTRAP_CONFIDENCE,
            },
            "markets": [
                market_posture(contract, trades, spines[market])
                for market in named
            ],
        },
    )


# -- printing it, and the command that produces it ----------------------------


def _cell_line(cell: dict[str, Any], *, width: int = 30) -> str:
    """One state cell as a line: the expectancy, its shape, and its interval.

    ``n`` is on the line whether or not anything else is, because a cell too thin
    to read must be visible as thin rather than absent — an empty line reads as a
    state that never happened.
    """
    label = cell["label"]
    if cell["closed"] == 0:
        return f"    {label:<{width}} n={cell['trades']}  no closed trades"
    boot = cell["bootstrap"]
    ci = (
        f"[{boot['ci_low']:+.2f}, {boot['ci_high']:+.2f}] p={boot['p_value']:.3f}"
        if boot["ci_low"] is not None
        else f"{boot['clusters']} {boot['cluster']}s — too thin for an interval"
    )
    return (
        f"    {label:<{width}} {cell['expectancy_r']:+.3f}R  "
        f"win {cell['win_rate']:.1%}  n={cell['closed']}  "
        f"med {cell['distribution']['median']:+.2f}  {ci}"
    )


def _pct(share: float | None) -> str:
    """A share as a percentage, or an em dash where there was nothing to divide.

    One spelling, because a blank and a ``0.0%`` mean different things — no trades
    versus trades that all lost — and formatting each site by hand is how the two
    end up looking the same.
    """
    return "—" if share is None else f"{share:.1%}"


def _verdict_line(body: dict[str, Any], point: str) -> str:
    """One posture's verdict, with the word the app prints beside it.

    The word is quoted on the page. The whole point of the cell is that the product
    says it today, so a verdict printed without it would be a statistic looking for
    a question.

    ``point`` is the point estimate and is labelled as one, because a verdict of
    ``undecided`` beside a large-looking number is exactly where a reader is
    tempted to take the number and drop the verdict.
    """
    return (
        f'  "{body["posture"]}" for {body["state"]} — {body["verdict"]} '
        f"against {body['judged_against']}; point estimate {point}"
    )


def format_posture(report: dict[str, Any]) -> str:
    """The priced posture as a page a terminal can print.

    The states come before the verdicts, in that order, because the verdicts are a
    reading of the cells and a reader who skims to a one-word answer must have
    passed the ``n`` behind it to get there.
    """
    lines: list[str] = [
        f"regime posture — arm {report['arm']}, state read at "
        f"{report['state_read_at']} (t−1)",
        f"  {report['state_read_at_note']}",
        f"  {report['regime_role']}: nothing is excluded by regime, every state "
        "trades, and each one's expectancy is measured",
        f"  {report['views']}",
    ]
    for body in report["markets"]:
        cond = body["conditioning"]
        lines += [
            "",
            f"{body['market']} — regime off {body['index']}, "
            f"{cond['trades']} trades over {cond['sessions']} sessions, "
            f"{cond['excluded_by_regime']} excluded by regime "
            f"({cond['excluded_other_markets']} other-market and "
            f"{cond['excluded_other_arms']} other-arm trades were set aside first)",
        ]
        for state in body["states"]:
            lines.append(f"  {state['state']}")
            lines += [_cell_line(cell) for cell in state["windows"]]

        cf = body["counterfactual"]
        lines += [
            "",
            _verdict_line(cf, f"{cf['effect']} {abs(cf['delta_total_r']):.1f}R"),
            f"    sitting out {cf['state']} changes the book by "
            f"{cf['delta_total_r']:+.1f}R over {cf['closed']} closed trades; "
            f"{cf['basis']}",
        ]
        red = body["reduced"]
        delta = red["delta_expectancy_r"]
        shape, friendly_shape = red["shape"], red["shape_friendly"]
        lines += [
            _verdict_line(
                red, "none — no trades on one side" if delta is None
                else f"{delta:+.3f}R",
            ),
            # The counts and both win rates, on the line under the verdict. A
            # relative verdict quoted without the two sides behind it is the one
            # figure on this page a reader could most easily misread as absolute.
            f"    CHOPPY n={shape['closed']} "
            f"win {_pct(shape['win_rate'])} against FRIENDLY "
            f"n={friendly_shape['closed']} win {_pct(friendly_shape['win_rate'])}",
        ]

        breadth = body["breadth"]
        median = breadth["median"]
        spread = (
            f"median {median:.1%} over {breadth['sessions']} sessions"
            if median is not None
            else "no sessions carried a reading"
        )
        through = body["follow_through"]
        lines += [
            "",
            f"  breadth (descriptive, never conditioned on): {spread}",
            f"    {breadth['warning']}",
            f"  follow-through (unbiased, never conditioned on): index broke out "
            f"on {_pct(through['breakout_rate'])} of {through['sessions']} sessions",
            f"    {through['note']}",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Price the regime posture over a persisted denominator and record it.

    The command::

        python -m backtest.posture --store data/backtest.duckdb \\
            --out-json references/backtest_regime_posture.json

    Both markets by default, because the contract's scope names both and the
    postures are priced per market — IDX magnitudes are not US magnitudes. Arm B
    only, matching the pre-registered headline, so the posture and the metric it
    qualifies are the same trades.

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
    # The contract's own scope, resolved by :mod:`backtest.metric`'s one fallback
    # rather than by a second copy of it here: defaulting at the command *and* in
    # the report would be two places for "which markets is this run about" to
    # diverge, and the divergence shows up as a market silently missing.
    markets = _reported_markets(contract, args.market)
    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        trades: list[SimulatedTrade] = []
        spines: dict[str, RegimeSpine] = {}
        for market in markets:
            trades += simulate_market(
                store, denominator, market, contract, arms=(PRIMARY_ARM,)
            )
            spines[market] = spine_for_market(denominator, market)
    finally:
        denominator.close()
        store.close()

    report = posture_report(contract, trades, spines, markets=markets)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_posture(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
