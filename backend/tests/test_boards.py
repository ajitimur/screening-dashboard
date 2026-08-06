"""Seam 6e (pure): the five leaderboards, built from the rank table.

Boards are a **read-time cut of the rank table**, not a stored stream (spec §5.2,
§7.2 — boards are not in the derived-table list). ``build_boards`` is pure over
rank rows so every property below is unit-tested without a store: raw-return
sort, the ``k/5`` breadth badge, the ``NEW`` marker against last session, and the
1w ``surge`` flag. Rank is on **pure return, no volatility adjustment** — the ADR
that rides each row is a column, never the sort key (§4.3 / ticket 06 R8/R9).
"""

from screener.boards import BOARD_SIZE, SURGE_THRESHOLD, build_boards
from screener.indicators import LOOKBACKS
from screener.ranks import TOP_DECILE, Rank


def _rank(symbol, lookback, raw_return, percentile=0.5):
    return Rank(symbol, lookback, percentile, raw_return)


def test_a_board_is_top_30_by_raw_return_descending():
    # 40 names ranked in 1w by ascending return; the board keeps the top 30.
    rows = [_rank(f"N{i:02d}", "1w", raw_return=i / 100) for i in range(40)]
    boards = {b.lookback: b for b in build_boards(rows, prev_rows=[], adrs={})}

    board = boards["1w"]
    assert len(board.rows) == BOARD_SIZE
    returns = [r.raw_return for r in board.rows]
    assert returns == sorted(returns, reverse=True)  # highest first
    # The bottom ten (N00..N09, the smallest returns) never made the cut.
    assert "N09" not in {r.symbol for r in board.rows}
    assert board.rows[0].symbol == "N39"


def test_all_five_boards_are_built():
    rows = [_rank(f"N{i}", lb, raw_return=i / 10) for lb in LOOKBACKS for i in range(5)]
    boards = build_boards(rows, prev_rows=[], adrs={})
    assert [b.lookback for b in boards] == list(LOOKBACKS)


def test_breadth_counts_top_decile_lookbacks():
    # ACE tops the decile in 1w, 1m and 3m (k=3); DUD in none (k=0).
    rows = []
    for lb in LOOKBACKS:
        top = lb in ("1w", "1m", "3m")
        rows.append(_rank("ACE", lb, 0.5, percentile=TOP_DECILE if top else 0.4))
        rows.append(_rank("DUD", lb, 0.1, percentile=0.2))
    boards = {b.lookback: b for b in build_boards(rows, prev_rows=[], adrs={})}

    ace = next(r for r in boards["1w"].rows if r.symbol == "ACE")
    dud = next(r for r in boards["1w"].rows if r.symbol == "DUD")
    assert ace.breadth == 3
    assert dud.breadth == 0


def test_new_marker_is_absence_from_last_sessions_board():
    prev = [_rank("STAY", "1m", 0.9), _rank("GONE", "1m", 0.8)]
    now = [_rank("STAY", "1m", 0.9), _rank("FRESH", "1m", 0.7)]
    board = {b.lookback: b for b in build_boards(now, prev_rows=prev, adrs={})}["1m"]

    by_symbol = {r.symbol: r for r in board.rows}
    assert by_symbol["STAY"].is_new is False  # on the board last session
    assert by_symbol["FRESH"].is_new is True  # absent last session


def test_new_marker_is_per_lookback():
    # A name on last session's 1w board but not its 3m board is NEW on 3m only.
    prev = [_rank("X", "1w", 0.9)]
    now = [_rank("X", "1w", 0.9), _rank("X", "3m", 0.5)]
    boards = {b.lookback: b for b in build_boards(now, prev_rows=prev, adrs={})}
    assert boards["1w"].rows[0].is_new is False
    assert boards["3m"].rows[0].is_new is True


def test_surge_flag_only_on_the_1w_board():
    rows = [_rank("HOT", lb, raw_return=SURGE_THRESHOLD + 0.05) for lb in LOOKBACKS]
    boards = {b.lookback: b for b in build_boards(rows, prev_rows=[], adrs={})}
    assert boards["1w"].rows[0].surge is True  # up ≥30% over the week
    # The same return on the 3m board is not the five-day scan and never flags.
    assert boards["3m"].rows[0].surge is False


def test_surge_flag_needs_the_threshold():
    rows = [
        _rank("HOT", "1w", SURGE_THRESHOLD),  # exactly 30% flags (inclusive)
        _rank("WARM", "1w", SURGE_THRESHOLD - 0.001),  # just under does not
    ]
    board = {b.lookback: b for b in build_boards(rows, prev_rows=[], adrs={})}["1w"]
    by_symbol = {r.symbol: r for r in board.rows}
    assert by_symbol["HOT"].surge is True
    assert by_symbol["WARM"].surge is False


def test_adr_rides_each_row_and_is_never_the_sort():
    # A low-ADR name that gained more still outranks a high-ADR name — the ADR is
    # a column, not the sort key (ticket 06 R9). The value is carried for the
    # toggle; missing ADR is carried as None, not fabricated.
    rows = [_rank("QUIET", "1w", 0.50), _rank("WILD", "1w", 0.40)]
    board = {b.lookback: b for b in build_boards(
        rows, prev_rows=[], adrs={"QUIET": 0.02, "WILD": 0.09}
    )}["1w"]
    assert board.rows[0].symbol == "QUIET"  # bigger raw return wins
    assert board.rows[0].adr == 0.02
    assert board.rows[1].adr == 0.09


def test_missing_adr_is_none():
    rows = [_rank("A", "1w", 0.5)]
    board = {b.lookback: b for b in build_boards(rows, prev_rows=[], adrs={})}["1w"]
    assert board.rows[0].adr is None
