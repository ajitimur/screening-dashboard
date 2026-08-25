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
"""

from __future__ import annotations

from .contract import (
    DEFAULT_CONTRACT,
    DEFAULT_CONTRACT_JSON,
    Cell,
    RunContract,
)
from .result import stamp_result
from .store import (
    IDX_SUFFIX,
    BuildCoverage,
    Refusal,
    build_backtest_store,
    market_symbol,
)

__all__ = [
    "Cell",
    "RunContract",
    "DEFAULT_CONTRACT",
    "DEFAULT_CONTRACT_JSON",
    "stamp_result",
    "IDX_SUFFIX",
    "BuildCoverage",
    "Refusal",
    "build_backtest_store",
    "market_symbol",
]
