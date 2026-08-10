"""Scheduling and run-on-open (spec §7.3, ticket 43).

The domain here is pure: given ``now`` and the store's last run of any status,
decide whether a run is *due* (its last final session is missing or quarantined),
and render the two per-market ``launchd`` jobs that fire the nightly run after
each market's own close.
"""

import plistlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

from screener.models import RunRecord, RunStatus
from screener.schedule import (
    RUN_HOUR,
    last_final_session,
    launchd_plist,
    run_is_due,
)

WIB = ZoneInfo("Asia/Jakarta")
ET = ZoneInfo("America/New_York")


def _run(session: date, status: RunStatus = "published") -> RunRecord:
    return RunRecord(
        market="IDX",
        session=session,
        status=status,
        symbols_enumerated=100,
        symbols_resolved=100 if status == "published" else 50,
        created_at=datetime(session.year, session.month, session.day, 19, 30),
    )


# -- last_final_session -------------------------------------------------------


def test_last_final_session_is_today_once_past_the_close_margin():
    # 2026-08-05 is a Wednesday; 20:00 WIB is well past IDX's 16:00 close + 30m.
    now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
    assert last_final_session("IDX", now) == date(2026, 8, 5)


def test_last_final_session_is_yesterday_before_the_close_margin():
    # 09:00 WIB on Wednesday: today's bar is not final yet, so the last final
    # session is Tuesday 2026-08-04.
    now = datetime(2026, 8, 5, 9, 0, tzinfo=WIB)
    assert last_final_session("IDX", now) == date(2026, 8, 4)


def test_last_final_session_skips_the_weekend():
    # Sunday 2026-08-09, 20:00 WIB: no session Sat/Sun, so the last final one is
    # Friday 2026-08-07.
    now = datetime(2026, 8, 9, 20, 0, tzinfo=WIB)
    assert last_final_session("IDX", now) == date(2026, 8, 7)


def test_last_final_session_reads_now_in_the_market_timezone():
    # US close is 16:00 ET; 17:00 ET on 2026-08-05 is past the margin. The same
    # instant expressed in UTC must resolve identically.
    now_utc = datetime(2026, 8, 5, 21, 0, tzinfo=ZoneInfo("UTC"))  # 17:00 ET
    assert last_final_session("US", now_utc) == date(2026, 8, 5)


# -- run_is_due ---------------------------------------------------------------


def test_run_is_due_when_the_store_is_empty():
    now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
    assert run_is_due(None, "IDX", now) is True


def test_run_is_due_when_the_last_final_session_is_missing():
    # Stored through Tuesday, but Wednesday's bar is now final — a run is due.
    now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
    assert run_is_due(_run(date(2026, 8, 4)), "IDX", now) is True


def test_run_is_not_due_when_the_store_has_the_last_final_session():
    now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
    assert run_is_due(_run(date(2026, 8, 5)), "IDX", now) is False


def test_run_is_not_due_before_tonights_close():
    # 09:00 WIB Wednesday: the last final session is Tuesday, already stored.
    now = datetime(2026, 8, 5, 9, 0, tzinfo=WIB)
    assert run_is_due(_run(date(2026, 8, 4)), "IDX", now) is False


def test_run_is_due_when_the_last_final_session_is_quarantined():
    # The last final session has a run record, so it is not *missing* — but it
    # quarantined, so nothing was published for it and the fix that would let it
    # publish must get a same-day retry rather than waiting for the calendar to
    # roll (issue #103).
    now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
    assert run_is_due(_run(date(2026, 8, 5), "quarantined"), "IDX", now) is True


# -- launchd_plist ------------------------------------------------------------


def test_launchd_plist_is_a_valid_plist_scheduled_after_the_market_close():
    xml = launchd_plist("IDX")
    parsed = plistlib.loads(xml.encode())

    # One job per market, labelled by market.
    assert parsed["Label"] == "com.screener.run.idx"
    # It invokes the run entry point for this market.
    assert "screener.run" in parsed["ProgramArguments"]
    assert "IDX" in parsed["ProgramArguments"]
    # Fires after IDX's close (≥19:00 WIB, spec §7.3).
    assert parsed["StartCalendarInterval"]["Hour"] == RUN_HOUR["IDX"] == 19


def test_launchd_plist_us_fires_after_the_us_close():
    parsed = plistlib.loads(launchd_plist("US").encode())
    assert parsed["Label"] == "com.screener.run.us"
    assert parsed["StartCalendarInterval"]["Hour"] == RUN_HOUR["US"] == 17
    assert "US" in parsed["ProgramArguments"]


def test_launchd_plist_uses_start_calendar_interval_so_a_missed_job_wakes():
    # StartCalendarInterval is the key that fires a missed job once on wake — a
    # sleeping laptop delays a run rather than losing it (spec §7.3). StartInterval
    # (a plain period) would not, so its absence is load-bearing.
    parsed = plistlib.loads(launchd_plist("US").encode())
    assert "StartCalendarInterval" in parsed
    assert "StartInterval" not in parsed


def test_launchd_plist_threads_through_the_working_directory_and_python():
    xml = launchd_plist("IDX", python="/opt/py/bin/python", working_dir="/srv/app")
    parsed = plistlib.loads(xml.encode())
    assert parsed["ProgramArguments"][0] == "/opt/py/bin/python"
    assert parsed["WorkingDirectory"] == "/srv/app"
