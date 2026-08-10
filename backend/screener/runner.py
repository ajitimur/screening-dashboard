"""The run-on-open coordinator (spec §7.3).

Opening a market tab whose last final session is missing from the store kicks a
run with a progress state. ``RunManager`` owns that background run: it runs one
market's pipeline off the request thread, tracks its status so the tab can show
a progress state and poll for completion, and is **single-flight per market** —
a second open while a run is in flight joins the existing run rather than
starting a duplicate.

The manager is deliberately blind to *what* the run does. It takes a ``runner``
callable (``market -> None``); the app wires that to open a store + source and
call :func:`screener.pipeline.run_market_universe` for the due session. Reads are
never served from a half-written session: every read endpoint keys off the last
*published* run record, which :func:`run_market_universe` writes last, so the
new session only becomes visible once the whole run has landed.

An optional ``recompute_runner`` (``market, session -> None``) drives the
operator override — re-pulling a published session after an enumeration fix
(issue #111). It shares the same single-flight flag, so a recompute and a
run-on-open of the same market cannot run at once; either joins whichever is
already in flight.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Callable, Literal

RunState = Literal["idle", "running", "failed"]


class RunManager:
    """Coordinates one background pipeline run per market, single-flight."""

    def __init__(
        self,
        runner: Callable[[str], None],
        recompute_runner: Callable[[str, date | None], None] | None = None,
    ) -> None:
        self._runner = runner
        self._recompute_runner = recompute_runner
        self._lock = threading.Lock()
        self._state: dict[str, RunState] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._error: dict[str, str] = {}

    def trigger(self, market: str) -> bool:
        """Start a run-on-open for ``market`` unless one is already in flight.

        Returns ``True`` when a run was started, ``False`` when one was already
        running (the run-on-open that arrives mid-run is a no-op, not a
        duplicate). The status flips to ``running`` before the thread starts, so
        a caller that sees ``True`` can rely on :meth:`is_running`.
        """
        return self._start(market, lambda: self._runner(market))

    def trigger_recompute(self, market: str, session: date | None = None) -> bool:
        """Start an operator recompute of ``session`` for ``market`` (issue #111).

        The same single-flight contract as :meth:`trigger` — ``False`` when a run
        (of either kind) is already in flight — but drives the recompute runner,
        which re-pulls and replaces a published session only if the fresh pull
        clears the completeness gate. ``session`` defaults to the last final
        session. Raises :class:`RuntimeError` when no recompute runner was wired.
        """
        if self._recompute_runner is None:
            raise RuntimeError("no recompute runner configured")
        recompute = self._recompute_runner
        return self._start(market, lambda: recompute(market, session))

    def _start(self, market: str, job: Callable[[], None]) -> bool:
        with self._lock:
            if self._state.get(market) == "running":
                return False
            self._state[market] = "running"
            self._error.pop(market, None)
            thread = threading.Thread(
                target=self._run, args=(market, job), name=f"run-{market}", daemon=True
            )
            self._threads[market] = thread
        thread.start()
        return True

    def _run(self, market: str, job: Callable[[], None]) -> None:
        try:
            job()
        except Exception as exc:  # a failed pull must clear the running flag
            with self._lock:
                self._state[market] = "failed"
                self._error[market] = str(exc)
            return
        with self._lock:
            self._state[market] = "idle"

    def status(self, market: str) -> RunState:
        """The market's current run state — ``idle`` before any run."""
        with self._lock:
            return self._state.get(market, "idle")

    def is_running(self, market: str) -> bool:
        return self.status(market) == "running"

    def error(self, market: str) -> str | None:
        """The last failure message for ``market``, or ``None``."""
        with self._lock:
            return self._error.get(market)

    def join(self, market: str, timeout: float | None = None) -> None:
        """Block until ``market``'s in-flight run finishes — for tests and
        graceful shutdown; the request path polls :meth:`is_running` instead."""
        with self._lock:
            thread = self._threads.get(market)
        if thread is not None:
            thread.join(timeout)
