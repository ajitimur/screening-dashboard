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
bar fetcher and its refusal ledger, whose names *are* re-exported below.

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
