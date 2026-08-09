"""A long pull that says where it is, and gets there faster (issue #96).

Two orthogonal complaints about the same loop. A US pull walked ~7,300 symbols
one at a time and printed nothing until it finished, so for the better part of
an hour a healthy run and a wedged one were the same observation: silence, with
``running: true``. And it took the better part of an hour *because* it was
sequential — each ``resolve`` blocked on a Yahoo round-trip before the next
began, so the 12 req/s cap (spec §3.3) was a ceiling the loop never came near.

So: a heartbeat every :data:`PROGRESS_EVERY` symbols, and enough resolves in
flight to actually spend the pacing budget. The budget itself does not move,
which is what :class:`Pacer` is now responsible for holding across threads, and
neither do the resolution semantics — those are the point of the whole module
and are asserted here to survive the pool.
"""

import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import PROGRESS_EVERY, progress_line, run_market_universe
from screener.source import (
    Instrument,
    Pacer,
    PermanentlyUnavailableError,
    Source,
    resolve_all,
)
from screener.store import Store

WIB = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)


class _Client:
    """Enumerates a fixed list; ``fetch`` runs ``behaviour`` for each symbol.

    ``behaviour`` is called with the symbol and returns bars, or raises — the
    tests below use it to block, to count, or to refuse.
    """

    def __init__(self, instruments=None, behaviour=lambda symbol: []) -> None:
        self._instruments = instruments or {}
        self._behaviour = behaviour

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol, start=None):
        return self._behaviour(symbol)

    def fetch_info(self, symbol):
        return {}


def _source(client, **kw):
    """A source with pacing and backoff neutralised — these tests are about the
    loop around it, not the waiting inside it."""
    return Source(client, rate_per_sec=100_000, sleep=lambda s: None, **kw)


# -- the pacer holds the cap across threads -----------------------------------


def test_pacer_holds_the_aggregate_rate_across_concurrent_callers():
    # The cap belongs to the provider, not to a caller. Unlocked, every thread
    # reads the same ``_next_allowed``, sleeps the same delay and fires together
    # — ten workers would burst at ten times the rate, which is exactly the
    # throttling the pacing exists to avoid.
    rate, calls, workers = 200.0, 100, 10
    pacer = Pacer(rate)
    barrier = threading.Barrier(workers)

    def hammer():
        barrier.wait()  # start together, so any burst is maximally visible
        for _ in range(calls // workers):
            pacer.wait()

    started = time.monotonic()
    threads = [threading.Thread(target=hammer) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started

    floor = (calls - 1) / rate
    assert elapsed >= floor * 0.9, (
        f"{calls} paced calls across {workers} threads took {elapsed:.3f}s; "
        f"the {rate}/s cap needs at least {floor:.3f}s"
    )


def test_pacer_sleeps_outside_the_lock_so_waits_overlap():
    # Serialising the *claim* is required; serialising the *wait* would make the
    # pool pointless, because each worker's pacing sleep would stack onto every
    # other's instead of running alongside it.
    workers = 8
    pacer = Pacer(4.0)  # a 250ms interval, so stacking is unmistakable
    barrier = threading.Barrier(workers)

    def claim():
        barrier.wait()
        pacer.wait()

    started = time.monotonic()
    threads = [threading.Thread(target=claim) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started

    # Eight overlapping waits finish when the *last* slot arrives (7 intervals),
    # not when their sleeps have been added up (1+2+...+7 = 28 intervals).
    assert elapsed < 7 * 0.25 * 1.5


# -- resolve_all: concurrent, complete, and semantically unchanged ------------


def test_resolve_all_runs_symbols_concurrently():
    # The proof is a barrier: it releases only once ``workers`` fetches are
    # inside it at the same moment. A sequential loop can never satisfy it, so
    # this test times out rather than passing slowly.
    workers = 6
    barrier = threading.Barrier(workers, timeout=10)

    def block(symbol):
        barrier.wait()
        return [{"row": symbol}]

    source = _source(_Client(behaviour=block))
    symbols = [f"S{i}" for i in range(workers * 3)]

    results = list(resolve_all(source, symbols, workers=workers))

    assert len(results) == len(symbols)
    assert all(r.status == "resolved" for r in results)


def test_resolve_all_returns_every_symbol_exactly_once():
    source = _source(_Client(behaviour=lambda symbol: [{"row": symbol}]))
    symbols = [f"S{i}" for i in range(500)]

    results = list(resolve_all(source, symbols, workers=12))

    assert Counter(r.symbol for r in results) == Counter(symbols)


def test_resolve_all_keeps_the_resolution_semantics_under_concurrency():
    # The three outcomes the rest of the system turns on (spec §3.2/§3.4): bars
    # resolve, silence is unresolved and never absent, and a stated refusal is
    # answered once. Moving the loop into a pool must not touch any of them.
    attempts: Counter[str] = Counter()
    lock = threading.Lock()

    def behaviour(symbol):
        with lock:
            attempts[symbol] += 1
        if symbol.startswith("REFUSED"):
            raise PermanentlyUnavailableError(f"{symbol}: period 'max' is invalid")
        if symbol.startswith("SILENT"):
            return []
        return [{"row": symbol}]

    symbols = [f"{kind}{i}" for kind in ("OK", "SILENT", "REFUSED") for i in range(20)]
    source = _source(_Client(behaviour=behaviour), max_attempts=4)

    by_symbol = {r.symbol: r for r in resolve_all(source, symbols, workers=8)}

    assert all(by_symbol[f"OK{i}"].status == "resolved" for i in range(20))
    assert all(by_symbol[f"SILENT{i}"].status == "unresolved" for i in range(20))
    assert all(by_symbol[f"REFUSED{i}"].status == "refused" for i in range(20))
    # Silence still earns the full retry budget; a refusal still costs one call.
    assert attempts["SILENT0"] == 4
    assert attempts["REFUSED0"] == 1


def test_resolve_all_bounds_how_many_symbols_are_in_flight():
    # A completed future holds a symbol's whole price history. Submitting all
    # ~7,300 up front would let the pool run far ahead of the consumer writing
    # bars to the store and pile the entire market in memory.
    workers = 4
    started: list[str] = []
    gate = threading.Event()

    def behaviour(symbol):
        started.append(symbol)
        gate.wait(timeout=10)
        return [{"row": symbol}]

    source = _source(_Client(behaviour=behaviour))
    symbols = [f"S{i}" for i in range(200)]

    results = resolve_all(source, symbols, workers=workers)
    next(results)  # nothing completes until the gate opens, so prime it in a thread
    gate.set()

    # Give the pool a moment to run away with the queue if it is going to.
    time.sleep(0.2)
    assert len(started) <= workers * 2 + 1, (
        f"{len(started)} of {len(symbols)} symbols were dispatched before the "
        "consumer had taken its first result"
    )
    results.close()


def test_resolve_all_with_one_worker_is_the_sequential_loop():
    order: list[str] = []
    source = _source(_Client(behaviour=lambda s: order.append(s) or [{"row": s}]))
    symbols = [f"S{i}" for i in range(20)]

    results = list(resolve_all(source, symbols, workers=1))

    assert order == symbols
    assert [r.symbol for r in results] == symbols


# -- the heartbeat line -------------------------------------------------------


def test_progress_line_breaks_out_the_outcomes_and_estimates_the_remainder():
    counts = Counter({"resolved": 1_105, "unresolved": 83, "refused": 12})

    line = progress_line("US", 1_200, 7_297, counts, elapsed=600.0)

    assert "US: pull 1,200/7,297" in line
    # Broken out, not summed: a rising silent count mid-pull is a throttled run
    # and is worth killing an hour before the completeness gate would.
    assert "1,105 resolved" in line
    assert "83 silent" in line
    assert "12 refused" in line
    # 1,200 in 10 minutes leaves 6,097 to go — a little over 50 more.
    assert "~50m left" in line


def test_progress_line_drops_the_estimate_on_the_final_line():
    counts = Counter({"resolved": 10})
    assert "left" not in progress_line("IDX", 10, 10, counts, elapsed=5.0)


@pytest.mark.parametrize(
    "elapsed, expected",
    [(45.0, "~45s left"), (300.0, "~5m left"), (5_400.0, "~1h30m left")],
)
def test_progress_line_scales_the_estimate_to_a_readable_unit(elapsed, expected):
    # Half done, so the time spent is the time left.
    assert expected in progress_line("US", 1, 2, Counter({"resolved": 1}), elapsed=elapsed)


# -- the run heartbeats while it pulls ----------------------------------------


def _instruments(n):
    return [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        *(
            Instrument(market="IDX", symbol=f"S{i}", role="candidate", name=f"Corp {i} Tbk")
            for i in range(n)
        ),
    ]


def test_the_run_heartbeats_while_the_pull_is_still_in_flight(store: Store, tmp_path):
    # The complaint this issue opened with: the only account of a pull was
    # summarize_pull, which lands once, at the end. These lines land *during*.
    total = PROGRESS_EVERY * 2 + 10
    instruments = _instruments(total - 1)
    source = _source(_Client({"IDX": instruments}, behaviour=lambda s: []))
    lines: list[str] = []

    run_market_universe(
        store,
        source,
        "IDX",
        date(2026, 8, 20),
        now=NOW,
        digests_dir=tmp_path,
        progress=lines.append,
    )

    # One line per PROGRESS_EVERY symbols, plus a last one closing out the pull.
    # The tail sweep's own lines (issue #104) land after all of these and are a
    # different heartbeat, so the pull's account is read on its own.
    pull_lines = [ln for ln in lines if ln.startswith("IDX: pull")]
    assert len(pull_lines) == 3
    assert pull_lines[0].startswith(f"IDX: pull {PROGRESS_EVERY:,}/{total:,}")
    assert pull_lines[1].startswith(f"IDX: pull {PROGRESS_EVERY * 2:,}/{total:,}")
    assert pull_lines[2].startswith(f"IDX: pull {total:,}/{total:,}")
    assert lines[:3] == pull_lines[:3], "a sweep line interleaved with the pull's"


def test_the_run_ingests_bars_on_the_calling_thread(store: Store, tmp_path):
    # resolve_all fetches concurrently but yields one result at a time, so every
    # store write stays where it was. The store is not safe to write from the
    # pool, and this is the invariant that keeps it from having to be.
    instruments = _instruments(40)
    # Liquid enough (Rp 2B/day) and long enough to build a real universe, so the
    # run goes all the way through its write stages rather than short-circuiting.
    bars = [
        {"Date": date(2026, 7, 1) + timedelta(days=i), "Open": 2000.0, "High": 2001.0,
         "Low": 1999.0, "Close": 2000.0, "Adj Close": 2000.0, "Volume": 1_000_000}
        for i in range(25)
    ]
    source = _source(_Client({"IDX": instruments}, behaviour=lambda s: bars))
    writing_threads: set[int] = set()
    append_bars = store.append_bars

    def recording_append_bars(*args, **kwargs):
        writing_threads.add(threading.get_ident())
        return append_bars(*args, **kwargs)

    store.append_bars = recording_append_bars  # type: ignore[method-assign]

    run_market_universe(
        store, source, "IDX", date(2026, 8, 20), now=NOW,
        digests_dir=tmp_path, progress=lambda line: None,
    )

    assert writing_threads == {threading.get_ident()}
