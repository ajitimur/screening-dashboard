"""Seam 6c: the append-only ``ranks`` table, and its rolling 2-year window.

The rank table is the map's fourth irrecoverable nightly stream (ticket 06 R5):
last night's ranks cannot be reconstructed later because the universe they were
ranked against is gone. It is also the **first stream that discards** — a rolling
2-year window, the sole casualty a future multi-year study. This seam pins the
append-only write (per the store discipline) and the retention prune.
"""

from datetime import date

import pytest

from screener.ranks import Rank
from screener.store import SessionExistsError, Store


def _rank(symbol, lookback, pct, ret):
    return Rank(symbol, lookback, pct, ret)


def test_append_and_read_back_rank_rows(store: Store):
    rows = [
        _rank("AAA", "1w", 0.95, 0.30),
        _rank("AAA", "3m", 0.80, 0.50),
        _rank("BBB", "1w", 0.40, 0.05),
    ]
    store.append_ranks("US", date(2026, 8, 5), rows)

    read = store.ranks("US", date(2026, 8, 5))
    assert set(read) == set(rows)  # Rank is a frozen dataclass, hashable
    assert all(isinstance(r, Rank) for r in read)


def test_rewriting_a_session_of_ranks_is_refused(store: Store):
    store.append_ranks("US", date(2026, 8, 5), [_rank("A", "1w", 0.9, 0.2)])
    with pytest.raises(SessionExistsError):
        store.append_ranks("US", date(2026, 8, 5), [_rank("A", "1w", 0.1, 0.0)])
    # The original row survives untouched.
    assert store.ranks("US", date(2026, 8, 5)) == [_rank("A", "1w", 0.9, 0.2)]


def test_ranks_are_kept_per_market(store: Store):
    store.append_ranks("US", date(2026, 8, 5), [_rank("A", "1w", 0.9, 0.2)])
    store.append_ranks("IDX", date(2026, 8, 5), [_rank("Z", "1w", 0.9, 0.2)])
    assert [r.symbol for r in store.ranks("US", date(2026, 8, 5))] == ["A"]
    assert [r.symbol for r in store.ranks("IDX", date(2026, 8, 5))] == ["Z"]


def test_ranks_older_than_two_years_are_pruned_on_append(store: Store):
    # An old session, then one just over two years later. Appending the newer
    # session prunes everything strictly older than the 2-year window.
    store.append_ranks("US", date(2024, 8, 4), [_rank("OLD", "1w", 0.9, 0.2)])
    store.append_ranks("US", date(2026, 8, 5), [_rank("NEW", "1w", 0.9, 0.2)])

    assert store.ranks("US", date(2024, 8, 4)) == []  # dropped, past the window
    assert [r.symbol for r in store.ranks("US", date(2026, 8, 5))] == ["NEW"]


def test_ranks_inside_the_two_year_window_are_retained(store: Store):
    # A session exactly two years back is on the edge and kept.
    store.append_ranks("US", date(2024, 8, 5), [_rank("EDGE", "1w", 0.9, 0.2)])
    store.append_ranks("US", date(2026, 8, 5), [_rank("NEW", "1w", 0.9, 0.2)])
    assert [r.symbol for r in store.ranks("US", date(2024, 8, 5))] == ["EDGE"]


def test_pruning_is_per_market(store: Store):
    # A new US session must not prune an old IDX session — retention is per market.
    store.append_ranks("IDX", date(2024, 8, 4), [_rank("OLDIDX", "1w", 0.9, 0.2)])
    store.append_ranks("US", date(2026, 8, 5), [_rank("NEWUS", "1w", 0.9, 0.2)])
    assert [r.symbol for r in store.ranks("IDX", date(2024, 8, 4))] == ["OLDIDX"]
