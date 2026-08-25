"""Stamping the run contract into every result the package emits (issue #184).

The acceptance criterion is that any result the backtest emits carries the
contract that produced it, and that two runs under different contracts are
distinguishable from their serialised output alone. Both hold if — and only if —
the serialised contract rides on every result. :func:`stamp_result` is the one
place that happens: every later phase's serialiser wraps its payload here, so a
figure can never be committed without the contract that produced it, and two
runs' outputs differ wherever their contracts differ.
"""

from __future__ import annotations

from typing import Any

from .contract import RunContract

# The key the contract rides under on every stamped result. Fixed so a reader
# always finds the contract in the same place, whatever the payload is.
CONTRACT_KEY = "contract"


def stamp_result(contract: RunContract, payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``payload`` with the serialised ``contract`` stamped onto it.

    The contract is placed under :data:`CONTRACT_KEY` at the top of the result so
    it travels with every figure the package emits. A payload that already
    carries a ``contract`` key is a bug — a result cannot claim two contracts —
    so it is rejected rather than silently overwritten.
    """
    if CONTRACT_KEY in payload:
        raise ValueError(
            f"payload already carries a {CONTRACT_KEY!r} key; a result cannot "
            "claim two contracts"
        )
    return {CONTRACT_KEY: contract.to_dict(), **payload}
