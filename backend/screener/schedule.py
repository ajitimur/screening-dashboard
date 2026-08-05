"""Scheduling and run-on-open (spec §7.3).

The pipeline runs itself, per market, without being remembered. Two mechanisms,
deliberately both:

- **Two ``launchd`` jobs, one per market**, firing after that market's *own*
  close — there is no global nightly job, because IDX and US close hours apart
  and no coherent "tonight" spans both. ``StartCalendarInterval`` fires a missed
  job once on wake, so a sleeping laptop *delays* a run rather than losing it.
- **Run-on-open:** opening a market tab whose last final session is missing from
  the store kicks a run. Run-on-open alone was rejected (a ~9-minute pull does
  not fit the 10-minute nightly budget); manual-only was rejected (a forgotten
  night is invisible until you notice the as-of date).

This module owns the *decision* both mechanisms share — is the last final
session missing? — and renders the plists. The run itself is
:func:`screener.pipeline.run_market_universe`; the background coordinator that
run-on-open drives is :class:`screener.runner.RunManager`.
"""

from __future__ import annotations

import plistlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .bars import EXCHANGE, is_final

# The market-local hour each scheduled job fires at, *after* that market's close
# (spec §7.3): ≥19:00 WIB for IDX (the 2026-08-04 bar was measured final at 19:49
# WIB against a 16:00 close; earlier is unproven), ≥17:00 ET for US. launchd's
# StartCalendarInterval is keyed in the *machine's* local time, so a host is
# expected to run in the market's timezone (or generate a per-host plist); the
# hour is stated market-local because that is the only frame the finality margin
# is defined in.
RUN_HOUR = {"IDX": 19, "US": 17}

# How far back last_final_session will walk for a final weekday — a bound past
# the longest plausible market closure (a long holiday weekend) so the search
# always terminates.
_MAX_LOOKBACK_DAYS = 10


def last_final_session(market: str, now: datetime) -> date:
    """The most recent session whose bar is *final* as of ``now`` (spec §3.4).

    Walks back from ``now`` in the exchange's local calendar, skipping weekends,
    to the first weekday past its close + the finality margin. ``now`` must be
    timezone-aware; it is read in the market's own timezone, so the same instant
    resolves identically however it is expressed.

    This is the newest session a run *could* have produced — the yardstick both
    the scheduled job and run-on-open measure the store against. Holidays are not
    modelled (there is no trading calendar): a holiday yields a session for which
    the pull finds no new final bar, which backfill treats as an absent session
    and leaves no hole.
    """
    local = now.astimezone(ZoneInfo(EXCHANGE[market]["tz"]))
    session = local.date()
    for _ in range(_MAX_LOOKBACK_DAYS):
        if session.weekday() < 5 and is_final(session, market, now):
            return session
        session -= timedelta(days=1)
    return session


def run_is_due(latest_session: date | None, market: str, now: datetime) -> bool:
    """Is a run due — is the last final session missing from the store?

    ``latest_session`` is the store's last *published* session (``None`` when no
    run has published). A run is due when that session is behind
    :func:`last_final_session` — the one predicate the scheduled job checks on
    fire and the tab checks on open, so the two mechanisms cannot disagree about
    what "tonight" is.
    """
    if latest_session is None:
        return True
    return latest_session < last_final_session(market, now)


def launchd_plist(
    market: str,
    *,
    python: str = "/usr/bin/python3",
    working_dir: str = "/opt/screener",
) -> str:
    """Render one market's ``launchd`` job as a plist XML string (spec §7.3).

    ``StartCalendarInterval`` — not ``StartInterval`` — is deliberate: it fires a
    *missed* job once on wake, so a laptop asleep at the market's close delays the
    run to wake rather than losing the night. The job invokes
    ``python -m screener.run <MARKET>``, which gates on :func:`run_is_due` and
    drives :func:`screener.pipeline.run_market_universe`.
    """
    if market not in RUN_HOUR:
        raise ValueError(f"unknown market {market!r}")
    job = {
        "Label": f"com.screener.run.{market.lower()}",
        "ProgramArguments": [python, "-m", "screener.run", market],
        "WorkingDirectory": working_dir,
        # After the market's own close, in the machine's local time. On wake past
        # this hour, launchd runs the job once — the delayed-not-lost property.
        "StartCalendarInterval": {"Hour": RUN_HOUR[market], "Minute": 0},
        # Don't fire on load/reboot; the calendar interval is the only trigger.
        "RunAtLoad": False,
        "StandardOutPath": f"{working_dir}/logs/run.{market.lower()}.out.log",
        "StandardErrorPath": f"{working_dir}/logs/run.{market.lower()}.err.log",
    }
    return plistlib.dumps(job).decode()
