"""The sector/industry label cache and its policy (spec §3.1, §3.3, §7.4 stage 7).

Every universe member carries a **sector** and an **industry**, and both arrive
in the *same* source request — which is what makes industry the theme layer for
free (spec §4.4). A label costs one request per symbol, so a full pass every
night is far too long; the cache is the one *incremental* piece of the pipeline
(spec §3.3, §7.4). Its policy is three rules:

- **New names block.** A member absent from the cache has its labels fetched
  before it can appear on any surface — a name with no industry cannot be placed
  on the axis, so this is correctness, not cost.
- **Existing names roll.** Roughly ``1/SLICE`` of already-cached members refresh
  each night — the stalest first — so the universe turns over monthly with
  bounded staleness and a nightly cost that does not grow with the universe
  (old members are not re-fetched every night).
- **A failed fetch never nulls a cached value.** Silence — an empty ``.info`` or
  a persistent 429, byte-identical by spec §3.2 — leaves yesterday's label in
  place and reschedules the fetch. This is sticky membership (§3.4 rule 6) one
  layer up: removal (here, a label change) needs positive evidence, and the
  retry is implicit — an un-updated ``as_of`` keeps the name among the stalest.

This module is the *pure* half: the :class:`Label` record and the selection of
which symbols to fetch tonight. :func:`screener.pipeline.refresh_labels` is the
store-and-source-driven wrapper that does the actual fetching and caching.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

# Existing members refresh on a rolling 1/30th slice nightly: the universe turns
# over in ~a month, so staleness is bounded at ~SLICE nights (spec §3.3, ~73
# names / ~2 min measured). One over this is the fraction refreshed per night.
SLICE = 30


@dataclass(frozen=True)
class Label:
    """One symbol's cached sector/industry, stamped with the run date it was
    fetched. ``as_of`` is an as-of-only capture — never backfilled (spec §7.3);
    it also drives the rolling refresh (the stalest ``as_of`` goes first)."""

    symbol: str
    sector: str
    industry: str
    as_of: date


def select_fetches(
    members: list[str],
    cached: dict[str, Label],
    *,
    slice_size: int = SLICE,
) -> tuple[list[str], list[str]]:
    """Split tonight's ``members`` into ``(new, refresh)`` symbols to fetch.

    ``new`` is every member with no cached label — these *block* (they cannot
    appear until fetched). ``refresh`` is the stalest ``ceil(len(existing) /
    slice_size)`` already-cached members, so about ``1/slice_size`` of the
    warm universe rolls each night and none goes un-refreshed longer than
    ``slice_size`` nights. Ordering is ``(as_of, symbol)`` so it is deterministic
    and a failed fetch (which leaves ``as_of`` untouched) is retried first next
    night.
    """
    new = [s for s in members if s not in cached]
    existing = [s for s in members if s in cached]
    count = math.ceil(len(existing) / slice_size) if existing else 0
    refresh = sorted(existing, key=lambda s: (cached[s].as_of, s))[:count]
    return new, refresh
