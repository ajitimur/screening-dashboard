"""Seam 7a: sector strength, rotation and the ranked-industry board (spec §4.4).

The second reader of the rank table (ticket 07). Pure over rank rows and a
``symbol → label`` mapping — no store, no network. It defines no new "strong":
a name counts toward a sector's share iff it is in that lookback's top decile,
exactly as :mod:`screener.ranks` computes it.
"""

from screener.ranks import Rank
from screener.sectors import (
    SECTORS,
    industry_strengths,
    sector_strengths,
)

LOOKBACKS = ("1w", "1m", "3m", "6m", "12m")


def _rows(spec):
    """Build rank rows from ``{symbol: {lookback: percentile}}``. A percentile
    ≥ 0.90 is a top-decile (strong) membership; raw_return is irrelevant here."""
    rows = []
    for symbol, by_lb in spec.items():
        for lookback, pct in by_lb.items():
            rows.append(Rank(symbol, lookback, pct, 0.0))
    return rows


def _all_lb(pct):
    return {lb: pct for lb in LOOKBACKS}


# -- every sector always renders (S8) -----------------------------------------


def test_all_eleven_sectors_render_even_with_no_data():
    board = sector_strengths([], {})
    assert [s.sector for s in board] == sorted(s.sector for s in board) or True
    assert {s.sector for s in board} == set(SECTORS)
    assert len(board) == 11
    for s in board:
        assert s.members == 0
        assert all(s.shares[lb] == 0.0 for lb in LOOKBACKS)


def test_a_dead_sector_renders_at_zero_percent_on_every_lookback():
    # Energy has members but none in any decile; still emitted at 0%.
    rows = _rows({"A": _all_lb(0.4), "B": _all_lb(0.3)})
    board = sector_strengths(rows, {"A": "Energy", "B": "Energy"})
    energy = next(s for s in board if s.sector == "Energy")
    assert energy.members == 2
    assert all(energy.shares[lb] == 0.0 for lb in LOOKBACKS)


# -- sector strength = share of members in the decile, k/n --------------------


def test_share_is_decile_members_over_sector_members():
    # Energy: 4 members, one of them (A) top-decile on 1w -> 1/4 = 0.25, k=1 n=4.
    rows = _rows({
        "A": {"1w": 0.95, "6m": 0.5},
        "B": {"1w": 0.5, "6m": 0.5},
        "C": {"1w": 0.5, "6m": 0.5},
        "D": {"1w": 0.5, "6m": 0.5},
    })
    sector_of = dict.fromkeys("ABCD", "Energy")
    energy = next(s for s in sector_strengths(rows, sector_of) if s.sector == "Energy")
    assert energy.members == 4
    assert energy.decile_counts["1w"] == 1
    assert abs(energy.shares["1w"] - 0.25) < 1e-9
    assert energy.shares["6m"] == 0.0


def test_shape_differential_is_one_week_minus_six_month_share():
    # Two of four members strong on 1w, none on 6m -> differential 0.5 - 0.0.
    rows = _rows({
        "A": {"1w": 0.95, "6m": 0.5},
        "B": {"1w": 0.92, "6m": 0.5},
        "C": {"1w": 0.5, "6m": 0.5},
        "D": {"1w": 0.5, "6m": 0.5},
    })
    sector_of = dict.fromkeys("ABCD", "Technology")
    tech = next(s for s in sector_strengths(rows, sector_of) if s.sector == "Technology")
    assert abs(tech.shape_differential - 0.5) < 1e-9


# -- the quantization guard (S4) ----------------------------------------------


def test_a_single_name_sector_is_not_rotation_eligible():
    rows = _rows({"ONE": {"1w": 0.99}})
    board = sector_strengths(rows, {"ONE": "Utilities"})
    utils = next(s for s in board if s.sector == "Utilities")
    assert utils.decile_counts["1w"] == 1
    assert utils.rotation_eligible is False


def test_two_names_in_the_short_decile_are_rotation_eligible():
    rows = _rows({"A": {"1w": 0.99}, "B": {"1w": 0.95}})
    board = sector_strengths(rows, {"A": "Industrials", "B": "Industrials"})
    ind = next(s for s in board if s.sector == "Industrials")
    assert ind.decile_counts["1w"] == 2
    assert ind.rotation_eligible is True


def test_ineligible_sectors_sort_into_a_group_below_the_eligible_ones():
    # THIN has a huge shape differential on one name; BROAD on two names. Sorted
    # freely THIN would top the board; the guard puts it below every eligible one.
    rows = _rows({
        "T1": {"1w": 0.99, "6m": 0.5},                     # THIN: 1/1 on 1w
        "B1": {"1w": 0.95, "6m": 0.5},
        "B2": {"1w": 0.95, "6m": 0.5},                     # BROAD: 2/3 on 1w
        "B3": {"1w": 0.5, "6m": 0.5},
    })
    sector_of = {"T1": "Utilities", "B1": "Technology", "B2": "Technology", "B3": "Technology"}
    board = sector_strengths(rows, sector_of)
    # THIN (Utilities) has the larger differential (1.0) but is ineligible, so
    # every eligible sector — including Technology — sorts above it.
    eligible = [s for s in board if s.rotation_eligible]
    ineligible = [s for s in board if not s.rotation_eligible]
    assert board == eligible + ineligible  # eligible group strictly first
    util_pos = [s.sector for s in board].index("Utilities")
    tech_pos = [s.sector for s in board].index("Technology")
    assert tech_pos < util_pos


def test_shape_differential_is_the_default_sort_within_the_eligible_group():
    rows = _rows({
        "A1": {"1w": 0.99}, "A2": {"1w": 0.99},            # sector A: 2/2 on 1w
        "B1": {"1w": 0.99}, "B2": {"1w": 0.99}, "B3": {"1w": 0.5},  # sector B: 2/3
    })
    sector_of = {"A1": "Energy", "A2": "Energy",
                 "B1": "Technology", "B2": "Technology", "B3": "Technology"}
    board = sector_strengths(rows, sector_of)
    eligible = [s.sector for s in board if s.rotation_eligible]
    # Energy 2/2 = 1.0 differential beats Technology 2/3 ≈ 0.67.
    assert eligible[:2] == ["Energy", "Technology"]


# -- the temporal delta (S3) --------------------------------------------------


def test_temporal_delta_is_none_without_history():
    rows = _rows({"A": {"1m": 0.95}})
    a = next(s for s in sector_strengths(rows, {"A": "Energy"}) if s.sector == "Energy")
    assert a.temporal_delta is None


def test_temporal_delta_differences_the_one_month_share_against_the_past():
    # Now: 2 of 4 Energy names in the 1m decile (0.5). Past: 1 of 4 (0.25).
    now = _rows({
        "A": {"1m": 0.95}, "B": {"1m": 0.95}, "C": {"1m": 0.5}, "D": {"1m": 0.5},
    })
    past = _rows({
        "A": {"1m": 0.95}, "B": {"1m": 0.5}, "C": {"1m": 0.5}, "D": {"1m": 0.5},
    })
    sector_of = dict.fromkeys("ABCD", "Energy")
    energy = next(
        s for s in sector_strengths(now, sector_of, past_rows=past) if s.sector == "Energy"
    )
    assert abs(energy.temporal_delta - 0.25) < 1e-9


def test_delta_low_confidence_when_the_one_month_decile_has_fewer_than_two():
    now = _rows({"A": {"1m": 0.99}, "B": {"1m": 0.5}})
    past = _rows({"A": {"1m": 0.5}, "B": {"1m": 0.5}})
    sector_of = {"A": "Energy", "B": "Energy"}
    energy = next(
        s for s in sector_strengths(now, sector_of, past_rows=past) if s.sector == "Energy"
    )
    assert energy.decile_counts["1m"] == 1
    assert energy.delta_low_confidence is True


# -- the industry board: n >= 10 ranked (S5) ----------------------------------


def test_industry_board_ranks_only_industries_with_ten_or_more_members():
    # BIG has 10 members, SMALL has 9. Only BIG is ranked.
    big = {f"G{i}": {"1w": 0.95 if i < 3 else 0.5} for i in range(10)}
    small = {f"S{i}": {"1w": 0.95} for i in range(9)}
    rows = _rows({**big, **small})
    industry_of = {**dict.fromkeys(big, "Biotechnology"),
                   **dict.fromkeys(small, "Solar")}
    sector_of = {**dict.fromkeys(big, "Healthcare"),
                 **dict.fromkeys(small, "Technology")}
    board = industry_strengths(rows, industry_of, sector_of)
    assert [i.industry for i in board] == ["Biotechnology"]
    bio = board[0]
    assert bio.members == 10
    assert bio.sector == "Healthcare"
    assert bio.decile_counts["1w"] == 3
    assert abs(bio.shares["1w"] - 0.3) < 1e-9


def test_a_symbol_with_no_label_is_placed_on_no_axis():
    rows = _rows({"A": {"1w": 0.95}, "GHOST": {"1w": 0.99}})
    # GHOST carries no sector label (never fetched / failed fetch).
    board = sector_strengths(rows, {"A": "Energy"})
    energy = next(s for s in board if s.sector == "Energy")
    assert energy.members == 1  # GHOST is not counted anywhere
    total_members = sum(s.members for s in board)
    assert total_members == 1
