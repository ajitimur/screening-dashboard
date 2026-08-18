"""A run-scoped bar-read cache at the store boundary (issue #125, PRD #114).

A replay run rebuilds the universe, ranks and detections session by session, and
every one of those stages reads a symbol's *whole* bar history and then slices it
to the session under evaluation (``[b for b in store.bars(...) if b.session <=
session]``). :func:`screener.universe.rebuild_universe` alone does this for every
candidate on every session — across 7,529 symbols and 947 sessions that is ~7.1M
identical DuckDB round-trips, ~147 minutes of pure re-fetching, essentially the
whole runtime of the study.

Bars are immutable for the life of a replay: the build copies them once and the
chain only ever *writes* the derived streams (``universe``, ``ranks``,
``detections``). No caller mutates the list :meth:`screener.store.Store.bars`
returns — every one builds a new list from it — and :class:`~screener.bars.Bar`
is frozen. So handing back the same list object on a repeat read is
semantics-preserving, and doing it at the store boundary leaves the app's own
screening functions (:func:`rebuild_universe`, :func:`rebuild_ranks`,
:func:`rebuild_detections`) unmodified: they still measure the app that exists,
they just stop paying for the same query twice (issue #125 acceptance).

The cache is bounded by the number of symbols, so once every name has been read
once it stops growing — peak memory is one copy of the store's bars, a few GB for
a full US 2019–2022 replay, not a leak that grows with session count.
"""

from __future__ import annotations

import duckdb

from screener.bars import Bar
from screener.store import Store


class CachingStore(Store):
    """A :class:`~screener.store.Store` that memoizes :meth:`bars` for the life of
    a replay run, delegating every other read and write to the underlying store.

    Constructed by wrapping an already-open store, over whose connection it reads
    and writes — so a universe or rank row written through the cache is visible to
    the next read exactly as it would be through the plain store. Only ``bars`` is
    intercepted; a bar write (:meth:`append_bars`, :meth:`replace_bars`) evicts the
    affected symbol so a cached read can never go stale, though a replay run writes
    no bars once the chain begins.

    Use :meth:`wrap` rather than the constructor when the store might already be a
    cache, so the whole run shares one cache instead of nesting a second, cold one.
    """

    def __init__(self, inner: Store) -> None:
        # Share the wrapped store's connection instead of re-running __init__'s
        # schema create + migrate: the inner store already reconciled the file,
        # and both must read and write the same rows for a cached write to show up
        # on the next read.
        self._con: duckdb.DuckDBPyConnection = inner._con
        self._inner = inner
        self._bars_cache: dict[tuple[str, str], list[Bar]] = {}

    @classmethod
    def wrap(cls, store: Store) -> "CachingStore":
        """Return ``store`` itself if it already caches, else wrap it.

        A replay run threads one store through several stages (the chain, then the
        detection pass); wrapping at each would give each stage its own cold cache
        and re-read every symbol per stage. ``wrap`` keeps the run on a single
        shared cache."""
        if isinstance(store, CachingStore):
            return store
        return cls(store)

    def bars(self, market: str, symbol: str) -> list[Bar]:
        """The symbol's bars, read once from the store and served from memory
        after. Byte-identical to a fresh read — the same list of frozen bars — and
        never re-queried within the run."""
        key = (market, symbol)
        cached = self._bars_cache.get(key)
        if cached is None:
            cached = super().bars(market, symbol)
            self._bars_cache[key] = cached
        return cached

    def append_bars(self, market: str, symbol: str, bars: list[Bar]) -> int:
        """Append bars and evict the symbol, so the next read reflects the write.

        A replay run writes no bars once the chain begins, so this is defensive:
        it keeps the cache honest if a caller ever does mutate the bar history."""
        self._bars_cache.pop((market, symbol), None)
        return super().append_bars(market, symbol, bars)

    def replace_bars(self, market: str, symbol: str, bars: list[Bar]) -> int:
        """Rewrite a symbol's bars and evict it from the cache (see
        :meth:`append_bars`)."""
        self._bars_cache.pop((market, symbol), None)
        return super().replace_bars(market, symbol, bars)
