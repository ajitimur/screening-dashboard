"""The out-of-sample backtest (PRD #182) — the mechanical denominator.

Where :mod:`replay` means "the 828-trade reference study over US 2019–2022",
:mod:`backtest` means "the mechanical denominator over two markets and fourteen
years". The two differ in market, window and universe, so folding the second
into the first would leave the existing window and market constants meaning two
things at once. This package therefore lives beside :mod:`replay` rather than
extending it, and **imports** the replay chain and field machinery for reuse
rather than copying it (PRD "Implementation Decisions").

Issue #184 lands the first cell of it: the run contract as a single frozen,
serialisable value. Everything the run decides before any code runs — scope,
the universe gates, the regime source, the three exit arms, costs, the primary
metric and the kill/ship criteria — lives in one :class:`RunContract`, each cell
carrying its one-line justification. The contract is *data*, not module-level
constants, because the plan requires that a later contract change be a new run
recorded beside the old one, and that is only enforceable if the contract
travels with the results it produced (:func:`stamp_result`).

Issue #185 lands the second: :mod:`backtest.universe`, the contract's stateless
universe classifier. Issue #186 lands the third: :mod:`backtest.store`, the paced
bar fetcher and its refusal ledger, whose names *are* re-exported below. Issue
#187 lands the fourth, :mod:`backtest.crawl` — the runner that points that
fetcher at both markets over the contract's store window, and the command that
produced the committed store.

:mod:`backtest.crawl`'s names are not re-exported, for the same reason the
universe's are not: ``main``, ``crawl_market`` and ``CRAWL_START`` say what they
are only under the module qualifier. It is a runner, and its caller is a
terminal.

Issue #188 lands the first end-to-end path through the machine: :mod:`backtest.chain`
puts the contract's universe on the replay chain's own machinery,
:mod:`backtest.denominator` holds the rows that come out — membership, the three
regime columns, ranks, and every detection with its full record, its star-score
breakdown and both candidate dimensions — and :mod:`backtest.run` is the run that
produces them over one market and one window. Those rows are the denominator, and
:func:`~backtest.run.run_denominator` is the one entry point.

:mod:`backtest.run`'s names are **not** re-exported here, and for a mechanical
reason rather than a naming one: that module is also the run's command
(``python -m backtest.run``), and a package that imports it at package-import
time makes the interpreter find it already in ``sys.modules`` before it executes
it as ``__main__`` — which Python reports as a ``RuntimeWarning`` on every
invocation of the documented command. So the entry point is reached as
``backtest.run.run_denominator``.

Issues #189 and #190 land Phase 4: :mod:`backtest.simulate` turns each persisted
detection into a trade on each of the three exit arms. Entry is the detection's own
trigger — a close through it signals, the next open fills — and the stop is the
detection's own unmodified. Both are computed once and shared, so the arms differ in
the exit and in nothing else: B trails a 10MA, C a 20MA, and A takes 50% off at the
close of the fifth session after entry and trails the remainder on a 10MA, its R
position-weighted per leg and summed. The result is denominated in R off the
detection's stop width **in ADR**, so a rescale of the bar series moves numerator and
denominator together and R does not move at all; the one absolute-price comparison
that is not immune rides on every trade as a price-scale flag whose dropped count is
reported.

:mod:`backtest.simulate`'s names are **not** re-exported here, and the mechanical
reason is now doubled: it is a command in its own right
(``python -m backtest.simulate``), *and* it imports
:class:`~backtest.run.ContractDrift`, so re-exporting it would pull both it and
``backtest.run`` into ``sys.modules`` at package-import time and make either
documented command warn on every invocation. The entry point is reached as
``backtest.simulate.simulate_market``.

Issue #193 lands the first of Phase 5: :mod:`backtest.figures`, the three figures the
denominator was built to produce. Detections per session, the share that trigger, and
the share that reach a favourable outcome — precision, which the reference study can
report no value for at all because every result in it is conditioned on trades the
trader took. Reported per market and per year and never pooled only, plotted across
the window so a year whose count collapses is visible as the data hole it is, and every
rate carrying the coverage count it was measured against.

:mod:`backtest.figures`'s names are **not** re-exported here either, and for the same
mechanical reason as :mod:`backtest.simulate`'s: it is a command
(``python -m backtest.figures``) and it imports that module, so the entry point is
reached as ``backtest.figures.figures_for_market``.

Issue #191 lands Phase 5's **pre-registered** cell: :mod:`backtest.metric`, the one
metric the run promised in advance — arm B's after-cost expectancy in R, per market
per year. It reads no bar either. The simulator already denominated each trade in R,
so this module is arithmetic over those trades: the contract's per-market commission
and slippage charged on both sides and divided by the trade's own stop width, the
win rate and the R-distribution reported beside every expectancy, per year always
and the 2020–21-excluded figure beside the full-window one, and significance
bootstrapped by resampling **symbols** rather than rows. It computes and records the
headline **before any swept variant exists**, and says so with the count of variants
behind it.

The two Phase 5 modules divide by what they measure rather than by when they ran:
:mod:`backtest.figures` reports what the denominator *found* — detections, the share
that trigger, precision — and :mod:`backtest.metric` reports what trading it *paid*,
after costs, on the one arm the contract pre-registered.

:mod:`backtest.metric`'s names are **not** re-exported here for the reasons that
already keep :mod:`backtest.simulate` out: it is a command
(``python -m backtest.metric``) and it imports both that module and
:class:`~backtest.run.ContractDrift`, so re-exporting it would make either
documented command warn on every invocation. The entry point is
``backtest.metric.metric_report``.

Issue #192 lands Phase 5's most product-relevant cell: :mod:`backtest.posture`, which
prices the two words the app already prints. "Sit out" for ``HOSTILE`` and "reduced"
for ``CHOPPY`` ship in the product today on no measured basis; this module reports
after-cost expectancy **per regime state, per market, with n on every cell**, computes
what sitting out ``HOSTILE`` would have cost or saved, and answers ``CHOPPY``'s
"reduced" against ``FRIENDLY``'s measured expectancy rather than against the word.

It reads no bar either. The state comes from the reading :mod:`backtest.run` already
persisted for each session, joined to each trade on its **detection session** — which
is t−1, the night the candidate was listed with its posture beside it and two sessions
before the fill. The per-cell arithmetic is :mod:`backtest.metric`'s own, so a posture
cell and a headline cell cannot report the same trades differently.

The load-bearing property is that regime **conditions and never filters**. The three
states and an undefined bucket partition the trades, and the report accounts for the
two declared non-regime exclusions — the other market and the other arms — rather than
reducing the whole claim to one zero. What actually holds the promise sits upstream and
is structural: :mod:`backtest.simulate` reads no regime column when it produces trades,
pinned by a test that flips a persisted state and gets the same trades back.

Both regime companions are reported and neither is conditioned on. Breadth carries its
survivorship warning and can never be a cohort key —
:func:`~backtest.posture.posture_cell` takes a state and refuses anything else — while
follow-through is named plainly as **unbiased where breadth is not**, the one regime
signal the live app can never backfill and this run reconstructs legitimately.

:mod:`backtest.posture`'s names are **not** re-exported here, for the reasons that
already keep :mod:`backtest.metric` out: it is a command (``python -m
backtest.posture``) and it imports both that module and
:class:`~backtest.run.ContractDrift`. The entry point is
``backtest.posture.posture_report``.

Issue #194 lands Phase 5's ranking cell: :mod:`backtest.ranking`, the out-of-sample
test §4a's claim has never had. Outcomes bucketed by star-score decile, per market
and per year, with n on every bucket and significance bootstrapped clustered by
symbol. §4a asked whether the rubric separates his *picks* from the field, on the
field the v2 weights had been fitted to — a fit statistic, and marginal at
p = 0.055 even so. Here the outcome variable is R after costs, which no weight was
fitted to and no detection's score could see, so §4a's figures ride on the payload
with the reason they are not comparable rather than being left for a reader to line
up. The score is coarse — seven dimensions of eight integral points — so a score
value is never split across two buckets: the buckets collapse to fewer than ten and
each names the decile positions it covers, which is the honest reading of a
distribution most of which can sit on one score.

:mod:`backtest.ranking`'s names are **not** re-exported here, for the reasons that
already keep :mod:`backtest.metric` out: it is a command
(``python -m backtest.ranking``) and it imports both that module and
:class:`~backtest.run.ContractDrift`. The entry point is
``backtest.ranking.ranking_report``.

Issue #195 lands the second half of Phase 5's rubric question:
:mod:`backtest.candidates`, which measures both registered candidate dimensions
against **outcomes** rather than against the trader's selection. ADR 0005 admits a
dimension on a selection contrast because that was the only instrument available
when it was written; both registrations then failed on it — ``RS line`` refused for
a wrong-way gap, ``Relative move`` positive on both fields and stalled 0.06pp
inside a threshold the ADR itself calls a judgement. Here each candidate's cohort
splits three ways, never two: hit and miss under the pre-registered cut applied at
read time by the rubric's own reader, and **absent** where the question was never
asked. That third group is load-bearing rather than tidy — ``Relative move``'s cut
is zero, so an absence coerced to a number would land exactly on it — so absence
carries its own n and enters no gap. The published selection figures ride on every
candidate's cell under their own verdict key, because a dimension that ranks
outcomes and one that matches a selection are two claims that can point opposite
ways. Nothing here admits a dimension, and
:func:`~backtest.candidates.check_not_admitted` makes that executable.

:mod:`backtest.candidates`'s names are **not** re-exported here, for the reasons
that already keep :mod:`backtest.ranking` out: it is a command
(``python -m backtest.candidates``) and it imports both that module and
:class:`~backtest.run.ContractDrift`. The entry point is
``backtest.candidates.candidates_report``.

The universe's names are not re-exported, and the reason is naming rather than
import weight: ``classify``, ``Candidate`` and ``is_member`` each already mean
something else one import away (:mod:`screener.universe`, :mod:`replay.reference`),
so they are worth the module qualifier — ``backtest.universe.classify`` says which
universe it classifies. There is no import-weight argument to make either way:
:mod:`backtest.store` reaches the duckdb-backed store layer, so importing this
package has pulled it in since #186 regardless.
"""

from __future__ import annotations

from .contract import (
    DEFAULT_CONTRACT,
    DEFAULT_CONTRACT_JSON,
    Cell,
    RunContract,
)
from .chain import backtest_chain, excluded_references, stateless_universe
from .result import stamp_result
from .store import (
    BuildCoverage,
    LiveStoreWriteRefused,
    Refusal,
    build_backtest_store,
    coverage_path,
    market_symbol,
)

__all__ = [
    "Cell",
    "backtest_chain",
    "excluded_references",
    "stateless_universe",
    "RunContract",
    "DEFAULT_CONTRACT",
    "DEFAULT_CONTRACT_JSON",
    "stamp_result",
    "BuildCoverage",
    "LiveStoreWriteRefused",
    "Refusal",
    "build_backtest_store",
    "coverage_path",
    "market_symbol",
]
