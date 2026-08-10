"""The scheduled run entry point: ``python -m screener.run <MARKET>`` (spec §7.3).

This is what the two ``launchd`` jobs invoke and what run-on-open drives in the
background. It is the thinnest possible wrapper around the gate and the pipeline:
compute ``now``, ask :func:`run_is_due` whether the last final session is
missing, and — only if it is — run :func:`run_market_universe` for that session.
Backfill of any absent sessions in between is the pipeline's own concern; this
layer decides *whether* tonight needs a run and for *which* session.

The source is a parameter so the decision logic is testable without the network.
``main`` builds the real one via :func:`screener.source.default_source`, which is
the single place the live Yahoo/Nasdaq client is wired — not yet implemented, so
a bare invocation fails loudly rather than pulling nothing.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .bars import EXCHANGE
from .models import RunRecord
from .pipeline import DEFAULT_DIGESTS_DIR, run_market_universe, summarize_pull
from .schedule import last_final_session, run_is_due
from .source import Source
from .store import Store


def run_once(
    store: Store,
    source: Source,
    market: str,
    *,
    now: datetime,
    digests_dir: Path = DEFAULT_DIGESTS_DIR,
) -> RunRecord | None:
    """Run ``market``'s pipeline for the last final session, if it is due.

    Returns the resulting :class:`RunRecord`, or ``None`` when the store already
    holds the last final session as a *published* run (nothing was due — a
    quarantined one is retried, issue #103). ``now`` must be timezone-aware; it
    fixes both the finality decision and the session run.
    """
    if not run_is_due(store.last_run(market), market, now):
        return None
    session = last_final_session(market, now)
    return run_market_universe(
        store, source, market, session, now=now, digests_dir=digests_dir
    )


def recompute_once(
    store: Store,
    source: Source,
    market: str,
    session: date,
    *,
    now: datetime,
    digests_dir: Path = DEFAULT_DIGESTS_DIR,
) -> RunRecord | None:
    """Operator override: re-pull ``session`` and replace it if the pull is clean.

    The supported answer to "we shipped an enumeration fix, now make this
    published session reflect it" (issue #111). Unlike :func:`run_once` it does
    *not* gate on :func:`run_is_due` — a published session is never "due", which
    is the whole reason the correction had no supported path — and it targets the
    session the operator names rather than the last final one. The replacement is
    a safe atomic swap: :func:`run_market_universe` re-pulls, and only if the
    fresh pull clears the completeness gate does it supersede the published
    session; a throttled recompute returns ``None`` and leaves the good session
    standing. Returns the fresh :class:`RunRecord`, or ``None`` when the pull fell
    short and the existing session was kept.
    """
    return run_market_universe(
        store, source, market, session, now=now, digests_dir=digests_dir, recompute=True
    )


def run_live(market: str) -> RunRecord | None:
    """Wire the real store and source and run ``market``'s due session.

    Opens the file-backed store and the live source, computes ``now`` in the
    market's own timezone, and runs the due session — the single production path
    shared by the scheduled CLI and run-on-open (:class:`screener.runner.RunManager`).
    Each call owns its store connection, so a background run never shares the
    app's read connection. Returns the :class:`RunRecord`, or ``None`` when
    nothing was due.

    The run's account of its own pull is printed here, while the store is still
    open, because this is the one path both the launchd jobs and run-on-open go
    through — the scheduled jobs capture stdout, so a quarantined run explains
    itself in the log file rather than only in the database (issue #91).
    """
    from .app import DEFAULT_DB_PATH
    from .source import default_source

    now = datetime.now(ZoneInfo(EXCHANGE[market]["tz"]))
    store = Store.open(DEFAULT_DB_PATH)
    try:
        record = run_once(store, default_source(), market, now=now)
        if record is not None:
            print(summarize_pull(record, store.run_failures(market, record.session)))
        return record
    finally:
        store.close()


def recompute_live(market: str, session: date | None = None) -> RunRecord | None:
    """Wire the real store and source and recompute one published ``session``.

    The live counterpart of :func:`recompute_once` — the operator path for
    correcting a published session after an enumeration fix (issue #111). Opens
    the file-backed store and live source exactly as :func:`run_live` does, and
    prints the fresh pull's account while the store is open. ``session`` defaults
    to the last final session — the #110 case is "correct *today's* published
    universe" — but any published session can be named. Returns the fresh
    :class:`RunRecord`, or ``None`` when the pull fell short and the existing
    session was kept.
    """
    from .app import DEFAULT_DB_PATH
    from .source import default_source

    now = datetime.now(ZoneInfo(EXCHANGE[market]["tz"]))
    target = session if session is not None else last_final_session(market, now)
    store = Store.open(DEFAULT_DB_PATH)
    try:
        record = recompute_once(store, default_source(), market, target, now=now)
        if record is not None:
            print(summarize_pull(record, store.run_failures(market, record.session)))
        return record
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    """CLI: ``screener.run <MARKET> [--recompute [SESSION]]``.

    With no flag, runs the due session for one market against the live store and
    source (what launchd invokes). ``--recompute`` is the operator override for
    correcting a *published* session after an enumeration fix (issue #111): it
    re-pulls and replaces that session only if the fresh pull clears the
    completeness gate, so a throttled retry can never downgrade good data.
    ``SESSION`` is an ``YYYY-MM-DD`` date and defaults to the last final session.
    """
    parser = argparse.ArgumentParser(prog="screener.run")
    parser.add_argument("market", type=str.upper, choices=sorted(EXCHANGE))
    parser.add_argument(
        "--recompute",
        nargs="?",
        const="",
        metavar="SESSION",
        help="re-pull and replace a published session (default: last final); "
        "the swap only lands if the fresh pull clears the completeness gate",
    )
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2
    market = args.market

    if args.recompute is not None:
        try:
            session = (
                date.fromisoformat(args.recompute) if args.recompute else None
            )
        except ValueError:
            print(
                f"invalid --recompute session {args.recompute!r}; "
                "expected YYYY-MM-DD",
                file=sys.stderr,
            )
            return 2
        try:
            record = recompute_live(market, session)
        except Exception as exc:  # a mis-aimed recompute explains itself
            print(f"{market}: recompute failed — {exc}", file=sys.stderr)
            return 1
        if record is None:
            print(f"{market}: recompute pull fell short, published session kept")
        return 0

    # A run that happened has already printed its own account of the pull
    # (:func:`summarize_pull`, called in ``run_live`` while the store is open);
    # only the no-run case is left to say here.
    if run_live(market) is None:
        print(f"{market}: already current, no run")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
